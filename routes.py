import os
import io
import json
import uuid
import time
import secrets
import shutil
import zipfile
from datetime import datetime
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session, send_file, jsonify, flash
from dotenv import set_key, dotenv_values

import database
from version import VERSION

clips_bp = Blueprint("clips", __name__)

INICIO_SERVIDOR = secrets.token_hex(8)
DURACION_DESBLOQUEO = 120  # 2 minutos
RUTA_ENV = ".env"
RUTA_ULTIMO_BACKUP = "ultimo_backup.txt"

CATEGORIAS_TEXTO_LARGO = ('Novelas', 'Borrador', 'Resumen')
CARPETA_IMAGENES_DOCS = os.path.join("static", "uploads", "documentos")
EXTENSIONES_IMAGENES = {"png", "jpg", "jpeg", "gif", "webp", "svg"}


# ==========================================
# UTILIDADES Y SEGURIDAD
# ==========================================

def registrar_log(accion):
    if os.environ.get("LOG_MODE", "true").lower() == "true":
        hora = datetime.now().strftime("%H:%M:%S")
        print(f"[{hora} LOG] {accion}")

def esta_desbloqueado():
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
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get("autenticado"):
            return redirect(url_for("clips.login"))
        return f(*args, **kwargs)
    return decorador

def extension_valida(nombre_archivo):
    return "." in nombre_archivo and nombre_archivo.rsplit(".", 1)[1].lower() in EXTENSIONES_IMAGENES

@clips_bp.app_context_processor
def inyectar_contexto():
    return {
        "app_version": VERSION
    }


# ==========================================
# AUTENTICACIÓN
# ==========================================

@clips_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        clave_ingresada = request.form.get("password")
        if clave_ingresada == os.environ.get("APP_PASSWORD", "cambiame"):
            session["autenticado"] = True
            registrar_log(f"Inicio de sesión exitoso desde {request.remote_addr}")
            return redirect(url_for("clips.index"))
        error = "Contraseña incorrecta."
        registrar_log(f"Intento de inicio de sesión fallido desde {request.remote_addr}")
    return render_template("login.html", error=error)

@clips_bp.route("/logout")
def logout():
    session.clear()
    registrar_log("Cierre de sesión manual")
    return redirect(url_for("clips.login"))


# ==========================================
# CLIPS RÁPIDOS Y PROMPTS
# ==========================================

@clips_bp.route("/")
@login_requerido
def index():
    database.purgar_expirados()
    conn = database.obtener_conexion()
    clips = conn.execute("""
        SELECT * FROM clips 
        WHERE categoria NOT IN ('Novelas', 'Borrador', 'Resumen') 
          AND categoria NOT LIKE 'Codigo:%' 
        ORDER BY es_favorito DESC, id DESC
    """).fetchall()
    
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
        registrar_log(f"Clip rápido creado: [{categoria}] '{titulo or 'Sin título'}'")

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
        registrar_log(f"Clip '{clip['titulo'] or clip_id}' {accion}")
        
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
        registrar_log(f"Clip editado: [{categoria}] '{titulo or clip_id}' (Caducidad: {opcion_duracion})")

    return redirect(url_for("clips.index"))

@clips_bp.route("/eliminar/<int:clip_id>", methods=["GET", "POST", "DELETE"])
@login_requerido
def eliminar(clip_id):
    conn = database.obtener_conexion()
    clip = conn.execute("SELECT categoria, titulo FROM clips WHERE id = ?", (clip_id,)).fetchone()
    es_texto_largo = clip and clip["categoria"] in CATEGORIAS_TEXTO_LARGO
    es_codigo = clip and clip["categoria"].startswith("Codigo:")
    titulo = clip["titulo"] if clip else str(clip_id)

    conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
    conn.commit()
    conn.close()
    registrar_log(f"Elemento eliminado: '{titulo}'")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return {"ok": True, "id": clip_id}

    if es_texto_largo:
        return redirect(url_for("clips.biblioteca_novelas"))
    if es_codigo:
        return redirect(url_for("clips.seccion_codigo"))
    return redirect(url_for("clips.index"))


# ==========================================
# BORRADORES & RESÚMENES
# ==========================================

@clips_bp.route("/novelas")
@login_requerido
def biblioteca_novelas():
    conn = database.obtener_conexion()
    resumenes = conn.execute(
        "SELECT * FROM clips WHERE categoria IN ('Novelas', 'Borrador', 'Resumen') ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template("novelas.html", resumenes=resumenes)

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
    if tipo_doc not in ["Borrador", "Resumen"]:
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
        registrar_log(f"{tipo_doc} actualizado: '{titulo}'")
    else:
        clip_uuid = str(uuid.uuid4())[:8]
        conn.execute("""
            INSERT INTO clips (uuid, titulo, contenido, categoria, fecha_creacion, expira_en, vistas_restantes)
            VALUES (?, ?, ?, ?, ?, NULL, -1)
        """, (clip_uuid, titulo, contenido, tipo_doc, ahora))
        registrar_log(f"Nuevo {tipo_doc} creado: '{titulo}'")

    conn.commit()
    conn.close()
    return redirect(url_for("clips.biblioteca_novelas"))



@clips_bp.route("/configuracion/desbloquear", methods=["POST"])
@login_requerido
def desbloquear_critico():
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
    session.pop("desbloqueo_critico", None)
    registrar_log("Configuración crítica bloqueada manualmente")
    return redirect(url_for("clips.configuracion"))

@clips_bp.route("/configuracion/cerrar_sesiones", methods=["POST"])
@login_requerido
def cerrar_sesiones_globales():
    nueva_key = secrets.token_hex(32)
    set_key(RUTA_ENV, "SECRET_KEY", nueva_key)
    os.environ["SECRET_KEY"] = nueva_key
    registrar_log("Cierre de sesión global: SECRET_KEY regenerada en .env")
    session.clear()
    return redirect(url_for("clips.login"))

@clips_bp.route("/configuracion/exportar")
@login_requerido
def exportar_backup():
    """Genera respaldo en JSON (solo texto) o en ZIP (JSON + imágenes físicas)."""
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

    with open(RUTA_ULTIMO_BACKUP, "w") as f:
        f.write(str(time.time()))

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    # Caso 1: Con imágenes -> Paquete ZIP
    if incluir_imagenes:
        memoria_zip = io.BytesIO()
        with zipfile.ZipFile(memoria_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("pcm_datos.json", json_bytes)

            carpeta_img = CARPETA_IMAGENES_DOCS
            if os.path.exists(carpeta_img):
                for img_name in os.listdir(carpeta_img):
                    ruta_img = os.path.join(carpeta_img, img_name)
                    if os.path.isfile(ruta_img):
                        zf.write(ruta_img, arcname=f"imagenes/{img_name}")

        memoria_zip.seek(0)
        nombre = f"pcm_backup_completo_{fecha_str}.zip"
        registrar_log("Exportación ZIP completada (Clips + Documentos + Imágenes)")
        return send_file(memoria_zip, as_attachment=True, download_name=nombre, mimetype="application/zip")

    # Caso 2: Solo texto -> Archivo JSON
    memoria_json = io.BytesIO(json_bytes)
    nombre = f"pcm_backup_texto_{fecha_str}.json"
    registrar_log("Exportación JSON completada (Clips + Documentos)")
    return send_file(memoria_json, as_attachment=True, download_name=nombre, mimetype="application/json")

@clips_bp.route("/configuracion/importar", methods=["POST"])
@login_requerido
def importar_backup():
    """Restaura tanto archivos .json como archivos .zip con imágenes."""
    archivo = request.files.get("archivo_backup")
    if not archivo or archivo.filename == "":
        flash("No seleccionaste ningún archivo.", "error")
        return redirect(url_for("clips.configuracion"))

    nombre_archivo = archivo.filename.lower()
    if not (nombre_archivo.endswith(".json") or nombre_archivo.endswith(".zip")):
        flash("Formato no válido. Solo se admiten archivos .JSON o paquetes .ZIP.", "error")
        return redirect(url_for("clips.configuracion"))

    try:
        carpeta_img = CARPETA_IMAGENES_DOCS
        os.makedirs(carpeta_img, exist_ok=True)
        contenido = None

        if nombre_archivo.endswith(".zip"):
            with zipfile.ZipFile(archivo, "r") as zf:
                json_encontrado = next((n for n in zf.namelist() if n.endswith(".json")), None)
                if not json_encontrado:
                    flash("El archivo ZIP no contiene ningún archivo de datos JSON válido.", "error")
                    return redirect(url_for("clips.configuracion"))

                contenido = json.loads(zf.read(json_encontrado).decode("utf-8"))

                # Restaurar imágenes físicas
                for item in zf.namelist():
                    if item.startswith("imagenes/") and not item.endswith("/"):
                        nombre_img = os.path.basename(item)
                        ruta_destino = os.path.join(carpeta_img, nombre_img)
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

        registrar_log(f"Restauración completada: {len(clips_a_restaurar)} clips y {len(docs_a_restaurar)} documentos")
        return redirect(url_for("clips.configuracion", guardado=1))

    except Exception as e:
        registrar_log(f"Error crítico al restaurar copia: {str(e)}")
        flash(f"Error al procesar el archivo: {e}", "error")
        return redirect(url_for("clips.configuracion"))

@clips_bp.route("/configuracion/borrar_todo", methods=["POST"])
@login_requerido
def borrar_todo():
    if not esta_desbloqueado():
        return redirect(url_for("clips.configuracion"))

    conn = database.obtener_conexion()
    conn.execute("DELETE FROM clips")
    conn.execute("DELETE FROM documentos")
    conn.commit()
    conn.close()
    registrar_log("⚠️ Vaciado total de base de datos ejecutado")
    return redirect(url_for("clips.configuracion", guardado=1))


# ==========================================
# SNIPPETS DE CÓDIGO & MARKDOWN
# ==========================================

@clips_bp.route("/codigo")
@login_requerido
def seccion_codigo():
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
            INSERT INTO clips (uuid, titulo, contenido, categoria, fecha_creacion, expira_en, vistas_restantes)
            VALUES (?, ?, ?, ?, ?, NULL, -1)
        """, (clip_uuid, titulo, contenido, categoria_codigo, ahora))
        conn.commit()
        conn.close()
        registrar_log(f"Snippet de código guardado: [{lenguaje}] '{titulo}'")

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
            SET titulo = ?, categoria = ?, contenido = ?
            WHERE id = ?
        """, (titulo, categoria_codigo, contenido, clip_id))
        conn.commit()
        conn.close()
        registrar_log(f"Snippet de código editado: [{lenguaje}] '{titulo}'")

    return redirect(url_for("clips.seccion_codigo"))


# ==========================================
# FUSIONADOR DE TEXTOS / PROMPTS
# ==========================================

@clips_bp.route("/fusionador")
@login_requerido
def fusionador():
    return render_template("fusionador.html")


# ==========================================
# GESTOR DE DOCUMENTOS & MATH STUDIO
# ==========================================

@clips_bp.route("/documentos")
@login_requerido
def documentos():
    """Hub central: lista todos los documentos guardados."""
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, titulo, contenido, creado_en, actualizado_en 
        FROM documentos 
        ORDER BY actualizado_en DESC
    """)
    documentos = cursor.fetchall()
    conn.close()
    return render_template("lista_documentos.html", documentos=documentos)

@clips_bp.route("/documentos/estudio")
@login_requerido
def documentos_nuevo():
    """Abre el editor en blanco para redactar un documento nuevo."""
    return render_template("documentos.html", doc=None)

@clips_bp.route("/documentos/estudio/<int:doc_id>")
@login_requerido
def documentos_editar(doc_id):
    """Carga un documento existente en el editor por su ID."""
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT id, titulo, contenido FROM documentos WHERE id = ?", (doc_id,))
    doc = cursor.fetchone()
    conn.close()

    if not doc:
        flash("El documento solicitado no existe.", "error")
        return redirect(url_for("clips.documentos"))

    return render_template("documentos.html", doc=doc)

@clips_bp.route("/documentos/api/guardar", methods=["POST"])
@login_requerido
def api_guardar_documento():
    """API silenciosa: guarda o actualiza el documento vía AJAX/Fetch."""
    data = request.get_json() or {}
    doc_id = data.get("id")
    titulo = (data.get("titulo") or "").strip() or "Sin título"
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
    else:
        cursor.execute("""
            INSERT INTO documentos (titulo, contenido) 
            VALUES (?, ?)
        """, (titulo, contenido))
        nuevo_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return jsonify({"ok": True, "id": nuevo_id, "titulo": titulo})

@clips_bp.route("/documentos/eliminar/<int:doc_id>", methods=["POST"])
@login_requerido
def eliminar_documento(doc_id):
    """Elimina un documento de la base de datos."""
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documentos WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
    
    flash("Documento eliminado correctamente.", "info")
    return redirect(url_for("clips.documentos"))


# ==========================================
# GESTOR DE IMÁGENES PARA DOCUMENTOS
# ==========================================

@clips_bp.route("/documentos/api/subir_imagen", methods=["POST"])
@login_requerido
def api_subir_imagen_documento():
    """Sube una imagen física al servidor y devuelve la ruta Markdown lista para usar."""
    if "imagen" not in request.files:
        return jsonify({"ok": False, "error": "No se envió ningún archivo"}), 400

    archivo = request.files["imagen"]
    if not archivo or archivo.filename == "":
        return jsonify({"ok": False, "error": "Archivo vacío"}), 400

    if not extension_valida(archivo.filename):
        return jsonify({"ok": False, "error": "Formato inválido (usa PNG, JPG, WEBP, GIF o SVG)"}), 400

    os.makedirs(CARPETA_IMAGENES_DOCS, exist_ok=True)

    extension = archivo.filename.rsplit(".", 1)[1].lower()
    nombre_seguro = f"img_{uuid.uuid4().hex[:10]}.{extension}"
    ruta_destino = os.path.join(CARPETA_IMAGENES_DOCS, nombre_seguro)
    archivo.save(ruta_destino)

    url_relativa = f"/static/uploads/documentos/{nombre_seguro}"
    registrar_log(f"Imagen adjuntada a documentos: {nombre_seguro}")

    return jsonify({
        "ok": True,
        "url": url_relativa,
        "nombre": nombre_seguro,
        "markdown": f"![Imagen]({url_relativa})"
    })

@clips_bp.route("/documentos/api/imagenes", methods=["GET"])
@login_requerido
def api_listar_imagenes_documentos():
    """Devuelve el listado de imágenes disponibles en el servidor."""
    os.makedirs(CARPETA_IMAGENES_DOCS, exist_ok=True)
    imagenes = []

    try:
        for archivo in os.listdir(CARPETA_IMAGENES_DOCS):
            if extension_valida(archivo):
                ruta_completa = os.path.join(CARPETA_IMAGENES_DOCS, archivo)
                imagenes.append({
                    "nombre": archivo,
                    "url": f"/static/uploads/documentos/{archivo}",
                    "fecha": os.path.getmtime(ruta_completa)
                })
        imagenes.sort(key=lambda x: x["fecha"], reverse=True)
    except Exception as e:
        registrar_log(f"Error al listar imágenes: {e}")

    return jsonify({"ok": True, "imagenes": imagenes})

@clips_bp.route("/documentos/api/eliminar_imagen/<nombre>", methods=["POST"])
@login_requerido
def api_eliminar_imagen_documento(nombre):
    """Elimina una imagen de static/uploads/documentos/."""
    if os.path.basename(nombre) != nombre or not extension_valida(nombre):
        return jsonify({"ok": False, "error": "Nombre de archivo no válido"}), 400

    ruta_archivo = os.path.join(CARPETA_IMAGENES_DOCS, nombre)
    
    if os.path.exists(ruta_archivo):
        try:
            os.remove(ruta_archivo)
            registrar_log(f"Imagen eliminada: {nombre}")
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    
    return jsonify({"ok": False, "error": "Archivo no encontrado"}), 404


def formatear_tamano(bytes_cant):
    """Convierte bytes a formato legible (B, KB, MB)."""
    if bytes_cant < 1024:
        return f"{bytes_cant} B"
    elif bytes_cant < 1024 * 1024:
        return f"{bytes_cant / 1024:.1f} KB"
    else:
        return f"{bytes_cant / (1024 * 1024):.2f} MB"


@clips_bp.route("/configuracion", methods=["GET", "POST"])
@login_requerido
def configuracion():
    desbloqueado = esta_desbloqueado()
    segundos_restantes = max(0, int(session.get("desbloqueo_expira", 0) - time.time())) if desbloqueado else 0

    if request.method == "POST":
        if not desbloqueado:
            return redirect(url_for("clips.configuracion"))

        nueva_pass = request.form.get("app_password", "").strip()
        if nueva_pass:
            set_key(RUTA_ENV, "APP_PASSWORD", nueva_pass)
            os.environ["APP_PASSWORD"] = nueva_pass
            registrar_log("APP_PASSWORD actualizada")

        nuevo_host = request.form.get("host", "").strip()
        if nuevo_host:
            set_key(RUTA_ENV, "HOST", nuevo_host)
            os.environ["HOST"] = nuevo_host

        nuevo_port = request.form.get("port", "").strip()
        if nuevo_port:
            set_key(RUTA_ENV, "PORT", nuevo_port)
            os.environ["PORT"] = nuevo_port

        log_mode = "true" if "log_mode" in request.form else "false"
        set_key(RUTA_ENV, "LOG_MODE", log_mode)
        os.environ["LOG_MODE"] = log_mode

        return redirect(url_for("clips.configuracion", guardado=1))

    # Conteos de base de datos
    conn = database.obtener_conexion()
    total_clips = conn.execute("SELECT COUNT(*) FROM clips WHERE categoria NOT IN ('Novelas', 'Borrador', 'Resumen') AND categoria NOT LIKE 'Codigo:%'").fetchone()[0]
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


@clips_bp.route("/configuracion/purgar_imagenes", methods=["POST"])
@login_requerido
def purgar_imagenes_huerfanas():
    """Elimina del disco las imágenes no referenciadas en ningún documento ni clip."""
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
                        registrar_log(f"Imagen huérfana purgada: {archivo}")
                    except Exception as e:
                        registrar_log(f"Error al purgar {archivo}: {e}")

    liberado_str = formatear_tamano(bytes_liberados)
    if purgadas > 0:
        flash(f"Limpieza completada: se eliminaron {purgadas} imágenes huérfanas liberando {liberado_str}.", "info")
    else:
        flash("El almacenamiento está limpio: no se encontraron imágenes huérfanas.", "info")

    return redirect(url_for("clips.configuracion"))