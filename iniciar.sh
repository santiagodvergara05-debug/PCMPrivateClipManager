#!/usr/bin/env bash

# Posicionarse en la carpeta del script
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "==================================================="
echo "       INICIANDO PCMPrivateClipManager LOCAL       "
echo "==================================================="

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "[!] Entorno virtual no encontrado. Usando Python del sistema..."
fi

# Abrir el navegador en segundo plano
(sleep 1.2 && (xdg-open http://127.0.0.1:5545 2>/dev/null || open http://127.0.0.1:5545 2>/dev/null)) &

# Ejecutar servidor
python3 app.py