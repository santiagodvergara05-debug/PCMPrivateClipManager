import os
import sys
import time
import secrets
import logging
import socket
import sqlite3
import shutil
from datetime import datetime
from dotenv import load_dotenv, dotenv_values, set_key
from flask import Flask
import database
from routes import clips_bp, RUTA_ULTIMO_BACKUP
import webbrowser
import threading
from version import VERSION

ES_EXE = getattr(sys, "frozen", False)
if ES_EXE:
    DIRECTORIO_RAIZ = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", DIRECTORIO_RAIZ)
else:
    DIRECTORIO_RAIZ = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = DIRECTORIO_RAIZ

app = Flask(
    __name__,
    template_folder=os.path.join(BUNDLE_DIR, "templates"),
    static_folder=os.path.join(BUNDLE_DIR, "static")
)
app.register_blueprint(clips_bp)

# Rutas de almacenamiento persistente
ENV_PATH = os.path.join(DIRECTORIO_RAIZ, ".env")
DB_PATH = os.path.join(DIRECTORIO_RAIZ, "pcm.db")
UPLOADS_DIR = os.path.join(DIRECTORIO_RAIZ, "static", "uploads", "documentos")
BACKUPS_DIR = os.path.join(DIRECTORIO_RAIZ, "backups")


# ==========================================
# MOTOR DE TELEMETRÍA Y LOGS ESTILO INIT
# ==========================================

def klog(estado, mensaje, delay=0.12):
    """Imprime mensajes formateados al estilo init/kernel de Linux."""
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


# ==========================================
# GESTIÓN Y AUTORREPARACIÓN DE ENTORNO (.ENV)
# ==========================================

VALORES_PREDETERMINADOS = {
    "SISTEMA_INICIALIZADO": "true",
    "SECRET_KEY": lambda: secrets.token_hex(32),
    "MASTER_KEY": lambda: secrets.token_hex(32),
    "APP_PASSWORD": "cambiame",
    "CONTRASENA_MOSTRADA": "false",
    "AUTO_ABRIR_NAVEGADOR": "false",
    "FLASK_DEBUG": "false",
    "LOG_MODE": "true",
    "PORT": "5545",
    "HOST": "0.0.0.0",
}

def escribir_env_seguro(ruta_env, mapa_valores):
    """Escribe todas las variables en una sola pasada con reintentos para evitar WinError 5 en Windows."""
    for _ in range(4):
        try:
            with open(ruta_env, "w", encoding="utf-8") as f:
                for k, v in mapa_valores.items():
                    f.write(f"{k}='{v}'\n")
            return True
        except (PermissionError, OSError):
            time.sleep(0.15)
    return False

def sanitizar_y_reparar_env(ruta_env):
    """
    Protección contra sabotaje: detecta archivos .env ilegibles, claves vacías,
    sabotajes binarios o puertos/hosts fuera de rango. Aísla archivos dañados y
    devuelve (faltantes, ya_inicializado, env_existia, archivo_danado, advertencias).
    """
    valores = {}
    archivo_danado = False
    env_existia = os.path.exists(ruta_env)

    if env_existia:
        try:
            with open(ruta_env, "r", encoding="utf-8") as f:
                f.read()
            valores = dict(dotenv_values(ruta_env))
        except Exception:
            archivo_danado = True

    if archivo_danado:
        ya_inicializado = True
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
        # El sistema ya estuvo en marcha si la bandera es true o si pcm.db ya existe en disco
        flag_env = str(valores.get("SISTEMA_INICIALIZADO", "")).strip("'\"").lower() == "true"
        ya_inicializado = flag_env or os.path.exists(DB_PATH)

    hubo_cambios = archivo_danado or (not env_existia)
    faltantes = []
    advertencias = []

    # Detección de incoherencia: DB presente pero SISTEMA_INICIALIZADO explícitamente en 'false'
    val_init = valores.get("SISTEMA_INICIALIZADO")
    if val_init is not None and str(val_init).strip("'\"").lower() == "false" and os.path.exists(DB_PATH):
        advertencias.append("Inconsistencia: Base de datos activa pero SISTEMA_INICIALIZADO='false'. Corrigiendo a 'true'...")
        valores["SISTEMA_INICIALIZADO"] = "true"
        hubo_cambios = True

    # 1. Comprobar claves predeterminadas faltantes o vacías
    for clave, valor_default in VALORES_PREDETERMINADOS.items():
        val = valores.get(clave)
        if val is None or not str(val).strip():
            nuevo_val = valor_default() if callable(valor_default) else valor_default
            valores[clave] = nuevo_val
            faltantes.append(clave)
            hubo_cambios = True

    # 2. Sanitizar Puerto (PORT): rango 1 a 65535
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

    # 3. Sanitizar Interfaz de Red (HOST)
    host_raw = str(valores.get("HOST", "0.0.0.0")).strip("'\"")
    if host_raw not in ["127.0.0.1", "0.0.0.0"]:
        advertencias.append(f"Host no estándar detectado ({host_raw}). Normalizando a 0.0.0.0...")
        valores["HOST"] = "0.0.0.0"
        hubo_cambios = True

    # 4. Escritura segura en disco
    if hubo_cambios:
        exito = escribir_env_seguro(ruta_env, valores)
        if not exito:
            klog("warn", "No se pudo actualizar .env en disco por bloqueo del SO. Usando valores en memoria.")

    for k, v in valores.items():
        os.environ[k] = str(v)

    return faltantes, ya_inicializado, env_existia, archivo_danado, advertencias


# ==========================================
# AUDITORÍA AVANZADA DE BASE DE DATOS SQLITE
# ==========================================

def auditar_integridad_db(db_path):
    """
    Verifica integridad física, esquemas maestros y previene bloqueos de concurrencia.
    """
    if not os.path.exists(db_path):
        return "ausente", 0, 0, 0, 0

    conn = None
    try:
        # Timeout bajo para detectar bloqueos exclusivos de CLI_chaos
        conn = sqlite3.connect(db_path, timeout=2.0)
        cur = conn.cursor()

        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        if not res or res[0] != "ok":
            return "corrupta", 0, 0, 0, 0

        # Verificación estricta de esquemas maestros
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('clips', 'documentos');")
        tablas = [r[0] for r in cur.fetchall()]
        if len(tablas) < 2:
            return "incompleta", 0, 0, 0, 0

        cur.execute("SELECT COUNT(*) FROM clips WHERE categoria NOT IN ('Novelas', 'Borrador', 'Resumen') AND categoria NOT LIKE 'Codigo:%';")
        total_clips = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM clips WHERE categoria LIKE 'Codigo:%';")
        total_codigo = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM clips WHERE categoria IN ('Novelas', 'Borrador', 'Resumen');")
        total_resumenes = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM documentos;")
        total_docs = cur.fetchone()[0]

        return "ok", total_clips, total_codigo, total_resumenes, total_docs

    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return "bloqueada", 0, 0, 0, 0
        return "corrupta", 0, 0, 0, 0
    except Exception:
        return "corrupta", 0, 0, 0, 0
    finally:
        if conn:
            conn.close()


# ==========================================
# SANEAMIENTO DE SISTEMA DE ARCHIVOS
# ==========================================

def sanear_directorios_y_archivos(ya_inicializado=False):
    """Garantiza la presencia de todas las carpetas, alerta borrados accidentales y depura archivos basura."""
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
                klog("warn", "Las imágenes de documentos existentes fallarán hasta restaurar un backup .ZIP.")
            else:
                klog("init", f"Directorio aprovisionado: /{nombre}")
        else:
            klog("ok", f"Directorio confirmado: /{nombre}")

    # Purgar archivos de 0 bytes en uploads generados por sabotaje
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
            klog("warn", f"Saneamiento: {purgados} archivo(s) huérfanos de 0 bytes eliminados de uploads.")


# ==========================================
# RUTINA PRINCIPAL DE ARRANQUE (BOOTLOADER)
# ==========================================

if __name__ == "__main__":
    es_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

    # Migración retrocompatible transparente
    antigua_db = os.path.join(DIRECTORIO_RAIZ, "cliptemp.db")
    if os.path.exists(antigua_db) and not os.path.exists(DB_PATH):
        try:
            os.rename(antigua_db, DB_PATH)
        except Exception:
            pass

    if not es_reloader:
        print("\n" + "=" * 65)
        print(f"   BOOTLOADER :: PCMPrivateClipManager v{VERSION} (LAN & RESILIENT)   ")
        print("=" * 65)
        time.sleep(0.2)

# 1. Auditoría y aprovisionamiento detallado del entorno (.env)
        faltantes, ya_inicializado, env_existia, archivo_danado, advertencias = sanitizar_y_reparar_env(ENV_PATH)

        if not env_existia:
            klog("warn", "Configuración .env no encontrada. Iniciando aprovisionamiento...")
            for clave in faltantes:
                klog("init", f"Variable faltante detectada: generando {clave} con su valor predeterminado...")
            klog("ok", f"Archivo .env creado con {len(faltantes)} variable(s) iniciales.")

        elif archivo_danado:
            for clave in faltantes:
                klog("init", f"Variable regenerada tras cuarentena: {clave}...")
            klog("ok", f"Archivo .env reconstruido con {len(faltantes)} variable(s) iniciales.")

        else:
            klog("ok", "Archivo .env cargado desde almacenamiento local.")
            for adv in advertencias:
                klog("warn", adv)
                if "SISTEMA_INICIALIZADO" in adv:
                    klog("info", "SISTEMA_INICIALIZADO= puede indicar sabotaje o borrado accidental, no se recomienda modificar manualmente.")

            for clave in faltantes:
                klog("init", f"Variable faltante detectada: generando {clave} con su valor predeterminado...")

            if faltantes or advertencias:
                total_mod = len(faltantes) + len(advertencias)
                klog("ok", f"Archivo .env reparado ({total_mod} parámetro(s) restaurado(s)).")
            else:
                klog("ok", "Archivo .env verificado: todas las variables presentes.")

        # Carga de variables en el contexto de Flask
        try:
            load_dotenv(ENV_PATH, override=True)
        except Exception:
            pass

        app.secret_key = os.environ.get("SECRET_KEY")

        if os.environ.get("MASTER_KEY") and os.environ.get("SECRET_KEY"):
            klog("ok", "Llaves maestras criptográficas listas (256 bits).")

        # 2. Directorios físicos y multimedia con contexto previo
        klog("init", "Verificando estructura de directorios y almacenamiento...")
        sanear_directorios_y_archivos(ya_inicializado=ya_inicializado)

        # 3. Auditoría de Base de Datos con diferenciación de primer inicio vs borrado accidental
        estado_db, n_clips, n_codigos, n_resumenes, n_docs = auditar_integridad_db(DB_PATH)

        if estado_db == "bloqueada":
            klog("fail", "La base de datos se encuentra bloqueada por otro proceso.")
            klog("warn", "Esperando 2 segundos para liberación del candado...")
            time.sleep(2)
            estado_db, n_clips, n_codigos, n_resumenes, n_docs = auditar_integridad_db(DB_PATH)
            if estado_db == "bloqueada":
                klog("fail", "Imposible acceder a pcm.db. Cierre el proceso que mantiene el bloqueo.")
                sys.exit(1)

        if estado_db == "ausente":
            if not ya_inicializado:
                # Caso A: Primer arranque real del sistema
                klog("info", "Almacenamiento persistente SQLite ausente.")
                klog("init", "Creando base de datos SQLite y esquemas relacionales...")
                klog("info", "pcm.db será generado en el directorio raíz de la aplicación.")
                database.inicializar_db()
                klog("ok", "Base de datos creada e indexada correctamente.")
            else:
                # Caso B: El sistema ya estaba en marcha pero la base fue eliminada (Opción 5 Chaos)
                klog("fail", "Almacenamiento SQLite ausente o eliminado por accidente.")
                klog("warn", "Se detectó configuración previa (.env) pero pcm.db no existe.")
                klog("warn", "Creando una base de datos SQLite limpia para permitir el arranque...")
                klog("init", "Creando base de datos SQLite y esquemas relacionales...")
                klog("info", "pcm.db será generado en el directorio raíz de la aplicación.")
                database.inicializar_db()
                klog("ok", "Base de datos SQLite limpia configurada.")
                klog("warn", "Base antigua no recuperable. Restaure desde /configuracion si posee backup.")

        elif estado_db == "corrupta":
            klog("fail", "Base de datos SQLite dañada o ilegible (Fallo de integridad).")
            cuarentena_db = f"pcm.db.corrupt_{int(time.time())}"
            liberado = False
            try:
                os.rename(DB_PATH, os.path.join(DIRECTORIO_RAIZ, cuarentena_db))
                klog("warn", f"Archivo dañado aislado en cuarentena: {cuarentena_db}")
                liberado = True
            except Exception as err_mv:
                klog("warn", f"Fallo al mover archivo ({err_mv}). Forzando eliminación...")
                try:
                    os.remove(DB_PATH)
                    liberado = True
                except Exception as err_rm:
                    klog("fail", f"Fallo irrecuperable de disco: {err_rm}")

            if liberado:
                klog("init", "Regenerando esquema SQLite limpio para restablecer servicio...")
                database.inicializar_db()
                klog("ok", "Servicio SQLite recuperado en estado limpio.")
                klog("warn", "Base dañada aislada. Restaure su backup desde Configuración.")
            else:
                sys.exit(1)

        elif estado_db == "incompleta":
            klog("warn", "Desviación de esquema detectada (tablas faltantes).")
            klog("init", "Ejecutando migración y regeneración de tablas faltantes...")
            database.inicializar_db()
            klog("ok", "Esquema relacional completado sin pérdida de datos existentes.")

        elif estado_db == "ok":
            database.inicializar_db()
            klog("ok", f"Base verificada: {n_clips} clips, {n_codigos} cod, {n_resumenes} bor, {n_docs} docs.")

        # 4. Auditoría de Respaldo Previo
        ruta_backup = os.path.join(DIRECTORIO_RAIZ, RUTA_ULTIMO_BACKUP)
        if os.path.exists(ruta_backup):
            try:
                with open(ruta_backup, "r") as f:
                    ts = float(f.read().strip())
                    fecha_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
                    klog("ok", f"Último respaldo verificado: {fecha_str}")
            except Exception:
                klog("warn", "Archivo de seguimiento de backup corrupto (ignorado con seguridad).")
        else:
            klog("info", "No se detecta snapshot de respaldo previo.")

        # Alerta de contraseña de fábrica
        contrasena_ya_mostrada = os.environ.get("CONTRASENA_MOSTRADA", "false").lower() == "true"
        if os.environ.get("APP_PASSWORD") == "cambiame" and not contrasena_ya_mostrada:
            print("\n" + "!" * 65)
            print(" [!] ALERTA CRÍTICA: Credencial de fábrica activa ('cambiame')")
            print(" [i] Cámbiela desde la pestaña Ajustes (⚙️) o mediante CLI_admin.py.")
            print("!" * 65)
            set_key(ENV_PATH, "CONTRASENA_MOSTRADA", "true")
            os.environ["CONTRASENA_MOSTRADA"] = "true"

        print("\n" + "-" * 65)
        print(" [i] CONSOLA FUERA DE BANDA DISPONIBLE: python CLI_admin.py")
        print(" [i] SUITE DE ESTRÉS & RESILIENCIA:      python CLI_chaos.py")
        print("-" * 65)

    # Configuración de Red y Despliegue Flask
    load_dotenv(ENV_PATH, override=True)
    app.secret_key = os.environ.get("SECRET_KEY")

    log_mode_activo = os.environ.get("LOG_MODE", "false").lower() == "true"
    if not log_mode_activo:
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

    debug_mode = False if ES_EXE else (os.environ.get("FLASK_DEBUG", "false").lower() == "true")
    host = os.environ.get("HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("PORT", "5545"))
    except ValueError:
        port = 5545

    if not es_reloader:
        if host == "0.0.0.0":
            ip_lan = "127.0.0.1"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip_lan = s.getsockname()[0]
                s.close()
            except Exception:
                try:
                    ip_lan = socket.gethostbyname(socket.gethostname())
                except Exception:
                    pass

            klog("info", f"Modo Debug: {debug_mode}")
            klog("ok", f"Servidor Local:   http://127.0.0.1:{port}")
            klog("ok", f"Acceso LAN Red:   http://{ip_lan}:{port}")
            klog("info", "Acceso multidispositivo habilitado en la red local.")
        else:
            klog("info", f"Modo Debug: {debug_mode}")
            klog("ok", f"Servidor Local enrutado en http://{host}:{port}")
            klog("fail", "Acceso LAN Red: Desactivado (modo exclusivo de equipo local)")

        print("-" * 65)
        print(">>> PCMPrivateClipManager OPERATIVO Y LISTO <<<")
        print("-" * 65 + "\n")

    if ES_EXE and not es_reloader:
        auto_abrir = os.environ.get("AUTO_ABRIR_NAVEGADOR", "false").lower() == "true"
        if auto_abrir:
            threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()

    app.run(
        host=host,
        port=port,
        debug=debug_mode,
        use_reloader=False if ES_EXE else True,
        extra_files=[ENV_PATH] if not ES_EXE else []
    )