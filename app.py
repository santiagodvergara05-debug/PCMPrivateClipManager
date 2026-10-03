"""
==============================================================================
PCM PRIVATE CLIP MANAGER - NÚCLEO DEL SERVIDOR Y BOOTLOADER (APP.PY)
==============================================================================
Punto de entrada principal del sistema. Responsabilidades:
1. Detección de entorno de ejecución (Desarrollo vs Binario congelado PyInstaller).
2. Inicialización de la aplicación Flask y definición de límites globales (250 MiB).
3. Telemetría de arranque estilo init/kernel de Linux con formateo ANSI.
4. Motor de autorreparación, sanitización y serialización segura del archivo .env.
5. Saneamiento del sistema de archivos, purga de huérfanos y aislamiento WAL.
6. Auditoría exhaustiva de integridad SQLite (Magic Header, Tablas y Esquema).
7. Protocolo de Disaster Recovery y Rescate Automático desde Bóvedas BYOC.
8. Auditoría cruzada de sincronización condicionada al modo operativo.
9. Resolución dinámica de interfaz local/LAN y puesta en marcha del servidor WSGI.
==============================================================================
"""

# ==============================================================================
# SECCIÓN 1: IMPORTACIONES Y RESOLUCIÓN DE RUTAS DEL SISTEMA
# ==============================================================================
import os
import sys
import time
import secrets
import logging
import socket
import sqlite3
import shutil
import webbrowser
import threading
import hashlib
from datetime import datetime

# Componentes del framework web y variables de entorno
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv, dotenv_values, set_key
from logger_http import configurar_logger_http

# Módulos internos de la arquitectura PCM
import database
import sync_manager
from routes import clips_bp, RUTA_ULTIMO_BACKUP, RUTA_ULTIMO_SYNC
from version import VERSION

# Detección de empaquetado PyInstaller (sys.frozen = True cuando es un binario .exe)
ES_EXE = getattr(sys, "frozen", False)
if ES_EXE:
    DIRECTORIO_RAIZ = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", DIRECTORIO_RAIZ)
else:
    DIRECTORIO_RAIZ = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = DIRECTORIO_RAIZ
os.chdir(DIRECTORIO_RAIZ)

# Rutas persistentes en disco local
ENV_PATH = os.path.join(DIRECTORIO_RAIZ, ".env")
DB_PATH = os.path.join(DIRECTORIO_RAIZ, "pcm.db")
UPLOADS_DIR = os.path.join(DIRECTORIO_RAIZ, "static", "uploads", "documentos")
BACKUPS_DIR = os.path.join(DIRECTORIO_RAIZ, "backups")


# ==============================================================================
# SECCIÓN 2: INICIALIZACIÓN DE FLASK Y REGLAS DE SEGURIDAD GLOBALES
# ==============================================================================
app = Flask(
    __name__,
    template_folder=os.path.join(BUNDLE_DIR, "templates"),
    static_folder=os.path.join(BUNDLE_DIR, "static")
)

# Registro único del Blueprint de rutas
app.register_blueprint(clips_bp)

# Activar el traductor visual de peticiones HTTP
configurar_logger_http(app)

@app.route("/static/uploads/documentos/<path:filename>")
def servir_imagenes_subidas(filename):
    """Sirve los archivos multimedia directamente desde la carpeta física del disco."""
    return send_from_directory(UPLOADS_DIR, filename)

# Límite global amplio para soportar backups completos con multimedia: 250 MiB
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024

# Blindaje de identidad: Política de cookies de sesión
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False


@app.errorhandler(413)
def error_archivo_demasiado_grande(e):
    ip_origen = request.remote_addr
    print(f"\n\033[91m[ALERTA DE SEGURIDAD :: OVERFLOW]\033[0m Carga masiva interceptada (> 250 MB) desde IP: {ip_origen}")
    return jsonify({
        "ok": False,
        "error": "El archivo excede el tamaño máximo permitido por el servidor (250 MB)."
    }), 413


# ==============================================================================
# SECCIÓN 3: MOTOR DE TELEMETRÍA Y UTILIDADES DE INTEGRIDAD
# ==============================================================================
def klog(estado, mensaje, delay=0.07):
    prefijos = {
        "ok":   "  [\033[92m  OK  \033[0m] ",
        "info": "  [\033[94m INFO \033[0m] ",
        "warn": "  [\033[93m WARN \033[0m] ",
        "fail": "  [\033[91m FAIL \033[0m] ",
        "init": "  [\033[95m INIT \033[0m] "
    }
    prefijo = prefijos.get(estado.lower(), "  [ .... ] ")
    if not sys.stdout.isatty():
        prefijo = f"  [{estado.upper():^6}] "
    print(f"{prefijo}{mensaje}")
    if delay > 0:
        time.sleep(delay)


def calcular_sha256_local(ruta):
    """Calcula el hash SHA-256 en bloques de 64 KB de forma segura."""
    if not os.path.exists(ruta):
        return None
    try:
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(65536), b""):
                h.update(bloque)
        return h.hexdigest()
    except Exception:
        return None


# ==============================================================================
# SECCIÓN 4: GESTIÓN, RESILIENCIA Y AUTORREPARACIÓN DE ENTORNO (.ENV)
# ==============================================================================
VALORES_PREDETERMINADOS = {
    "SECRET_KEY": lambda: secrets.token_hex(32),
    "CONTRASENA_MOSTRADA": "false",
    "AUTO_ABRIR_NAVEGADOR": "true",
    "FLASK_DEBUG": "false",
    "LOG_MODE": "false",
    "PORT": "5545",
    "HOST": "127.0.0.1",
    "SISTEMA_INICIALIZADO": "true",
    "MASTER_KEY": lambda: secrets.token_hex(32),
    "APP_PASSWORD": "cambiame",
    # Módulo de Sincronización BYOC (E2EE)
    "SYNC_HABILITADO": "false",
    "SYNC_CARPETA": "",
    "SYNC_MODO_CIFRADO": "auto",  # 'auto' o 'libre'
    "SYNC_CLAVE": lambda: secrets.token_hex(32),
    "SYNC_AUTO_APLICAR": "true",
    "SYNC_NOMBRE_DISPOSITIVO": lambda: socket.gethostname(),
    "SYNC_ULTIMA_REVISION": "0",
}

def serializar_valor_env(valor):
    v_str = str(valor).replace("\r", "").replace("\n", "")
    v_str = v_str.replace("\\", "\\\\").replace("'", r"\'")
    return f"'{v_str}'"


def escribir_env_seguro(ruta_env, mapa_valores):
    for _ in range(4):
        try:
            with open(ruta_env, "w", encoding="utf-8") as f:
                for k, v in mapa_valores.items():
                    f.write(f"{k}={serializar_valor_env(v)}\n")
            return True
        except (PermissionError, OSError):
            time.sleep(0.15)
    return False


def sanitizar_y_reparar_env(ruta_env):
    valores = {}
    archivo_danado = False
    env_existia = os.path.exists(ruta_env)
    
    ya_inicializado = os.path.exists(DB_PATH)

    if env_existia:
        try:
            with open(ruta_env, "r", encoding="utf-8") as f:
                contenido_raw = f.read()
                if "\x00" in contenido_raw:
                    archivo_danado = True
                else:
                    valores = dict(dotenv_values(ruta_env))
        except Exception:
            archivo_danado = True

    if archivo_danado:
        klog("fail", "Archivo .env ilegible o corrupto (sabotaje de datos binarios).")
        quarantine = f".env.corrupt_{int(time.time())}"
        try:
            os.rename(ruta_env, os.path.join(DIRECTORIO_RAIZ, quarantine))
            klog("warn", f"Configuración dañada aislada como: {quarantine}")
        except Exception:
            try:
                os.remove(ruta_env)
            except Exception:
                pass
        valores = {}
    else:
        flag_env = str(valores.get("SISTEMA_INICIALIZADO", "")).strip("'\"").lower() == "true"
        ya_inicializado = flag_env or ya_inicializado

    hubo_cambios = archivo_danado or (not env_existia)
    faltantes = []
    advertencias = []

    val_init = valores.get("SISTEMA_INICIALIZADO")
    if val_init is not None and str(val_init).strip("'\"").lower() == "false" and os.path.exists(DB_PATH):
        advertencias.append("Inconsistencia: Base de datos activa pero SISTEMA_INICIALIZADO='false'. Corrigiendo a 'true'...")
        valores["SISTEMA_INICIALIZADO"] = "true"
        hubo_cambios = True

    for clave, valor_default in VALORES_PREDETERMINADOS.items():
        val = valores.get(clave)

        if clave == "SYNC_CARPETA":
            if val is None:
                valores[clave] = ""
                faltantes.append(clave)
                hubo_cambios = True
            continue

        if val is None or not str(val).strip():
            nuevo_val = valor_default() if callable(valor_default) else valor_default
            valores[clave] = nuevo_val
            faltantes.append(clave)
            hubo_cambios = True

    puerto_raw = valores.get("PORT", "5545")
    try:
        puerto_num = int(str(puerto_raw).strip("'\""))
        if not (1 <= puerto_num <= 65535):
            raise ValueError
        valores["PORT"] = str(puerto_num)
    except Exception:
        advertencias.append(f"Puerto inválido detectado ({puerto_raw}). Restableciendo a 5545...")
        valores["PORT"] = "5545"
        hubo_cambios = True

    host_raw = str(valores.get("HOST", "127.0.0.1")).strip("'\"")
    if host_raw not in ["127.0.0.1", "0.0.0.0"]:
        advertencias.append(f"Host no estándar detectado ({host_raw}). Normalizando a 127.0.0.1...")
        valores["HOST"] = "127.0.0.1"
        hubo_cambios = True

    if hubo_cambios:
        exito = escribir_env_seguro(ruta_env, valores)
        if not exito:
            klog("warn", "No se pudo actualizar .env en disco por bloqueo del SO. Usando valores en memoria.")

    for k, v in valores.items():
        os.environ[k] = str(v)

    return faltantes, ya_inicializado, env_existia, archivo_danado, advertencias


# ==============================================================================
# SECCIÓN 5: AUDITORÍA AVANZADA DE INTEGRIDAD SQLITE (BLINDADA CONTRA CAOS)
# ==============================================================================
def auditar_integridad_db(db_path):
    if not os.path.exists(db_path):
        return "ausente", 0, 0, 0, 0

    if os.path.getsize(db_path) == 0:
        return "ausente", 0, 0, 0, 0

    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=3.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        if not res or res[0] != "ok":
            return "corrupta", 0, 0, 0, 0

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('clips', 'documentos');")
        tablas = [r["name"] for r in cur.fetchall()]
        if "clips" not in tablas or "documentos" not in tablas:
            return "incompleta", 0, 0, 0, 0

        try:
            database.migrar_columna_tipo(conn)
        except Exception:
            pass

        def contar_seguro(query):
            try:
                cur.execute(query)
                r = cur.fetchone()
                return r[0] if r else 0
            except Exception:
                return 0

        total_clips = contar_seguro("SELECT COUNT(*) FROM clips WHERE tipo = 'clip';")
        total_codigo = contar_seguro("SELECT COUNT(*) FROM clips WHERE tipo = 'codigo';")
        total_resumenes = contar_seguro("SELECT COUNT(*) FROM clips WHERE tipo = 'nota';")
        total_docs = contar_seguro("SELECT COUNT(*) FROM documentos;")

        return "ok", total_clips, total_codigo, total_resumenes, total_docs

    except sqlite3.OperationalError as e:
        err_msg = str(e).lower()
        if "locked" in err_msg or "busy" in err_msg:
            return "bloqueada", 0, 0, 0, 0
        return "corrupta", 0, 0, 0, 0

    except (sqlite3.DatabaseError, sqlite3.Error):
        return "corrupta", 0, 0, 0, 0

    except Exception:
        return "corrupta", 0, 0, 0, 0

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ==============================================================================
# SECCIÓN 6: SANEAMIENTO DEL SISTEMA DE ARCHIVOS Y PURGA DE TEMPORALES
# ==============================================================================
def sanear_directorios_y_archivos(ya_inicializado=False):
    directorios = [
        ("templates", os.path.join(DIRECTORIO_RAIZ, "templates")),
        ("static", os.path.join(DIRECTORIO_RAIZ, "static")),
        ("uploads/documentos", UPLOADS_DIR),
        ("backups", BACKUPS_DIR)
    ]

    for nombre, ruta in directorios:
        if not os.path.exists(ruta):
            os.makedirs(ruta, exist_ok=True)
            if ya_inicializado and nombre == "uploads/documentos":
                klog("warn", "Directorio multimedia ausente o eliminado externamente: /uploads/documentos")
                klog("init", "Regenerando carpeta vacía para permitir nuevas subidas...")
            else:
                klog("init", f"Directorio aprovisionado: /{nombre}")
        else:
            klog("ok", f"Directorio confirmado: /{nombre}")

    if os.path.exists(UPLOADS_DIR):
        purgados = 0
        for f in os.listdir(UPLOADS_DIR):
            rf = os.path.join(UPLOADS_DIR, f)
            if os.path.isfile(rf) and os.path.getsize(rf) == 0:
                try:
                    os.remove(rf)
                    purgados += 1
                except Exception:
                    pass
        if purgados > 0:
            klog("warn", f"Saneamiento: {purgados} archivo(s) huérfano(s) de 0 bytes eliminados de uploads.")

    purgados_sync = 0
    for elemento in os.listdir(DIRECTORIO_RAIZ):
        if elemento.endswith((".pre_sync", ".zip.tmp", ".db.tmp")):
            try:
                os.remove(os.path.join(DIRECTORIO_RAIZ, elemento))
                purgados_sync += 1
            except Exception:
                pass
    if purgados_sync > 0:
        klog("warn", f"Saneamiento: {purgados_sync} archivo(s) temporales residuales de sincronización eliminados.")


# ==============================================================================
# SECCIÓN 7: RUTINA DE ARRANQUE (BOOTLOADER), RED LAN Y SERVIDOR WSGI
# ==============================================================================
if __name__ == "__main__":
    es_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

    antigua_db = os.path.join(DIRECTORIO_RAIZ, "cliptemp.db")
    if os.path.exists(antigua_db) and not os.path.exists(DB_PATH):
        try:
            os.rename(antigua_db, DB_PATH)
        except Exception:
            pass

    if not es_reloader:
        print("\n" + "=" * 65)
        print(f"   BOOTLOADER :: PCMPrivateClipManager v{VERSION} (OFFLINE & SECURE)   ")
        print("=" * 65)
        time.sleep(0.10)

        # 1. Auditoría y aprovisionamiento del entorno .env
        faltantes, ya_inicializado, env_existia, archivo_danado, advertencias = sanitizar_y_reparar_env(ENV_PATH)

        if not env_existia:
            klog("warn", "Configuración .env no encontrada. Iniciando aprovisionamiento inicial...")
            for clave in faltantes:
                klog("init", f"Generando clave predeterminada: {clave}")
            klog("ok", f"Archivo .env de fábrica creado con {len(faltantes)} variables.")

        elif archivo_danado:
            for clave in faltantes:
                klog("init", f"Regenerando clave tras aislamiento: {clave}")
            klog("ok", f"Archivo .env recuperado con {len(faltantes)} variables.")

        else:
            klog("ok", "Archivo .env cargado desde almacenamiento local.")
            for adv in advertencias:
                klog("warn", adv)

            for clave in faltantes:
                klog("init", f"Restaurando parámetro faltante: {clave}")

            if faltantes or advertencias:
                klog("ok", "Archivo .env reparado con éxito.")
            else:
                klog("ok", "Archivo .env verificado: integridad completa.")

        try:
            load_dotenv(ENV_PATH, override=True)
        except Exception:
            pass

        app.secret_key = os.environ.get("SECRET_KEY")

        # --- Verificación de Entropía y Longitud de Claves Maestras ---
        master_val = os.environ.get("MASTER_KEY", "").strip("'\"")
        sync_clave_val = os.environ.get("SYNC_CLAVE", "").strip("'\"")

        es_hex_64 = lambda s: len(s) == 64 and all(c in "0123456789abcdefABCDEF" for c in s)

        master_es_256 = es_hex_64(master_val)
        sync_es_256 = es_hex_64(sync_clave_val)

        if master_es_256:
            klog("ok", "Llaves criptográficas maestras activas (256 bits).")
        else:
            bits_master = len(master_val.encode("utf-8")) * 8
            klog("info", f"Llave maestra manual activa ({bits_master} bits / clave personalizada detectada).")
            klog("info", f"clave maestra analizada ({len(master_val)} caracteres detectada).")

        sync_activa_check = os.environ.get("SYNC_HABILITADO", "false").strip().lower() == "true"
        if sync_activa_check and not sync_es_256 and os.environ.get("SYNC_MODO_CIFRADO", "auto") != "libre":
            bits_sync = len(sync_clave_val.encode("utf-8")) * 8
            klog("info", f"SYNC_CLAVE manual detectada de ({bits_sync} bits).")
            klog("info", f"SYNC_CLAVE analizada ({len(sync_clave_val)} caracteres detectados).")

        # 2. Comprobación y saneamiento de almacenamiento físico
        klog("init", "Verificando estructura de almacenamiento...")
        sanear_directorios_y_archivos(ya_inicializado=ya_inicializado)

        # 3. Auditoría estructural local inicial de SQLite
        estado_db, n_clips, n_codigos, n_resumenes, n_docs = auditar_integridad_db(DB_PATH)

        if estado_db == "bloqueada":
            klog("fail", "La base de datos se encuentra bloqueada por otro proceso.")
            klog("warn", "Esperando 2 segundos para liberación de candado...")
            time.sleep(2)
            estado_db, n_clips, n_codigos, n_resumenes, n_docs = auditar_integridad_db(DB_PATH)
            if estado_db == "bloqueada":
                klog("fail", "Imposible acceder a pcm.db. Cierre el proceso que mantiene el bloqueo exclusivo.")
                sys.exit(1)

        if estado_db == "corrupta":
            klog("fail", "Base de datos dañada o ilegible (sabotaje / corrupción estructural).")
            cuarentena_db = f"pcm.db.corrupt_{int(time.time())}"
            try:
                os.rename(DB_PATH, os.path.join(DIRECTORIO_RAIZ, cuarentena_db))
                klog("warn", f"Base de datos corrupta aislada en cuarentena: {cuarentena_db}")
            except Exception:
                try:
                    os.remove(DB_PATH)
                except Exception:
                    pass

            for ext_wal in ["-wal", "-shm", "-journal"]:
                f_wal = DB_PATH + ext_wal
                if os.path.exists(f_wal):
                    try:
                        os.remove(f_wal)
                    except Exception:
                        pass
            estado_db = "ausente"

        # 4. Protocolo de Sincronización BYOC y Disaster Recovery
        sync_activa = os.environ.get("SYNC_HABILITADO", "false").strip().lower() == "true"
        carpeta_nube = os.environ.get("SYNC_CARPETA", "").strip()
        auto_aplicar = os.environ.get("SYNC_AUTO_APLICAR", "false").strip().lower() == "true"
        recuperada_de_nube = False
        boveda_bloqueada_corrupta = False
        rev_local = 0
        rev_remota = 0

        try:
            rev_local = int(os.environ.get("SYNC_ULTIMA_REVISION", "0").strip())
        except ValueError:
            rev_local = 0

        if sync_activa and carpeta_nube:
            klog("init", f"Verificando enlace BYOC: {carpeta_nube}")
            if not os.path.isdir(carpeta_nube):
                klog("warn", "Carpeta de sincronización inalcanzable. Operando en modo local.")
            else:
                ruta_meta_fisica = os.path.join(carpeta_nube, "pcm_vault.meta")
                ruta_zip_fisica = os.path.join(carpeta_nube, "pcm_vault.zip")
                
                meta = sync_manager.leer_metadatos_remotos(carpeta_nube)
                
                if os.path.exists(ruta_meta_fisica) and not meta:
                    boveda_bloqueada_corrupta = True
                    klog("fail", "Archivo 'pcm_vault.meta' corrupto o ilegible en la nube.")
                    klog("warn", "Ignorando bóveda remota dañada por seguridad (modo local forzado).")

                elif meta:
                    rev_remota = int(meta.get("revision", 0))
                    origen = meta.get("ultimo_equipo", "Nodo Externo")
                    modo_cif = os.environ.get("SYNC_MODO_CIFRADO", "auto").strip().lower()
                    clave = "" if modo_cif == "libre" else os.environ.get("SYNC_CLAVE", "").strip()

                    zip_presente = os.path.exists(ruta_zip_fisica) and os.path.getsize(ruta_zip_fisica) > 0

                    if not zip_presente:
                        boveda_bloqueada_corrupta = True
                        klog("fail", f"Inconsistencia en la nube: Existe .meta (#{rev_remota}) pero falta 'pcm_vault.zip'.")

                    # CASO RESCATE: Base local ausente pero hay copia en la nube
                    elif estado_db == "ausente":
                        klog("warn", f"Base local no disponible. Ejecutando Rescate Automático (#{rev_remota} desde '{origen}')...")
                        exito, msg = sync_manager.importar_boveda_cifrada(carpeta_nube, DB_PATH, UPLOADS_DIR, clave)
                        if exito:
                            klog("ok", f"Rescate completado con éxito: {msg}")
                            rev_local = rev_remota
                            recuperada_de_nube = True
                            try:
                                with open(os.path.join(DIRECTORIO_RAIZ, RUTA_ULTIMO_SYNC), "w", encoding="utf-8") as f:
                                    f.write(str(time.time()))
                                set_key(ENV_PATH, "SYNC_ULTIMA_REVISION", str(rev_remota))
                                os.environ["SYNC_ULTIMA_REVISION"] = str(rev_remota)
                            except Exception:
                                pass
                            estado_db, n_clips, n_codigos, n_resumenes, n_docs = auditar_integridad_db(DB_PATH)
                        else:
                            boveda_bloqueada_corrupta = True
                            klog("fail", f"Fallo al rescatar desde la nube (Firma SHA-256 o clave errónea): {msg}")

                    # CASO ACTUALIZACIÓN HABITUAL
                    elif rev_remota > rev_local:
                        klog("info", f"Revisión remota #{rev_remota} disponible desde '{origen}' (Local: #{rev_local}).")
                        if auto_aplicar:
                            klog("init", "Auto-aplicando actualización de bóveda desde la nube...")
                            exito, msg = sync_manager.importar_boveda_cifrada(carpeta_nube, DB_PATH, UPLOADS_DIR, clave)
                            if exito:
                                klog("ok", f"Bóveda aplicada con éxito: {msg}")
                                rev_local = rev_remota
                                try:
                                    with open(os.path.join(DIRECTORIO_RAIZ, RUTA_ULTIMO_SYNC), "w", encoding="utf-8") as f:
                                        f.write(str(time.time()))
                                    set_key(ENV_PATH, "SYNC_ULTIMA_REVISION", str(rev_remota))
                                    os.environ["SYNC_ULTIMA_REVISION"] = str(rev_remota)
                                except Exception:
                                    pass
                            else:
                                boveda_bloqueada_corrupta = True
                                klog("fail", f"Sincronización rechazada (Integridad SHA-256 comprometida): {msg}")
                        else:
                            klog("warn", f"Actualización pendiente (#{rev_remota} > #{rev_local}). Subida bloqueada por seguridad anti-atraso.")

                    elif rev_remota == rev_local:
                        if not os.path.exists(ruta_zip_fisica) or os.path.getsize(ruta_zip_fisica) == 0:
                            boveda_bloqueada_corrupta = True
                            klog("fail", f"Alerta en la nube: Existe .meta (#{rev_local}) pero 'pcm_vault.zip' está ausente o vacío.")
                        else:
                            hash_esperado = meta.get("hash_sha256") or meta.get("sha256") or meta.get("hash")
                            if hash_esperado:
                                hash_real = calcular_sha256_local(ruta_zip_fisica)
                                if hash_real != hash_esperado:
                                    boveda_bloqueada_corrupta = True
                                    klog("fail", f"Bóveda remota dañada: 'pcm_vault.zip' no coincide con su firma SHA-256.")
                                    klog("warn", "La copia remota está corrupta. Se sugiere re-subir la bóveda local.")
                                else:
                                    klog("ok", f"Bóveda sincronizada al día con la nube (Revisión #{rev_local} verificada).")
                            else:
                                klog("ok", f"Bóveda sincronizada al día con la nube (Revisión #{rev_local}).")

        # 5. Inicialización y Autocuración de Esquema
        if estado_db == "ausente" and not recuperada_de_nube:
            klog("info", "Generando base de datos pcm.db limpia e indexada...")
            database.inicializar_db()
            klog("ok", "Base de datos SQLite creada.")
            try:
                with open(os.path.join(DIRECTORIO_RAIZ, RUTA_ULTIMO_SYNC), "w", encoding="utf-8") as f:
                    f.write(str(time.time() + 2.0))
            except Exception:
                pass
            estado_db, n_clips, n_codigos, n_resumenes, n_docs = auditar_integridad_db(DB_PATH)

        elif estado_db in ["incompleta", "ok"]:
            database.inicializar_db()
            klog("ok", f"Base verificada: {n_clips} clips, {n_codigos} cod, {n_resumenes} notas, {n_docs} docs.")

        # 6. Auditoría cruzada de sincronización y modificaciones
        if sync_activa and carpeta_nube:
            ruta_sync = os.path.join(DIRECTORIO_RAIZ, RUTA_ULTIMO_SYNC)
            ultimo_sync_ts = 0.0
            hay_nube_pendiente = bool(rev_remota > rev_local)

            if os.path.exists(ruta_sync):
                try:
                    with open(ruta_sync, "r", encoding="utf-8") as f:
                        ultimo_sync_ts = float(f.read().strip())
                        fecha_sync_str = datetime.fromtimestamp(ultimo_sync_ts).strftime("%Y-%m-%d %H:%M:%S")

                        if os.path.exists(DB_PATH):
                            db_mtime = os.path.getmtime(DB_PATH)
                            total_registros = n_clips + n_codigos + n_resumenes + n_docs

                            if total_registros > 0 and db_mtime > (ultimo_sync_ts + 1.5):
                                klog("warn", f"Cambios locales en pcm.db posteriores al último sync ({fecha_sync_str}).")
                            elif boveda_bloqueada_corrupta:
                                klog("fail", f"Sincronización suspendida: Bóveda remota #{rev_remota} bloqueada por integridad.")
                            elif hay_nube_pendiente:
                                klog("warn", f"Último sync local: {fecha_sync_str} (Pendiente descargar #{rev_remota} de la nube).")
                            else:
                                klog("ok", f"Última sincronización confirmada: {fecha_sync_str} (Datos locales al día).")
                        else:
                            klog("ok", f"Última sincronización registrada: {fecha_sync_str}")
                except Exception:
                    klog("warn", "Archivo de seguimiento de sincronización corrupto (ignorado).")
            else:
                klog("info", "Sin registro de sincronización previa en este nodo (archivo testigo ausente).")
        else:
            klog("info", "Sincronización BYOC desactivada (Operando en modo local independiente).")

        # 7. Verificación de última instantánea de respaldo manual (JSON/ZIP)
        ruta_backup = os.path.join(DIRECTORIO_RAIZ, RUTA_ULTIMO_BACKUP)
        if os.path.exists(ruta_backup):
            try:
                with open(ruta_backup, "r", encoding="utf-8") as f:
                    ts_bk = float(f.read().strip())
                    fecha_bk_str = datetime.fromtimestamp(ts_bk).strftime("%Y-%m-%d %H:%M")
                    klog("ok", f"Último respaldo manual verificado: {fecha_bk_str}")
            except Exception:
                klog("warn", "Archivo de seguimiento de respaldo manual corrupto (ignorado).")
        else:
            klog("info", "No se detecta snapshot de respaldo manual previo.")

        # 8. Detección y advertencia de credenciales por defecto
        contrasena_ya_mostrada = os.environ.get("CONTRASENA_MOSTRADA", "false").strip().lower() == "true"
        if os.environ.get("APP_PASSWORD") == "cambiame" and not contrasena_ya_mostrada:
            print("\n" + "!" * 65)
            print(" [!] PRIMER INICIO DETECTADO: Credencial temporal activa ('cambiame')")
            print(" [i] Visualice la Master Key e inicie sesión en la pantalla web.")
            print("!" * 65)

        print("\n" + "-" * 65)
        comando_cli = "CLI_admin.exe" if ES_EXE else "python CLI_admin.py"
        print(f" [i] CONSOLA DE ADMINISTRACIÓN DISPONIBLE: {comando_cli}")
        print("-" * 65)

    # Configuración de red y modo WSGI
    load_dotenv(ENV_PATH, override=True)
    app.secret_key = os.environ.get("SECRET_KEY")

    debug_mode = False if ES_EXE else (os.environ.get("FLASK_DEBUG", "false").strip().lower() == "true")
    host = os.environ.get("HOST", "127.0.0.1").strip()
    try:
        port = int(os.environ.get("PORT", "5545").strip())
    except ValueError:
        port = 5545

    if not es_reloader:
        klog("info", f"Modo Debug: {debug_mode}")
        if host == "0.0.0.0":
            ip_lan = "127.0.0.1"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("10.255.255.255", 1))
                ip_lan = s.getsockname()[0]
                s.close()
            except Exception:
                try:
                    ip_lan = socket.gethostbyname(socket.gethostname())
                except Exception:
                    pass

            klog("ok", f"Servidor Local:   http://127.0.0.1:{port}")
            klog("ok", f"Acceso LAN Red:   http://{ip_lan}:{port}")
            klog("info", "Acceso multidispositivo habilitado en la red local.")
        else:
            klog("ok", f"Servidor Local enrutado en http://{host}:{port}")
            klog("fail", "Acceso LAN Red: no disponible")
            klog("info", "Acceso LAN Red: Desactivado (modo exclusivo PC local)")

        print("-" * 65)
        print(">>> PCMPrivateClipManager OPERATIVO Y LISTO <<<")
        print("-" * 65 + "\n")

    auto_abrir = os.environ.get("AUTO_ABRIR_NAVEGADOR", "true").strip().lower() == "true"
    if auto_abrir and (ES_EXE or not es_reloader):
        url_destino = f"http://127.0.0.1:{port}"
        threading.Timer(1.2, lambda: webbrowser.open(url_destino)).start()

    app.run(
        host=host,
        port=port,
        debug=debug_mode,
        use_reloader=False if ES_EXE else True,
        extra_files=[ENV_PATH] if not ES_EXE else []
    )