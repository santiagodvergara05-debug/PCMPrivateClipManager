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
6. Diagnóstico y mantenimiento del sistema de archivos y base de datos SQLite.
==============================================================================
"""

import os
import io
import json
import time
import secrets
import shutil
import zipfile
import uuid
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
from version import VERSION

# Instanciación del Blueprint principal
clips_bp = Blueprint("clips", __name__)

# ==============================================================================
# CONFIGURACIONES Y CONSTANTES DE OPERACIÓN
# ==============================================================================
# Token volátil generado en RAM cada vez que arranca Flask. Invalida desbloqueos previos.
INICIO_SERVIDOR = secrets.token_hex(8)

# Tiempo de gracia (en segundos) para modificar configuraciones maestras/críticas
DURACION_DESBLOQUEO = 120  # 2 minutos

# Rutas locales de configuración y auditoría
RUTA_ENV = ".env"
RUTA_ULTIMO_BACKUP = "ultimo_backup.txt"

# Clasificación de categorías que usan la vista extendida de novela/borrador
CATEGORIAS_TEXTO_LARGO = ("Nota", "Borrador", "Resumen", "Apuntes", "Texto Plano", "Novelas")

# Directorio de almacenamiento para imágenes asociadas a documentos Markdown
CARPETA_IMAGENES_DOCS = os.path.join("static", "uploads", "documentos")

# Límite estricto de archivo individual para subidas multimedia (25 MiB)
LIMITE_MB_IMAGEN = 25
MAX_BYTES_IMAGEN = LIMITE_MB_IMAGEN * 1024 * 1024  # 26,214,400 bytes

# Extensiones autorizadas por nomenclatura
EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "gif", "webp"}

# Firmas binarias estándar (Magic Bytes) para validación real contra exploits
CABECERAS_MAGICAS = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp"  # WebP inicia con RIFF y lleva WEBP en el offset 8
}


# ==============================================================================
# SECCIÓN 1: UTILIDADES DE SISTEMA, AUDITORÍA Y REGISTRO EN TERMINAL
# ==============================================================================

# Paleta ANSI de alta visibilidad para terminales modernas (Dark Theme)
CLR_RESET   = "\033[0m"
CLR_GRIS    = "\033[90m"
CLR_AZUL    = "\033[94m"
CLR_CYAN    = "\033[96m"
CLR_VERDE   = "\033[92m"
CLR_AMARILLO= "\033[93m"
CLR_ROJO    = "\033[91m"
CLR_MAGENTA = "\033[95m"
CLR_BOLD    = "\033[1m"

def registrar_log(accion, tipo=None):
    """
    Imprime eventos en consola con formato enriquecido, marcas temporales 
    e insignias coloreadas según la criticidad del evento.
    """
    if os.environ.get("LOG_MODE", "true").lower() != "true":
        return

    hora = datetime.now().strftime("%H:%M:%S")
    accion_lower = accion.lower()

    # 1. Alertas y Errores Críticos
    if tipo == "ERROR" or any(k in accion_lower for k in ["error", "fallid", "rechazad", "peligro", "no autorizada"]):
        badge = f"{CLR_BOLD}{CLR_ROJO}✖ [PCM :: ALERTA]{CLR_RESET}"
        texto_formateado = f"{CLR_ROJO}{accion}{CLR_RESET}"

    # 2. Creación, Guardado y Actualización (Se evalúa primero para capturar notas y borradores)
    elif tipo == "SUCCESS" or any(k in accion_lower for k in ["éxito", "exitos", "cread", "guardad", "actualizad", "iniciad"]):
        badge = f"{CLR_BOLD}{CLR_VERDE}✔ [PCM :: ÉXITO]{CLR_RESET}"
        texto_formateado = f"{CLR_VERDE}{accion}{CLR_RESET}"

    # 3. Eliminaciones (Usa estrictamente la raíz 'elimin' para no colisionar con 'Borrador')
    elif tipo == "DELETE" or any(k in accion_lower for k in ["elimin", "purgada", "vaciado total"]):
        badge = f"{CLR_BOLD}{CLR_MAGENTA}🗑 [PCM :: DELETE]{CLR_RESET}"
        texto_formateado = f"{CLR_MAGENTA}{accion}{CLR_RESET}"

    # 4. Operaciones de Sistema, Llaves y Sesiones
    elif tipo == "SYS" or any(k in accion_lower for k in ["desbloque", "bloque", "sesión", "rotad", "crític"]):
        badge = f"{CLR_BOLD}{CLR_AMARILLO}⚡ [PCM :: SYS]{CLR_RESET}"
        texto_formateado = f"{CLR_AMARILLO}{accion}{CLR_RESET}"

    # 5. Información general
    else:
        badge = f"{CLR_BOLD}{CLR_CYAN}ℹ [PCM :: INFO]{CLR_RESET}"
        texto_formateado = f"{CLR_CYAN}{accion}{CLR_RESET}"

    # Salida por consola formateada
    print(f"{CLR_GRIS}[{hora}]{CLR_RESET} {badge} {texto_formateado}") 


def esta_desbloqueado():
    """Valida si la sesión actual posee autorización para ejecutar acciones críticas en ajustes."""
    if not session.get("desbloqueo_critico"):
        return False
    # Si el servidor se reinició, el token volátil no coincidirá -> sesión invalidada
    if session.get("desbloqueo_servidor") != INICIO_SERVIDOR:
        session.pop("desbloqueo_critico", None)
        return False
    # Verificación de tiempo de expiración
    if time.time() > session.get("desbloqueo_expira", 0):
        session.pop("desbloqueo_critico", None)
        return False
    return True


def login_requerido(f):
    """Decorador para proteger rutas contra accesos no autenticados en la red LAN."""
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get("autenticado"):
            # Si alguien intenta modificar estado (POST/PUT/DELETE) sin estar autenticado
            if request.method in ["POST", "PUT", "DELETE"]:
                ip = request.remote_addr
                print(f"\n\033[91m[SEGURIDAD :: PETICIÓN NO AUTORIZADA]\033[0m Intento de llamada {request.method} sin sesión a '{request.path}' desde IP: {ip}")
                if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"ok": False, "error": "Sesión no válida o expirada."}), 401

            return redirect(url_for("clips.login"))
        return f(*args, **kwargs)
    return decorador


def extension_valida(nombre_archivo):
    """Verifica sintácticamente la extensión del archivo según la lista permitida."""
    return "." in nombre_archivo and nombre_archivo.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS


def validar_firma_binaria_imagen(stream):
    """
    Inspecciona la cabecera binaria del flujo de datos (Magic Bytes).
    Evita ataques de inyección donde se camuflan ejecutables con extensión .png.
    """
    posicion_original = stream.tell()
    stream.seek(0)
    cabecera = stream.read(32)
    stream.seek(posicion_original)  # Restablece el puntero de lectura para poder guardarlo luego

    for firma, ext in CABECERAS_MAGICAS.items():
        if cabecera.startswith(firma):
            if firma == b"RIFF" and b"WEBP" not in cabecera[:16]:
                continue
            return ext
    return None


def formatear_tamano(bytes_cant):
    """Convierte una cantidad de bytes a una cadena amigable legible para humanos (B, KB, MB)."""
    if bytes_cant < 1024:
        return f"{bytes_cant} B"
    elif bytes_cant < 1024 * 1024:
        return f"{bytes_cant / 1024:.1f} KB"
    else:
        return f"{bytes_cant / (1024 * 1024):.2f} MB"


@clips_bp.app_context_processor
def inyectar_contexto():
    """Inyecta variables globales en todos los templates HTML renderizados."""
    return {
        "app_version": VERSION
    }


# ==============================================================================
# SECCIÓN 2: CONTROL DE ACCESO Y AUTENTICACIÓN
# ==============================================================================

@clips_bp.route("/login", methods=["GET", "POST"])
def login():
    # Si el usuario ya está autenticado, va directo al panel principal
    if session.get("autenticado"):
        return redirect(url_for("clips.index"))

    # Verifica si es el primer inicio ('false' muestra el cartel, 'true' lo oculta)
    mostrar_credenciales = os.environ.get("CONTRASENA_MOSTRADA", "false").strip().lower() != "true"
    error = None

    if request.method == "POST":
        password_ingresada = request.form.get("password", "").strip()
        app_password = os.environ.get("APP_PASSWORD", "cambiame").strip()
        master_key = os.environ.get("MASTER_KEY", "").strip()

        # Validación contra APP_PASSWORD o MASTER_KEY
        if password_ingresada and (password_ingresada == app_password or (master_key and password_ingresada == master_key)):
            session["autenticado"] = True
            session.permanent = True

            try:
                registrar_log(f"Inicio de sesión exitoso desde {request.remote_addr}")
            except Exception:
                pass

            # Si era el primer inicio, muta el .env a true para ocultar credenciales a futuro
            if mostrar_credenciales:
                try:
                    set_key(RUTA_ENV, "CONTRASENA_MOSTRADA", "true")
                    os.environ["CONTRASENA_MOSTRADA"] = "true"
                    try:
                        registrar_log("Primer inicio detectado: aviso de credenciales ocultado permanentemente")
                    except Exception:
                        pass
                except Exception as e:
                    print(f"Error actualizando RUTA_ENV: {e}")

            return redirect(url_for("clips.index"))
        else:
            error = "Contraseña incorrecta. Inténtalo de nuevo."
            try:
                registrar_log(f"Intento fallido de inicio de sesión desde {request.remote_addr}")
            except Exception:
                pass

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
    """Limpia las variables de sesión y redirige a la pantalla de login."""
    session.clear()
    registrar_log("Cierre de sesión manual ejecutado")
    return redirect(url_for("clips.login"))


# ==============================================================================
# SECCIÓN 3: CLIPS RÁPIDOS Y PORTAPAPELES
# ==============================================================================

@clips_bp.route("/")
@login_requerido
def index():
    """Panel principal: lista clips activos y depura los que hayan caducado."""
    database.purgar_expirados()
    conn = database.obtener_conexion()

    # Obtener clips excluyendo categorías que tienen módulos propios
    clips = conn.execute("""
        SELECT * FROM clips 
        WHERE categoria NOT IN ('Novelas', 'Borrador', 'Resumen') 
          AND categoria NOT LIKE 'Codigo:%' 
        ORDER BY es_favorito DESC, id DESC
    """).fetchall()

    # Listado dinámico de etiquetas/categorías creadas
    categorias_raw = conn.execute("""
        SELECT DISTINCT categoria 
        FROM clips 
        WHERE categoria NOT IN ('Novelas', 'Borrador', 'Resumen') 
          AND categoria NOT LIKE 'Codigo:%' 
          AND TRIM(categoria) != '' 
        ORDER BY categoria COLLATE NOCASE ASC
    """).fetchall()
    categorias = [r["categoria"] for r in categorias_raw]

    conn.close()
    return render_template("index.html", clips=clips, categorias=categorias)


@clips_bp.route("/crear", methods=["POST"])
@login_requerido
def crear():
    """Crea un nuevo clip rápido con tiempo de autodestrucción opcional."""
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
            INSERT INTO clips (uuid, titulo, contenido, categoria, fecha_creacion, expira_en, vistas_restantes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (clip_uuid, titulo, contenido, categoria, ahora, expira_en, vistas))
        conn.commit()
        conn.close()
        registrar_log(f"Clip creado: [{categoria}] '{titulo or 'Sin título'}'")

    return redirect(url_for("clips.index"))


@clips_bp.route("/favorito/<int:clip_id>", methods=["POST"])
@login_requerido
def alternar_favorito(clip_id):
    """Fija o desfija un clip al inicio de la bandeja."""
    conn = database.obtener_conexion()
    clip = conn.execute("SELECT es_favorito, titulo FROM clips WHERE id = ?", (clip_id,)).fetchone()

    if clip:
        nuevo_estado = 0 if clip["es_favorito"] == 1 else 1
        conn.execute("UPDATE clips SET es_favorito = ? WHERE id = ?", (nuevo_estado, clip_id))
        conn.commit()
        accion = "fijado en favoritos" if nuevo_estado == 1 else "removido de favoritos"
        registrar_log(f"Clip '{clip['titulo'] or clip_id}' {accion}")

    conn.close()
    return redirect(url_for("clips.index"))


@clips_bp.route("/editar/<int:clip_id>", methods=["POST"])
@login_requerido
def editar_clip(clip_id):
    """Actualiza la información, contenido o temporizador de un clip."""
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
        registrar_log(f"Clip modificado: [{categoria}] '{titulo or clip_id}'")

    return redirect(url_for("clips.index"))


@clips_bp.route("/eliminar/<int:clip_id>", methods=["GET", "POST", "DELETE"])
@login_requerido
def eliminar(clip_id):
    """Elimina clips de cualquier categoría soportando llamadas estándar y fetch/AJAX."""
    conn = database.obtener_conexion()
    clip = conn.execute("SELECT categoria, titulo FROM clips WHERE id = ?", (clip_id,)).fetchone()
    es_texto_largo = clip and clip["categoria"] in CATEGORIAS_TEXTO_LARGO
    es_codigo = clip and clip["categoria"].startswith("Codigo:")
    titulo = clip["titulo"] if clip else str(clip_id)

    conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
    conn.commit()
    conn.close()
    registrar_log(f"Registro eliminado: '{titulo}'")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"ok": True, "id": clip_id})

    if es_texto_largo:
        return redirect(url_for("clips.biblioteca_novelas"))
    if es_codigo:
        return redirect(url_for("clips.seccion_codigo"))
    return redirect(url_for("clips.index"))


# ==============================================
# SECCIÓN 4: MÓDULO DE BORRADORES Y RESÚMENES
# ==============================================

@clips_bp.route("/notas")
@login_requerido
def biblioteca_novelas():
    """Muestra el catálogo de textos extensos (5 categorías)."""
    conn = database.obtener_conexion()
    resumenes = conn.execute("""
        SELECT * FROM clips 
        WHERE categoria IN ('Nota', 'Borrador', 'Resumen', 'Apuntes', 'Texto Plano', 'Novelas') 
        ORDER BY id DESC
    """).fetchall()
    conn.close()
    return render_template("notas.html", resumenes=resumenes)


@clips_bp.route("/editor")
@clips_bp.route("/editor/<int:clip_id>")
@login_requerido
def editor(clip_id=None):
    """Carga la interfaz del editor simple de notas/borradores."""
    clip = None
    if clip_id:
        conn = database.obtener_conexion()
        clip = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        conn.close()
    return render_template("editor.html", clip=clip)


@clips_bp.route("/guardar_resumen", methods=["POST"])
@login_requerido
def guardar_resumen():
    """Persiste los cambios del editor simple de borradores."""
    clip_id = request.form.get("clip_id")
    titulo = request.form.get("titulo", "").strip() or "Texto sin título"
    tipo_doc = request.form.get("tipo_doc", "Borrador").strip()
    # Permitir las 5 categorías válidas
    categorias_permitidas = ["Nota", "Borrador", "Resumen", "Apuntes", "Texto Plano"]
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
            SET titulo = ?, contenido = ?, categoria = ? 
            WHERE id = ?
        """, (titulo, contenido, tipo_doc, clip_id))
        registrar_log(f"Nota actualizada [{tipo_doc}]: '{titulo}'")
    else:
        clip_uuid = str(uuid.uuid4())[:8]
        conn.execute("""
            INSERT INTO clips (uuid, titulo, contenido, categoria, fecha_creacion, expira_en, vistas_restantes)
            VALUES (?, ?, ?, ?, ?, NULL, -1)
        """, (clip_uuid, titulo, contenido, tipo_doc, ahora))
        registrar_log(f"Nueva nota guardada [{tipo_doc}]: '{titulo}'")

    conn.commit()
    conn.close()
    return redirect(url_for("clips.biblioteca_novelas"))


# ==============================================================================
# SECCIÓN 5: SNIPPETS DE CÓDIGO Y SINTAXIS
# ==============================================================================

@clips_bp.route("/codigo")
@login_requerido
def seccion_codigo():
    """Biblioteca especializada en fragmentos de código ordenados por lenguaje."""
    conn = database.obtener_conexion()
    snippets = conn.execute(
        "SELECT * FROM clips WHERE categoria LIKE 'Codigo:%' ORDER BY id DESC"
    ).fetchall()

    lenguajes_raw = conn.execute("""
        SELECT DISTINCT categoria FROM clips 
        WHERE categoria LIKE 'Codigo:%' 
        ORDER BY categoria ASC
    """).fetchall()
    lenguajes = [r["categoria"].replace("Codigo:", "") for r in lenguajes_raw]

    conn.close()
    return render_template("codigo.html", snippets=snippets, lenguajes_disponibles=lenguajes)


@clips_bp.route("/codigo/nuevo")
@login_requerido
def nuevo_codigo():
    """Abre el formulario para añadir un nuevo snippet de código."""
    return render_template("agregar_codigo.html")


@clips_bp.route("/codigo/guardar", methods=["POST"])
@login_requerido
def guardar_codigo():
    """Registra un nuevo snippet de programación asociando el prefijo de lenguaje."""
    titulo = request.form.get("titulo", "").strip() or "Snippet sin título"
    lenguaje = request.form.get("lenguaje", "Texto").strip()
    contenido = request.form.get("contenido", "").strip()

    if contenido:
        categoria_codigo = f"Codigo:{lenguaje}"
        clip_uuid = str(uuid.uuid4())[:8]
        ahora = int(time.time())

        conn = database.obtener_conexion()
        conn.execute("""
            INSERT INTO clips (uuid, titulo, contenido, categoria, fecha_creacion, expira_en, vistas_restantes)
            VALUES (?, ?, ?, ?, ?, NULL, -1)
        """, (clip_uuid, titulo, contenido, categoria_codigo, ahora))
        conn.commit()
        conn.close()
        registrar_log(f"Snippet guardado: [{lenguaje}] '{titulo}'")

    return redirect(url_for("clips.seccion_codigo"))


@clips_bp.route("/codigo/editar/<int:clip_id>", methods=["POST"])
@login_requerido
def editar_codigo(clip_id):
    """Actualiza el lenguaje, título o contenido de un snippet."""
    titulo = request.form.get("titulo", "").strip() or "Snippet sin título"
    lenguaje = request.form.get("lenguaje", "Texto").strip()
    contenido = request.form.get("contenido", "").strip()

    if contenido:
        categoria_codigo = f"Codigo:{lenguaje}"
        conn = database.obtener_conexion()
        conn.execute("""
            UPDATE clips 
            SET titulo = ?, categoria = ?, contenido = ?
            WHERE id = ?
        """, (titulo, categoria_codigo, contenido, clip_id))
        conn.commit()
        conn.close()
        registrar_log(f"Snippet actualizado: [{lenguaje}] '{titulo}'")

    return redirect(url_for("clips.seccion_codigo"))


# ==============================================================================
# SECCIÓN 6: HERRAMIENTAS ADICIONALES (FUSIONADOR)
# ==============================================================================

@clips_bp.route("/fusionador")
@login_requerido
def fusionador():
    """Herramienta para concatenar prompts y formatear textos combinados."""
    registrar_log("Herramienta Fusionador de textos abierta")
    return render_template("fusionador.html")


# ==============================================================================
# SECCIÓN 7: GESTOR DE DOCUMENTOS TÉCNICOS (MARKDOWN, LATEX & MERMAID)
# ==============================================================================

@clips_bp.route("/documentos")
@login_requerido
def documentos():
    """Hub central: lista la biblioteca de documentos técnicos guardados."""
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
    """Abre el editor profesional (documentos.html) en blanco."""
    return render_template("documentos.html", doc=None)


@clips_bp.route("/documentos/estudio/<int:doc_id>")
@login_requerido
def documentos_editar(doc_id):
    """Carga un documento persistido en el editor para su modificación."""
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

    # ---> REGISTRO EN CONSOLA:
    registrar_log(accion_desc)

    return jsonify({"ok": True, "id": nuevo_id, "titulo": titulo})


@clips_bp.route("/documentos/eliminar/<int:doc_id>", methods=["POST"])
@login_requerido
def eliminar_documento(doc_id):
    """Elimina permanentemente un documento de la tabla 'documentos'."""
    conn = database.obtener_conexion()
    cursor = conn.cursor()

    # Obtener el título antes de borrarlo para registrarlo en el log
    cursor.execute("SELECT titulo FROM documentos WHERE id = ?", (doc_id,))
    doc = cursor.fetchone()
    titulo_doc = doc["titulo"] if doc else f"ID #{doc_id}"

    cursor.execute("DELETE FROM documentos WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

    # ---> REGISTRO EN CONSOLA:
    registrar_log(f"Documento eliminado: '{titulo_doc}'")

    flash("Documento eliminado correctamente.", "info")
    return redirect(url_for("clips.documentos"))


# ==============================================================================
# SECCIÓN 8: GESTOR MULTIMEDIA BLINDADO (SUBIDA, AUDITORÍA & BORRADO)
# ==============================================================================

@clips_bp.route("/documentos/api/subir_imagen", methods=["POST"])
@login_requerido
def api_subir_imagen_documento():
    """
    Sube una imagen al servidor aplicando validación en capas:
    1. Existencia y nombre válido.
    2. Límite físico en stream (<= 25 MiB).
    3. Extensión declarada válida.
    4. Inspección binaria de Magic Bytes para verificar que sea una imagen real.
    5. Asignación de UUID seguro para prevenir Path Traversal y sobreescrituras.
    """
    # 1. Comprobar que la petición contenga el campo 'imagen'
    if "imagen" not in request.files:
        return jsonify({"ok": False, "error": "No se envió ningún archivo en la petición."}), 400

    archivo = request.files["imagen"]
    if not archivo or archivo.filename == "":
        return jsonify({"ok": False, "error": "El nombre del archivo está vacío."}), 400

    # 2. Comprobación estricta de tamaño en stream (Límite 25 MiB)
    archivo.seek(0, os.SEEK_END)
    tamano_bytes = archivo.tell()
    archivo.seek(0)  # Rebobinar al inicio obligatorio

    if tamano_bytes > MAX_BYTES_IMAGEN:
        return jsonify({
            "ok": False, 
            "error": f"El archivo supera el límite permitido de {LIMITE_MB_IMAGEN} MB ({formatear_tamano(tamano_bytes)})."
        }), 413

    # 3. Validación de extensión de archivo
    if not extension_valida(archivo.filename):
        return jsonify({
            "ok": False, 
            "error": "Extensión no permitida. Formatos aceptados: PNG, JPG, JPEG, GIF, WEBP."
        }), 400

    # 4. Inspección binaria de cabeceras (Magic Bytes)
    formato_real = validar_firma_binaria_imagen(archivo.stream)
    if not formato_real:
        ip = request.remote_addr
        print(f"\n\033[93m[ACTIVIDAD SOSPECHOSA :: PAYLOAD FALSO]\033[0m Archivo con cabecera binaria inválida/falsificada rechazado. Archivo: '{archivo.filename}' | IP: {ip}")
        return jsonify({
            "ok": False, 
            "error": "El archivo está dañado o no corresponde a una imagen válida (firma binaria rechazada)."
        }), 400

    # 5. Guardado seguro en disco con identificador UUID
    os.makedirs(CARPETA_IMAGENES_DOCS, exist_ok=True)
    nombre_limpio = secure_filename(archivo.filename)
    nombre_seguro = f"img_{uuid.uuid4().hex[:12]}.{formato_real}"
    ruta_destino = os.path.join(CARPETA_IMAGENES_DOCS, nombre_seguro)

    archivo.save(ruta_destino)

    url_relativa = f"/static/uploads/documentos/{nombre_seguro}"
    registrar_log(f"Imagen subida con éxito: {nombre_seguro} ({formatear_tamano(tamano_bytes)})")

    return jsonify({
        "ok": True,
        "url": url_relativa,
        "nombre": nombre_limpio or nombre_seguro,
        "markdown": f"![{nombre_limpio or 'Imagen'}]({url_relativa})"
    })


@clips_bp.route("/documentos/api/imagenes", methods=["GET"])
@login_requerido
def api_listar_imagenes_documentos():
    """Devuelve la colección de imágenes del servidor para poblar la galería del editor."""
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
        # Ordenar por fecha de modificación (las más recientes primero)
        imagenes.sort(key=lambda x: x["fecha"], reverse=True)
    except Exception as e:
        registrar_log(f"Error al listar galería de imágenes: {e}")

    return jsonify({"ok": True, "imagenes": imagenes})


@clips_bp.route("/documentos/api/eliminar_imagen/<nombre>", methods=["POST"])
@login_requerido
def api_eliminar_imagen_documento(nombre):
    """Elimina una imagen puntual del disco garantizando que no haya escape de directorio."""
    # Evita ataques de Path Traversal (ej. ../../archivo)
    if os.path.basename(nombre) != nombre or not extension_valida(nombre):
        ip = request.remote_addr
        print(f"\n\033[91m[ALERTA DE INTRUSIÓN :: PATH TRAVERSAL]\033[0m Parámetro malicioso interceptado en borrado: '{nombre}' | IP: {ip}")
        return jsonify({"ok": False, "error": "Identificador de archivo no válido."}), 400

    ruta_archivo = os.path.join(CARPETA_IMAGENES_DOCS, nombre)

    if os.path.exists(ruta_archivo):
        try:
            os.remove(ruta_archivo)
            registrar_log(f"Imagen eliminada de disco: {nombre}")
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": f"Error al eliminar: {str(e)}"}), 500

    return jsonify({"ok": False, "error": "El archivo especificado no existe."}), 404


# ==============================================================================
# SECCIÓN 9: AJUSTES DE SISTEMA, GESTIÓN DE BACKUPS Y PURGA
# ==============================================================================

@clips_bp.route("/configuracion", methods=["GET", "POST"])
@login_requerido
def configuracion():
    """Panel de administración, telemetría y configuración del entorno .env."""
    desbloqueado = esta_desbloqueado()
    segundos_restantes = max(0, int(session.get("desbloqueo_expira", 0) - time.time())) if desbloqueado else 0

    if request.method == "POST":
        if not desbloqueado:
            return redirect(url_for("clips.configuracion"))

        nueva_pass = request.form.get("app_password", "").strip()
        if nueva_pass:
            set_key(RUTA_ENV, "APP_PASSWORD", nueva_pass)
            os.environ["APP_PASSWORD"] = nueva_pass
            registrar_log("APP_PASSWORD actualizada con éxito")

        nuevo_host = request.form.get("host", "").strip()
        if nuevo_host:
            set_key(RUTA_ENV, "HOST", nuevo_host)
            os.environ["HOST"] = nuevo_host

    # --- Parámetros de red y entorno ---
        nuevo_port = request.form.get("port", "").strip()
        if nuevo_port:
            set_key(RUTA_ENV, "PORT", nuevo_port)
            os.environ["PORT"] = nuevo_port

        log_mode = "true" if "log_mode" in request.form else "false"
        set_key(RUTA_ENV, "LOG_MODE", log_mode)
        os.environ["LOG_MODE"] = log_mode

        auto_abrir = "true" if "auto_abrir_navegador" in request.form else "false"
        set_key(RUTA_ENV, "AUTO_ABRIR_NAVEGADOR", auto_abrir)
        os.environ["AUTO_ABRIR_NAVEGADOR"] = auto_abrir

        # ---> REGISTRO GENERAL DE AJUSTES:
        registrar_log("Ajustes del servidor y variables .env actualizadas")

        return redirect(url_for("clips.configuracion", guardado=1))

    registrar_log("Panel de configuración y ajustes del sistema abierto")

    # Métricas de base de datos SQLite
    conn = database.obtener_conexion()
    total_clips = conn.execute(
        "SELECT COUNT(*) FROM clips WHERE categoria NOT IN ('Novelas', 'Borrador', 'Resumen') AND categoria NOT LIKE 'Codigo:%'"
    ).fetchone()[0]

    # Métricas de base de datos SQLite
    conn = database.obtener_conexion()
    total_clips = conn.execute(
        "SELECT COUNT(*) FROM clips WHERE categoria NOT IN ('Novelas', 'Borrador', 'Resumen') AND categoria NOT LIKE 'Codigo:%'"
    ).fetchone()[0]
    total_codigo = conn.execute("SELECT COUNT(*) FROM clips WHERE categoria LIKE 'Codigo:%'").fetchone()[0]
    total_resumenes = conn.execute("SELECT COUNT(*) FROM clips WHERE categoria IN ('Novelas', 'Borrador', 'Resumen')").fetchone()[0]
    total_documentos = conn.execute("SELECT COUNT(*) FROM documentos").fetchone()[0]
    conn.close()

    # Diagnóstico de almacenamiento físico
    peso_db = "0 KB"
    if os.path.exists("pcm.db"):
        peso_db = formatear_tamano(os.path.getsize("pcm.db"))

    total_peso_img = 0
    cant_imagenes = 0
    if os.path.exists(CARPETA_IMAGENES_DOCS):
        for archivo in os.listdir(CARPETA_IMAGENES_DOCS):
            ruta_f = os.path.join(CARPETA_IMAGENES_DOCS, archivo)
            if os.path.isfile(ruta_f):
                cant_imagenes += 1
                total_peso_img += os.path.getsize(ruta_f)
    peso_imagenes = formatear_tamano(total_peso_img)

    valores = dotenv_values(RUTA_ENV)

    return render_template(
        "config.html",
        total_clips=total_clips,
        total_codigo=total_codigo,
        total_resumenes=total_resumenes,
        total_documentos=total_documentos,
        peso_db=peso_db,
        peso_imagenes=peso_imagenes,
        cant_imagenes=cant_imagenes,
        valores=valores,
        desbloqueo_critico_activo=desbloqueado,
        desbloqueo_segundos_restantes=segundos_restantes
    )


@clips_bp.route("/configuracion/desbloquear", methods=["POST"])
@login_requerido
def desbloquear_critico():
    """Valida la MASTER_KEY para permitir cambios en puertos, credenciales o vaciado."""
    clave_ingresada = request.form.get("master_key", "").strip()
    if clave_ingresada and clave_ingresada == os.environ.get("MASTER_KEY"):
        session["desbloqueo_critico"] = True
        session["desbloqueo_expira"] = time.time() + DURACION_DESBLOQUEO
        session["desbloqueo_servidor"] = INICIO_SERVIDOR
        registrar_log("Configuración crítica desbloqueada por 2 minutos")
        return redirect(url_for("clips.configuracion"))

    registrar_log("Intento fallido de desbloqueo crítico")
    return redirect(url_for("clips.configuracion", error_master=1))


@clips_bp.route("/configuracion/bloquear", methods=["POST"])
@login_requerido
def bloquear_critico():
    """Cierra manualmente el acceso administrativo anticipando el vencimiento del timer."""
    session.pop("desbloqueo_critico", None)
    registrar_log("Configuración crítica bloqueada manualmente")
    return redirect(url_for("clips.configuracion"))


@clips_bp.route("/configuracion/cerrar_sesiones", methods=["POST"])
@login_requerido
def cerrar_sesiones_globales():
    """Fuerza el deslogueo en todos los navegadores regenerando la SECRET_KEY."""
    nueva_key = secrets.token_hex(32)
    
    # 1. Persistir en disco para futuros reinicios
    set_key(RUTA_ENV, "SECRET_KEY", nueva_key)
    os.environ["SECRET_KEY"] = nueva_key
    
    # 2. Rotación en caliente: invalida de inmediato las cookies en RAM sin reiniciar el .exe
    current_app.secret_key = nueva_key
    
    registrar_log("Cierre global: SECRET_KEY rotada en memoria y persistida en .env")
    session.clear()
    return redirect(url_for("clips.login"))


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
            "version_schema": "2.2",
            "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_clips": len(clips),
            "total_documentos": len(docs)
        },
        "clips": clips,
        "documentos": docs
    }

    # Registro de última fecha de exportación
    with open(RUTA_ULTIMO_BACKUP, "w", encoding="utf-8") as f:
        f.write(str(time.time()))

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    # Caso 1: Paquete ZIP completo con carpeta de imágenes
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
        registrar_log("Exportación ZIP completada (Clips + Documentos + Imágenes)")
        return send_file(memoria_zip, as_attachment=True, download_name=nombre_zip, mimetype="application/zip")

    # Caso 2: Solo base de datos en JSON
    memoria_json = io.BytesIO(json_bytes)
    nombre_json = f"pcm_backup_texto_{fecha_str}.json"
    registrar_log("Exportación JSON completada (Clips + Documentos)")
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

                # Restauración de imágenes físicas
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

        for c in clips_a_restaurar:
            cur.execute("""
                INSERT OR REPLACE INTO clips (uuid, titulo, contenido, categoria, fecha_creacion, expira_en, vistas_restantes, es_favorito)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c["uuid"], c.get("titulo", ""), c["contenido"],
                c.get("categoria", "General"), c.get("fecha_creacion", int(time.time())),
                c.get("expira_en"), c.get("vistas_restantes", -1), c.get("es_favorito", 0)
            ))

        for d in docs_a_restaurar:
            cur.execute("""
                INSERT OR REPLACE INTO documentos (id, titulo, contenido, creado_en, actualizado_en)
                VALUES (?, ?, ?, ?, ?)
            """, (
                d.get("id"), d.get("titulo", "Sin título"), d.get("contenido", ""),
                d.get("creado_en", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                d.get("actualizado_en", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ))

        conn.commit()
        conn.close()

        registrar_log(f"Restauración exitosa: {len(clips_a_restaurar)} clips y {len(docs_a_restaurar)} documentos")
        return redirect(url_for("clips.configuracion", guardado=1))

    except Exception as e:
        registrar_log(f"Error crítico durante la restauración: {str(e)}")
        flash(f"Fallo al procesar el archivo de backup: {e}", "error")
        return redirect(url_for("clips.configuracion"))


@clips_bp.route("/configuracion/borrar_todo", methods=["POST"])
@login_requerido
def borrar_todo():
    """Vaciado integral de tablas relacionales bajo confirmación con MASTER_KEY."""
    if not esta_desbloqueado():
        return redirect(url_for("clips.configuracion"))

    conn = database.obtener_conexion()
    conn.execute("DELETE FROM clips")
    conn.execute("DELETE FROM documentos")
    conn.commit()
    conn.close()
    registrar_log("⚠️ Vaciado total de base de datos ejecutado con éxito")
    return redirect(url_for("clips.configuracion", guardado=1))


@clips_bp.route("/configuracion/purgar_imagenes", methods=["POST"])
@login_requerido
def purgar_imagenes_huerfanas():
    """
    Escanea la carpeta de subidas y elimina cualquier archivo gráfico
    que ya no esté referenciado en el texto de ningún documento ni clip.
    """
    conn = database.obtener_conexion()
    docs = conn.execute("SELECT contenido FROM documentos").fetchall()
    clips = conn.execute("SELECT contenido FROM clips").fetchall()
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
                        registrar_log(f"Imagen huérfana eliminada: {archivo}")
                    except Exception as e:
                        registrar_log(f"Error al purgar archivo huérfano {archivo}: {e}")

    liberado_str = formatear_tamano(bytes_liberados)
    if purgadas > 0:
        flash(f"Limpieza completada: se eliminaron {purgadas} imágenes huérfanas liberando {liberado_str}.", "info")
    else:
        flash("El almacenamiento está optimizado: no se encontraron imágenes huérfanas.", "info")

    return redirect(url_for("clips.configuracion"))