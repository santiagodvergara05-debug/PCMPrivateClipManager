import sqlite3
import os
import time

DB_NAME = "pcm.db"

def migrar_base_antigua():
    """Migra automáticamente el archivo anterior cliptemp.db a pcm.db si existe."""
    if os.path.exists("cliptemp.db") and not os.path.exists(DB_NAME):
        try:
            os.rename("cliptemp.db", DB_NAME)
            print("  [\033[92m  OK  \033[0m] Migración: 'cliptemp.db' renombrado exitosamente a 'pcm.db'")
        except Exception as e:
            print(f"  [\033[93m WARN \033[0m] No se pudo renombrar cliptemp.db: {e}")

def obtener_conexion():
    migrar_base_antigua()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_db():
    migrar_base_antigua()
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    # 1. Tabla de clips rápidos / notas temporales
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE NOT NULL,
            titulo TEXT,
            contenido TEXT NOT NULL,
            categoria TEXT DEFAULT 'General',
            fecha_creacion INTEGER NOT NULL,
            expira_en INTEGER,
            vistas_restantes INTEGER DEFAULT -1,
            es_favorito INTEGER DEFAULT 0
        )
    """)

    # 2. Nueva tabla dedicada para Documentos & Math Studio
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            contenido TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def purgar_expirados():
    ahora = int(time.time())
    conn = obtener_conexion()
    conn.execute("DELETE FROM clips WHERE expira_en IS NOT NULL AND expira_en <= ? AND es_favorito = 0", (ahora,))
    conn.commit()
    conn.close()