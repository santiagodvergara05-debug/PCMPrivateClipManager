"""
==============================================================================
PCM PRIVATE CLIP MANAGER - NÚCLEO DEL SERVIDOR Y BOOTLOADER (APP.PY)
==============================================================================
Punto de entrada principal del sistema. Responsabilidades:
1. Detección de entorno de ejecución (Desarrollo vs Binario congelado PyInstaller).
2. Inicialización de la aplicación Flask y definición de límites globales (250 MiB).
3. Telemetría de arranque estilo init/kernel de Linux con formateo ANSI.
4. Motor de autorreparación, sanitización y serialización segura del archivo .env.
5. Auditoría de integridad estructural y concurrencia de la base de datos SQLite.
6. Aprovisionamiento, saneamiento de directorios y purga de archivos huérfanos.
7. Resolución dinámica de interfaz local/LAN y puesta en marcha del servidor.
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
from datetime import datetime

# Componentes del framework web y variables de entorno
from flask import Flask, jsonify, request
from dotenv import load_dotenv, dotenv_values, set_key

# Módulos internos de la arquitectura PCM
import database
from routes import clips_bp, RUTA_ULTIMO_BACKUP
from version import VERSION

# Detección de empaquetado PyInstaller (sys.frozen = True cuando es un binario .exe)
ES_EXE = getattr(sys, "frozen", False)
if ES_EXE:
    # Directorio donde reside el ejecutable físico
    DIRECTORIO_RAIZ = os.path.dirname(sys.executable)
    # Carpeta temporal donde PyInstaller descomprime los recursos estáticos y templates
    BUNDLE_DIR = getattr(sys, "_MEIPASS", DIRECTORIO_RAIZ)
else:
    # Entorno estándar de desarrollo de Python
    DIRECTORIO_RAIZ = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = DIRECTORIO_RAIZ

# Definición centralizada de rutas persistentes en el disco local
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

# Límite global amplio para soportar backups completos con multimedia: 250 MiB
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024  # 262,144,000 bytes

# ------------------------------------------------------------------------------
# BLINDAJE DE IDENTIDAD: POLÍTICA DE COOKIES DE SESIÓN
#  HttpOnly → mitiga robo de cookie mediante JavaScript
#  SameSite=Lax → mitiga una parte importante de ataques CSRF
# ------------------------------------------------------------------------------
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False


@app.errorhandler(413)
def error_archivo_demasiado_grande(e):
    """Intercepta peticiones que superen el límite físico de 250 MB."""
    ip_origen = request.remote_addr
    print(f"\n\033[91m[ALERTA DE SEGURIDAD :: OVERFLOW]\033[0m Carga masiva interceptada (> 250 MB) desde IP: {ip_origen}")
    return jsonify({
        "ok": False,
        "error": "El archivo excede el tamaño máximo permitido por el servidor (250 MB)."
    }), 413


# ==============================================================================
# SECCIÓN 3: MOTOR DE TELEMETRÍA Y LOGS ESTILO INIT / KERNEL
# ==============================================================================
def klog(estado, mensaje, delay=0.10):
    """
    Imprime mensajes de telemetría en consola formateados con códigos de color ANSI
    simulando el inicio de un kernel Linux. Respeta terminales sin soporte TTY.
    """
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
}

def serializar_valor_env(valor):
    """
    Normaliza y escapa valores para persistencia en .env.
    """
    v_str = str(valor).replace("\r", "").replace("\n", "")
    v_str = v_str.replace("\\", "\\\\").replace("'", r"\'")
    return f"'{v_str}'"


def escribir_env_seguro(ruta_env, mapa_valores):
    """
    Escribe atómicamente todas las claves del archivo .env en una única pasada.
    """
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
    """
    Protección activa contra manipulación y corrupción:
    1. Detecta archivos .env ilegibles o alterados con datos binarios y los aísla en cuarentena.
    2. Regenera parámetros faltantes con generadores criptográficos independientes.
    3. Normaliza rangos de puerto (1..65535) y direcciones IP de enlace.
    """
    valores = {}
    archivo_danado = False
    env_existia = os.path.exists(ruta_env)

    # 1. Comprobación de legibilidad
    if env_existia:
        try:
            with open(ruta_env, "r", encoding="utf-8") as f:
                f.read()
            valores = dict(dotenv_values(ruta_env))
        except Exception:
            archivo_danado = True

    # 2. Aislamiento preventivo ante sabotaje o corrupción
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
        flag_env = str(valores.get("SISTEMA_INICIALIZADO", "")).strip("'\"").lower() == "true"
        ya_inicializado = flag_env or os.path.exists(DB_PATH)

    hubo_cambios = archivo_danado or (not env_existia)
    faltantes = []
    advertencias = []

    # 3. Detección de incoherencias de estado
    val_init = valores.get("SISTEMA_INICIALIZADO")
    if val_init is not None and str(val_init).strip("'\"").lower() == "false" and os.path.exists(DB_PATH):
        advertencias.append("Inconsistencia: Base de datos activa pero SISTEMA_INICIALIZADO='false'. Corrigiendo a 'true'...")
        valores["SISTEMA_INICIALIZADO"] = "true"
        hubo_cambios = True

    # 4. Provisión de claves predeterminadas ausentes o vacías
    for clave, valor_default in VALORES_PREDETERMINADOS.items():
        val = valores.get(clave)
        if val is None or not str(val).strip():
            nuevo_val = valor_default() if callable(valor_default) else valor_default
            valores[clave] = nuevo_val
            faltantes.append(clave)
            hubo_cambios = True

    # 5. Sanitización de Puerto de Red (PORT: 1 a 65535)
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

    # 6. Sanitización de Interfaz de Escucha (HOST)
    host_raw = str(valores.get("HOST", "127.0.0.1")).strip("'\"")
    if host_raw not in ["127.0.0.1", "0.0.0.0"]:
        advertencias.append(f"Host no estándar detectado ({host_raw}). Normalizando a 127.0.0.1...")
        valores["HOST"] = "127.0.0.1"
        hubo_cambios = True

    # 7. Persistencia final en disco
    if hubo_cambios:
        exito = escribir_env_seguro(ruta_env, valores)
        if not exito:
            klog("warn", "No se pudo actualizar .env en disco por bloqueo del SO. Usando valores en memoria.")

    for k, v in valores.items():
        os.environ[k] = str(v)

    return faltantes, ya_inicializado, env_existia, archivo_danado, advertencias


# ==============================================================================
# SECCIÓN 5: AUDITORÍA AVANZADA DE INTEGRIDAD SQLITE
# ==============================================================================
def auditar_integridad_db(db_path):
    """
    Inspecciona la salud física del motor SQLite:
    - PRAGMA integrity_check para detectar páginas de disco corruptas.
    - Presencia de esquemas relacionales mínimos obligatorios ('clips', 'documentos').
    - Cuantifica registros por categoría para telemetría.
    """
    if not os.path.exists(db_path):
        return "ausente", 0, 0, 0, 0

    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        cur = conn.cursor()

        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        if not res or res[0] != "ok":
            return "corrupta", 0, 0, 0, 0

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('clips', 'documentos');")
        tablas = [r[0] for r in cur.fetchall()]
        if len(tablas) < 2:
            return "incompleta", 0, 0, 0, 0

        # Cómputo de métricas con soporte para las 5 categorías de notas
        cur.execute("""
            SELECT COUNT(*) FROM clips 
            WHERE categoria NOT IN ('Nota', 'Borrador', 'Resumen', 'Apuntes', 'Texto Plano', 'Novelas') 
              AND categoria NOT LIKE 'Codigo:%';
        """)
        total_clips = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM clips WHERE categoria LIKE 'Codigo:%';")
        total_codigo = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM clips 
            WHERE categoria IN ('Nota', 'Borrador', 'Resumen', 'Apuntes', 'Texto Plano', 'Novelas');
        """)
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


# ==============================================================================
# SECCIÓN 6: SANEAMIENTO DEL SISTEMA DE ARCHIVOS Y PURGA
# ==============================================================================
def sanear_directorios_y_archivos(ya_inicializado=False):
    """
    Verifica y aprovisiona los directorios indispensables para la ejecución.
    Elimina archivos temporales o huérfanos de 0 bytes.
    """
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


# ==============================================================================
# SECCIÓN 7: RUTINA DE ARRANQUE (BOOTLOADER), RED LAN Y SERVIDOR WSGI
# ==============================================================================
if __name__ == "__main__":
    es_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

    # Migración transparente de versiones heredadas (cliptemp.db -> pcm.db)
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
        time.sleep(0.15)

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

        if os.environ.get("MASTER_KEY") and os.environ.get("SECRET_KEY"):
            klog("ok", "Llaves criptográficas maestras activas (256 bits).")

        # 2. Comprobación y aprovisionamiento de carpetas físicas
        klog("init", "Verificando estructura de almacenamiento...")
        sanear_directorios_y_archivos(ya_inicializado=ya_inicializado)

        # 3. Auditoría de integridad de base de datos SQLite
        estado_db, n_clips, n_codigos, n_resumenes, n_docs = auditar_integridad_db(DB_PATH)

        if estado_db == "bloqueada":
            klog("fail", "La base de datos se encuentra bloqueada por otro proceso.")
            klog("warn", "Esperando 2 segundos...")
            time.sleep(2)
            estado_db, n_clips, n_codigos, n_resumenes, n_docs = auditar_integridad_db(DB_PATH)
            if estado_db == "bloqueada":
                klog("fail", "Imposible acceder a pcm.db. Cierre el proceso que mantiene el candado.")
                sys.exit(1)

        if estado_db == "ausente":
            klog("info", "Base de datos persistente ausente. Generando pcm.db limpio...")
            database.inicializar_db()
            klog("ok", "Base de datos SQLite creada e indexada.")

        elif estado_db == "corrupta":
            klog("fail", "Base de datos dañada o ilegible. Aislándola en cuarentena...")
            cuarentena_db = f"pcm.db.corrupt_{int(time.time())}"
            try:
                os.rename(DB_PATH, os.path.join(DIRECTORIO_RAIZ, cuarentena_db))
                klog("warn", f"Base corrupta aislada: {cuarentena_db}")
            except Exception:
                try:
                    os.remove(DB_PATH)
                except Exception:
                    pass
            database.inicializar_db()
            klog("ok", "Nueva base de datos inicializada en estado limpio.")

        elif estado_db in ["incompleta", "ok"]:
            database.inicializar_db()
            klog("ok", f"Base verificada: {n_clips} clips, {n_codigos} cod, {n_resumenes} notas, {n_docs} docs.")

        # 4. Verificación de última instantánea de respaldo
        ruta_backup = os.path.join(DIRECTORIO_RAIZ, RUTA_ULTIMO_BACKUP)
        if os.path.exists(ruta_backup):
            try:
                with open(ruta_backup, "r", encoding="utf-8") as f:
                    ts = float(f.read().strip())
                    fecha_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                    klog("ok", f"Último respaldo verificado: {fecha_str}")
            except Exception:
                klog("warn", "Archivo de seguimiento de backup corrupto (ignorado).")
        else:
            klog("info", "No se detecta snapshot de respaldo previo.")

        # 5. Detección y advertencia de credenciales por defecto (sin mutar .env)
        contrasena_ya_mostrada = os.environ.get("CONTRASENA_MOSTRADA", "false").strip().lower() == "true"
        if os.environ.get("APP_PASSWORD") == "cambiame" and not contrasena_ya_mostrada:
            print("\n" + "!" * 65)
            print(" [!] PRIMER INICIO DETECTADO: Credencial temporal activa ('cambiame')")
            print(" [i] Visualice la Master Key e inicie sesión en la pantalla web.")
            print("!" * 65)

        # ---> REINCORPORAR ESTE BLOQUE AQUÍ:
        print("\n" + "-" * 65)
        comando_cli = "CLI_admin.exe" if ES_EXE else "python CLI_admin.py"
        print(f" [i] CONSOLA DE ADMINISTRACIÓN DISPONIBLE: {comando_cli}")
        print("-" * 65)



    # Configuración de red y modo de logging de Werkzeug
    load_dotenv(ENV_PATH, override=True)
    app.secret_key = os.environ.get("SECRET_KEY")

    log_mode_activo = os.environ.get("LOG_MODE", "false").strip().lower() == "true"
    if not log_mode_activo:
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

    debug_mode = False if ES_EXE else (os.environ.get("FLASK_DEBUG", "false").strip().lower() == "true")
    host = os.environ.get("HOST", "127.0.0.1").strip()
    try:
        port = int(os.environ.get("PORT", "5545").strip())
    except ValueError:
        port = 5545

    # Resolución de acceso local o LAN
    if not es_reloader:
        klog("info", f"Modo Debug: {debug_mode}")
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

            klog("ok", f"Servidor Local:   http://127.0.0.1:{port}")
            klog("ok", f"Acceso LAN Red:   http://{ip_lan}:{port}")
            klog("info", "Acceso multidispositivo habilitado en la red local.")
        else:
            klog("ok", f"Servidor Local enrutado en http://{host}:{port}")
            klog("fail", f"Acceso LAN Red: no disponible")
            klog("info", "Acceso LAN Red: Desactivado (modo exclusivo PC local)")

        print("-" * 65)
        print(">>> PCMPrivateClipManager OPERATIVO Y LISTO <<<")
        print("-" * 65 + "\n")

    # Apertura diferida del navegador
    auto_abrir = os.environ.get("AUTO_ABRIR_NAVEGADOR", "true").strip().lower() == "true"
    if auto_abrir and (ES_EXE or not es_reloader):
        url_destino = f"http://127.0.0.1:{port}"
        threading.Timer(1.2, lambda: webbrowser.open(url_destino)).start()

    # Ejecución del servidor HTTP
    app.run(
        host=host,
        port=port,
        debug=debug_mode,
        use_reloader=False if ES_EXE else True,
        extra_files=[ENV_PATH] if not ES_EXE else []
    )