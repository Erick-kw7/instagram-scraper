# Instagram Profile Scraper con Playwright & Panel de Control

> **Proyecto Académico — Arquitectura de Software**  
> **Carrera de Ingeniería en Sistemas | 7.º Semestre**  
> **Universidad Central del Ecuador (UCE)**  
> **Autor:** Erick Simbaña  
> **Cuenta objetivo de la consigna:** `@sausage_player`

Este proyecto explora la ingeniería inversa y automatización con **Playwright** en Python para auditar, extraer y estructurar en JSON el contenido de perfiles de Instagram, implementando además un **Panel de Control Web Interactivo** local para la monitorización en tiempo real.

---

## Evolución del Proyecto: Versión Inicial vs. Versión Final

Para fines de evaluación en la materia de **Arquitectura de Software**, se documenta la progresión experimental desde las primeras pruebas limitadas hasta la arquitectura final consolidada:

| Criterio / Métrica | Versión Inicial (Pruebas Previas) | Versión Final (Arquitectura Actual) |
|---|---|---|
| **Método de Acceso** | Sin sesión o con login manual en formulario (generaba reCAPTCHAs y bloqueos HTTP 429). | **Inyección de Cookies en `.env`** (`sessionid`, `ds_user_id`, `csrftoken`), emulando una sesión humana legítima sin captchas ni bloqueos. |
| **Límite de Posts** | Limitado por Instagram a 12 o 24 posts en modo anónimo. | **100% de las publicaciones** (50 de 50 en la cuenta asignada `@sausage_player`), recorridas una a una. |
| **Descarga Multimedia** | Ninguna (solo se guardaba el texto alternativo `alt`). | **Descarga completa a disco**: fotos en alta resolución (`.jpg`), carruseles y reels/videos nativos (`.mp4`) en `descargas_<usuario>/`. |
| **Manejo de Videos / Reels** | No soportado; bloqueado por flujos en memoria `blob:https://...`. | **Superación de blobs**: inspección de componentes React (`__reactFiber`) para extraer el manifiesto MPEG-DASH `<BaseURL>` y descargar el video real. |
| **Reacciones (Likes)** | No disponible en la versión inicial. | **Conteo exacto y detección de Likes Ocultos** (`likes_ocultos: true`, `likes: null`) cuando el autor los oculta. |
| **Comentarios** | No disponible en la versión inicial. | **Conteo real y oficial** (`Ver los X comentarios`), filtrando respuestas legítimas y descartando el pie de foto del autor y dots de carrusel. |
| **Seguidores y Seguidos** | Solo conteos numéricos de la cabecera. | **Listas completas de usuarios**: extracción de `@usuario`, nombre visible, URL y avatar mediante scroll modal con Set anti-duplicados. |
| **Interfaz de Usuario** | Únicamente línea de comandos (CLI) con pausas manuales. | **Panel de Control Web (`app.py`)** con terminal de logs en vivo, visor de galería y comprobador de cookies. |

---

## Objetivo

Organizar en un documento estructurado `datos_<usuario>.json` los campos íntegros del perfil:

- Identificación: `@usuario`, nombre completo, biografía con saltos de línea/emojis y foto de avatar.
- Indicadores: Insignia de verificación y estado público/privado.
- Conteos oficiales: Publicaciones totales, seguidores y seguidos.
- Publicaciones detalladas:
  - Clasificación estricta: `publicacion` (foto fija), `carrusel` (álbum de varias fotos) o `reel` / `video`.
  - Fecha UTC de publicación y enlace permanente.
  - Descripción completa (*caption*).
  - Conteo de likes (o estado oculto).
  - Conteo de comentarios y muestra de respuestas.
  - Enlaces de CDN y rutas de archivos locales descargados (`.jpg` y `.mp4`).
- Listas de usuarios de Seguidores y Seguidos.

> **Nota sobre privacidad:** Por respeto a la privacidad de datos reales, los archivos de captura reales (`datos_sausage_player.json` y la carpeta `descargas_sausage_player/`) **no se publican en el repositorio** y están protegidos por `.gitignore`. Se incluye el archivo [ejemplo_datos.json](ejemplo_datos.json) con datos estructurados de referencia.

---

## Herramientas y Tecnologías

| Herramienta | Rol en la Arquitectura | Justificación Técnica |
|---|---|---|
| **Python 3.10+** | Lenguaje Principal | Manejo de flujos de datos, peticiones y estructuración JSON. |
| **Playwright (Chromium)** | Automatización Web | Emulación de navegador real capaz de ejecutar JavaScript moderno y Single Page Applications (SPA). |
| **python-dotenv** | Seguridad y Configuración | Carga de variables de entorno locales desde `.env` sin exponer credenciales en el código. |
| **Requests** | Validación Previa | Comprobación de estado HTTP de cookies antes de iniciar el navegador gráfico. |
| **Vanilla HTML/CSS/JS** | Dashboard Web (`app.py`) | Panel de control local sin sobrecarga de frameworks externos pesados. |

*(Herramientas evaluadas previamente como `beautifulsoup4`, `Scrapy` o `Selenium` no forman parte del pipeline de producción debido a los bloqueos de renderizado dinámico de Instagram).*

---

## Cómo Funciona la Arquitectura

1. **Inyección de Sesión Segura**:
   Playwright inicia una instancia limpia de Chromium e inyecta las cookies de sesión activa (`sessionid`, `ds_user_id`, `csrftoken`) provistas en `.env`. Esto evita el muro de login, los captchas y la necesidad de introducir contraseñas.
2. **Lectura de Cabecera y OpenGraph**:
   Se extrae el metadato `og:description` y el texto de la cabecera visible para comparar conteos y obtener la biografía de forma heurística.
3. **Navegación Modal de Publicaciones**:
   Se abre la primera publicación en un diálogo modal (`div[role="dialog"]`) y se navega secuencialmente con la tecla `ArrowRight`.
4. **Descarga Limpia de Multimedia**:
   - **Fotos / Carruseles**: Se obtienen las URLs directas de las imágenes en alta resolución y se descargan a disco como `{shortcode}_{i}.jpg`.
   - **Videos / Reels**: En lugar de depender de URLs temporales `blob:`, se inspecciona el árbol de componentes internos de React del elemento `<video>` para obtener el enlace nativo `<BaseURL>` del archivo `.mp4`, evitando la contaminación por videos precargados de fondo.
5. **Exploración de la pestaña `/reels/`**:
   Si la cuenta tiene videos archivados exclusivamente en su pestaña de Reels, el script navega a `/<usuario>/reels/` y procesa los videos restantes.
6. **Extracción de Seguidores y Seguidos**:
   Abre los modales correspondientes y realiza scroll continuo manteniendo un `Set` en memoria para descartar duplicados hasta alcanzar el total deseado.

---

## Estructura del Repositorio

```text
instagram-scraper/
├── app.py                                  # Panel de Control Web y servidor local (localhost:5000)
├── extraer_playwright.py                   # Motor Playwright consolidado
├── ejemplo_datos.json                      # Estructura de salida JSON con datos de ejemplo
├── requirements.txt                        # Dependencias de Python
├── .env.example                            # Plantilla de variables de entorno
├── .gitignore                              # Exclusión de .env, datos reales y descargas
├── README.md                               # Documentación del proyecto
├── Informe_Tecnico_Instagram_Scraper.docx  # Memoria técnica formal en Word
└── Informe_Tecnico_Instagram_Scraper.pdf   # Memoria técnica formal en PDF
```

---

## Instalación y Uso

### 1. Preparación del Entorno

```powershell
# Crear y activar entorno virtual
python -m venv .venv
.venv\Scripts\Activate.ps1

# Instalar dependencias y navegador Chromium
pip install -r requirements.txt
playwright install chromium
```

### 2. Configurar Cookies en `.env`

Copia la plantilla y coloca tus cookies de sesión obtenidas desde las Herramientas de Desarrollador (`F12` -> Application -> Cookies -> instagram.com):

```powershell
copy .env.example .env
```

Contenido de `.env`:
```env
TARGET_USER=sausage_player
IG_SESSIONID=tu_sessionid_aqui
IG_DS_USER_ID=tu_ds_user_id_aqui
IG_CSRFTOKEN=tu_csrftoken_aqui
```

### 3. Ejecución

#### Opción A: Mediante el Panel de Control Web (Recomendado)
```powershell
python app.py
```
Abre en tu navegador `http://localhost:5000` para operar con interfaz gráfica, ver la terminal de logs en vivo y previsualizar publicaciones y multimedia.

#### Opción B: Por Línea de Comandos (CLI)
```powershell
# Modo automático completo
python extraer_playwright.py --auto

# Extraer un número específico de posts (ej. 10 publicaciones)
python extraer_playwright.py --max-posts 10

# Modo en segundo plano (headless)
python extraer_playwright.py --auto --headless

# Solo perfil básico (sin multimedia)
python extraer_playwright.py --solo-perfil
```

---

## Seguridad y Buenas Prácticas para Git

Al mantener este repositorio en Git:

* **Archivos para control de versiones:** `extraer_playwright.py`, `app.py`, `requirements.txt`, `.env.example`, `.gitignore`, `README.md`, `ejemplo_datos.json` e informes técnicos.
* **Archivos que NUNCA se suben (ignorados en `.gitignore`):**
  * `.env` (contiene la cookie privada de sesión).
  * `datos_*.json` (datos reales recolectados).
  * `descargas_*/` (imágenes y videos descargados).
  * `.venv/` y `__pycache__/`.

---

## Conceptos de Arquitectura de Software Aprendidos

1. **SPA (Single Page Application) y Client-Side Rendering**: Las plataformas como Instagram dependen de React para hidratar el DOM dinámicamente; las peticiones HTTP tradicionales reciben un cascarón vacío.
2. **Session Hijacking / Cookie Injection**: Cómo los identificadores de sesión evitan autenticaciones repetitivas y mitigan desafíos de seguridad (2FA/reCAPTCHA).
3. **Flujos Multimedia y MSE (MediaSource Extensions)**: Comprensión de por qué los navegadores no permiten hacer `fetch()` a URLs `blob:` y cómo inspeccionar el árbol React para llegar al archivo contenedor MP4 original.
4. **Resiliencia ante Heurísticas Cambiantes**: Implementación de fallbacks (lectura cruzada entre cabecera visible y etiquetas OpenGraph) para garantizar la consistencia de los datos.
5. **Desacoplamiento de Interfaz y Lógica**: Separación del motor de extracción por lotes (`extraer_playwright.py`) de la capa de presentación y control de usuario (`app.py`).

---

## Autor

**Erick Simbaña**  
*Ingeniería en Sistemas, 7.º semestre*  
*Facultad de Ingeniería y Ciencias Aplicadas*  
*Universidad Central del Ecuador (UCE) — 2026*
