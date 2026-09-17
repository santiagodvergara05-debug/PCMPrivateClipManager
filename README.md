# PCMPrivateClipManager

**PCMPrivateClipManager** es una suite autocontenida y resiliente para la gestión privada de notas temporales, fragmentos de código con resaltado de sintaxis, redacción de novelas/borradores y documentación técnica con soporte de fórmulas matemáticas (LaTeX/KaTeX) y gestión multimedia.

Diseñado bajo una arquitectura tolerante a fallos, opera con un **Bootloader de autocuración** capaz de aislar corrupción de datos en caliente, mitigar bloqueos del sistema operativo y restablecer configuraciones saboteadas sin interrumpir el servicio local o en red local (LAN).

---

## 🚀 Características Principales

### 1. ⚡ Clips Rápidos & Prompts

* **Gestión temporal:** Expiración configurable (10 min, 1 hora, 24 horas, 7 días o permanentes).
* **Organización reactiva:** Filtrado dinámico por categorías con píldoras interactivas autogeneradas y barra de búsqueda instantánea.
* **Prioridad:** Fijado de clips preferidos en el encabezado.
* **Acciones rápidas:** Copiado en un clic y pegado directo desde el portapapeles del sistema.

### 2. 💻 Snippets de Código (Mini-IDE)

* **Resaltado de sintaxis:** Integración con Highlight.js (Python, JavaScript, HTML, CSS, SQL, Bash, Markdown, JSON y texto plano).
* **Numeración sincronizada (Gutter):** Columna de números de línea coordinada entre el editor y la vista modal expandida.
* **Comportamiento IDE:** Soporte para indentación con tabulaciones nativas (`Tab`) y atajos habituales.
* **Métricas técnicas:** Conteo exacto de líneas y caracteres en tiempo real.

### 3. 📄 Borradores & Resúmenes

* **Redacción extensa:** Espacio optimizado para capítulos literarios, documentación o borradores de estudio.
* **Vista previa Markdown:** Alternador dinámico entre escritura y lectura renderizada con tipografía limpia.
* **Métricas en tiempo real:** Lectura estimada en minutos, conteo de palabras, líneas y caracteres.
* **Persistencia segura:** Guardado rápido vía `Ctrl + S` y exportación limpia a archivos `.md`.

### 4. 📐 Documentos & Math Studio (AI-Assisted Reports)
* **Sinergia con Modelos de IA:** Diseñado para recibir directamente el output crudo de asistentes de IA (Claude, ChatGPT, Gemini, DeepSeek) con explicaciones técnicas, tablas y derivaciones matemáticas complejas sin requerir formateo manual (tambien aplica a IAs locales si generan formatos MD).
* **Renderizado Matemático KaTeX:** Procesamiento instantáneo de notación científica y fórmulas LaTeX inline (`$...$`) y en bloque (`$$...$$`) sin depender de compiladores LaTeX pesados ni conexión a internet.
* **Control de Paginación A4:** Soporte de directivas de salto de página (`\newpage`) y adaptación milimétrica a formato A4 listo para impresión y guardado directo como PDF vectorial.
* **Gestión Multimedia Segura:** Subida y renderizado de capturas con validación binaria estricta de *Magic Bytes* (PNG, JPEG, GIF, WEBP) previniendo inyecciones de archivos corruptos.
* **Consolidador de Documentos:** Módulo de fusión para unificar múltiples entregas o secciones de apuntes en un informe técnico maestro.

### 5. 🛡️ Bootloader de Autocuración & Resiliencia

* **Auditoría física SQLite:** Comprobación de integridad estructural (`PRAGMA integrity_check`) al inicio; las bases dañadas se aíslan en cuarentena (`pcm.db.corrupt_<timestamp>`) y el esquema relacional se regenera en milisegundos.
* **Resolución de *Schema Drift*:** Detección de tablas faltantes y migración no destructiva de esquemas.
* **Tolerancia a bloqueos de concurrencia:** Detección de estados `database is locked` y espera activa con liberación limpia.
* **Entorno blindado (.env):** Sanitización contra sabotaje de bytes binarios UTF-8, corrección de rangos de puertos/host y autorreconciliación de estado previo (`SISTEMA_INICIALIZADO`).
* **Telemetría kernel (`klog`):** Trazabilidad visual en consola estilo *init* de Unix para diagnóstico instantáneo de fallas.

### 6. 🛠️ Consola Fuera de Banda (`CLI_admin.py`)

* Panel interactivo de consola para mantenimiento y rescate sin levantar el servidor web:
* Inspección y rotación de contraseñas de acceso y llaves maestras criptográficas (256 bits).
* Purga de imágenes huérfanas en disco (archivos sin referencia activa en la base).
* Limpieza de archivos en cuarentena (`.corrupt_*`).
* Restauración completa a valores de fábrica.



### 7. 🧪 Suite de Caos & Estrés (`CLI_chaos.py`)

* Herramienta especializada de ingeniería de caos para pruebas de regresión y robustez:
* Sabotaje de cabeceras SQLite e inyección de fallos de integridad.
* Eliminación de esquemas y borrado accidental simulado.
* Inyección de candados exclusivos de concurrencia.
* Corrupción binaria de archivos `.env`, puertos fuera de rango e imágenes vacías.



---

## 🛠️ Stack Tecnológico

* **Backend:** Python 3.9+, Flask, SQLite3 (modo seguro / concurrente).
* **Frontend:** HTML5 semántico, CSS3 modular (tema oscuro técnico) y JavaScript moderno (ES6+).
* **Motores Cliente:** [Highlight.js](https://highlightjs.org/), [Marked.js](https://marked.js.org/), [KaTeX](https://katex.org/).
* **Seguridad:** Criptografía de 256 bits con `secrets`, hashing seguro y validación de firmas binarias de archivos.

---

## 📁 Estructura del Proyecto

```text
PCMPrivateClipManager/
├── static/
│   ├── css/
│   │   ├── base.css                  # Estilos globales y navegación
│   │   ├── clips.css                 # Interfaz de clips rápidos
│   │   ├── codigo.css                # Mini-IDE y gutter de código
│   │   ├── config.css                # Panel de ajustes y backups
│   │   ├── documentos.css            # Grilla y visor de documentos
│   │   ├── editor.css                # Editor dual y render Markdown/KaTeX
│   │   ├── fusionador.css            # Vista de consolidación de notas
│   │   ├── index.css                 # Buscador y filtros de categorías
│   │   ├── katex.min.css             # Estilos de notación matemática
│   │   ├── login.css                 # Pantalla de acceso
│   │   └── novelas.css               # Biblioteca de borradores
│   └── uploads/
│       └── documentos/               # Almacenamiento local de multimedia
├── templates/
│   ├── base.html                     # Layout base y encabezados
│   ├── agregar_codigo.html           # Modal/vista de creación de snippets
│   ├── codigo.html                   # Vista principal de código
│   ├── config.html                   # Interfaz web de configuración
│   ├── documentos.html               # Galería técnica de documentos
│   ├── editor.html                   # Editor de redacción dual (Math/MD)
│   ├── fusionador.html               # Fusión y mezcla de documentos
│   ├── index.html                    # Tablero de clips rápidos
│   ├── lista_documentos.html         # Lista de selección e índices
│   ├── login.html                    # Autenticación web
│   └── novelas.html                  # Biblioteca de borradores
├── app.py                            # Núcleo Flask y Bootloader de arranque
├── backup.py                         # Motor CLI de respaldo y restauración
├── CLI_admin.py                      # Consola de administración fuera de banda
├── CLI_chaos.py                      # Banco de pruebas de estrés y caos
├── database.py                       # Gestión relacional y esquemas SQLite
├── routes.py                         # Endpoints, APIs y controladores web
├── version.py                        # Control de versiones del sistema
├── iniciar.bat                       # Script de ejecución para Windows
├── iniciar.sh                        # Script de ejecución para Linux/macOS
├── requirements.txt                  # Requerimientos de dependencias
└── .gitignore                        # Reglas de exclusión de Git

```

---

## ⚙️ Instalación y Puesta en Marcha

### Prerrequisitos

* Python 3.9 o superior instalado en el sistema.

### 1. Clonar el repositorio

```bash
git clone https://github.com/santiagodvergara05-debug/PCMPrivateClipManager.git
cd PCMPrivateClipManager

```

### 2. Configurar entorno virtual e instalar dependencias

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

```

### 3. Iniciar el servicio

* **Windows:** Doble clic sobre `iniciar.bat` (o en consola: `python app.py`).
* **Linux / macOS:** `./iniciar.sh` (conceder permisos previamente con `chmod +x iniciar.sh`).

Ingresa desde tu navegador a `[http://127.0.0.1:5545](http://127.0.0.1:5545)`.

> **Nota:** La contraseña inicial por defecto es `cambiame`. Cámbiala de inmediato desde la pestaña **⚙️ Ajustes** o mediante `CLI_admin.py`.

---

## 🧰 Herramientas de Mantenimiento

### Consola de Administración Fuera de Banda

Permite gestionar parámetros de seguridad y disco sin encender el servidor HTTP:

```bash
python CLI_admin.py

```

### Motor de Respaldos (`backup.py`)

* **Exportar toda la colección a JSON:**
```bash
python backup.py export

```


* **Generar copia binaria de `pcm.db`:**
```bash
python backup.py raw

```


* **Restaurar o fusionar datos desde un respaldo:**
```bash
python backup.py restore ruta/al/archivo.json

```



### Banco de Pruebas de Estrés (`CLI_chaos.py`)

Para evaluar el comportamiento del bootloader ante desastres controlados (requiere `FLASK_DEBUG=true`):

```bash
python CLI_chaos.py

```

---

## 👤 Autor

Desarrollado por **[santiagodvergara05-debug](https://www.google.com/search?q=https://github.com/santiagodvergara05-debug)**.