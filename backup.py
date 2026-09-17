import sys
import os
import io
import json
import shutil
import zipfile
import time
from datetime import datetime
import database

CARPETA_BACKUPS = "backups"
CARPETA_IMAGENES_DOCS = os.path.join("static", "uploads", "documentos")


def asegurar_carpetas():
    os.makedirs(CARPETA_BACKUPS, exist_ok=True)
    os.makedirs(CARPETA_IMAGENES_DOCS, exist_ok=True)


def recopilar_datos_db():
    """Recopila tanto clips como documentos de la base SQLite."""
    conn = database.obtener_conexion()
    
    filas_clips = conn.execute("SELECT * FROM clips ORDER BY id ASC").fetchall()
    clips = [dict(f) for f in filas_clips]

    filas_docs = conn.execute("SELECT * FROM documentos ORDER BY id ASC").fetchall()
    docs = [dict(f) for f in filas_docs]

    conn.close()

    return {
        "metadata": {
            "sistema": "PCMPrivateClipManager",
            "version_schema": "2.2",
            "generado_en": datetime.now().isoformat(),
            "total_clips": len(clips),
            "total_documentos": len(docs)
        },
        "clips": clips,
        "documentos": docs
    }


def exportar_json(nombre_personalizado=None):
    """Exporta solo texto (Clips + Documentos) en un archivo JSON."""
    asegurar_carpetas()
    paquete = recopilar_datos_db()

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo = nombre_personalizado or os.path.join(CARPETA_BACKUPS, f"pcm_backup_{fecha_str}.json")

    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(paquete, f, indent=2, ensure_ascii=False)

    print(f"[✓] Respaldo JSON generado ({len(paquete['clips'])} clips, {len(paquete['documentos'])} documentos): {archivo}")
    return archivo


def exportar_zip_completo():
    """Exporta JSON + Carpeta de imágenes físicas dentro de un archivo ZIP."""
    asegurar_carpetas()
    paquete = recopilar_datos_db()
    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo_zip = os.path.join(CARPETA_BACKUPS, f"pcm_backup_completo_{fecha_str}.zip")

    with zipfile.ZipFile(archivo_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        # Guardar JSON dentro del zip
        json_str = json.dumps(paquete, indent=2, ensure_ascii=False)
        zf.writestr("datos.json", json_str)

        # Guardar imágenes de documentos
        if os.path.exists(CARPETA_IMAGENES_DOCS):
            for img in os.listdir(CARPETA_IMAGENES_DOCS):
                ruta_img = os.path.join(CARPETA_IMAGENES_DOCS, img)
                if os.path.isfile(ruta_img):
                    zf.write(ruta_img, arcname=f"imagenes/{img}")

    print(f"[✓] Respaldo ZIP completo generado con éxito: {archivo_zip}")
    return archivo_zip


def restaurar_datos(datos):
    """Inserta clips y documentos en SQLite."""
    conn = database.obtener_conexion()
    cursor = conn.cursor()

    clips = datos.get("clips", [])
    for c in clips:
        cursor.execute("""
            INSERT OR REPLACE INTO clips (uuid, titulo, contenido, categoria, fecha_creacion, expira_en, vistas_restantes, es_favorito)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            c["uuid"], c.get("titulo", ""), c["contenido"],
            c.get("categoria", "General"), c.get("fecha_creacion", int(time.time())),
            c.get("expira_en"), c.get("vistas_restantes", -1), c.get("es_favorito", 0)
        ))

    docs = datos.get("documentos", [])
    for d in docs:
        cursor.execute("""
            INSERT OR REPLACE INTO documentos (id, titulo, contenido, creado_en, actualizado_en)
            VALUES (?, ?, ?, ?, ?)
        """, (
            d.get("id"), d.get("titulo", "Sin título"), d.get("contenido", ""),
            d.get("creado_en", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            d.get("actualizado_en", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ))

    conn.commit()
    conn.close()
    return len(clips), len(docs)


def importar_archivo(ruta_archivo):
    """Detecta si el archivo es ZIP o JSON y restaura correspondientemente."""
    asegurar_carpetas()
    if not os.path.exists(ruta_archivo):
        print(f"[X] Archivo no encontrado: {ruta_archivo}")
        return

    if ruta_archivo.endswith(".zip"):
        with zipfile.ZipFile(ruta_archivo, "r") as zf:
            nombres = zf.namelist()
            json_file = next((n for n in nombres if n.endswith(".json")), None)
            if not json_file:
                print("[X] El ZIP no contiene ningún archivo de datos JSON.")
                return

            datos = json.loads(zf.read(json_file).decode("utf-8"))

            # Extraer imágenes a la carpeta de uploads
            for item in nombres:
                if item.startswith("imagenes/") and not item.endswith("/"):
                    nombre_img = os.path.basename(item)
                    ruta_salida = os.path.join(CARPETA_IMAGENES_DOCS, nombre_img)
                    with zf.open(item) as src, open(ruta_salida, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            c_cnt, d_cnt = restaurar_datos(datos)
            print(f"[✓] ZIP restaurado: {c_cnt} clips, {d_cnt} documentos y sus imágenes físicas.")

    elif ruta_archivo.endswith(".json"):
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            datos = json.load(f)
        c_cnt, d_cnt = restaurar_datos(datos)
        print(f"[✓] JSON restaurado: {c_cnt} clips y {d_cnt} documentos.")