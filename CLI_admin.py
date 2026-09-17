import os
import sys
import time
import glob
import secrets
import sqlite3
import shutil
from datetime import datetime
from dotenv import load_dotenv, set_key

ES_EXE = getattr(sys, "frozen", False)
if ES_EXE:
    DIRECTORIO_RAIZ = os.path.dirname(sys.executable)
else:
    DIRECTORIO_RAIZ = os.path.dirname(os.path.abspath(__file__))

ENV_PATH = os.path.join(DIRECTORIO_RAIZ, ".env")
DB_PATH = os.path.join(DIRECTORIO_RAIZ, "pcm.db")
RUTA_ULTIMO_BACKUP = os.path.join(DIRECTORIO_RAIZ, "ultimo_backup.txt")
CARPETA_IMAGENES = os.path.join(DIRECTORIO_RAIZ, "static", "uploads", "documentos")
CARPETA_BACKUPS = os.path.join(DIRECTORIO_RAIZ, "backups")


def limpiar_pantalla():
    os.system("cls" if os.name == "nt" else "clear")


def formatear_bytes(b):
    if b < 1024:
        return f"{b} B"
    elif b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b / (1024 * 1024):.2f} MB"


def verificar_entorno():
    """Bloquea el acceso al panel si no existe un archivo .env generado."""
    if not os.path.exists(ENV_PATH):
        limpiar_pantalla()
        print("=" * 65)
        print("    [!] ERROR: ARCHIVO DE CONFIGURACIÓN (.env) NO DETECTADO")
        print("=" * 65)
        print(" La consola administrativa fuera de banda no puede operar")
        print(" sin un entorno base aprovisionado.")
        print("")
        print(" Inicie el servidor principal (app.py o el ejecutable) al menos")
        print(" una vez para generar las claves criptográficas e inicializar")
        print(" la base de datos.")
        print("=" * 65)
        input("\nPresione ENTER para salir...")
        sys.exit(1)


def obtener_resumen_db():
    if not os.path.exists(DB_PATH):
        return "DB no inicializada"
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*) FROM clips 
            WHERE categoria NOT IN ('Novelas', 'Borrador', 'Resumen') 
              AND categoria NOT LIKE 'Codigo:%'
        """)
        n_clips = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM clips WHERE categoria LIKE 'Codigo:%'")
        n_codigo = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM clips WHERE categoria IN ('Novelas', 'Borrador', 'Resumen')")
        n_borradores = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM documentos")
        n_docs = cur.fetchone()[0]

        conn.close()
        return f"{n_clips} clips | {n_codigo} cod | {n_borradores} bor | {n_docs} docs"
    except Exception:
        return "DB inaccesible"


def obtener_conteo_cuarentena():
    """Cuenta todos los archivos de aislamiento y pruebas en el directorio raíz."""
    patrones = [
        os.path.join(DIRECTORIO_RAIZ, "*.corrupt_*"),
        os.path.join(DIRECTORIO_RAIZ, ".env.corrupt_*"),
        os.path.join(DIRECTORIO_RAIZ, "pcm.db.corrupt_*"),
        os.path.join(CARPETA_IMAGENES, "img_corrupta_*"),
        os.path.join(CARPETA_IMAGENES, "img_falsa_*")
    ]
    archivos = set()
    for p in patrones:
        archivos.update(glob.glob(p))
    return len(archivos)


def obtener_info_disco():
    peso_db = "0 KB"
    if os.path.exists(DB_PATH):
        peso_db = formatear_bytes(os.path.getsize(DB_PATH))

    total_img = 0
    peso_img = 0
    if os.path.exists(CARPETA_IMAGENES):
        for arch in os.listdir(CARPETA_IMAGENES):
            ruta_f = os.path.join(CARPETA_IMAGENES, arch)
            if os.path.isfile(ruta_f):
                total_img += 1
                peso_img += os.path.getsize(ruta_f)

    cuarentena_cant = obtener_conteo_cuarentena()
    return f"DB: {peso_db} | Fotos: {total_img} ({formatear_bytes(peso_img)}) | Cuarentena: {cuarentena_cant}"


def obtener_info_backup():
    if os.path.exists(RUTA_ULTIMO_BACKUP):
        try:
            with open(RUTA_ULTIMO_BACKUP, "r") as f:
                ts = float(f.read().strip())
                return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "Corrupto"
    return "Nunca realizado"


def submenu_inspeccion(titulo, etiqueta, valor):
    limpiar_pantalla()
    print("=" * 65)
    print(f"             INSPECCIÓN DE SEGURIDAD :: {titulo.upper()}")
    print("=" * 65)
    print(f"\n {etiqueta}:")
    print(f" \033[92m{valor}\033[0m" if sys.stdout.isatty() else f" {valor}")
    print("\n" + "-" * 65)
    print("  1. Volver al menú principal")
    print("  2. Salir del programa")
    print("=" * 65)

    while True:
        opc = input("Selecciona una opción [1-2]: ").strip()
        if opc == "1":
            return
        elif opc == "2":
            print("\nCerrando consola de administración...")
            sys.exit(0)
        else:
            print("Opción inválida. Ingrese 1 o 2.")


def pausar():
    input("\nPresione ENTER para continuar...")


def purgar_imagenes_huerfanas_cli():
    limpiar_pantalla()
    print("=" * 65)
    print("        PURGA DE IMÁGENES HUÉRFANAS EN ALMACENAMIENTO")
    print("=" * 65)
    if not os.path.exists(CARPETA_IMAGENES):
        print("\n[INFO] La carpeta de imágenes no existe o está vacía.")
        pausar()
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT contenido FROM documentos")
        docs = cur.fetchall()
        cur.execute("SELECT contenido FROM clips")
        clips = cur.fetchall()
        conn.close()

        todo_el_texto = " ".join([(d[0] or "") for d in docs] + [(c[0] or "") for c in clips])
        archivos = [f for f in os.listdir(CARPETA_IMAGENES) if os.path.isfile(os.path.join(CARPETA_IMAGENES, f))]

        huerfanas = [f for f in archivos if f not in todo_el_texto and f != ".gitkeep"]

        if not huerfanas:
            print("\n[✓] Almacenamiento limpio: no se detectaron archivos huérfanos.")
            pausar()
            return

        print(f"\nSe encontraron {len(huerfanas)} imágenes sin enlace en la base de datos:")
        for h in huerfanas[:10]:
            print(f"  - {h}")
        if len(huerfanas) > 10:
            print(f"  ... y {len(huerfanas) - 10} más.")

        conf = input("\n¿Desea eliminarlas permanentemente del disco? (s/N): ").strip().lower()
        if conf == "s":
            borrados = 0
            bytes_liberados = 0
            for f in huerfanas:
                ruta = os.path.join(CARPETA_IMAGENES, f)
                try:
                    tam = os.path.getsize(ruta)
                    os.remove(ruta)
                    borrados += 1
                    bytes_liberados += tam
                except Exception as e:
                    print(f"[!] Error al eliminar {f}: {e}")
            print(f"\n[✓] Purga exitosa: {borrados} archivos borrados ({formatear_bytes(bytes_liberados)} liberados).")
        else:
            print("\n[INFO] Operación cancelada.")
    except Exception as e:
        print(f"\n[ERROR] Falló el escaneo de base de datos: {e}")

    pausar()


def limpiar_cuarentena_cli():
    limpiar_pantalla()
    print("=" * 65)
    print("         LIMPIEZA DE ARCHIVOS EN CUARENTENA Y PRUEBAS")
    print("=" * 65)

    patrones = [
        os.path.join(DIRECTORIO_RAIZ, "pcm.db.corrupt_*"),
        os.path.join(DIRECTORIO_RAIZ, ".env.corrupt_*"),
        os.path.join(DIRECTORIO_RAIZ, "*.corrupt_*"),
        os.path.join(CARPETA_IMAGENES, "img_corrupta_*"),
        os.path.join(CARPETA_IMAGENES, "img_falsa_*")
    ]
    archivos = set()
    for p in patrones:
        archivos.update(glob.glob(p))

    if not archivos:
        print("\n[✓] No se detectaron archivos de cuarentena o sabotaje pendientes.")
        pausar()
        return

    print(f"\nSe detectaron {len(archivos)} archivo(s) aislados en el entorno:")
    for a in sorted(archivos):
        print(f"  - {os.path.basename(a)}")

    conf = input("\n¿Desea eliminarlos permanentemente? (s/N): ").strip().lower()
    if conf == "s":
        borrados = 0
        for a in archivos:
            try:
                os.remove(a)
                borrados += 1
            except Exception as e:
                print(f"[!] No se pudo eliminar {os.path.basename(a)}: {e}")
        print(f"\n[✓] Limpieza exitosa: {borrados} archivo(s) eliminados de la raíz.")
    else:
        print("\n[INFO] Operación cancelada.")

    pausar()


def main():
    while True:
        verificar_entorno()
        limpiar_pantalla()
        load_dotenv(ENV_PATH, override=True)

        host = os.environ.get("HOST", "127.0.0.1")
        port = os.environ.get("PORT", "5545")
        debug = "Sí" if os.environ.get("FLASK_DEBUG", "false").lower() == "true" else "No"
        logs = "Sí" if os.environ.get("LOG_MODE", "false").lower() == "true" else "No"
        auto_nav = "Sí" if os.environ.get("AUTO_ABRIR_NAVEGADOR", "true").lower() == "true" else "No"

        tipo_red = "Global" if host == "0.0.0.0" else "Local"

        print("=" * 65)
        print("     PANEL DE CONTROL ADMINISTRATIVO :: PCMPrivateClipManager")
        print("=" * 65)
        print(f" Red: {host} ({tipo_red})   | Puerto HTTP: {port}")
        print(f" Registros: {obtener_resumen_db()}")
        print(f" Disco:     {obtener_info_disco()}")
        print(f" Estado:    Debug: {debug} | Logs Consola: {logs} | Auto-Nav: {auto_nav}")
        print("-" * 65)
        print(f" Último Backup Registrado: {obtener_info_backup()}")
        print("-" * 65)
        print(" GESTIÓN DE SEGURIDAD CRÍTICA")
        print("   P. Inspeccionar contraseña web (APP_PASSWORD)")
        print("   M. Inspeccionar MASTER_KEY (para desbloqueos web)")
        print("   1. Cambiar contraseña web (APP_PASSWORD)")
        print("   2. Rotar MASTER_KEY (Criptografía 256 bits)")
        print("   3. Rotar SECRET_KEY (Invalida sesiones activas)")
        print("   4. Rotar MASTER_KEY y SECRET_KEY simultáneamente")
        print("")
        print(" PREFERENCIAS Y ALCANCE DE RED")
        print("   5. Alternar Depuración Flask (FLASK_DEBUG)")
        print("   6. Alternar Registro en Consola (LOG_MODE)")
        print("   7. Cambiar Puerto HTTP de Escucha (PORT)")
        print("   8. Alternar Alcance de Red (Local 127.0.0.1 <-> Global 0.0.0.0)")
        print("   9. Alternar Auto-abrir Navegador al Iniciar (.exe)")
        print("")
        print(" MANTENIMIENTO Y ALMACENAMIENTO")
        print("   I. Purgar imágenes huérfanas en disco")
        print("   C. Limpiar archivos en cuarentena (.corrupt_*)")
        print("   R. Restaurar de fábrica (Eliminar DB, .env, fotos, backups y cuarentena)")
        print("   0. Salir")
        print("=" * 65)

        opcion = input("Selecciona una opción: ").strip().lower()

        if opcion == "p":
            pass_actual = os.environ.get("APP_PASSWORD", "cambiame")
            submenu_inspeccion("Contraseña de Acceso Web", "APP_PASSWORD CONFIGURADA", pass_actual)

        elif opcion == "m":
            master_actual = os.environ.get("MASTER_KEY", "No configurada")
            submenu_inspeccion("Llave Maestra", "MASTER_KEY CONFIGURADA", master_actual)

        elif opcion == "1":
            nueva_pass = input("\nIngrese la nueva contraseña web: ").strip()
            if nueva_pass:
                set_key(ENV_PATH, "APP_PASSWORD", nueva_pass)
                os.environ["APP_PASSWORD"] = nueva_pass
                print("[OK] Contraseña web actualizada.")
            else:
                print("[WARN] Operación cancelada: contraseña vacía.")
            pausar()

        elif opcion == "2":
            nueva_master = secrets.token_hex(32)
            set_key(ENV_PATH, "MASTER_KEY", nueva_master)
            os.environ["MASTER_KEY"] = nueva_master
            print(f"\n[OK] MASTER_KEY regenerada exitosamente.")
            pausar()

        elif opcion == "3":
            nueva_secret = secrets.token_hex(32)
            set_key(ENV_PATH, "SECRET_KEY", nueva_secret)
            os.environ["SECRET_KEY"] = nueva_secret
            print(f"\n[OK] SECRET_KEY regenerada. Todas las sesiones web fueron invalidadas.")
            pausar()

        elif opcion == "4":
            nueva_master = secrets.token_hex(32)
            nueva_secret = secrets.token_hex(32)
            set_key(ENV_PATH, "MASTER_KEY", nueva_master)
            set_key(ENV_PATH, "SECRET_KEY", nueva_secret)
            os.environ["MASTER_KEY"] = nueva_master
            os.environ["SECRET_KEY"] = nueva_secret
            print(f"\n[OK] Ambas llaves maestras regeneradas con éxito.")
            pausar()

        elif opcion == "5":
            val = "false" if debug == "Sí" else "true"
            set_key(ENV_PATH, "FLASK_DEBUG", val)
            print(f"\n[OK] FLASK_DEBUG configurado a: {val}")
            pausar()

        elif opcion == "6":
            val = "false" if logs == "Sí" else "true"
            set_key(ENV_PATH, "LOG_MODE", val)
            print(f"\n[OK] LOG_MODE configurado a: {val}")
            pausar()

        elif opcion == "7":
            nuevo_puerto = input("\nIngrese el nuevo puerto HTTP (ej. 5545): ").strip()
            if nuevo_puerto.isdigit() and 1 <= int(nuevo_puerto) <= 65535:
                set_key(ENV_PATH, "PORT", nuevo_puerto)
                print(f"[OK] Puerto actualizado a: {nuevo_puerto}")
            else:
                print("[FAIL] Puerto inválido.")
            pausar()

        elif opcion == "8":
            nuevo_host = "127.0.0.1" if host == "0.0.0.0" else "0.0.0.0"
            set_key(ENV_PATH, "HOST", nuevo_host)
            print(f"\n[OK] Escucha de red cambiada a: {nuevo_host}")
            pausar()

        elif opcion == "9":
            val = "false" if auto_nav == "Sí" else "true"
            set_key(ENV_PATH, "AUTO_ABRIR_NAVEGADOR", val)
            os.environ["AUTO_ABRIR_NAVEGADOR"] = val
            print(f"\n[OK] AUTO_ABRIR_NAVEGADOR configurado a: {val}")
            pausar()

        elif opcion == "i":
            purgar_imagenes_huerfanas_cli()

        elif opcion == "c":
            limpiar_cuarentena_cli()

        elif opcion == "r":
            print("\n" + "!" * 65)
            print(" PELIGRO: ESTA ACCIÓN ELIMINARÁ DB, .ENV, FOTOS, BACKUPS Y CUARENTENA")
            print("!" * 65)
            conf = input("Escriba 'CONFIRMAR' para proceder: ").strip()
            if conf == "CONFIRMAR":
                elementos_a_borrar = [DB_PATH, ENV_PATH, RUTA_ULTIMO_BACKUP]
                for f in elementos_a_borrar:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except Exception:
                            pass

                for carpeta in [CARPETA_IMAGENES, CARPETA_BACKUPS]:
                    if os.path.exists(carpeta):
                        try:
                            shutil.rmtree(carpeta)
                        except Exception:
                            pass

                # Purga total de cuarentena y restos temporales
                patrones_cuarentena = [
                    os.path.join(DIRECTORIO_RAIZ, "*.corrupt_*"),
                    os.path.join(DIRECTORIO_RAIZ, ".env.corrupt_*"),
                    os.path.join(DIRECTORIO_RAIZ, "pcm.db.corrupt_*"),
                    os.path.join(CARPETA_IMAGENES, "img_corrupta_*"),
                    os.path.join(CARPETA_IMAGENES, "img_falsa_*")
                ]
                for pat in patrones_cuarentena:
                    for arch in glob.glob(pat):
                        try:
                            os.remove(arch)
                        except Exception:
                            pass

                print("\n[OK] Sistema restaurado a estado inicial de fábrica.")
                pausar()
                sys.exit(0)
            else:
                print("\n[INFO] Restauración cancelada.")
                pausar()

        elif opcion == "0":
            print("\nCerrando consola de administración...")
            break


if __name__ == "__main__":
    verificar_entorno()
    main()