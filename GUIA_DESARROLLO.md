---

# Guía de Entorno y Desarrollo Local

### 1. Extensiones recomendadas para VS Code

Herramientas necesarias para sintaxis, resaltado de plantillas y administración de base de datos:

* **Python** (`ms-python.python`): Soporte de lenguaje, depuración y autocompletado.


* **Pylance** (`ms-python.vscode-pylance`): Análisis estático de tipos y rendimiento.


* **Better Jinja** (`samuelcolvin.jinjahtml`): Resaltado de sintaxis para plantillas HTML de Flask.


* **DotENV** (`mikestead.dotenv`): Resaltado de sintaxis para archivos `.env`.


* **SQLite Viewer** (`qwtel.sqlite-viewer` o `Florian Klampfer`): Visualización gráfica de tablas y registros `.db` dentro del editor.



---

### 2. Estructura inicial del proyecto (Solo primera vez)

Comandos de PowerShell para generar el árbol de carpetas y archivos base:

```powershell
# Crear carpetas requeridas por Flask
New-Item -ItemType Directory templates, static

# Crear archivos principales de la aplicación
New-Item -ItemType File app.py, database.py, routes.py, requirements.txt, .env, .gitignore

```

---

### 3. Configuración del Entorno Virtual (.venv)

#### En Windows (PowerShell)

Si PowerShell bloquea la ejecución de scripts por defecto:

```powershell
# 1. Permitir scripts locales (ejecutar una sola vez por usuario)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 2. Crear el entorno virtual
python -m venv .venv

# 3. Activar el entorno
.\.venv\Scripts\Activate.ps1

```

#### En Linux / macOS / Git Bash

```bash
# 1. Crear entorno virtual
python3 -m venv .venv

# 2. Activar entorno
source .venv/bin/activate

```

---

### 4. Gestión de Dependencias (`pip`)

> Asegúrate de que figure `(.venv)` al inicio de la terminal antes de ejecutar estos comandos.
> 
> 

```bash
# Actualizar el gestor de paquetes
python -m pip install --upgrade pip

# Instalar dependencias del proyecto
pip install -r requirements.txt

# Si instalas un paquete nuevo manualmente (ej: pip install requests):
# Congelar solo las dependencias activas del entorno
pip freeze > requirements.txt

```

---

### 5. Reglas de Git (`.gitignore`)

Archivos y carpetas que **nunca** deben subirse al repositorio para no romper rutas entre computadoras:

```text
.venv/
venv/
__pycache__/
*.pyc
*.db
.env

```