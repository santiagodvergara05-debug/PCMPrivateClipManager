"""
==============================================================================
PCM PRIVATE CLIP MANAGER - ENRUTADOR Y CONTROLADOR CENTRAL (ROUTES.PY)
==============================================================================
Núcleo de peticiones HTTP para Flask. Gestiona:
1. Control de acceso, sesiones y desbloqueo maestro temporal.
2. CRUD para Clips rápidos, Snippets de código y Borradores/Novelas.
3. Persistencia de Documentos técnicos (Markdown, KaTeX, Mermaid).
4. Subida segura y validación binaria de imágenes (Tope estricto de 25 MiB).
5. Sistema de exportación/importación de backups (.json y .zip con assets).
6. Sincronización BYOC multidispositivo con cifrado E2EE (AES-256).
7. Diagnóstico, integridad criptográfica SHA-256 y mantenimiento de base de datos.
==============================================================================
"""

import os
import sys
import subprocess
import io
import json
import time
import secrets
import shutil
import zipfile
import uuid
import hashlib
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
    jsonify,
    flash,
    current_app
)
from dotenv import set_key, dotenv_values

import database
import sync_manager
from version import VERSION

# Instanciación del Blueprint principal
clips_bp = Blueprint("clips", __name__)

# ==============================================================================
# SECCIÓN 1: CONFIGURACIONES Y CONSTANTES DE OPERACIÓN
# ==============================================================================
INICIO_SERVIDOR = secrets.token_hex(8)
DURACION_DESBLOQUEO = 120  # 2 minutos

RUTA_ENV = ".env"
RUTA_ULTIMO_BACKUP = "ultimo_backup.txt"
RUTA_ULTIMO_SYNC = "ultimo_sync.txt"

CATEGORIAS_TEXTO_LARGO = ("Nota", "Borrador", "Resumen", "Apuntes", "Texto Plano", "Novelas", "Prompt")
CARPETA_IMAGENES_DOCS = os.path.join("static", "uploads", "documentos")

LIMITE_MB_IMAGEN = 25
MAX_BYTES_IMAGEN = LIMITE_MB_IMAGEN * 1024 * 1024

EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "gif", "webp"}

CABECERAS_MAGICAS = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp"
}


# ==============================================================================
# SECCIÓN 2: MOTOR DE AUDITORÍA, TELEMETRÍA Y LOGGING ANSI EN TERMINAL
# ==============================================================================
CLR_RESET    = "\033[0m"
CLR_GRIS     = "\033[90m"
CLR_AZUL     = "\033[94m"
CLR_CYAN     = "\033[96m"
CLR_VERDE    = "\033[92m"
CLR_AMARILLO = "\033[93m"
CLR_ROJO     = "\033[91m"
CLR_MAGENTA  = "\033[95m"
CLR_BOLD     = "\033[1m"

def registrar_log(accion, tipo=None):
    """Emite registros formateados en consola respetando la variable LOG_MODE."""
    if os.environ.get("LOG_MODE", "true").lower() != "true":
        return

    hora = datetime.now().strftime("%H:%M:%S")
    accion_lower = accion.lower()

    if tipo == "ERROR" or (tipo is None and any(k in accion_lower for k in ["error", "fallid", "rechazad", "peligro", "no autorizada", "dañado", "corrupto"])):
        badge = f"{CLR_BOLD}{CLR_ROJO}✖ [PCM :: ALERTA]{CLR_RESET}"
        texto_formateado = f"{CLR_ROJO}{accion}{CLR_RESET}"
    elif tipo == "WARN" or (tipo is None and any(k in accion_lower for k in ["advertencia", "aviso", "conflicto", "ignorado", "bloqueada", "pendiente"])):
        badge = f"{CLR_BOLD}{CLR_AMARILLO}⚠ [PCM :: WARN]{CLR_RESET}"
        texto_formateado = f"{CLR_AMARILLO}{accion}{CLR_RESET}"
    elif tipo == "SUCCESS" or (tipo is None and any(k in accion_lower for k in ["éxito", "exitos", "cread", "guardad", "actualizad", "iniciad", "restaurad"])):
        badge = f"{CLR_BOLD}{CLR_VERDE}✔ [PCM :: ÉXITO]{CLR_RESET}"
        texto_formateado = f"{CLR_VERDE}{accion}{CLR_RESET}"
    elif tipo == "DELETE" or (tipo is None and any(k in accion_lower for k in ["elimin", "purgada", "vaciado total"])):
        badge = f"{CLR_BOLD}{CLR_MAGENTA}🗑 [PCM :: DELETE]{CLR_RESET}"
        texto_formateado = f"{CLR_MAGENTA}{accion}{CLR_RESET}"
    elif tipo == "SYS" or (tipo is None and any(k in accion_lower for k in ["desbloque", "bloque", "sesión", "rotad", "crític", "sync"])):
        badge = f"{CLR_BOLD}{CLR_AMARILLO}⚡ [PCM :: SYS]{CLR_RESET}"
        texto_formateado = f"{CLR_AMARILLO}{accion}{CLR_RESET}"
    else:
        badge = f"{CLR_BOLD}{CLR_CYAN}ℹ [PCM :: INFO]{CLR_RESET}"
        texto_formateado = f"{CLR_CYAN}{accion}{CLR_RESET}"

    print(f"{CLR_GRIS}[{hora}]{CLR_RESET} {badge} {texto_formateado}")


# ==============================================================================
# SECCIÓN 3: CONTROL DE ACCESO, SESIÓN Y DECORADORES DE SEGURIDAD
# ==============================================================================
def esta_desbloqueado():
    """Valida si la sesión administrativa cuenta con desbloqueo crítico activo y vigente."""
    if not session.get("desbloqueo_critico"):
        return False
    if session.get("desbloqueo_servidor") != INICIO_SERVIDOR:
        session.pop("desbloqueo_critico", None)
        return False
    if time.time() > session.get("desbloqueo_expira", 0):
        session.pop("desbloqueo_critico", None)
        return False
    return True


def login_requerido(f):
    """Decorador para proteger rutas autenticadas contra accesos anónimos."""
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get("autenticado"):
            ip = request.remote_addr
            registrar_log(f"Acceso no autorizado interceptado en '{request.path}' ({request.method}) desde IP: {ip}", "ERROR")
            if request.method in ["POST", "PUT", "DELETE"]:
                if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"ok": False, "error": "Sesión no válida o expirada."}), 401
            return redirect(url_for("clips.login"))
        return f(*args, **kwargs)
    return decorador


# ==============================================================================
# SECCIÓN 4: UTILIDADES DE ARCHIVOS, HASHING E INTEGRIDAD CRIPTOGRÁFICA
# ==============================================================================
def extension_valida(nombre_archivo):
    """Verifica si el archivo posee una extensión autorizada."""
    return "." in nombre_archivo and nombre_archivo.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS


def validar_firma_binaria_imagen(stream):
    """Inspecciona los números mágicos del flujo binario para descartar extensiones falsificadas."""
    posicion_original = stream.tell()
    stream.seek(0)
    cabecera = stream.read(32)
    stream.seek(posicion_original)

    for firma, ext in CABECERAS_MAGICAS.items():
        if cabecera.startswith(firma):
            if firma == b"RIFF" and b"WEBP" not in cabecera[:16]:
                continue
            return ext
    return None


def formatear_tamano(bytes_cant):
    """Convierte bytes a formato legible (B, KB, MB)."""
    if bytes_cant < 1024:
        return f"{bytes_cant} B"
    elif bytes_cant < 1024 * 1024:
        return f"{bytes_cant / 1024:.1f} KB"
    else:
        return f"{bytes_cant / (1024 * 1024):.2f} MB"

formatear_bytes = formatear_tamano


def calcular_sha256_archivo(ruta):
    """Calcula el hash SHA-256 de un archivo en disco de forma segura mediante streaming en bloques."""
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


def verificar_integridad_zip_remoto(ruta_zip, meta_dict):
    """Valida la integridad estructural de un archivo ZIP y su coincidencia con la firma SHA-256."""
    if not os.path.exists(ruta_zip) or os.path.getsize(ruta_zip) == 0:
        return False

    # 1. Validación estructural nativa de archivo ZIP
    if not zipfile.is_zipfile(ruta_zip):
        return False

    # 2. Validación de firma criptográfica SHA-256 tolerante a distintas claves
    if meta_dict:
        hash_esperado = (
            meta_dict.get("sha256")
            or meta_dict.get("hash_sha256")
            or meta_dict.get("hash")
            or meta_dict.get("checksum")
        )
        if hash_esperado:
            hash_calculado = calcular_sha256_archivo(ruta_zip)
            if hash_calculado != hash_esperado:
                return False

    return True


# ==============================================================================
# SECCIÓN 5: PROCESADOR DE CONTEXTO GLOBAL (JINJA2 TEMPLATES)
# ==============================================================================
@clips_bp.app_context_processor
def inyectar_contexto():
    """Inyecta variables de sistema y el estado de sincronización en todas las vistas."""
    sync_hab = os.environ.get("SYNC_HABILITADO", "false").lower() == "true"
    sync_carp = os.environ.get("SYNC_CARPETA", "").strip()
    cambios_pendientes = False

    if sync_hab and sync_carp and os.path.isdir(sync_carp):
        ultimo_sync_ts = 0.0
        if os.path.exists(RUTA_ULTIMO_SYNC):
            try:
                with open(RUTA_ULTIMO_SYNC, "r", encoding="utf-8") as f:
                    ultimo_sync_ts = float(f.read().strip())
            except Exception:
                ultimo_sync_ts = 0.0

        db_path = getattr(database, "DB_PATH", "pcm.db")
        if os.path.exists(db_path):
            db_mtime = os.path.getmtime(db_path)
            if db_mtime > (ultimo_sync_ts + 1.5):
                cambios_pendientes = True

    return {
        "app_version": VERSION,
        "sync_hab": sync_hab,
        "sync_pendiente": cambios_pendientes
    }


# ==============================================================================
# SECCIÓN 6: AUTENTICACIÓN Y CONTROL DE ACCESO
# ==============================================================================
@clips_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("autenticado"):
        return redirect(url_for("clips.index"))

    mostrar_credenciales = os.environ.get("CONTRASENA_MOSTRADA", "false").strip().lower() != "true"
    error = None

    if request.method == "POST":
        password_ingresada = request.form.get("password", "").strip()
        app_password = os.environ.get("APP_PASSWORD", "cambiame").strip()
        master_key = os.environ.get("MASTER_KEY", "").strip()

        if password_ingresada and (password_ingresada == app_password or (master_key and password_ingresada == master_key)):
            session["autenticado"] = True
            session.permanent = True
            registrar_log(f"Inicio de sesión exitoso desde IP: {request.remote_addr}", "SUCCESS")

            if mostrar_credenciales:
                try:
                    set_key(RUTA_ENV, "CONTRASENA_MOSTRADA", "true")
                    os.environ["CONTRASENA_MOSTRADA"] = "true"
                    registrar_log("Primer inicio completado: aviso de credenciales temporales ocultado permanentemente", "SYS")
                except Exception as e:
                    registrar_log(f"Error actualizando bandera de credenciales en .env: {e}", "ERROR")

            return redirect(url_for("clips.index"))
        else:
            error = "Contraseña incorrecta. Inténtalo de nuevo."
            registrar_log(f"Intento fallido de inicio de sesión desde IP: {request.remote_addr}", "ERROR")

    temp_password = os.environ.get("APP_PASSWORD", "cambiame")
    master_key_val = os.environ.get("MASTER_KEY", "")

    return render_template(
        "login.html",
        error=error,
        mostrar_credenciales=mostrar_credenciales,
        temp_password=temp_password,
        master_key=master_key_val
    )


@clips_bp.route("/logout")
def logout():
    session.clear()
    registrar_log("Cierre de sesión manual ejecutado", "SYS")
    return redirect(url_for("clips.login"))


# ==============================================================================
# SECCIÓN 7: CLIPS RÁPIDOS Y PORTAPAPELES
# ==============================================================================
@clips_bp.route("/")
@login_requerido
def index():
    database.purgar_expirados()
    conn = database.obtener_conexion()

    clips = conn.execute("""
        SELECT * FROM clips 
        WHERE tipo = 'clip'
        ORDER BY es_favorito DESC, id DESC
    """).fetchall()

    categorias_raw = conn.execute("""
        SELECT DISTINCT categoria 
        FROM clips 
        WHERE tipo = 'clip'
          AND TRIM(categoria) != '' 
        ORDER BY categoria COLLATE NOCASE ASC
    """).fetchall()
    categorias = [r["categoria"] for r in categorias_raw]

    conn.close()
    return render_template("index.html", clips=clips, categorias=categorias)


@clips_bp.route("/crear", methods=["POST"])
@login_requerido
def crear():
    titulo = request.form.get("titulo", "").strip()
    contenido = request.form.get("contenido", "").strip()
    categoria = request.form.get("categoria", "General").strip() or "General"
    duracion_min = int(request.form.get("duracion", 0))
    vistas = -1

    if contenido:
        ahora = int(time.time())
        expira_en = ahora + (duracion_min * 60) if duracion_min > 0 else None
        clip_uuid = str(uuid.uuid4())[:8]

        conn = database.obtener_conexion()
        conn.execute("""
            INSERT INTO clips (uuid, titulo, contenido, categoria, tipo, fecha_creacion, expira_en, vistas_restantes)
            VALUES (?, ?, ?, ?, 'clip', ?, ?, ?)
        """, (clip_uuid, titulo, contenido, categoria, ahora, expira_en, vistas))
        conn.commit()
        conn.close()
        registrar_log(f"Clip creado: [{categoria}] '{titulo or 'Sin título'}'", "SUCCESS")

    return redirect(url_for("clips.index"))


@clips_bp.route("/favorito/<int:clip_id>", methods=["POST"])
@login_requerido
def alternar_favorito(clip_id):
    conn = database.obtener_conexion()
    clip = conn.execute("SELECT es_favorito, titulo FROM clips WHERE id = ?", (clip_id,)).fetchone()

    if clip:
        nuevo_estado = 0 if clip["es_favorito"] == 1 else 1
        conn.execute("UPDATE clips SET es_favorito = ? WHERE id = ?", (nuevo_estado, clip_id))
        conn.commit()
        accion = "fijado en favoritos" if nuevo_estado == 1 else "removido de favoritos"
        registrar_log(f"Clip '{clip['titulo'] or clip_id}' {accion}", "SUCCESS")

    conn.close()
    return redirect(url_for("clips.index"))


@clips_bp.route("/editar/<int:clip_id>", methods=["POST"])
@login_requerido
def editar_clip(clip_id):
    titulo = request.form.get("titulo", "").strip()
    categoria = request.form.get("categoria", "General").strip() or "General"
    contenido = request.form.get("contenido", "").strip()
    opcion_duracion = request.form.get("duracion", "mantener")

    if contenido:
        conn = database.obtener_conexion()
        ahora = int(time.time())

        if opcion_duracion == "mantener":
            conn.execute("""
                UPDATE clips 
                SET titulo = ?, categoria = ?, contenido = ?
                WHERE id = ?
            """, (titulo, categoria, contenido, clip_id))
        elif opcion_duracion == "0":
            conn.execute("""
                UPDATE clips 
                SET titulo = ?, categoria = ?, contenido = ?, expira_en = NULL
                WHERE id = ?
            """, (titulo, categoria, contenido, clip_id))
        else:
            minutos = int(opcion_duracion)
            nuevo_expira = ahora + (minutos * 60)
            conn.execute("""
                UPDATE clips 
                SET titulo = ?, categoria = ?, contenido = ?, expira_en = ?
                WHERE id = ?
            """, (titulo, categoria, contenido, nuevo_expira, clip_id))

        conn.commit()
        conn.close()
        registrar_log(f"Clip modificado: [{categoria}] '{titulo or clip_id}'", "SUCCESS")

    return redirect(url_for("clips.index"))


@clips_bp.route("/eliminar/<int:clip_id>", methods=["GET", "POST", "DELETE"])
@login_requerido
def eliminar(clip_id):
    conn = database.obtener_conexion()
    clip = conn.execute("SELECT categoria, tipo, titulo FROM clips WHERE id = ?", (clip_id,)).fetchone()
    
    es_texto_largo = clip and (clip["tipo"] == "nota" or clip["categoria"] in CATEGORIAS_TEXTO_LARGO)
    es_codigo = clip and (clip["tipo"] == "codigo" or clip["categoria"].startswith("Codigo:"))
    titulo = clip["titulo"] if clip else str(clip_id)

    conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
    conn.commit()
    conn.close()
    registrar_log(f"Registro eliminado: '{titulo}'", "DELETE")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"ok": True, "id": clip_id})

    if es_texto_largo:
        return redirect(url_for("clips.biblioteca_novelas"))
    if es_codigo:
        return redirect(url_for("clips.seccion_codigo"))
    return redirect(url_for("clips.index"))


# ==============================================================================
# SECCIÓN 8: MÓDULO DE BORRADORES Y RESÚMENES (NOTAS)
# ==============================================================================
@clips_bp.route("/notas")
@login_requerido
def biblioteca_novelas():
    conn = database.obtener_conexion()
    resumenes = conn.execute("""
        SELECT * FROM clips 
        WHERE tipo = 'nota' 
        ORDER BY id DESC
    """).fetchall()
    conn.close()
    return render_template("notas.html", resumenes=resumenes)


@clips_bp.route("/editor")
@clips_bp.route("/editor/<int:clip_id>")
@login_requerido
def editor(clip_id=None):
    clip = None
    if clip_id:
        conn = database.obtener_conexion()
        clip = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        conn.close()
    return render_template("editor.html", clip=clip)


@clips_bp.route("/guardar_resumen", methods=["POST"])
@login_requerido
def guardar_resumen():
    clip_id = request.form.get("clip_id")
    titulo = request.form.get("titulo", "").strip() or "Texto sin título"
    tipo_doc = request.form.get("tipo_doc", "Borrador").strip()
    
    categorias_permitidas = ["Nota", "Borrador", "Resumen", "Apuntes", "Texto Plano", "Prompt"]
    if tipo_doc not in categorias_permitidas:
        tipo_doc = "Borrador"

    contenido = request.form.get("contenido", "").strip()
    if not contenido:
        return redirect(url_for("clips.biblioteca_novelas"))

    conn = database.obtener_conexion()
    ahora = int(time.time())

    if clip_id:
        conn.execute("""
            UPDATE clips 
            SET titulo = ?, contenido = ?, categoria = ?, tipo = 'nota'
            WHERE id = ?
        """, (titulo, contenido, tipo_doc, clip_id))
        registrar_log(f"Nota actualizada [{tipo_doc}]: '{titulo}'", "SUCCESS")
    else:
        clip_uuid = str(uuid.uuid4())[:8]
        conn.execute("""
            INSERT INTO clips (uuid, titulo, contenido, categoria, tipo, fecha_creacion, expira_en, vistas_restantes)
            VALUES (?, ?, ?, ?, 'nota', ?, NULL, -1)
        """, (clip_uuid, titulo, contenido, tipo_doc, ahora))
        registrar_log(f"Nueva nota guardada [{tipo_doc}]: '{titulo}'", "SUCCESS")

    conn.commit()
    conn.close()
    return redirect(url_for("clips.biblioteca_novelas"))


# ==============================================================================
# SECCIÓN 9: SNIPPETS DE CÓDIGO Y SINTAXIS
# ==============================================================================
@clips_bp.route("/codigo")
@login_requerido
def seccion_codigo():
    conn = database.obtener_conexion()
    snippets = conn.execute(
        "SELECT * FROM clips WHERE tipo = 'codigo' OR categoria LIKE 'Codigo:%' ORDER BY id DESC"
    ).fetchall()

    lenguajes_raw = conn.execute("""
        SELECT DISTINCT categoria FROM clips 
        WHERE tipo = 'codigo' OR categoria LIKE 'Codigo:%' 
        ORDER BY categoria ASC
    """).fetchall()
    lenguajes = [r["categoria"].replace("Codigo:", "") for r in lenguajes_raw]

    conn.close()
    return render_template("codigo.html", snippets=snippets, lenguajes_disponibles=lenguajes)


@clips_bp.route("/codigo/nuevo")
@login_requerido
def nuevo_codigo():
    return render_template("agregar_codigo.html")


@clips_bp.route("/codigo/guardar", methods=["POST"])
@login_requerido
def guardar_codigo():
    titulo = request.form.get("titulo", "").strip() or "Snippet sin título"
    lenguaje = request.form.get("lenguaje", "Texto").strip()
    contenido = request.form.get("contenido", "").strip()

    if contenido:
        categoria_codigo = f"Codigo:{lenguaje}"
        clip_uuid = str(uuid.uuid4())[:8]
        ahora = int(time.time())

        conn = database.obtener_conexion()
        conn.execute("""
            INSERT INTO clips (uuid, titulo, contenido, categoria, tipo, fecha_creacion, expira_en, vistas_restantes)
            VALUES (?, ?, ?, ?, 'codigo', ?, NULL, -1)
        """, (clip_uuid, titulo, contenido, categoria_codigo, ahora))
        conn.commit()
        conn.close()
        registrar_log(f"Snippet guardado: [{lenguaje}] '{titulo}'", "SUCCESS")

    return redirect(url_for("clips.seccion_codigo"))


@clips_bp.route("/codigo/editar/<int:clip_id>", methods=["POST"])
@login_requerido
def editar_codigo(clip_id):
    titulo = request.form.get("titulo", "").strip() or "Snippet sin título"
    lenguaje = request.form.get("lenguaje", "Texto").strip()
    contenido = request.form.get("contenido", "").strip()

    if contenido:
        categoria_codigo = f"Codigo:{lenguaje}"
        conn = database.obtener_conexion()
        conn.execute("""
            UPDATE clips 
            SET titulo = ?, categoria = ?, contenido = ?, tipo = 'codigo'
            WHERE id = ?
        """, (titulo, categoria_codigo, contenido, clip_id))
        conn.commit()
        conn.close()
        registrar_log(f"Snippet actualizado: [{lenguaje}] '{titulo}'", "SUCCESS")

    return redirect(url_for("clips.seccion_codigo"))


# ==============================================================================
# SECCIÓN 10: HERRAMIENTAS ADICIONALES (FUSIONADOR)
# ==============================================================================
@clips_bp.route("/fusionador")
@login_requerido
def fusionador():
    registrar_log("Herramienta Fusionador de textos abierta", "INFO")
    return render_template("fusionador.html")


# ==============================================================================
# SECCIÓN 11: GESTOR DE DOCUMENTOS TÉCNICOS (MARKDOWN, LATEX & MERMAID)
# ==============================================================================
@clips_bp.route("/documentos")
@login_requerido
def documentos():
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, titulo, contenido, creado_en, actualizado_en 
        FROM documentos 
        ORDER BY actualizado_en DESC
    """)
    lista_docs = cursor.fetchall()
    conn.close()
    return render_template("lista_documentos.html", documentos=lista_docs)


@clips_bp.route("/documentos/estudio")
@login_requerido
def documentos_nuevo():
    return render_template("documentos.html", doc=None)


@clips_bp.route("/documentos/estudio/<int:doc_id>")
@login_requerido
def documentos_editar(doc_id):
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT id, titulo, contenido FROM documentos WHERE id = ?", (doc_id,))
    doc = cursor.fetchone()
    conn.close()

    if not doc:
        flash("El documento solicitado no existe en la base de datos.", "error")
        return redirect(url_for("clips.documentos"))

    return render_template("documentos.html", doc=doc)


@clips_bp.route("/documentos/api/guardar", methods=["POST"])
@login_requerido
def api_guardar_documento():
    data = request.get_json() or {}
    doc_id = data.get("id")
    titulo = (data.get("titulo") or "").strip() or "Documento sin título"
    contenido = data.get("contenido") or ""

    conn = database.obtener_conexion()
    cursor = conn.cursor()

    if doc_id:
        cursor.execute("""
            UPDATE documentos 
            SET titulo = ?, contenido = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (titulo, contenido, doc_id))
        nuevo_id = doc_id
        accion_desc = f"Documento actualizado: '{titulo}' (ID: {nuevo_id})"
    else:
        cursor.execute("""
            INSERT INTO documentos (titulo, contenido) 
            VALUES (?, ?)
        """, (titulo, contenido))
        nuevo_id = cursor.lastrowid
        accion_desc = f"Nuevo documento creado: '{titulo}' (ID: {nuevo_id})"

    conn.commit()
    conn.close()

    registrar_log(accion_desc, "SUCCESS")
    return jsonify({"ok": True, "id": nuevo_id, "titulo": titulo})


@clips_bp.route("/documentos/eliminar/<int:doc_id>", methods=["POST"])
@login_requerido
def eliminar_documento(doc_id):
    conn = database.obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("SELECT titulo FROM documentos WHERE id = ?", (doc_id,))
    doc = cursor.fetchone()
    titulo_doc = doc["titulo"] if doc else f"ID #{doc_id}"

    cursor.execute("DELETE FROM documentos WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

    registrar_log(f"Documento eliminado: '{titulo_doc}'", "DELETE")
    flash("Documento eliminado correctamente.", "info")
    return redirect(url_for("clips.documentos"))


# ==============================================================================
# SECCIÓN 12: GESTOR MULTIMEDIA BLINDADO (AUDITORÍA BINARIA Y SUBIDAS)
# ==============================================================================
@clips_bp.route("/documentos/api/subir_imagen", methods=["POST"])
@login_requerido
def api_subir_imagen_documento():
    if "imagen" not in request.files:
        return jsonify({"ok": False, "error": "No se envió ningún archivo en la petición."}), 400

    archivo = request.files["imagen"]
    if not archivo or archivo.filename == "":
        return jsonify({"ok": False, "error": "El nombre del archivo está vacío."}), 400

    archivo.seek(0, os.SEEK_END)
    tamano_bytes = archivo.tell()
    archivo.seek(0)

    if tamano_bytes > MAX_BYTES_IMAGEN:
        return jsonify({
            "ok": False, 
            "error": f"El archivo supera el límite permitido de {LIMITE_MB_IMAGEN} MB ({formatear_tamano(tamano_bytes)})."
        }), 413

    if not extension_valida(archivo.filename):
        return jsonify({
            "ok": False, 
            "error": "Extensión no permitida. Formatos aceptados: PNG, JPG, JPEG, GIF, WEBP."
        }), 400

    formato_real = validar_firma_binaria_imagen(archivo.stream)
    if not formato_real:
        ip = request.remote_addr
        registrar_log(f"Payload falso interceptado: imagen corrupta o firma inválida '{archivo.filename}' desde IP: {ip}", "ERROR")
        return jsonify({
            "ok": False, 
            "error": "El archivo está dañado o no corresponde a una imagen válida (firma binaria rechazada)."
        }), 400

    os.makedirs(CARPETA_IMAGENES_DOCS, exist_ok=True)
    nombre_limpio = secure_filename(archivo.filename)
    nombre_seguro = f"img_{uuid.uuid4().hex[:12]}.{formato_real}"
    ruta_destino = os.path.join(CARPETA_IMAGENES_DOCS, nombre_seguro)

    archivo.save(ruta_destino)

    url_relativa = f"/static/uploads/documentos/{nombre_seguro}"
    registrar_log(f"Imagen subida con éxito: {nombre_seguro} ({formatear_tamano(tamano_bytes)})", "SUCCESS")

    return jsonify({
        "ok": True,
        "url": url_relativa,
        "nombre": nombre_limpio or nombre_seguro,
        "markdown": f"![{nombre_limpio or 'Imagen'}]({url_relativa})"
    })


@clips_bp.route("/documentos/api/imagenes", methods=["GET"])
@login_requerido
def api_listar_imagenes_documentos():
    os.makedirs(CARPETA_IMAGENES_DOCS, exist_ok=True)
    imagenes = []

    try:
        for archivo in os.listdir(CARPETA_IMAGENES_DOCS):
            if extension_valida(archivo):
                ruta_completa = os.path.join(CARPETA_IMAGENES_DOCS, archivo)
                if os.path.isfile(ruta_completa):
                    imagenes.append({
                        "nombre": archivo,
                        "url": f"/static/uploads/documentos/{archivo}",
                        "fecha": os.path.getmtime(ruta_completa)
                    })
        imagenes.sort(key=lambda x: x["fecha"], reverse=True)
    except Exception as e:
        registrar_log(f"Error al listar galería de imágenes: {e}", "ERROR")

    return jsonify({"ok": True, "imagenes": imagenes})


@clips_bp.route("/documentos/api/eliminar_imagen/<nombre>", methods=["POST"])
@login_requerido
def api_eliminar_imagen_documento(nombre):
    if os.path.basename(nombre) != nombre or not extension_valida(nombre):
        ip = request.remote_addr
        registrar_log(f"Intrusión interceptada (Path Traversal en borrado): '{nombre}' desde IP: {ip}", "ERROR")
        return jsonify({"ok": False, "error": "Identificador de archivo no válido."}), 400

    ruta_archivo = os.path.join(CARPETA_IMAGENES_DOCS, nombre)

    if os.path.exists(ruta_archivo):
        try:
            os.remove(ruta_archivo)
            registrar_log(f"Imagen eliminada de disco: {nombre}", "DELETE")
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": f"Error al eliminar: {str(e)}"}), 500

    return jsonify({"ok": False, "error": "El archivo especificado no existe."}), 404


# ==============================================================================
# SECCIÓN 13: CONFIGURACIÓN, DESBLOQUEO CRÍTICO Y AJUSTES .ENV
# ==============================================================================
@clips_bp.route("/configuracion", methods=["GET", "POST"])
@login_requerido
def configuracion():
    """Panel de administración, telemetría y configuración del entorno .env."""
    desbloqueado = esta_desbloqueado()
    segundos_restantes = max(0, int(session.get("desbloqueo_expira", 0) - time.time())) if desbloqueado else 0

    if request.method == "POST":
        if not desbloqueado:
            flash("La configuración crítica se encuentra bloqueada. Use la Master Key para desbloquearla.", "error")
            return redirect(url_for("clips.configuracion"))

        hubo_cambios_generales = False

        # 1. Contraseña de acceso Web (Comparación de delta estricta para evitar falsos avisos)
        pass_anterior = os.environ.get("APP_PASSWORD", "cambiame").strip()
        nueva_pass = request.form.get("app_password", "").strip()
        if nueva_pass and nueva_pass != pass_anterior:
            set_key(RUTA_ENV, "APP_PASSWORD", nueva_pass)
            os.environ["APP_PASSWORD"] = nueva_pass
            hubo_cambios_generales = True
            registrar_log("Contraseña de acceso web (APP_PASSWORD) actualizada con éxito", "SUCCESS")

        # 2. Host y Puerto
        host_anterior = os.environ.get("HOST", "127.0.0.1").strip()
        nuevo_host = request.form.get("host", "").strip()
        if nuevo_host and nuevo_host != host_anterior:
            set_key(RUTA_ENV, "HOST", nuevo_host)
            os.environ["HOST"] = nuevo_host
            hubo_cambios_generales = True
            registrar_log(f"Interfaz HOST modificada: {nuevo_host}", "SYS")

        port_anterior = os.environ.get("PORT", "5545").strip()
        nuevo_port = request.form.get("port", "").strip()
        if nuevo_port and nuevo_port != port_anterior:
            set_key(RUTA_ENV, "PORT", nuevo_port)
            os.environ["PORT"] = nuevo_port
            hubo_cambios_generales = True
            registrar_log(f"Puerto local del servidor (PORT) modificado: {nuevo_port}", "SYS")

        # 3. Preferencias de arranque y depuración
        log_anterior = os.environ.get("LOG_MODE", "false").strip().lower()
        log_mode = "true" if "log_mode" in request.form else "false"
        if log_mode != log_anterior:
            set_key(RUTA_ENV, "LOG_MODE", log_mode)
            os.environ["LOG_MODE"] = log_mode
            hubo_cambios_generales = True
            registrar_log(f"Modo de registro detallado (LOG_MODE) fijado a: {log_mode}", "SYS")

        auto_anterior = os.environ.get("AUTO_ABRIR_NAVEGADOR", "false").strip().lower()
        auto_abrir = "true" if "auto_abrir_navegador" in request.form else "false"
        if auto_abrir != auto_anterior:
            set_key(RUTA_ENV, "AUTO_ABRIR_NAVEGADOR", auto_abrir)
            os.environ["AUTO_ABRIR_NAVEGADOR"] = auto_abrir
            hubo_cambios_generales = True
            registrar_log(f"Apertura automática de navegador fijada a: {auto_abrir}", "SYS")

        # 4. Parámetros de Sincronización BYOC (E2EE)
        sync_hab_anterior = os.environ.get("SYNC_HABILITADO", "false").strip().lower()
        sync_hab = "true" if "sync_habilitado" in request.form else "false"
        if sync_hab != sync_hab_anterior:
            set_key(RUTA_ENV, "SYNC_HABILITADO", sync_hab)
            os.environ["SYNC_HABILITADO"] = sync_hab
            hubo_cambios_generales = True
            registrar_log(f"Sincronización BYOC {'activada' if sync_hab == 'true' else 'desactivada'}", "SYS")

        carp_anterior = os.environ.get("SYNC_CARPETA", "").strip()
        sync_carp = request.form.get("sync_carpeta", "").strip()
        if sync_carp != carp_anterior:
            if sync_carp:
                try:
                    os.makedirs(sync_carp, exist_ok=True)
                except Exception:
                    pass
            set_key(RUTA_ENV, "SYNC_CARPETA", sync_carp)
            os.environ["SYNC_CARPETA"] = sync_carp
            hubo_cambios_generales = True
            registrar_log(f"Carpeta de sincronización BYOC actualizada: {sync_carp}", "SYS")

        modo_anterior = os.environ.get("SYNC_MODO_CIFRADO", "auto").strip().lower()
        sync_modo = request.form.get("sync_modo_cifrado", "auto").strip().lower()
        if sync_modo in ["auto", "manual", "libre"] and sync_modo != modo_anterior:
            set_key(RUTA_ENV, "SYNC_MODO_CIFRADO", sync_modo)
            os.environ["SYNC_MODO_CIFRADO"] = sync_modo
            hubo_cambios_generales = True
            registrar_log(f"Modo de cifrado BYOC modificado a: {sync_modo.upper()}", "SYS")

        auto_sync_ant = os.environ.get("SYNC_AUTO_APLICAR", "false").strip().lower()
        sync_auto = "true" if "sync_auto_aplicar" in request.form else "false"
        if sync_auto != auto_sync_ant:
            set_key(RUTA_ENV, "SYNC_AUTO_APLICAR", sync_auto)
            os.environ["SYNC_AUTO_APLICAR"] = sync_auto
            hubo_cambios_generales = True
            registrar_log(f"Auto-aplicación de revisiones en arranque fijada a: {sync_auto}", "SYS")

        disp_anterior = os.environ.get("SYNC_NOMBRE_DISPOSITIVO", "").strip()
        sync_disp = request.form.get("sync_nombre_dispositivo", "").strip()
        if sync_disp and sync_disp != disp_anterior:
            set_key(RUTA_ENV, "SYNC_NOMBRE_DISPOSITIVO", sync_disp)
            os.environ["SYNC_NOMBRE_DISPOSITIVO"] = sync_disp
            hubo_cambios_generales = True
            registrar_log(f"Nombre de dispositivo local fijado a: '{sync_disp}'", "SYS")

        # 5. Detección de Rotación Segura de Clave de Cifrado
        clave_anterior = os.environ.get("SYNC_CLAVE", "").strip()
        nueva_clave = request.form.get("sync_clave", "").strip()
        clave_rotada = bool(nueva_clave and nueva_clave != clave_anterior)

        if nueva_clave and nueva_clave != clave_anterior:
            set_key(RUTA_ENV, "SYNC_CLAVE", nueva_clave)
            os.environ["SYNC_CLAVE"] = nueva_clave
            hubo_cambios_generales = True

        rev_form = request.form.get("sync_ultima_revision", "").strip()
        rev_anterior = os.environ.get("SYNC_ULTIMA_REVISION", "0").strip()
        if rev_form.isdigit() and rev_form != rev_anterior:
            ruta_meta_f = os.path.join(sync_carp, "pcm_vault.meta") if sync_carp and os.path.isdir(sync_carp) else None
            existe_meta_fisico = bool(ruta_meta_f and os.path.exists(ruta_meta_f))
            meta_nube = sync_manager.leer_metadatos_remotos(sync_carp) if sync_carp and os.path.isdir(sync_carp) else None

            if not existe_meta_fisico and not meta_nube:
                set_key(RUTA_ENV, "SYNC_ULTIMA_REVISION", rev_form)
                os.environ["SYNC_ULTIMA_REVISION"] = rev_form
                hubo_cambios_generales = True
                registrar_log(f"Contador de revisión local fijado a: #{rev_form}", "SYS")
            else:
                registrar_log("Intento de cambio de revisión ignorado: existe una bóveda activa o archivo .meta en la nube", "WARN")

        # 6. Protocolo de Re-Cifrado Inmediato ante Rotación de Clave
        if clave_rotada and sync_hab == "true" and sync_carp and os.path.isdir(sync_carp):
            registrar_log(f"Iniciando protocolo de rotación de llave en: {sync_carp}", "SYS")
            
            archivos_a_purgar = ["pcm_vault.zip", "pcm_vault.meta", "pcm_vault.prev.zip", "pcm_vault.zip.tmp"]
            for archivo_obsoleto in archivos_a_purgar:
                ruta_obs = os.path.join(sync_carp, archivo_obsoleto)
                if os.path.exists(ruta_obs):
                    try:
                        os.remove(ruta_obs)
                        registrar_log(f"Bóveda obsoleta eliminada: {archivo_obsoleto}", "DELETE")
                    except Exception as e:
                        registrar_log(f"No se pudo eliminar {archivo_obsoleto}: {e}", "ERROR")

            try:
                rev_actual = int(os.environ.get("SYNC_ULTIMA_REVISION", "0").strip()) + 1
            except ValueError:
                rev_actual = 1

            db_path = getattr(database, "DB_PATH", "pcm.db")
            clave_empaque = "" if sync_modo == "libre" else nueva_clave

            registrar_log(f"Empaquetando pcm.db y adjuntos con nueva clave (Revisión #{rev_actual})...", "SYS")
            exito, msg = sync_manager.exportar_boveda_cifrada(
                carpeta_sync=sync_carp,
                ruta_db=db_path,
                carpeta_uploads=CARPETA_IMAGENES_DOCS,
                clave_sync=clave_empaque,
                nombre_equipo=sync_disp or "Dispositivo PCM",
                revision_actual=rev_actual
            )
            if exito:
                set_key(RUTA_ENV, "SYNC_ULTIMA_REVISION", str(rev_actual))
                os.environ["SYNC_ULTIMA_REVISION"] = str(rev_actual)
                registrar_log(f"Nueva bóveda publicada en la nube con éxito (Revisión #{rev_actual})", "SUCCESS")
                flash(f"🔑 Clave rotada con éxito. La bóveda anterior fue eliminada y regenerada con el nuevo cifrado (Revisión #{rev_actual}). Copia la nueva clave en tus otros equipos.", "success")
            else:
                registrar_log(f"Fallo al re-cifrar la bóveda con la nueva clave: {msg}", "ERROR")
                flash(f"⚠ La clave se guardó pero falló el re-cifrado en la nube: {msg}", "error")

        elif hubo_cambios_generales:
            registrar_log("Ajustes del servidor y variables .env actualizadas", "SUCCESS")

        return redirect(url_for("clips.configuracion", guardado=1))

    # ==========================================================================
    # PROCESAMIENTO GET: RECOPILACIÓN DE MÉTRICAS Y TELEMETRÍA
    # ==========================================================================
    registrar_log("Panel de configuración y ajustes del sistema abierto", "INFO")

    # 1. Diagnóstico de Base de Datos SQLite
    total_clips = 0
    total_resumenes = 0
    total_codigo = 0
    total_documentos = 0
    peso_db = "0 KB"

    db_path = getattr(database, "DB_PATH", "pcm.db")
    if os.path.exists(db_path):
        try:
            peso_db = formatear_tamano(os.path.getsize(db_path))
            conn = database.obtener_conexion()
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM clips WHERE tipo = 'clip'")
            total_clips = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM clips WHERE tipo = 'nota'")
            total_resumenes = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM clips WHERE tipo = 'codigo'")
            total_codigo = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM documentos")
            total_documentos = cur.fetchone()[0]
            conn.close()
        except Exception:
            pass

    # 2. Diagnóstico de Almacenamiento Multimedia
    cant_imagenes = 0
    peso_imagenes = "0 KB"
    if os.path.exists(CARPETA_IMAGENES_DOCS):
        try:
            archivos_img = [f for f in os.listdir(CARPETA_IMAGENES_DOCS) if os.path.isfile(os.path.join(CARPETA_IMAGENES_DOCS, f))]
            cant_imagenes = len(archivos_img)
            total_bytes = sum(os.path.getsize(os.path.join(CARPETA_IMAGENES_DOCS, f)) for f in archivos_img)
            peso_imagenes = formatear_tamano(total_bytes)
        except Exception:
            pass

    # 3. Diagnóstico de Sincronización BYOC en Vivo
    sync_hab_val = os.environ.get("SYNC_HABILITADO", "false").strip().lower() == "true"
    sync_carp_val = os.environ.get("SYNC_CARPETA", "").strip()

    try:
        rev_local = int(os.environ.get("SYNC_ULTIMA_REVISION", "0").strip())
    except ValueError:
        rev_local = 0

    meta_remoto = None
    rev_remota = 0
    estado_sync = "desactivado"

    if sync_hab_val and sync_carp_val and os.path.isdir(sync_carp_val):
        ruta_meta_fisica = os.path.join(sync_carp_val, "pcm_vault.meta")
        ruta_zip_fisica = os.path.join(sync_carp_val, "pcm_vault.zip")
        meta_remoto = sync_manager.leer_metadatos_remotos(sync_carp_val)

        if os.path.exists(ruta_meta_fisica) and not meta_remoto:
            estado_sync = "meta_corrupto"
        elif meta_remoto:
            rev_remota = int(meta_remoto.get("revision", 0))
            zip_valido = verificar_integridad_zip_remoto(ruta_zip_fisica, meta_remoto)

            if rev_remota > rev_local:
                estado_sync = "pendiente_descarga" if zip_valido else "zip_corrupto"
            elif rev_remota < rev_local:
                estado_sync = "adelantado_local"
            else:
                estado_sync = "al_dia" if zip_valido else "zip_corrupto"
        else:
            estado_sync = "sin_boveda_remota"
    elif sync_hab_val:
        estado_sync = "carpeta_invalida"

    valores_env = dict(dotenv_values(RUTA_ENV)) if os.path.exists(RUTA_ENV) else {}

    return render_template(
        "config.html",
        valores=valores_env,
        desbloqueo_critico_activo=desbloqueado,
        desbloqueo_segundos_restantes=segundos_restantes,
        total_clips=total_clips,
        total_resumenes=total_resumenes,
        total_codigo=total_codigo,
        total_documentos=total_documentos,
        peso_db=peso_db,
        cant_imagenes=cant_imagenes,
        peso_imagenes=peso_imagenes,
        rev_local=rev_local,
        rev_remota=rev_remota,
        meta_remoto=meta_remoto,
        estado_sync=estado_sync
    )


@clips_bp.route("/configuracion/desbloquear", methods=["POST"])
@login_requerido
def desbloquear_critico():
    clave_ingresada = request.form.get("master_key", "").strip()
    if clave_ingresada and clave_ingresada == os.environ.get("MASTER_KEY"):
        session["desbloqueo_critico"] = True
        session["desbloqueo_expira"] = time.time() + DURACION_DESBLOQUEO
        session["desbloqueo_servidor"] = INICIO_SERVIDOR
        registrar_log("Configuración crítica desbloqueada por 2 minutos con Master Key", "SYS")
        return redirect(url_for("clips.configuracion"))

    registrar_log("Intento fallido de desbloqueo crítico (Master Key incorrecta)", "ERROR")
    return redirect(url_for("clips.configuracion", error_master=1))


@clips_bp.route("/configuracion/bloquear", methods=["POST"])
@login_requerido
def bloquear_critico():
    session.pop("desbloqueo_critico", None)
    registrar_log("Configuración crítica bloqueada manualmente", "SYS")
    return redirect(url_for("clips.configuracion"))


@clips_bp.route("/configuracion/cerrar_sesiones", methods=["POST"])
@login_requerido
def cerrar_sesiones_globales():
    nueva_key = secrets.token_hex(32)
    set_key(RUTA_ENV, "SECRET_KEY", nueva_key)
    os.environ["SECRET_KEY"] = nueva_key
    current_app.secret_key = nueva_key
    
    registrar_log("Cierre de sesión global: SECRET_KEY rotada en memoria y persistida en .env", "SYS")
    session.clear()
    return redirect(url_for("clips.login"))


# ==============================================================================
# SECCIÓN 14: EXPORTACIÓN, IMPORTACIÓN, LIMPIEZA Y SINCRONIZACIÓN BYOC
# ==============================================================================
@clips_bp.route("/configuracion/exportar")
@login_requerido
def exportar_backup():
    """Genera respaldo en JSON (solo base relacional) o en ZIP (JSON + imágenes físicas)."""
    incluir_imagenes = request.args.get("imagenes") == "1"
    conn = database.obtener_conexion()

    filas_clips = conn.execute("SELECT * FROM clips ORDER BY id ASC").fetchall()
    clips = [dict(f) for f in filas_clips]

    filas_docs = conn.execute("SELECT * FROM documentos ORDER BY id ASC").fetchall()
    docs = [dict(f) for f in filas_docs]
    conn.close()

    payload = {
        "metadata": {
            "sistema": "PCMPrivateClipManager",
            "version_schema": VERSION,
            "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_clips": len(clips),
            "total_documentos": len(docs)
        },
        "clips": clips,
        "documentos": docs
    }

    with open(RUTA_ULTIMO_BACKUP, "w", encoding="utf-8") as f:
        f.write(str(time.time()))

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    if incluir_imagenes:
        memoria_zip = io.BytesIO()
        with zipfile.ZipFile(memoria_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("pcm_datos.json", json_bytes)

            if os.path.exists(CARPETA_IMAGENES_DOCS):
                for img_name in os.listdir(CARPETA_IMAGENES_DOCS):
                    ruta_img = os.path.join(CARPETA_IMAGENES_DOCS, img_name)
                    if os.path.isfile(ruta_img):
                        zf.write(ruta_img, arcname=f"imagenes/{img_name}")

        memoria_zip.seek(0)
        nombre_zip = f"pcm_backup_completo_{fecha_str}.zip"
        registrar_log(f"Exportación ZIP completada ({len(clips)} registros + {len(docs)} documentos + imágenes)", "SUCCESS")
        return send_file(memoria_zip, as_attachment=True, download_name=nombre_zip, mimetype="application/zip")

    memoria_json = io.BytesIO(json_bytes)
    nombre_json = f"pcm_backup_texto_{fecha_str}.json"
    registrar_log(f"Exportación JSON completada ({len(clips)} registros + {len(docs)} documentos)", "SUCCESS")
    return send_file(memoria_json, as_attachment=True, download_name=nombre_json, mimetype="application/json")


@clips_bp.route("/configuracion/importar", methods=["POST"])
@login_requerido
def importar_backup():
    """Restaura una instantánea a partir de archivos .json o paquetes .zip."""
    archivo = request.files.get("archivo_backup")
    if not archivo or archivo.filename == "":
        flash("No seleccionaste ningún archivo de respaldo.", "error")
        return redirect(url_for("clips.configuracion"))

    nombre_archivo = archivo.filename.lower()
    if not (nombre_archivo.endswith(".json") or nombre_archivo.endswith(".zip")):
        flash("Formato inválido. Solo se admiten copias .JSON o paquetes .ZIP.", "error")
        return redirect(url_for("clips.configuracion"))

    try:
        os.makedirs(CARPETA_IMAGENES_DOCS, exist_ok=True)
        contenido = None

        if nombre_archivo.endswith(".zip"):
            with zipfile.ZipFile(archivo, "r") as zf:
                json_encontrado = next((n for n in zf.namelist() if n.endswith(".json")), None)
                if not json_encontrado:
                    flash("El archivo ZIP no contiene un archivo de datos JSON válido.", "error")
                    return redirect(url_for("clips.configuracion"))

                contenido = json.loads(zf.read(json_encontrado).decode("utf-8"))

                for item in zf.namelist():
                    if item.startswith("imagenes/") and not item.endswith("/"):
                        nombre_img = os.path.basename(item)
                        ruta_destino = os.path.join(CARPETA_IMAGENES_DOCS, nombre_img)
                        with zf.open(item) as src, open(ruta_destino, "wb") as dst:
                            shutil.copyfileobj(src, dst)
        else:
            contenido = json.loads(archivo.read().decode("utf-8"))

        clips_a_restaurar = contenido.get("clips", [])
        docs_a_restaurar = contenido.get("documentos", [])

        conn = database.obtener_conexion()
        cur = conn.cursor()

        try:
            for c in clips_a_restaurar:
                tipo_clip = c.get("tipo")
                if not tipo_clip:
                    cat = c.get("categoria", "")
                    if cat.startswith("Codigo:"):
                        tipo_clip = "codigo"
                    elif cat in CATEGORIAS_TEXTO_LARGO:
                        tipo_clip = "nota"
                    else:
                        tipo_clip = "clip"

                cur.execute("""
                    INSERT OR REPLACE INTO clips (uuid, titulo, contenido, categoria, tipo, fecha_creacion, expira_en, vistas_restantes, es_favorito)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c.get("uuid") or str(uuid.uuid4())[:8],
                    c.get("titulo", ""),
                    c.get("contenido", ""),
                    c.get("categoria", "General"),
                    tipo_clip,
                    c.get("fecha_creacion", int(time.time())),
                    c.get("expira_en"),
                    c.get("vistas_restantes", -1),
                    c.get("es_favorito", 0)
                ))

            for d in docs_a_restaurar:
                cur.execute("""
                    INSERT OR REPLACE INTO documentos (id, titulo, contenido, creado_en, actualizado_en)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    d.get("id"),
                    d.get("titulo", "Sin título"),
                    d.get("contenido", ""),
                    d.get("creado_en", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    d.get("actualizado_en", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                ))

            conn.commit()
        finally:
            conn.close()

        registrar_log(f"Restauración exitosa: {len(clips_a_restaurar)} elementos clasificados y {len(docs_a_restaurar)} documentos", "SUCCESS")
        flash(f"Restauración completada con éxito: {len(clips_a_restaurar)} clips/notas/códigos y {len(docs_a_restaurar)} documentos.", "success")
        return redirect(url_for("clips.configuracion", guardado=1))

    except Exception as e:
        registrar_log(f"Error crítico durante la restauración de copia: {str(e)}", "ERROR")
        flash(f"Fallo al procesar el archivo de backup: {e}", "error")
        return redirect(url_for("clips.configuracion"))


@clips_bp.route("/configuracion/sync/subir", methods=["POST"])
@login_requerido
def sync_subir_boveda():
    """Empaqueta y exporta la base de datos y adjuntos hacia la carpeta de nube configurada."""
    carpeta_sync = os.environ.get("SYNC_CARPETA", "").strip()
    if not carpeta_sync or not os.path.isdir(carpeta_sync):
        flash("La carpeta de sincronización no está configurada o no es accesible.", "error")
        return redirect(url_for("clips.configuracion"))

    ruta_meta_fisica = os.path.join(carpeta_sync, "pcm_vault.meta")
    meta_remoto = sync_manager.leer_metadatos_remotos(carpeta_sync)

    if os.path.exists(ruta_meta_fisica) and not meta_remoto:
        registrar_log("Subida bloqueada: 'pcm_vault.meta' corrupto en la nube", "ERROR")
        flash("⛔ Subida bloqueada por seguridad: Se detectó un archivo 'pcm_vault.meta' corrupto en la nube. Repare o limpie la carpeta remota para evitar sobreescribir datos accidentalmente.", "error")
        return redirect(url_for("clips.configuracion"))

    registrar_log(f"Iniciando empaquetado de bóveda hacia: {carpeta_sync}", "SYS")

    try:
        rev_local = int(os.environ.get("SYNC_ULTIMA_REVISION", "0").strip())
    except ValueError:
        rev_local = 0

    if meta_remoto:
        rev_remota = int(meta_remoto.get("revision", 0))
        if rev_remota > rev_local:
            equipo_nube = meta_remoto.get("ultimo_equipo", "otro dispositivo")
            registrar_log(f"Subida rechazada: Conflicto detectado (Local #{rev_local} < Nube #{rev_remota} de {equipo_nube})", "WARN")
            flash(
                f"⛔ Subida bloqueada por seguridad: La nube tiene una versión más reciente "
                f"(#{rev_remota} subida por '{equipo_nube}'). Debes 'Descargar y Aplicar Cambios' "
                f"antes de poder subir datos nuevos.", 
                "error"
            )
            return redirect(url_for("clips.configuracion"))

    nueva_rev = rev_local + 1
    modo_cif = os.environ.get("SYNC_MODO_CIFRADO", "auto").strip().lower()
    clave = "" if modo_cif == "libre" else os.environ.get("SYNC_CLAVE", "").strip()
    nombre_disp = os.environ.get("SYNC_NOMBRE_DISPOSITIVO", "Dispositivo PCM").strip()
    db_path = getattr(database, "DB_PATH", "pcm.db")

    registrar_log(f"Empaquetando pcm.db y adjuntos con AES-256 (Revisión #{nueva_rev})...", "SYS")
    exito, msg = sync_manager.exportar_boveda_cifrada(
        carpeta_sync=carpeta_sync,
        ruta_db=db_path,
        carpeta_uploads=CARPETA_IMAGENES_DOCS,
        clave_sync=clave,
        nombre_equipo=nombre_disp,
        revision_actual=nueva_rev
    )

    if exito:
        with open(RUTA_ULTIMO_SYNC, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
        set_key(RUTA_ENV, "SYNC_ULTIMA_REVISION", str(nueva_rev))
        os.environ["SYNC_ULTIMA_REVISION"] = str(nueva_rev)
        registrar_log(f"Bóveda sincronizada a la nube con éxito (Revisión #{nueva_rev})", "SUCCESS")
        flash(f"Bóveda subida exitosamente a la carpeta compartida (Revisión #{nueva_rev}).", "success")
    else:
        registrar_log(f"Fallo al sincronizar bóveda a la nube: {msg}", "ERROR")
        flash(f"Error al exportar la bóveda: {msg}", "error")

    return redirect(url_for("clips.configuracion"))


@clips_bp.route("/configuracion/sync/descargar", methods=["POST"])
@login_requerido
def sync_descargar_boveda():
    """Descarga, valida integridad criptográfica y restaura la bóveda desde la nube."""
    carpeta_sync = os.environ.get("SYNC_CARPETA", "").strip()
    if not carpeta_sync or not os.path.isdir(carpeta_sync):
        flash("La carpeta de sincronización no está configurada o no es accesible.", "error")
        return redirect(url_for("clips.configuracion"))

    ruta_meta_fisica = os.path.join(carpeta_sync, "pcm_vault.meta")
    meta_remoto = sync_manager.leer_metadatos_remotos(carpeta_sync)

    if os.path.exists(ruta_meta_fisica) and not meta_remoto:
        registrar_log("Descarga abortada: 'pcm_vault.meta' corrupto en la nube", "ERROR")
        flash("El archivo de metadatos (.meta) en la nube está corrupto o ilegible. Operación abortada por seguridad.", "error")
        return redirect(url_for("clips.configuracion"))

    if not meta_remoto:
        flash("No se encontró ningún archivo de metadatos (.meta) en la carpeta de nube.", "error")
        return redirect(url_for("clips.configuracion"))

    modo_cif = os.environ.get("SYNC_MODO_CIFRADO", "auto").strip().lower()
    clave = "" if modo_cif == "libre" else os.environ.get("SYNC_CLAVE", "").strip()
    db_path = getattr(database, "DB_PATH", "pcm.db")

    registrar_log(f"Validando integridad SHA-256 e importando bóveda desde: {carpeta_sync}", "SYS")

    exito, msg = sync_manager.importar_boveda_cifrada(
        carpeta_sync=carpeta_sync,
        ruta_db_destino=db_path,
        carpeta_uploads_destino=CARPETA_IMAGENES_DOCS,
        clave_sync=clave
    )

    if exito:
        with open(RUTA_ULTIMO_SYNC, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
        rev_remota = str(meta_remoto.get("revision", 1))
        set_key(RUTA_ENV, "SYNC_ULTIMA_REVISION", rev_remota)
        os.environ["SYNC_ULTIMA_REVISION"] = rev_remota
        registrar_log(f"Bóveda importada desde la nube con éxito (Revisión #{rev_remota})", "SUCCESS")
        flash(f"Bóveda restaurada con éxito: {msg}", "success")
    else:
        registrar_log(f"Fallo al restaurar bóveda desde la nube: {msg}", "ERROR")
        flash(f"Error en la sincronización: {msg}", "error")

    return redirect(url_for("clips.configuracion"))


@clips_bp.route("/configuracion/sync/estado", methods=["GET"])
@login_requerido
def sync_consultar_estado():
    """Endpoint JSON para sondeo dinámico y verificación de estado desde la UI."""
    carpeta_sync = os.environ.get("SYNC_CARPETA", "").strip()
    sync_habilitado = os.environ.get("SYNC_HABILITADO", "false").lower() == "true"

    if not sync_habilitado or not carpeta_sync or not os.path.isdir(carpeta_sync):
        return jsonify({
            "habilitado": sync_habilitado,
            "carpeta_valida": bool(carpeta_sync and os.path.isdir(carpeta_sync)),
            "hay_boveda": False,
            "estado": "desconectado"
        })

    ruta_meta_fisica = os.path.join(carpeta_sync, "pcm_vault.meta")
    ruta_zip_fisica = os.path.join(carpeta_sync, "pcm_vault.zip")
    meta = sync_manager.leer_metadatos_remotos(carpeta_sync)

    try:
        rev_local = int(os.environ.get("SYNC_ULTIMA_REVISION", "0").strip())
    except ValueError:
        rev_local = 0

    if os.path.exists(ruta_meta_fisica) and not meta:
        registrar_log(f"Comprobación de nube: Archivo .meta corrupto en '{carpeta_sync}'", "ERROR")
        return jsonify({
            "habilitado": True,
            "carpeta_valida": True,
            "hay_boveda": False,
            "meta_corrupto": True,
            "rev_local": rev_local,
            "estado": "meta_corrupto"
        })

    if not meta:
        registrar_log(f"Comprobación de nube: Carpeta activa sin bóveda remota (Local: #{rev_local})", "SYS")
        return jsonify({
            "habilitado": True,
            "carpeta_valida": True,
            "hay_boveda": False,
            "meta_corrupto": False,
            "rev_local": rev_local,
            "estado": "sin_boveda_remota"
        })

    rev_remota = int(meta.get("revision", 0))
    equipo_remoto = meta.get("ultimo_equipo", "Desconocido")
    zip_valido = verificar_integridad_zip_remoto(ruta_zip_fisica, meta)

    estado = "al_dia"
    if rev_remota > rev_local:
        estado = "pendiente_descarga" if zip_valido else "zip_corrupto"
    elif rev_local > rev_remota:
        estado = "adelantado_local"
    elif not zip_valido:
        estado = "zip_corrupto"

    registrar_log(f"Comprobación de nube: Local #{rev_local} vs Nube #{rev_remota} [{equipo_remoto}] -> Estado: {estado}", "SYS")

    return jsonify({
        "habilitado": True,
        "carpeta_valida": True,
        "hay_boveda": True,
        "meta_corrupto": False,
        "rev_local": rev_local,
        "rev_remota": rev_remota,
        "ultimo_equipo": equipo_remoto,
        "timestamp": meta.get("timestamp", 0),
        "estado": estado
    })


@clips_bp.route("/configuracion/borrar_todo", methods=["POST"])
@login_requerido
def borrar_todo():
    if not esta_desbloqueado():
        return redirect(url_for("clips.configuracion"))

    conn = database.obtener_conexion()
    try:
        conn.execute("DELETE FROM clips")
        conn.execute("DELETE FROM documentos")
        conn.commit()
    finally:
        conn.close()

    registrar_log("Vaciado total de base de datos ejecutado con éxito", "DELETE")
    return redirect(url_for("clips.configuracion", guardado=1))


@clips_bp.route("/configuracion/purgar_imagenes", methods=["POST"])
@login_requerido
def purgar_imagenes_huerfanas():
    conn = database.obtener_conexion()
    try:
        docs = conn.execute("SELECT contenido FROM documentos").fetchall()
        clips = conn.execute("SELECT contenido FROM clips").fetchall()
    finally:
        conn.close()

    todo_el_texto = " ".join([(d["contenido"] or "") for d in docs] + [(c["contenido"] or "") for c in clips])

    purgadas = 0
    bytes_liberados = 0

    if os.path.exists(CARPETA_IMAGENES_DOCS):
        for archivo in os.listdir(CARPETA_IMAGENES_DOCS):
            ruta = os.path.join(CARPETA_IMAGENES_DOCS, archivo)
            if os.path.isfile(ruta):
                if archivo not in todo_el_texto:
                    try:
                        tam = os.path.getsize(ruta)
                        os.remove(ruta)
                        purgadas += 1
                        bytes_liberados += tam
                        registrar_log(f"Imagen huérfana eliminada: {archivo}", "DELETE")
                    except Exception as e:
                        registrar_log(f"Error al purgar archivo huérfano {archivo}: {e}", "ERROR")

    liberado_str = formatear_tamano(bytes_liberados)
    if purgadas > 0:
        registrar_log(f"Purga multimedia completada: {purgadas} archivos eliminados ({liberado_str} liberados)", "SUCCESS")
        flash(f"Limpieza completada: se eliminaron {purgadas} imágenes huérfanas liberando {liberado_str}.", "info")
    else:
        registrar_log("Purga multimedia ejecutada: no se detectaron archivos huérfanos", "INFO")
        flash("El almacenamiento está optimizado: no se encontraron imágenes huérfanas.", "info")

    return redirect(url_for("clips.configuracion"))


def seleccionar_carpeta_nativa():
    """Abre el explorador de directorios nativo del sistema operativo de forma resiliente."""
    if sys.platform == "win32":
        try:
            ps_script = (
                "[System.Reflection.Assembly]::LoadWithPartialName('System.windows.forms') | Out-Null; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "$f.Description = 'Selecciona la carpeta base de tu Nube (MEGA, Drive, Dropbox, Pendrive...)'; "
                "$f.ShowNewFolderButton = $true; "
                "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }"
            )
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
            salida = res.stdout.strip()
            if salida and os.path.isdir(salida):
                return os.path.normpath(salida)
        except Exception:
            pass

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        ruta = filedialog.askdirectory(title="Selecciona la carpeta base de tu Nube")
        root.destroy()
        if ruta and os.path.isdir(ruta):
            return os.path.normpath(ruta)
    except Exception:
        pass

    if sys.platform.startswith("linux"):
        try:
            res = subprocess.run(["zenity", "--file-selection", "--directory", "--title=Selecciona la carpeta de tu Nube"], capture_output=True, text=True)
            salida = res.stdout.strip()
            if salida and os.path.isdir(salida):
                return os.path.normpath(salida)
        except Exception:
            pass

    return None


@clips_bp.route("/configuracion/sync/explorar_carpeta", methods=["POST"])
@login_requerido
def sync_explorar_carpeta():
    """Abre el selector de carpetas del SO y genera automáticamente la subcarpeta PCM_Sync."""
    if not esta_desbloqueado():
        return jsonify({"ok": False, "error": "Debes desbloquear la configuración crítica con tu Master Key primero."}), 403

    ruta_base = seleccionar_carpeta_nativa()
    if not ruta_base:
        return jsonify({"ok": False, "cancelado": True})

    nombre_carpeta = os.path.basename(ruta_base.rstrip("/\\"))
    if nombre_carpeta.lower() != "pcm_sync":
        ruta_final = os.path.join(ruta_base, "PCM_Sync")
    else:
        ruta_final = ruta_base

    try:
        os.makedirs(ruta_final, exist_ok=True)
        registrar_log(f"Carpeta de sincronización BYOC provisionada: {ruta_final}", "SYS")
        return jsonify({
            "ok": True,
            "ruta": ruta_final,
            "creada": True
        })
    except Exception as e:
        registrar_log(f"Fallo al provisionar carpeta BYOC en '{ruta_final}': {e}", "ERROR")
        return jsonify({"ok": False, "error": f"No se pudo crear la carpeta en la ruta seleccionada: {str(e)}"}), 500