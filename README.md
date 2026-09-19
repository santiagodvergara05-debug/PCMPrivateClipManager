# 📋 PCMPrivateClipManager (PCM)

**PCMPrivateClipManager** es una suite de productividad privada, autocontenida y de alta resiliencia diseñada para operar de forma 100% local o en red de área local (LAN). Centraliza la gestión de portapapeles temporal, fragmentos de código con resaltado de sintaxis, notas estructuradas en 5 categorías y un estudio completo de documentación técnica compatible con fórmulas matemáticas (KaTeX) y diagramas de flujo (Mermaid).

Construido bajo una filosofía de tolerancia extrema a fallos, incorpora un **Bootloader de autocuración** capaz de mitigar bloqueos del sistema operativo, aislar bases de datos corruptas en caliente y sanitizar archivos de configuración alterados sin interrumpir la operatividad del sistema.

---

## ✨ Características Destacadas

* **100% Offline & Air-Gapped:** Todos los motores de renderizado (KaTeX, Highlight.js, Mermaid, Marked y DOMPurify) residen localmente en el servidor. Cero peticiones externas a CDNs y privacidad absoluta.
* **Autocuración & Resiliencia:** Auditoría de integridad SQLite en cada arranque con cuarentena automática preventiva y regeneración atómica del archivo `.env`.
* **Seguridad Fuera de Banda:** Gestión crítica protegida por Llave Maestra criptográfica de 256 bits (`MASTER_KEY`) con temporizador de sesión volátil de 2 minutos.
* **Telemetría ANSI en Tiempo Real:** Motor de logs enriquecido con insignias y colores en consola para auditoría visual inmediata de eventos (`ÉXITO`, `SYS`, `INFO`, `ALERTA`, `DELETE`).
* **Sinergia con Modelos de IA:** Diseñado para recibir directamente código, derivaciones matemáticas y tablas generadas por LLMs (ChatGPT, Claude, DeepSeek, Gemini o modelos locales) sin pérdida de formato.

---

## 🚀 Módulos del Sistema

### 1. ⚡ Clips Rápidos & Prompts
* **Ciclo de vida configurable:** Autodestrucción por tiempo (10 min, 1 h, 24 h, 7 días) o almacenamiento permanente.
* **Organización dinámica:** Filtrado instantáneo mediante etiquetas reactivas autogeneradas y buscador en tiempo real.
* **Portapapeles activo:** Fijado de clips prioritarios al inicio y copiado con un solo clic.

### 2. 💻 Snippets de Código (Mini-IDE)
* **Resaltado de sintaxis offline:** Basado en Highlight.js para Python, JavaScript, HTML, CSS, SQL, Bash, JSON, Markdown y texto plano.
* **Edición fluida:** Soporte para tabulación nativa (`Tab`), conteo exacto de líneas y caracteres, y vista modal expandida con columna de numeración coordinada (*gutter*).

### 3. 📝 Bloc de Notas & Textos Extensos
* **5 Categorías estandarizadas:** Organización especializada para `Nota`, `Borrador`, `Resumen`, `Apuntes` y `Texto Plano`.
* **Editor con vista previa dual:** Alternador de lectura fluida en Markdown con tipografía optimizada para lectura prolongada.
* **Métricas de redacción:** Estimación del tiempo de lectura en minutos y conteo automático de palabras y párrafos.

### 4. 📐 Estudio de Documentos Técnicos (Math, KaTeX & Mermaid)
* **Notación matemática LaTeX:** Renderizado ultra rápido sin dependencias pesadas para fórmulas inline (`$...$`) y bloques de ecuaciones (`$$...$$`).
* **Diagramas interactivos:** Renderizado de diagramas de arquitectura, flujos y secuencias con Mermaid.js.
* **Preparado para impresión (Formato A4):** Control de saltos de página (`\newpage`) y diseño calibrado para exportar a PDF vectorial nítido desde el navegador.
* **Almacenamiento multimedia blindado:** Subida de imágenes de hasta 25 MB con validación binaria de *Magic Bytes* (PNG, JPG, GIF, WEBP) para neutralizar exploits de extensión falsa.
* **Mantenimiento inteligente:** Algoritmo de purga para escanear y eliminar imágenes huérfanas en disco que ya no se encuentren vinculadas a ningún documento.

### 5. ⚙️ Ajustes Críticos, Seguridad & Respaldos
* **Desbloqueo temporal con Master Key:** Las configuraciones sensibles (puerto, host de red y credenciales) requieren autenticación maestra y caducan tras 120 segundos de inactividad.
* **Cierre global de sesiones:** Rotación en caliente de `SECRET_KEY` que invalida instantáneamente todas las cookies de sesión activas en la red sin reiniciar el proceso.
* **Auto-arranque en navegador:** Configuración persistente (`AUTO_ABRIR_NAVEGADOR`) para desplegar la interfaz web al inicializar.
* **Respaldos duales (.JSON y .ZIP):** Exportación e importación con detección automática entre copias ligeras de texto o paquetes comprimidos completos con activos multimedia físicos.

---

## 🛡️ Arquitectura de Resiliencia & Seguridad

| Componente | Mecanismo de Protección |
| :--- | :--- |
| **Cookies de Sesión** | Banderas `HttpOnly` (previene robo por XSS) y `SameSite=Lax` (mitiga CSRF). |
| **Base de Datos** | Inspección física previa con `PRAGMA integrity_check`. Aislamiento en `.corrupt_<timestamp>` ante páginas dañadas y mitigación de bloqueos de concurrencia (*database locked*). |
| **Configuración (.env)** | Serialización atómica con escape de saltos de línea, saneamiento de puertos (1-65535) y autorreparación de claves ausentes. |
| **Multimedia** | Validación en capas: tamaño físico (25 MB), extensión sintáctica y verificación estricta de cabeceras binarias reales. |
| **Consola Fuera de Banda** | Utilidad `CLI_admin.py` para recuperación, rotación de llaves, purga y restablecimiento de fábrica sin levantar el servidor HTTP. |

---

## 📁 Estructura del Proyecto

```text
PCMPrivateClipManager/
├── static/
│   ├── css/
│   │   ├── base.css              # Variables de diseño y navegación unificada
│   │   ├── clips.css             # Estilos de tarjetas y filtros de clips
│   │   ├── codigo.css            # Gutter y contenedor del Mini-IDE
│   │   ├── config.css            # Panel de configuración, diagnóstico y métricas
│   │   ├── documentos.css        # Lienzo técnico A4 y galería multimedia
│   │   ├── editor.css            # Editor de redacción dual (Markdown/KaTeX)
│   │   ├── fusionador.css        # Herramienta de consolidación de textos
│   │   ├── github-dark.min.css   # Esquema visual de código para tema oscuro
│   │   ├── index.css             # Tablero general y buscador dinámico
│   │   ├── katex.min.css         # Hojas de estilo de notación matemática
│   │   ├── login.css             # Pantalla de acceso con tarjeta de credenciales
│   │   └── notas.css             # Catálogo de notas y borradores en cuadrícula
│   ├── js/                       # Motores de renderizado 100% locales (Offline)
│   │   ├── highlight.min.js
│   │   ├── katex.min.js
│   │   ├── marked.min.js
│   │   ├── marked-footnote.min.js
│   │   ├── mermaid.min.js
│   │   └── purify.min.js
│   └── uploads/
│       └── documentos/           # Almacenamiento local seguro para imágenes
├── templates/
│   ├── base.html                 # Plantilla principal y cabeceras
│   ├── agregar_codigo.html       # Formulario para nuevos snippets
│   ├── codigo.html               # Vista de biblioteca de snippets
│   ├── config.html               # Interfaz de ajustes y llaves de acceso
│   ├── documentos.html           # Editor profesional de documentos técnicos
│   ├── editor.html               # Editor de notas en 5 categorías
│   ├── fusionador.html           # Espacio de mezcla y unión de textos
│   ├── index.html                # Tablero de clips rápidos
│   ├── lista_documentos.html     # Índice de documentos técnicos guardados
│   ├── login.html                # Acceso web seguro con copiado rápido
│   └── notas.html                # Vista de catálogo del Bloc de Notas
├── app.py                        # Núcleo del servidor, bootloader y telemetría
├── database.py                   # Control de esquemas relacionales SQLite
├── routes.py                     # Controladores HTTP, APIs y lógica de negocio
├── CLI_admin.py                  # Consola interactiva fuera de banda
├── CLI_chaos.py                  # Suite de pruebas de estrés e inyección de fallos
├── version.py                    # Constante de versión del sistema
├── requirements.txt              # Dependencias de Python
├── iniciar.bat                   # Lanzador para entornos Windows
└── iniciar.sh                    # Lanzador para entornos Linux / macOS



---

## ⚙️ Instalación y Despliegue

### Requisitos Previos

* **Python 3.9** o superior instalado en el sistema.

### 1. Clonar el repositorio

```bash
git clone [https://github.com/santiagodvergara05-debug/PCMPrivateClipManager.git](https://github.com/santiagodvergara05-debug/PCMPrivateClipManager.git)
cd PCMPrivateClipManager

```

### 2. Crear entorno virtual e instalar dependencias

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

### 3. Puesta en marcha

* **En Windows:** Ejecutar `iniciar.bat` o iniciar desde terminal con:
```bash
python app.py

```


* **En Linux / macOS:** Conceder permisos de ejecución y arrancar:
```bash
chmod +x iniciar.sh
./iniciar.sh

```



El sistema abrirá automáticamente el navegador en:

```text
[http://127.0.0.1:5545](http://127.0.0.1:5545)

```

---

## 🔑 Primer Inicio y Credenciales de Fábrica

Al arrancar el sistema por primera vez (o tras un reseteo de fábrica), el bootloader aprovisionará el entorno con valores iniciales seguros:

* **Contraseña Web inicial:** `cambiame`
* **Llave Maestra (`MASTER_KEY`):** Se genera automáticamente con 256 bits de entropía criptográfica y se muestra en la tarjeta dorada de la pantalla de bienvenida para facilitar su copia.
* **Ocultamiento automático:** Una vez ingresado al sistema por primera vez, el aviso de credenciales se oculta permanentemente. Las contraseñas pueden actualizarse desde la pestaña **⚙️ Ajustes** o a través de `CLI_admin.py`.

---

## 🛠️ Consola de Administración Fuera de Banda (`CLI_admin.py`)

Para labores de rescate o administración sin necesidad de levantar el servidor web:

```bash
python CLI_admin.py

```

**Opciones disponibles en consola:**

1. Consultar estado, puerto y variables del archivo `.env`.
2. Modificar la contraseña de acceso (`APP_PASSWORD`).
3. Regenerar de forma segura la Llave Maestra (`MASTER_KEY`).
4. Purgar archivos e imágenes huérfanas en disco.
5. Limpiar registros y archivos en cuarentena (`.corrupt_*`).
6. Restablecer el sistema a valores de fábrica (*Factory Reset*).

---





```markdown
---

## 📦 Compilación a Ejecutables (.exe - Windows)

Para generar versiones binarias autónomas que no requieran tener Python instalado en el equipo final, puedes empaquetar tanto el servidor principal como la consola de administración utilizando **PyInstaller**.

### 1. Instalar PyInstaller en el entorno virtual
```bash
pip install pyinstaller

```

### 2. Compilar el servidor principal (`PCMPrivateClipManager.exe`)

Empaqueta el núcleo del sistema vinculando las carpetas locales de plantillas HTML y recursos estáticos:

```bash
python -m PyInstaller --noconfirm --onefile --console --name "PCMPrivateClipManager" --add-data "templates;templates" --add-data "static;static" app.py

```

### 3. Compilar la consola administrativa (`CLI_admin.exe`)

Genera el binario de rescate y mantenimiento fuera de banda:

```bash
python -m PyInstaller --noconfirm --onefile --console --name "CLI_admin" CLI_admin.py

```

### 4. Despliegue de los ejecutables

Una vez completada la compilación:

1. Encontrarás ambos archivos en la carpeta recién creada **`dist/`**:
* `PCMPrivateClipManager.exe`
* `CLI_admin.exe`


2. Puedes mover ambos ejecutables a cualquier carpeta independiente. Al iniciar `PCMPrivateClipManager.exe`, el sistema generará automáticamente sus directorios de trabajo, el archivo de configuración `.env` de fábrica y la base de datos `pcm.db`.

```

```



















## 👤 Autor

Desarrollado y mantenido por **[santiagodvergara05-debug]**.

```

```