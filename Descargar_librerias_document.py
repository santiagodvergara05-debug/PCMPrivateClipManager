#!/usr/bin/env python3
"""
==============================================================================
PCM PRIVATE CLIP MANAGER - GESTOR DE DEPENDENCIAS FRONTEND OFFLINE / LAN
==============================================================================
Descarga librerías locales en /static/js/ y /static/css/ para garantizar
autonomía total sin conexión a Internet (Marked, DOMPurify, KaTeX + fuentes,
Marked-Footnote, Mermaid.js y Highlight.js).

Uso:
    python Descargar_librerias_document.py
==============================================================================
"""

import os
import re
import sys
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuración de rutas
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

JS_DIR = os.path.join(PROJECT_ROOT, "static", "js")
CSS_DIR = os.path.join(PROJECT_ROOT, "static", "css")
FONTS_DIR = os.path.join(CSS_DIR, "fonts")

KATEX_VERSION = "0.16.9"
DOMPURIFY_VERSION = "3.0.9"
HIGHLIGHT_VERSION = "11.9.0"

# Catálogo unificado de librerías estáticas: (URL, destino, nombre_archivo)
ARCHIVOS = [
    # 1. Compilación Markdown y sanitización DOM
    (
        "https://cdn.jsdelivr.net/npm/marked/marked.min.js",
        JS_DIR,
        "marked.min.js",
    ),
    (
        f"https://cdn.jsdelivr.net/npm/dompurify@{DOMPURIFY_VERSION}/dist/purify.min.js",
        JS_DIR,
        "purify.min.js",
    ),
    # 2. Motor matemático KaTeX
    (
        f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.js",
        JS_DIR,
        "katex.min.js",
    ),
    (
        f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.css",
        CSS_DIR,
        "katex.min.css",
    ),
    # 3. Extensiones y diagramación
    (
        "https://cdn.jsdelivr.net/npm/marked-footnote/dist/index.umd.min.js",
        JS_DIR,
        "marked-footnote.min.js",
    ),
    (
        "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js",
        JS_DIR,
        "mermaid.min.js",
    ),
    # 4. Resaltado sintáctico de código (Highlight.js + Tema GitHub Dark)
    (
        f"https://cdnjs.cloudflare.com/ajax/libs/highlight.js/{HIGHLIGHT_VERSION}/highlight.min.js",
        JS_DIR,
        "highlight.min.js",
    ),
    (
        f"https://cdnjs.cloudflare.com/ajax/libs/highlight.js/{HIGHLIGHT_VERSION}/styles/github-dark.min.css",
        CSS_DIR,
        "github-dark.min.css",
    ),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (descarga-librerias-script)"}


# ---------------------------------------------------------------------------
# Rutinas de descarga
# ---------------------------------------------------------------------------

def descargar(url: str, destino_carpeta: str, nombre_archivo: str) -> str:
    """Descarga una URL en destino_carpeta/nombre_archivo. Devuelve la ruta final."""
    os.makedirs(destino_carpeta, exist_ok=True)
    ruta_final = os.path.join(destino_carpeta, nombre_archivo)

    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req) as resp:
            contenido = resp.read()
    except urllib.error.URLError as e:
        print(f"  ✗ ERROR descargando {url}\n    {e}")
        return ""

    with open(ruta_final, "wb") as f:
        f.write(contenido)

    kb = len(contenido) / 1024
    print(f"  ✓ {nombre_archivo}  ({kb:.1f} KB)")
    return ruta_final


def descargar_fuentes_katex(ruta_css: str) -> None:
    """Extrae referencias 'fonts/...' en katex.min.css y descarga cada variante tipográfica."""
    if not ruta_css or not os.path.exists(ruta_css):
        print("  ✗ No se pudo leer katex.min.css, se omiten las fuentes.")
        return

    with open(ruta_css, "r", encoding="utf-8") as f:
        contenido_css = f.read()

    nombres_fuentes = sorted(set(re.findall(r'fonts/([^)"\']+)', contenido_css)))

    if not nombres_fuentes:
        print("  ✗ No se encontraron referencias a fuentes en el CSS.")
        return

    print(f"\nDescargando {len(nombres_fuentes)} archivos de fuentes de KaTeX...")
    base_url = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/fonts/"

    ok, fail = 0, 0
    for nombre in nombres_fuentes:
        resultado = descargar(base_url + nombre, FONTS_DIR, nombre)
        if resultado:
            ok += 1
        else:
            fail += 1

    print(f"Fuentes: {ok} descargadas, {fail} con error.")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  PCM - SINCRONIZADOR DE DEPENDENCIAS ESTÁTICAS OFFLINE")
    print("=" * 60)
    print(f"Directorio raíz: {PROJECT_ROOT}")
    print(f"  JS    -> {JS_DIR}")
    print(f"  CSS   -> {CSS_DIR}")
    print(f"  Fonts -> {FONTS_DIR}\n")

    print("Descargando librerías principales...")
    ruta_katex_css = ""
    for url, carpeta, nombre in ARCHIVOS:
        ruta = descargar(url, carpeta, nombre)
        if nombre == "katex.min.css":
            ruta_katex_css = ruta

    descargar_fuentes_katex(ruta_katex_css)

    print("\n" + "=" * 60)
    print("Sincronización finalizada con éxito.")
    print("El sistema cuenta con todos los recursos necesarios para operar offline.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelado por el usuario.")