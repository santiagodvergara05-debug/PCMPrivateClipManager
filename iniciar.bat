@echo off
title PCMPrivateClipManager Server
color 0B
cd /d "%~dp0"

echo "==================================================="
echo "       INICIANDO PCMPrivateClipManager LOCAL       "
echo "==================================================="

:: Deteccion y activacion del entorno virtual
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo [!] Entorno virtual no encontrado. Usando Python del sistema...
)

:: Abrir navegador predeterminado en segundo plano tras 1 segundo
start "" cmd /c "timeout /t 1 /nobreak >nul && start http://127.0.0.1:5545"

:: Arrancar la aplicacion Flask
python app.py
pause