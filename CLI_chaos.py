import os
import sys
import glob
import sqlite3
import shutil
import time
from dotenv import dotenv_values, set_key

DIRECTORIO_RAIZ = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DIRECTORIO_RAIZ, "pcm.db")
ENV_PATH = os.path.join(DIRECTORIO_RAIZ, ".env")
UPLOADS_DIR = os.path.join(DIRECTORIO_RAIZ, "static", "uploads", "documentos")
BACKUPS_DIR = os.path.join(DIRECTORIO_RAIZ, "backups")
RUTA_ULTIMO_BACKUP = os.path.join(DIRECTORIO_RAIZ, "ultimo_backup.txt")


def limpiar_pantalla():
    os.system("cls" if os.name == "nt" else "clear")


def validar_seguridad_debug():
    """Bloquea la ejecución si FLASK_DEBUG no es explícitamente 'true' en el .env."""
    if not os.path.exists(ENV_PATH):
        print("\n[-] Error crítico: Archivo .env ausente. Operación de caos cancelada.")
        sys.exit(1)

    cfg = dotenv_values(ENV_PATH)
    debug_val = cfg.get("FLASK_DEBUG", "false").strip("'\"").lower()

    if debug_val != "true":
        limpiar_pantalla()
        print("=" * 70)
        print(" [!] ACCESO RESTRINGIDO :: MODO DEBUG INACTIVO")
        print("=" * 70)
        print(" Por seguridad, el generador de caos exige FLASK_DEBUG=true en .env.")
        print(" Active el modo debug mediante CLI_admin.py antes de realizar pruebas.")
        print(" Asegúrese de contar con respaldos de pcm.db y .env.")
        print("=" * 70 + "\n")
        sys.exit(1)


def pausar():
    input("\nPresione ENTER para continuar...")


# ==========================================
# VECTORES: CORRUPCIÓN DE BASE DE DATOS
# ==========================================

def corromper_cabecera_sqlite():
    """Destruye el Magic Header de 16 bytes de SQLite ('SQLite format 3\\000')."""
    if not os.path.exists(DB_PATH):
        print("[-] 'pcm.db' no existe.")
        return
    try:
        with open(DB_PATH, "r+b") as f:
            f.seek(0)
            f.write(b"CORRUPT_HEADER!!")
        print("[+] Éxito: Cabecera destruida. SQLite reportará 'file is not a database'.")
    except Exception as e:
        print(f"[-] Fallo al alterar cabecera: {e}")
    pausar()


def corromper_arbol_b():
    """Inyecta ruido binario en el cuerpo de datos para romper la consistencia de páginas."""
    if not os.path.exists(DB_PATH):
        print("[-] 'pcm.db' no existe.")
        return
    try:
        tam = os.path.getsize(DB_PATH)
        if tam < 1024:
            print("[-] Base de datos demasiado pequeña para fragmentar páginas.")
            return
        with open(DB_PATH, "r+b") as f:
            f.seek(tam // 2)
            f.write(os.urandom(128))
        print("[+] Éxito: Ruido inyectado. 'PRAGMA integrity_check' fallará.")
    except Exception as e:
        print(f"[-] Fallo al inyectar ruido: {e}")
    pausar()


def romper_esquema_tablas():
    """Elimina tablas críticas dejando el archivo de base de datos vivo (Schema Drift)."""
    if not os.path.exists(DB_PATH):
        print("[-] 'pcm.db' no existe.")
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DROP TABLE IF EXISTS documentos")
        conn.commit()
        conn.close()
        print("[+] Éxito: Tabla 'documentos' eliminada. Las consultas web lanzarán 'no such table'.")
    except Exception as e:
        print(f"[-] Error al eliminar tabla: {e}")
    pausar()


def eliminar_solo_db():
    """Borra pcm.db conservando el .env intacto."""
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print("[+] Éxito: 'pcm.db' borrado. Simula pérdida abrupta de almacenamiento.")
        except Exception as e:
            print(f"[-] Fallo al borrar: {e}")
    else:
        print("[i] 'pcm.db' ya se encuentra ausente.")
    pausar()


def bloquear_archivo_db():
    """Abre pcm.db con bloqueo exclusivo para simular un proceso trabado o colisión SQLite."""
    if not os.path.exists(DB_PATH):
        print("[-] 'pcm.db' no existe.")
        pausar()
        return
    print("\n[!] Bloqueando 'pcm.db' en modo EXCLUSIVE...")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=0.1)
        conn.isolation_level = "EXCLUSIVE"
        conn.execute("BEGIN EXCLUSIVE")
        print("[✓] Candado activo: Cualquier consulta de app.py lanzará 'database is locked'.")
        input("    Presione ENTER para liberar el candado y cerrar la conexión...")
        conn.rollback()
        conn.close()
        print("[+] Candado liberado.")
    except Exception as e:
        print(f"[-] Error al bloquear base de datos: {e}")
    pausar()


# ==========================================
# VECTORES: SISTEMA DE ARCHIVOS Y MULTIMEDIA
# ==========================================

def borrar_carpeta_uploads():
    """Elimina el directorio físico de imágenes."""
    if os.path.exists(UPLOADS_DIR):
        try:
            shutil.rmtree(UPLOADS_DIR)
            print("[+] Éxito: Carpeta 'static/uploads/documentos' eliminada por completo.")
        except Exception as e:
            print(f"[-] Fallo al borrar: {e}")
    else:
        print("[i] La carpeta de uploads ya estaba ausente.")
    pausar()


def inyectar_imagenes_basura():
    """Crea imágenes corruptas de 0 bytes o contenido inválido en uploads."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    try:
        # Archivo vacío
        with open(os.path.join(UPLOADS_DIR, "img_corrupta_vacia.png"), "wb") as f:
            pass
        # Archivo con texto en vez de imagen binaria
        with open(os.path.join(UPLOADS_DIR, "img_falsa_binaria.jpg"), "w") as f:
            f.write("ESTO_NO_ES_UN_JPG_VALIDO_SINO_TEXTO_PLANO")
        print("[+] Éxito: 2 imágenes corruptas creadas en 'static/uploads/documentos/'.")
    except Exception as e:
        print(f"[-] Error: {e}")
    pausar()


# ==========================================
# VECTORES: SABOTAJE DE CONFIGURACIÓN (.env)
# ==========================================

def sabotear_red_puerto():
    """Asigna valores fuera de rango a PORT y HOST."""
    if not os.path.exists(ENV_PATH):
        print("[-] .env ausente.")
        return
    set_key(ENV_PATH, "PORT", "99999")
    set_key(ENV_PATH, "HOST", "999.999.999.999")
    print("[+] Éxito: Configurado PORT=99999 y HOST=999.999.999.999 en .env.")
    pausar()


def vaciar_claves_seguridad():
    """Vacía SECRET_KEY y MASTER_KEY."""
    if not os.path.exists(ENV_PATH):
        print("[-] .env ausente.")
        return
    set_key(ENV_PATH, "SECRET_KEY", "")
    set_key(ENV_PATH, "MASTER_KEY", "")
    print("[+] Éxito: SECRET_KEY y MASTER_KEY vaciadas en .env.")
    pausar()


def corromper_archivo_env():
    """Sobrescribe el .env con bytes inválidos no interpretables."""
    if not os.path.exists(ENV_PATH):
        print("[-] .env no existe.")
        return
    try:
        with open(ENV_PATH, "wb") as f:
            f.write(b"\x00\xFF\xFE\x00_CORRUPT_ENV_DATA_#@!")
        print("[+] Éxito: .env sobrescrito con datos binarios rotos.")
    except Exception as e:
        print(f"[-] Error: {e}")
    pausar()


# ==========================================
# VECTORES: BACKUPS & CUARENTENA
# ==========================================

def corromper_timestamp_backup():
    """Inyecta texto no parseable en ultimo_backup.txt."""
    with open(RUTA_ULTIMO_BACKUP, "w") as f:
        f.write("TIMESTAMP_INVALIDO_TEXTO_BASURA")
    print("[+] Éxito: 'ultimo_backup.txt' contiene texto corrupto no numérico.")
    pausar()


def limpiar_archivos_cuarentena():
    """Limpia todos los residuos generados durante pruebas de estrés, incluidos los archivos ocultos .env."""
    patrones = [
        os.path.join(DIRECTORIO_RAIZ, "pcm.db.corrupt_*"),
        os.path.join(DIRECTORIO_RAIZ, ".env.corrupt_*"),     # Captura explícita para archivos con punto
        os.path.join(DIRECTORIO_RAIZ, "*.corrupt_*"),
        os.path.join(UPLOADS_DIR, "img_corrupta_*"),
        os.path.join(UPLOADS_DIR, "img_falsa_*")
    ]
    borrados = 0
    for pat in patrones:
        for arch in glob.glob(pat):
            try:
                os.remove(arch)
                borrados += 1
                print(f"[+] Eliminado de cuarentena: {os.path.basename(arch)}")
            except Exception as e:
                print(f"[-] No se pudo eliminar {os.path.basename(arch)}: {e}")

    print(f"\n[✓] Limpieza completada: {borrados} archivo(s) removidos.")
    pausar()


def estado_archivos():
    """Muestra el estado del entorno reconociendo archivos .env en cuarentena."""
    print("\n--- ESTADO DEL ENTORNO LOCAL ---")
    print(f" .env:          {'PRESENTE' if os.path.exists(ENV_PATH) else 'AUSENTE'}")
    tam_db = str(os.path.getsize(DB_PATH)) + " bytes" if os.path.exists(DB_PATH) else "AUSENTE"
    print(f" pcm.db:        {tam_db}")
    cant_img = len(os.listdir(UPLOADS_DIR)) if os.path.exists(UPLOADS_DIR) else "DIR INEXISTENTE"
    print(f" Uploads docs:  {cant_img}")

    # Conteo exacto sumando la base y los archivos .env aislados
    corruptos_db = glob.glob(os.path.join(DIRECTORIO_RAIZ, "pcm.db.corrupt_*"))
    corruptos_env = glob.glob(os.path.join(DIRECTORIO_RAIZ, ".env.corrupt_*"))
    total_cuarentena = len(corruptos_db) + len(corruptos_env)

    print(f" Cuarentena:    {total_cuarentena} archivo(s)")
    print("-" * 33)


# ==========================================
# INTERFAZ PRINCIPAL
# ==========================================

def estado_archivos():
    print("\n--- ESTADO DEL ENTORNO LOCAL ---")
    print(f" .env:          {'PRESENTE' if os.path.exists(ENV_PATH) else 'AUSENTE'}")
    tam_db = str(os.path.getsize(DB_PATH)) + " bytes" if os.path.exists(DB_PATH) else "AUSENTE"
    print(f" pcm.db:        {tam_db}")
    cant_img = len(os.listdir(UPLOADS_DIR)) if os.path.exists(UPLOADS_DIR) else "DIR INEXISTENTE"
    print(f" Uploads docs:  {cant_img}")
    corruptos = glob.glob(os.path.join(DIRECTORIO_RAIZ, "pcm.db.corrupt_*"))
    print(f" Cuarentena:    {len(corruptos)} archivo(s)")
    print("-" * 33)


def menu():
    while True:
        validar_seguridad_debug()
        limpiar_pantalla()
        estado_archivos()

        print("\nSIMULADOR DE CAOS & ESTRÉS :: PCMPrivateClipManager (DEBUG MODE)")
        print(" [ BASE DE DATOS SQLITE ]")
        print("  1. Corromper cabecera de pcm.db (Magic Header inválido)")
        print("  2. Corromper árbol de páginas (Fallo de integridad)")
        print("  3. Borrar tabla 'documentos' (Schema Drift / Column mismatch)")
        print("  4. Bloquear pcm.db con candado exclusivo (Database locked)")
        print("  5. Borrar archivo pcm.db (Simular pérdida accidental)")
        print("")
        print(" [ ARCHIVOS & MULTIMEDIA ]")
        print("  6. Borrar directorio static/uploads/documentos/")
        print("  7. Inyectar imágenes corruptas de 0 bytes")
        print("")
        print(" [ ENTORNO & .ENV ]")
        print("  8. Inyectar puerto/host inválidos (PORT=99999)")
        print("  9. Vaciar SECRET_KEY y MASTER_KEY")
        print(" 10. Corromper archivo .env con bytes basura")
        print("")
        print(" [ MANTENIMIENTO ]")
        print(" 11. Corromper ultimo_backup.txt")
        print(" 12. Limpiar archivos de cuarentena y pruebas (.corrupt_*)")
        print("  0. Salir")

        op = input("\nSelecciona un vector de caos: ").strip()

        if op == "1":
            corromper_cabecera_sqlite()
        elif op == "2":
            corromper_arbol_b()
        elif op == "3":
            romper_esquema_tablas()
        elif op == "4":
            bloquear_archivo_db()
        elif op == "5":
            eliminar_solo_db()
        elif op == "6":
            borrar_carpeta_uploads()
        elif op == "7":
            inyectar_imagenes_basura()
        elif op == "8":
            sabotear_red_puerto()
        elif op == "9":
            vaciar_claves_seguridad()
        elif op == "10":
            corromper_archivo_env()
        elif op == "11":
            corromper_timestamp_backup()
        elif op == "12":
            limpiar_archivos_cuarentena()
        elif op == "0":
            print("[*] Saliendo del simulador de caos.")
            break
        else:
            print("[-] Opción no válida.")
            time.sleep(0.8)


if __name__ == "__main__":
    validar_seguridad_debug()
    menu()