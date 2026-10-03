"""
==============================================================================
PCM PRIVATE CLIP MANAGER - SIMULADOR DE CAOS & ESTRÉS (CLI_CHAOS.PY)
==============================================================================
Herramienta de Ingeniería del Caos para pruebas de resiliencia y autorreparación:
1. Sabotaje de integridad de base de datos SQLite (Headers, B-Tree, Schema Drift).
2. Concurrencia y bloqueos exclusivos de archivos de base de datos.
3. Destrucción de directorios multimedia e inyección de huérfanos.
4. Sabotaje binario y de red del archivo de configuración .env.
5. Inyección de caos en sincronización BYOC (Bóvedas truncadas, SHA-256, Meta).
6. Limpieza integral de cuarentena y residuos de prueba.
==============================================================================
"""

import os
import sys
import glob
import json
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
RUTA_ULTIMO_SYNC = os.path.join(DIRECTORIO_RAIZ, "ultimo_sync.txt")


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


def obtener_carpeta_nube():
    """Obtiene la carpeta configurada en SYNC_CARPETA si existe."""
    if not os.path.exists(ENV_PATH):
        return None
    cfg = dotenv_values(ENV_PATH)
    carp = cfg.get("SYNC_CARPETA", "").strip("'\"")
    return carp if (carp and os.path.isdir(carp)) else None


# ==============================================================================
# VECTORES: CORRUPCIÓN DE BASE DE DATOS SQLITE
# ==============================================================================

def corromper_cabecera_sqlite():
    """Destruye el Magic Header de 16 bytes de SQLite ('SQLite format 3\\000')."""
    if not os.path.exists(DB_PATH):
        print("[-] 'pcm.db' no existe.")
        pausar()
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
        pausar()
        return
    try:
        tam = os.path.getsize(DB_PATH)
        if tam < 1024:
            print("[-] Base de datos demasiado pequeña para fragmentar páginas.")
            pausar()
            return
        with open(DB_PATH, "r+b") as f:
            f.seek(tam // 2)
            f.write(os.urandom(128))
        print("[+] Éxito: Ruido inyectado. 'PRAGMA integrity_check' fallará.")
    except Exception as e:
        print(f"[-] Fallo al inyectar ruido: {e}")
    pausar()


def romper_esquema_tablas():
    """Elimina la tabla 'documentos' dejando la base viva (Schema Drift)."""
    if not os.path.exists(DB_PATH):
        print("[-] 'pcm.db' no existe.")
        pausar()
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DROP TABLE IF EXISTS documentos")
        conn.commit()
        conn.close()
        print("[+] Éxito: Tabla 'documentos' eliminada. Prueba autocuración en app.py.")
    except Exception as e:
        print(f"[-] Error al eliminar tabla: {e}")
    pausar()


def bloquear_archivo_db():
    """Abre pcm.db con bloqueo exclusivo para simular un proceso bloqueante."""
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


def eliminar_solo_db():
    """Borra pcm.db conservando el resto intacto."""
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print("[+] Éxito: 'pcm.db' borrado. Simula pérdida accidental o desastre de disco.")
        except Exception as e:
            print(f"[-] Fallo al borrar: {e}")
    else:
        print("[i] 'pcm.db' ya se encuentra ausente.")
    pausar()


# ==============================================================================
# VECTORES: SISTEMA DE ARCHIVOS Y MULTIMEDIA
# ==============================================================================

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
    """Crea imágenes corruptas de 0 bytes y texto plano."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    try:
        with open(os.path.join(UPLOADS_DIR, "img_corrupta_vacia.png"), "wb") as f:
            pass
        with open(os.path.join(UPLOADS_DIR, "img_falsa_binaria.jpg"), "w") as f:
            f.write("ESTO_NO_ES_UN_JPG_VALIDO_SINO_TEXTO_PLANO")
        print("[+] Éxito: 2 imágenes anómalas inyectadas en uploads.")
    except Exception as e:
        print(f"[-] Error: {e}")
    pausar()


# ==============================================================================
# VECTORES: SABOTAJE DE CONFIGURACIÓN (.ENV)
# ==============================================================================

def sabotear_red_puerto():
    """Asigna valores fuera de rango a PORT y HOST."""
    if not os.path.exists(ENV_PATH):
        print("[-] .env ausente.")
        pausar()
        return
    set_key(ENV_PATH, "PORT", "99999")
    set_key(ENV_PATH, "HOST", "999.999.999.999")
    print("[+] Éxito: Configurado PORT=99999 y HOST=999.999.999.999 en .env.")
    pausar()


def vaciar_claves_seguridad():
    """Vacía SECRET_KEY y MASTER_KEY."""
    if not os.path.exists(ENV_PATH):
        print("[-] .env ausente.")
        pausar()
        return
    set_key(ENV_PATH, "SECRET_KEY", "")
    set_key(ENV_PATH, "MASTER_KEY", "")
    print("[+] Éxito: SECRET_KEY y MASTER_KEY vaciadas en .env.")
    pausar()


def corromper_archivo_env():
    """Sobrescribe el .env con bytes nulos no interpretables."""
    if not os.path.exists(ENV_PATH):
        print("[-] .env no existe.")
        pausar()
        return
    try:
        with open(ENV_PATH, "wb") as f:
            f.write(b"\x00\xFF\xFE\x00_CORRUPT_ENV_DATA_#@!")
        print("[+] Éxito: .env sobrescrito con datos binarios rotos.")
    except Exception as e:
        print(f"[-] Error: {e}")
    pausar()


# ==============================================================================
# VECTORES: SINCRONIZACIÓN BYOC & INTEGRIDAD CRIPTOGRÁFICA
# ==============================================================================

def corromper_boveda_zip_nube():
    """Mutila pcm_vault.zip y fuerza una revisión remota superior para probar el rechazo por SHA-256."""
    nube = obtener_carpeta_nube()
    if not nube:
        print("[-] SYNC_CARPETA no configurada o inaccesible.")
        pausar()
        return
    ruta_zip = os.path.join(nube, "pcm_vault.zip")
    ruta_meta = os.path.join(nube, "pcm_vault.meta")
    if not os.path.exists(ruta_zip):
        print(f"[-] No se encontró 'pcm_vault.zip' en: {nube}")
        pausar()
        return
    try:
        # 1. Truncar y corromper el contenido binario del ZIP
        tam = os.path.getsize(ruta_zip)
        with open(ruta_zip, "r+b") as f:
            f.seek(max(0, tam // 2))
            f.write(b"CORRUPTED_ZIP_STREAM_CHAOS_BYTE_INJECTION")
            f.truncate(max(100, tam - 200))

        # 2. Incrementar la revisión en el .meta para obligar al bootloader/UI a intentar descargarlo
        if os.path.exists(ruta_meta):
            try:
                with open(ruta_meta, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                datos["revision"] = int(datos.get("revision", 0)) + 1
                with open(ruta_meta, "w", encoding="utf-8") as f:
                    json.dump(datos, f, indent=2)
                print(f"[+] 'pcm_vault.meta' actualizado a #{datos['revision']} para forzar el intento de descarga.")
            except Exception:
                pass

        print("[+] Éxito: 'pcm_vault.zip' mutilado. La verificación SHA-256 debe abortar cualquier intento de aplicación.")
    except Exception as e:
        print(f"[-] Error: {e}")
    pausar()


def corromper_metadatos_nube():
    """Sobrescribe pcm_vault.meta con JSON corrupto / roto."""
    nube = obtener_carpeta_nube()
    if not nube:
        print("[-] SYNC_CARPETA no configurada o inaccesible.")
        pausar()
        return
    ruta_meta = os.path.join(nube, "pcm_vault.meta")
    if not os.path.exists(ruta_meta):
        print(f"[-] No se encontró 'pcm_vault.meta' en: {nube}")
        pausar()
        return
    try:
        with open(ruta_meta, "w", encoding="utf-8") as f:
            f.write("{'revision': 'BROKEN_JSON_SYNTAX_ERROR',,,,,,")
        print("[+] Éxito: 'pcm_vault.meta' saboteado. El sistema debe operar en modo local sin crashear.")
    except Exception as e:
        print(f"[-] Error: {e}")
    pausar()


def sabotear_revision_nube():
    """Modifica la revisión del meta remoto fijándola a #99999 (tolerante a JSON rotos previos)."""
    nube = obtener_carpeta_nube()
    if not nube:
        print("[-] SYNC_CARPETA no configurada o inaccesible.")
        pausar()
        return
    ruta_meta = os.path.join(nube, "pcm_vault.meta")
    try:
        datos = {}
        if os.path.exists(ruta_meta):
            try:
                with open(ruta_meta, "r", encoding="utf-8") as f:
                    datos = json.load(f)
            except Exception:
                # Si el JSON fue roto previamente por el Vector 12, se reconstruye
                datos = {"algoritmo": "AES-256", "hash_sha256": "fake_hash"}

        datos["revision"] = 99999
        datos["ultimo_equipo"] = "Chaos-Node-Saboteur"
        with open(ruta_meta, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2)
        print("[+] Éxito: Revisión en la nube fijada a #99999. El botón de subida debe quedar bloqueado.")
    except Exception as e:
        print(f"[-] Error: {e}")
    pausar()


def corromper_timestamp_sync():
    """Inyecta texto basura en ultimo_sync.txt."""
    try:
        with open(RUTA_ULTIMO_SYNC, "w", encoding="utf-8") as f:
            f.write("TIMESTAMP_SYNC_CORRUPTO_ERROR")
        print("[+] Éxito: 'ultimo_sync.txt' contiene texto corrupto no numérico.")
    except Exception as e:
        print(f"[-] Error: {e}")
    pausar()


def sembrar_temporales_sync():
    """Crea archivos .pre_sync y .zip.tmp para probar la purga del bootloader."""
    try:
        with open(os.path.join(DIRECTORIO_RAIZ, "pcm.db.pre_sync"), "w") as f:
            f.write("RESIDUO_PRE_SYNC_ABORTADO")
        with open(os.path.join(DIRECTORIO_RAIZ, "pcm_vault.zip.tmp"), "w") as f:
            f.write("RESIDUO_TEMP_DESCARGA_INCOMPLETA")
        print("[+] Éxito: Creados 'pcm.db.pre_sync' y 'pcm_vault.zip.tmp'.")
    except Exception as e:
        print(f"[-] Error: {e}")
    pausar()


# ==============================================================================
# VECTORES: RESPALDOS Y CUARENTENA
# ==============================================================================

def corromper_timestamp_backup():
    """Inyecta texto no parseable en ultimo_backup.txt."""
    try:
        with open(RUTA_ULTIMO_BACKUP, "w", encoding="utf-8") as f:
            f.write("TIMESTAMP_INVALIDO_TEXTO_BASURA")
        print("[+] Éxito: 'ultimo_backup.txt' contiene texto corrupto no numérico.")
    except Exception as e:
        print(f"[-] Error: {e}")
    pausar()


def limpiar_archivos_cuarentena():
    """Limpia todos los residuos generados durante pruebas de estrés."""
    patrones = [
        os.path.join(DIRECTORIO_RAIZ, "pcm.db.corrupt_*"),
        os.path.join(DIRECTORIO_RAIZ, ".env.corrupt_*"),
        os.path.join(DIRECTORIO_RAIZ, "*.corrupt_*"),
        os.path.join(DIRECTORIO_RAIZ, "*.pre_sync"),
        os.path.join(DIRECTORIO_RAIZ, "*.zip.tmp"),
        os.path.join(DIRECTORIO_RAIZ, "*.db.tmp"),
        os.path.join(UPLOADS_DIR, "img_corrupta_*"),
        os.path.join(UPLOADS_DIR, "img_falsa_*")
    ]
    borrados = 0
    for pat in patrones:
        for arch in glob.glob(pat):
            try:
                os.remove(arch)
                borrados += 1
                print(f"[+] Eliminado de cuarentena/prueba: {os.path.basename(arch)}")
            except Exception as e:
                print(f"[-] No se pudo eliminar {os.path.basename(arch)}: {e}")

    print(f"\n[✓] Limpieza completada: {borrados} archivo(s) removidos.")
    pausar()


# ==============================================================================
# MONITOR DE ESTADO Y MENÚ INTERACTIVO
# ==============================================================================

def estado_archivos():
    """Muestra el estado en tiempo real del entorno, nube y cuarentena."""
    print("\n--- ESTADO DEL ENTORNO LOCAL & NUBE ---")
    print(f" .env:          {'PRESENTE' if os.path.exists(ENV_PATH) else 'AUSENTE'}")
    tam_db = f"{os.path.getsize(DB_PATH)} bytes" if os.path.exists(DB_PATH) else "AUSENTE"
    print(f" pcm.db:        {tam_db}")
    cant_img = len(os.listdir(UPLOADS_DIR)) if os.path.exists(UPLOADS_DIR) else "DIR INEXISTENTE"
    print(f" Uploads docs:  {cant_img}")

    # Telemetría de sincronización BYOC
    nube = obtener_carpeta_nube()
    if nube:
        meta_p = os.path.join(nube, "pcm_vault.meta")
        if os.path.exists(meta_p):
            try:
                with open(meta_p, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                print(f" Nube BYOC:     CONECTADA (Revisión #{meta.get('revision')} - {meta.get('ultimo_equipo')})")
            except Exception:
                print(" Nube BYOC:     CONECTADA (Metadatos .meta CORRUPTOS)")
        else:
            print(" Nube BYOC:     CONECTADA (Sin bóveda activa)")
    else:
        print(" Nube BYOC:     DESCONECTADA / NO CONFIGURADA")

    # Conteo exacto de archivos en cuarentena
    corruptos_db = glob.glob(os.path.join(DIRECTORIO_RAIZ, "pcm.db.corrupt_*"))
    corruptos_env = glob.glob(os.path.join(DIRECTORIO_RAIZ, ".env.corrupt_*"))
    print(f" Cuarentena:    {len(corruptos_db) + len(corruptos_env)} archivo(s)")
    print("-" * 40)


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
        print("  7. Inyectar imágenes corruptas de 0 bytes y texto")
        print("")
        print(" [ ENTORNO & .ENV ]")
        print("  8. Inyectar puerto/host inválidos (PORT=99999)")
        print("  9. Vaciar SECRET_KEY y MASTER_KEY")
        print(" 10. Corromper archivo .env con bytes basura")
        print("")
        print(" [ SINCRONIZACIÓN BYOC & INTEGRIDAD ]")
        print(" 11. Mutilar / Truncar pcm_vault.zip en la nube (Test SHA-256)")
        print(" 12. Corromper metadatos pcm_vault.meta en la nube")
        print(" 13. Forzar conflicto de revisión remota superior (#99999)")
        print(" 14. Corromper testigo local ultimo_sync.txt")
        print(" 15. Sembrar archivos temporales atómicos (*.pre_sync, *.tmp)")
        print("")
        print(" [ MANTENIMIENTO ]")
        print(" 16. Corromper ultimo_backup.txt")
        print(" 17. Limpiar archivos de cuarentena y pruebas (.corrupt_*, *.tmp)")
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
            corromper_boveda_zip_nube()
        elif op == "12":
            corromper_metadatos_nube()
        elif op == "13":
            sabotear_revision_nube()
        elif op == "14":
            corromper_timestamp_sync()
        elif op == "15":
            sembrar_temporales_sync()
        elif op == "16":
            corromper_timestamp_backup()
        elif op == "17":
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