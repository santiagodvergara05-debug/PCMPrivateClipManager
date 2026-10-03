# 📋 PCMPrivateClipManager (PCM)

**PCMPrivateClipManager** es una plataforma de productividad personal, privada y de alta resiliencia diseñada para funcionar de forma 100% local o en red compartida (LAN). Centraliza la gestión de portapapeles temporal, fragmentos de código con resaltado sintáctico, blocs de notas estructurados y un estudio completo para redactar documentación técnica con fórmulas matemáticas (KaTeX) y diagramas interactivos (Mermaid).

Cuenta con un motor de **Sincronización BYOC (*Bring Your Own Cloud*) de Cero Conocimiento**, permitiéndote mantener tus datos alineados entre tu PC y tu notebook u otros dispositivos usando tu propia nube (OneDrive, Google Drive, MEGA, Dropbox o pendrives) sin depender de servidores de terceros. Además, su **Bootloader de Rescate Automático** vigila la salud de tu base de datos en cada inicio y recupera tu información automáticamente si detecta cualquier archivo dañado o borrado accidentalmente.

---

## ✨ Lo que puedes hacer con PCM

* 🔄 **Sincroniza tus equipos sin exponer tu privacidad:** Tus notas, códigos y documentos se transfieren entre tu PC y tu notebook a través de tu servicio de nube habitual, pero viajan totalmente blindados con cifrado militar **AES-256 local**. Tu proveedor de nube solo ve un paquete cifrado; nadie más que tú puede leer la información.
* 🚑 **Recuperación Automática ante Desastres (Disaster Recovery):** Si tu equipo se apaga abruptamente, la base de datos se corrompe o borras un archivo por error, el sistema lo detecta en el arranque, aísla el archivo dañado y restaura automáticamente la copia sana más reciente de tu nube.
* 🔀 **Fusiona textos y mide tokens para Inteligencia Artificial:** Combina directivas de sistema o plantillas fijas con entradas rápidas al instante. Incluye un calculador inteligente de **tokens en tiempo real**, calibrado especialmente para código fuente y caracteres asiáticos (chino, japonés y coreano).
tambien esta habilitado para fusionar textos normales,
* 🔒 **100% Offline y Autónomo (Air-Gapped):** Todos los componentes visuales, tipografías y librerías corren desde tu disco. Cero llamadas a servidores externos, cero rastreadores y funcionamiento garantizado sin conexión a Internet.
* 📐 **Estudio de Documentos Técnicos y Fórmulas:** Escribe apuntes científicos y documentación avanzada con renderizado inmediato de LaTeX y diagramas de flujo, listos para imprimir o exportar a formato PDF A4.
* 🛡️ **Seguridad Fuera de Banda:** Los ajustes críticos (claves de red, contraseñas y puertos) están protegidos por una **Llave Maestra (Master Key)** de 256 bits (modificable en el .env) y se bloquean automáticamente a los 2 minutos de inactividad o alguna modificacion critica realizada.

---

## 🚀 Módulos del Sistema

### 1. ⚡ Clips Rápidos & Prompts
* **Autodestrucción programada:** Configura la expiración de tus textos (10 min, 1 h, 24 h, 7 días) o consérvalos de forma indefinida.
* **Organización instantánea:** Filtrado ágil por categorías, buscador en vivo y sistema de favoritos para anclar textos recurrentes arriba.
* **Copiado al vuelo:** Pega y reutiliza cualquier elemento con un solo clic.

### 2. 🔀 Fusionador de Textos & Contador Inteligente de Tokens
* **Concatenación reactiva:** Pega tu consulta o variable y el sistema la unirá de inmediato con tu plantilla fija, copiándola de forma automática al portapapeles.
* **Cálculo de Tokens Multilingüe:**
  * **Prosa y Código:** Ponderación calibrada para sangrías, operadores (`{}`, `()`, `=>`) y sintaxis estructurada (~1 token cada 3.5 caracteres).
  * **Idiomas Asiáticos (CJK):** Detección por rangos Unicode para ideogramas chinos, kanji/kana japoneses y hangul coreano (~1.3 tokens por caracter).
* **Persistencia local:** Tu plantilla base permanece guardada de forma segura en tu navegador para que no tengas que reescribirla.

### 3. 💻 Snippets de Código (Mini-IDE)
* **Resaltado de sintaxis offline:** Soporte visual completo para Python, JavaScript, HTML, CSS, SQL, Bash, JSON y Markdown.
* **Experiencia de editor:** Soporte para indentación con tecla `Tab`, conteo de líneas/caracteres y visor modal expandido con columna de numeración (*gutter*).

### 4. 📝 Bloc de Notas & Textos Extensos
* **Clasificación en 5 categorías:** Diseñado para organizar `Nota`, `Borrador`, `Resumen`, `Apuntes` y `Texto Plano`.
* **Modo de lectura y edición dual:** Previsualización limpia de Markdown con cálculo automático de minutos de lectura y conteo de palabras.

### 5. 📐 Estudio de Documentos Técnicos (Math, KaTeX & Mermaid)
* **Notación Matemática LaTeX:** Renderizado de ecuaciones en línea (`$...$`) y bloques de fórmulas científicas (`$$...$$`).
* **Diagramas Mermaid:** Crea mapas conceptuales, diagramas de arquitectura y secuencias directamente desde código de texto.
* **Galería multimedia protegida:** Subida de imágenes locales (hasta 25 MB) con validación binaria estricta (*Magic Bytes*) para impedir archivos falsificados.
* **Purga de almacenamiento:** Herramienta en un clic para escanear y eliminar imágenes huérfanas que ya no pertenezcan a ningún documento.

### 6. 🔄 Sincronización BYOC (E2EE AES-256) Multidispositivo
* **Configuración en un clic:** Selecciona la carpeta de tu servicio (OneDrive, Drive, MEGA, Dropbox o Pendrive) con el botón *Examinar* y PCM provisionará automáticamente la subcarpeta `PCM_Sync`.
* **Protección Anti-Atraso:** Si en la nube existe una versión más moderna generada por otro de tus equipos, el sistema bloquea subidas accidentales para evitar sobrescribir información.
* **Integridad Atómica SHA-256:** Ningún paquete remoto se instala en tu equipo si la descarga está incompleta o si el archivo fue alterado en tránsito.
* **Rotación de Claves:** Cambia tu contraseña de cifrado en cualquier momento; el sistema eliminará la bóveda anterior y generará una nueva versión limpia y re-cifrada.

### 7. ⚙️ Ajustes Críticos, Seguridad & Respaldos
* **Respaldos Manuales Duales:** Exporta o importa tus datos en formato `.JSON` (solo base relacional) o paquetes `.ZIP` completos (incluyendo todas tus imágenes físicas).
* **Cierre Global de Sesiones:** Invalida instantáneamente todas las sesiones activas en la red rotando la `SECRET_KEY` en memoria sin reiniciar el servidor.
* **Gestión de red:** Alterna entre modo exclusivo local (`127.0.0.1`) o acceso compartido para móviles y notebooks en tu red LAN (`0.0.0.0`).

---

## 🛡️ Bootloader Resiliente & Protocolo de Autocuración

El archivo de arranque `app.py` actúa como un supervisor de integridad que audita el sistema antes de iniciar el servidor web:

```text
[ ARRANQUE ] ──► ¿Existe .env íntegro? ──► NO ──► Regeneración atómica / Aislamiento
                     │
                    SÍ
                     ▼
         ¿Base de datos local sana?
          ├── SÍ ──► Comprobación de revisión con la nube
          └── NO (Corrupta o borrada)
                     │
                     ▼
         ¿Sincronización BYOC activa?
          ├── SÍ ──► 🚑 DISASTER RECOVERY: Restaura la última bóveda de la nube
          └── NO ──► Genera base de datos SQLite limpia y protegida


### Reglas Clave de Resiliencia:

1. **Rescate prioritario en emergencias:** Si `pcm.db` desaparece o sufre daños físicos, el rescate desde la nube **se ejecutará automáticamente incluso si la opción de auto-sincronizar al inicio está apagada**. La seguridad de tus datos tiene prioridad absoluta.
2. **Aislamiento local estricto:** Si la sincronización está inhabilitada en los ajustes (`SYNC_HABILITADO=false`), el bootloader ignorará cualquier carpeta remota y levantará un entorno local seguro.
3. **Cuarentena preventiva:** Cualquier base de datos o archivo `.env` que contenga bytes nulos o daño estructural es renombrado a `.corrupt_<timestamp>` para que nunca pierdas el historial físico mientras el sistema continúa operando.

---

## 📁 Estructura del Proyecto

```text
PCMPrivateClipManager/
├── static/
│   ├── css/
│   │   ├── base.css              # Paleta visual, tipografías y navegación
│   │   ├── clips.css             # Tarjetas de clips rápidos y filtros
│   │   ├── codigo.css            # Estructura del Mini-IDE y columna de numeración
│   │   ├── config.css            # Panel de control, métricas y modales BYOC
│   │   ├── documentos.css        # Lienzo A4 técnico y galería de fotos
│   │   ├── editor.css            # Editor de notas estructuradas
│   │   ├── fusionador.css        # Interfaz del fusionador de textos y telemetría
│   │   ├── github-dark.min.css   # Tema oscuro para sintaxis de código
│   │   ├── index.css             # Tablero principal de clips
│   │   ├── katex.min.css         # Estilos visuales de notación matemática
│   │   ├── login.css             # Acceso de autenticación
│   │   └── notas.css             # Catálogo en cuadrícula del bloc de notas
│   ├── js/                       # Motores de renderizado 100% locales (Offline)
│   │   ├── highlight.min.js
│   │   ├── katex.min.js
│   │   ├── marked.min.js
│   │   ├── marked-footnote.min.js
│   │   ├── mermaid.min.js
│   │   └── purify.min.js
│   └── uploads/documentos/       # Almacén local protegido para capturas e imágenes
├── templates/
│   ├── base.html                 # Estructura maestra HTML5
│   ├── agregar_codigo.html       # Creador de nuevos snippets
│   ├── codigo.html               # Biblioteca de snippets de código
│   ├── config.html               # Panel de ajustes, telemetría y modales BYOC
│   ├── documentos.html           # Editor técnico LaTeX + Mermaid
│   ├── editor.html               # Editor de notas en 5 categorías
│   ├── fusionador.html           # Fusionador de textos con cálculo de tokens
│   ├── index.html                # Tablero de clips rápidos
│   ├── lista_documentos.html     # Índice de documentos técnicos guardados
│   ├── login.html                # Acceso web seguro con copiado rápido
│   └── notas.html                # Galería del bloc de notas
├── app.py                        # Bootloader, autocuración y servidor WSGI
├── database.py                   # Esquemas y migraciones SQLite locales
├── routes.py                     # Controladores HTTP, APIs y lógica del sistema
├── sync_manager.py               # Motor criptográfico BYOC E2EE (AES-256)
├── logger_http.py                # Traductor visual ANSI de peticiones HTTP
├── CLI_admin.py                  # Consola de administración fuera de banda
├── CLI_chaos.py                  # Banco de pruebas de estrés e inyección de fallos
├── version.py                    # Identificador de versión del sistema
├── requirements.txt              # Librerías de Python requeridas
├── start.bat                     # Lanzador automático para Windows
└── start.sh                      # Lanzador automático para Linux / macOS

```

---

## ⚙️ Instalación y Despliegue

### Requisitos Previos

* **Python 3.9** o superior instalado en el equipo.

### 1. Clonar el repositorio

```bash
git clone [https://github.com/santiagodvergara05-debug/PCMPrivateClipManager.git](https://github.com/santiagodvergara05-debug/PCMPrivateClipManager.git)
cd PCMPrivateClipManager

```

### 2. Crear entorno virtual e instalar dependencias

```bash
# En Windows:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# En Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

```

### 3. Puesta en marcha

* **En Windows:** Haz doble clic sobre `start.bat` o ejecuta desde terminal:
```bash
start.bat

```


* **En Linux / macOS:** Otorga permisos de ejecución e inicia:
```bash
chmod +x start.sh
./start.sh

```



El sistema verificará las dependencias y abrirá automáticamente tu navegador en:

```text
[http://127.0.0.1:5545](http://127.0.0.1:5545)

```

---

## 🔑 Primer Inicio y Credenciales Predeterminadas

Cuando arranques PCM por primera vez (o tras un reseteo de fábrica), el bootloader preparará el entorno automáticamente:

* **Contraseña Web inicial:** `cambiame`
* **Llave Maestra (`MASTER_KEY`):** Se genera aleatoriamente con 256 bits de entropía y se muestra en una tarjeta dorada en la pantalla de bienvenida para que puedas copiarla.
* **Ocultamiento permanente:** En cuanto inicies sesión por primera vez, el aviso de bienvenida se ocultará de forma definitiva. Puedes cambiar tus contraseñas y llaves en cualquier momento desde **⚙️ Configuración** o mediante `CLI_admin.py`.

---

## 🛠️ Consola Administrativa Fuera de Banda (`CLI_admin.py`)

Si necesitas realizar labores de mantenimiento, configuración de red, gestión de sincronización o rescate sin necesidad de iniciar el servidor web:

```bash
python CLI_admin.py

```

### Funciones y Controles Disponibles:

#### 🔐 1. Gestión de Seguridad Crítica & Llaves

* **Inspección en vivo:** Consulta de forma directa la contraseña de acceso (`APP_PASSWORD`), la `MASTER_KEY` y la clave de cifrado de la nube (`SYNC_CLAVE`) sin abrir el archivo `.env`.
* **Rotación individual o masiva:** Modifica la contraseña web o regenera de forma criptográfica la `MASTER_KEY` (256 bits), la `SECRET_KEY` (cerrando sesiones activas) y la `SYNC_CLAVE` de la bóveda, o rota **todas las llaves en simultáneo**.

#### 🌐 2. Red, Servidor & Preferencias

* **Alternar alcance de red:** Cambia al instante entre modo PC Local (`127.0.0.1`) y Red LAN compartida (`0.0.0.0`).
* **Puerto y telemetría:** Modifica el puerto de escucha (`PORT`), activa o desactiva el modo de depuración (`FLASK_DEBUG`), el registro detallado en terminal (`LOG_MODE`) y la apertura automática del navegador.

#### 🔄 3. Sincronización BYOC & Control de Revisiones

* **Control del servicio:** Habilita o deshabilita el motor de sincronización (`SYNC_HABILITADO`) fuera de banda.
* **Identidad de nodo:** Renombra el identificador de este dispositivo (`SYNC_NOMBRE_DISPOSITIVO`).
* **Control de secuencia:** Reinicia de forma segura el contador local a la **Revisión #0** (operación permitida únicamente si la carpeta de la nube está limpia de bóvedas o metadatos activos).

#### 🧹 4. Mantenimiento, Almacenamiento & Cuarentena

* **Purga multimedia:** Escanea el almacenamiento y elimina imágenes huérfanas no referenciadas.
* **Limpieza de cuarentena:** Borra archivos aislados tras pruebas de estrés o incidentes (`.corrupt_*`, temporales `*.tmp` y residuales `*.pre_sync`).
* **Restablecimiento total (*Factory Reset*):** Purga absoluta de base de datos, configuraciones `.env`, capturas y copias de seguridad para devolver la suite a su estado inicial de fábrica.

```

---

## 📦 Compilación a Ejecutables (.exe en Windows)

Si deseas utilizar la aplicación como un ejecutable independiente sin necesidad de instalar Python en otros equipos:

### 1. Instalar PyInstaller en tu entorno virtual

```bash
pip install pyinstaller

```

### 2. Compilar el Servidor Principal (`PCMPrivateClipManager.exe`)

```bash
python -m PyInstaller --noconfirm --onefile --console --name "PCMPrivateClipManager" --add-data "templates;templates" --add-data "static;static" app.py

```

### 3. Compilar la Consola Administrativa (`CLI_admin.exe`)

```bash
python -m PyInstaller --noconfirm --onefile --console --name "CLI_admin" CLI_admin.py

```

Los ejecutables resultantes se ubicarán en la carpeta **`dist/`**. Puedes trasladarlos a cualquier carpeta o unidad externa; al ejecutarse por primera vez crearán automáticamente su propia base de datos y configuración protegida.

---

## 👤 Autor

Desarrollado y mantenido por **[santiagodvergara05-debug]**.

## 📄 Licencia

Este proyecto está distribuido bajo los términos de la **GNU Affero General Public License v3.0 (AGPLv3)**. Consulta el archivo [LICENSE](https://www.google.com/search?q=LICENSE) para más información.

```

```