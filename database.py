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

def migrar_columna_tipo(conn):
    """
    Verifica si existe la columna 'tipo' en la tabla clips.
    Si no existe, la añade de forma no destructiva y clasifica los registros existentes.
    """
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(clips)")
    columnas = [col["name"] for col in cursor.fetchall()]

    if "tipo" not in columnas:
        try:
            # 1. Agregar columna tipo sin alterar registros
            cursor.execute("ALTER TABLE clips ADD COLUMN tipo TEXT DEFAULT 'clip'")
            
            # 2. Clasificar los textos que pertenecen al Bloc de Notas
            cursor.execute("""
                UPDATE clips 
                SET tipo = 'nota' 
                WHERE categoria IN ('Nota', 'Borrador', 'Resumen', 'Apuntes', 'Texto Plano', 'Novelas', 'Prompt')
            """)
            
            # 3. Clasificar los fragmentos de código
            cursor.execute("""
                UPDATE clips 
                SET tipo = 'codigo' 
                WHERE categoria LIKE 'Codigo:%'
            """)

            conn.commit()
            print("  [\033[92m  OK  \033[0m] Migración estructural: columna 'tipo' incorporada y registros clasificados.")
        except Exception as e:
            print(f"  [\033[91m ERROR \033[0m] Fallo al migrar columna 'tipo': {e}")

def obtener_conexion():
    migrar_base_antigua()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_db():
    migrar_base_antigua()
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    # 1. Tabla de clips, notas y código
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT UNIQUE NOT NULL,
            titulo TEXT,
            contenido TEXT NOT NULL,
            categoria TEXT DEFAULT 'General',
            tipo TEXT DEFAULT 'clip',
            fecha_creacion INTEGER NOT NULL,
            expira_en INTEGER,
            vistas_restantes INTEGER DEFAULT -1,
            es_favorito INTEGER DEFAULT 0
        )
    """)

    # 2. Tabla dedicada para Documentos & Math Studio
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

    # Ejecutar migración de columna 'tipo' para bases de datos existentes
    migrar_columna_tipo(conn)

    conn.close()

def purgar_expirados():
    ahora = int(time.time())
    conn = obtener_conexion()
    conn.execute("DELETE FROM clips WHERE expira_en IS NOT NULL AND expira_en <= ? AND es_favorito = 0", (ahora,))
    conn.commit()
    conn.close()