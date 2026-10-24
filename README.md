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
| **Descarga Multimedia** | Ninguna (solo se guardaba el texto alternativo `alt`). | **Descarga completa a disco**: fotos en alta resolución (`.jpg`), carruseles y reels/videos nativos (`.mp4`) en `Descargas Multimedia/descargas_<usuario>/`. |
| **Manejo de Videos / Reels** | No soportado; bloqueado por flujos en memoria `blob:https://...`. | **Superación de blobs**: inspección de componentes React (`__reactFiber`) para extraer el manifiesto MPEG-DASH `<BaseURL>` y descargar el video real. |
| **Reacciones (Likes)** | No disponible en la versión inicial. | **Conteo exacto y detección de Likes Ocultos** (`likes_ocultos: true`, `likes: null`) cuando el autor los oculta. |
| **Comentarios** | No disponible en la versión inicial. | **Conteo real y oficial** (`Ver los X comentarios`), filtrando respuestas legítimas y descartando el pie de foto del autor y dots de carrusel. |
| **Seguidores y Seguidos** | Solo conteos numéricos de la cabecera. | **Listas completas de usuarios**: extracción de `@usuario`, nombre visible, URL y avatar mediante scroll modal con Set anti-duplicados. |
| **Interfaz de Usuario** | Únicamente línea de comandos (CLI) con pausas manuales. | **Panel de Control Web (`app.py`)** con terminal de logs en vivo, visor de galería y comprobador de cookies. |
| **Enriquecimiento con IA** | Inexistente (solo recolección de datos crudos sin interpretación). | **Fase 2: Perfilado Psicométrico Big Five (OCEAN)** con Google Gemini AI (`gemini-3.8-flash`), determinando arquetipos, puntuaciones porcentuales y evidencias empíricas. |

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
- **Enriquecimiento Psicológico (Fase 2)**: Metadatos psicométricos con puntuación de rasgos OCEAN, arquetipo de usuario y conclusión académica.

> **Nota sobre privacidad:** Por respeto a la privacidad de datos reales, los archivos de captura reales (`datos_sausage_player.json` y la carpeta `Descargas Multimedia/descargas_sausage_player/`) **no se publican en el repositorio** y están protegidos por `.gitignore`. Se incluye el archivo [ejemplo_datos.json](ejemplo_datos.json) con datos estructurados de referencia.

---

## Herramientas y Tecnologías

| Herramienta | Rol en la Arquitectura | Justificación Técnica |
|---|---|---|
| **Python 3.10+** | Lenguaje Principal | Manejo de flujos de datos, peticiones y estructuración JSON. |
| **Playwright (Chromium)** | Automatización Web (Fase 1) | Emulación de navegador real capaz de ejecutar JavaScript moderno y Single Page Applications (SPA). |
| **Google Gemini REST API** | Enriquecimiento con IA (Fase 2) | Inferencia de lenguaje natural para psicometría computacional (Big Five/OCEAN) con fallback dinámico de modelos (`gemini-3.8-flash`, `gemini-3.5-flash-lite`, etc.) y respuesta JSON estructurada. |
| **python-dotenv** | Seguridad y Configuración | Carga de variables de entorno locales desde `.env` sin exponer credenciales ni claves de API en el código. |
| **Requests** | Validación y Comunicación API | Comprobación de cookies de Instagram y consumo REST liviano de Gemini AI sin dependencias externas pesadas. |
| **Vanilla HTML/CSS/JS** | Dashboard Web (`app.py`) | Panel de control local interactivo con soporte de pestañas, logs en vivo y visualizador psicométrico reactivo. |

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
7. **Enriquecimiento Psicométrico Big Five (OCEAN)**:
   A partir del archivo JSON extraído en la Fase 1, el módulo `analizar_personalidad_gemini.py` toma las primeras 10 publicaciones y la biografía del usuario. Se envía un prompt de psicometría computacional a la API de Google Gemini (vía REST con fallback dinámico entre modelos recientes como `gemini-3.8-flash`). El análisis genera puntuaciones del 0 al 100% para las 5 dimensiones OCEAN, un arquetipo de personalidad, evidencias textuales extraídas del contenido y una conclusión ética/arquitectónica. El resultado se guarda en `analisis_bigfive_<usuario>.json` y enriquece `datos_<usuario>.json`.

---

## Fase 2: Módulo Psicométrico Big Five (OCEAN) con Gemini AI

El módulo psicométrico implementa técnicas de **Psicometría Computacional** y **Minería de Huella Digital** para analizar el perfil conductual del usuario a partir de sus contenidos públicos en Instagram.

### 1. ¿Qué es el Modelo Big Five (OCEAN)?
El modelo de los Cinco Grandes Factores de la Personalidad es el estándar científico más respaldado en psicología moderna para clasificar la personalidad en 5 dimensiones continuas:
- **O (Openness - Apertura a la Experiencia)**: Creatividad, curiosidad intelectual, estética, variedad temática y originalidad.
- **C (Conscientiousness - Responsabilidad / Tesón)**: Organización, constancia, atención al detalle y orientación a metas.
- **E (Extraversion - Extraversión)**: Sociabilidad, dinamismo, energía expresiva y búsqueda de interacción social.
- **A (Agreeableness - Amabilidad / Afabilidad)**: Empatía, calidez, tono cooperativo y cercanía con la comunidad.
- **N (Neuroticism - Reactividad Emocional)**: Grado de vulnerabilidad o reactividad emocional frente a estabilidad y templanza.

### 2. ¿Qué se usa en esta función?
- **Motor de Inferencia LLM**: Google Gemini REST API (endpoint `/v1beta/models/{modelo}:generateContent`).
- **Selección Dinámica de Modelos**: Sistema de auto-descubrimiento y fallback que consulta los modelos activos en la cuenta del usuario, priorizando versiones optimizadas (`gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`).
- **Determinismo y Estructura**: Invocación con `temperature: 0.2` y `responseMimeType: "application/json"` para garantizar una salida JSON válida según un esquema estricto (arquetipo, rasgo dominante, dimensiones con puntajes 0-100%, nivel y evidencias).
- **Consumo HTTP Nativo**: Uso directo de la biblioteca estándar `requests` sin atarse a SDKs experimentales que puedan generar conflictos de dependencias en Python 3.10+.
- **Seguridad**: Inyección estricta de `GEMINI_API_KEY` desde `.env` local, sin transmisión en repositorios ni exposición en el cliente.

### 3. ¿Dónde se usa en el proyecto?
- **Motor Backend / CLI (`analizar_personalidad_gemini.py`)**: Script autónomo invocable por terminal (`python analizar_personalidad_gemini.py <usuario>`) con visualización gráfica en consola mediante barras de progreso ASCII (`████░░░░`).
- **Servidor Web y Endpoints REST (`app.py`)**:
  - `GET /api/bigfive?usuario=<user>`: Lee y entrega el JSON psicométrico para renderizado asíncrono.
  - `POST /api/ejecutar_bigfive`: Dispara la inferencia de Gemini en un hilo en segundo plano (`threading.Thread`) sin bloquear la navegación ni la terminal de logs del panel.
- **Panel de Control Web Frontend (`app.py` - Pestaña "Psicología Big Five")**:
  - **Header Card**: Muestra el arquetipo dominante (ej. *'El Conector Lúdico'*), el rasgo predominante y el modelo Gemini exacto utilizado.
  - **Métricas OCEAN**: 5 tarjetas interactivas con barras de progreso coloreadas según la dimensión, porcentaje numérico (0-100%) e indicador de nivel (Alto, Medio, Bajo).
  - **Evidencias Empíricas**: Citas textuales extraídas de publicaciones o de la biografía que sustentan cada rasgo asignado.
  - **Conclusión Académica**: Reflexión ética sobre el perfilado digital y el impacto en arquitectura de software.
- **Persistencia Dual Organizada**:
  - Archivo exclusivo: `Análisis BigFive/analisis_bigfive_<usuario>.json`.
  - Integración en archivo maestro: Incrustado dentro del campo `"analisis_bigfive"` en `Datos Extraídos/datos_<usuario>.json`.

## Estructura del Repositorio

```text
instagram-scraper/
├── Datos Extraídos/                        # Carpeta con JSONs estructurados de perfiles (datos_*.json)
├── Análisis BigFive/                       # Carpeta con análisis psicométricos de Gemini AI (analisis_bigfive_*.json)
├── Descargas Multimedia/                   # Carpeta contenedora de descargas (descargas_<usuario>/)
├── app.py                                  # Panel de Control Web y servidor local (localhost:5000)
├── extraer_playwright.py                   # Fase 1: Motor Playwright de extracción y descargas
├── analizar_personalidad_gemini.py         # Fase 2: Motor de enriquecimiento psicológico (Big Five / OCEAN)
├── ejemplo_datos.json                      # Estructura de salida JSON con datos de ejemplo
├── requirements.txt                        # Dependencias de Python
├── .env.example                            # Plantilla de variables de entorno (Cookies + GEMINI_API_KEY)
├── .gitignore                              # Exclusión de .env, carpetas de datos reales y descargas
├── README.md                               # Documentación del proyecto

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

### 3. Configurar API Key de Gemini en `.env` (Fase 2)

Para la fase de enriquecimiento psicométrico, agrega tu clave gratuita obtenida de Google AI Studio en el archivo `.env`:
```ini
GEMINI_API_KEY=AIzaSy...tu_clave_aqui
```

> **Aviso de Seguridad:** La clave `GEMINI_API_KEY` se carga **exclusivamente de forma local** desde `.env`. Nunca se sube al repositorio ni se comparte en texto plano.

---

### 4. Ejecución

#### Opción A: Mediante el Panel de Control Web (Recomendado)
```powershell
python app.py
```
Abre en tu navegador `http://localhost:5000` para:
- Iniciar extracciones con Playwright y ver terminal de logs en tiempo real.
- Visualizar la pestaña **Psicología Big Five (IA)** con gráficos de barras OCEAN y evidencias citadas.
- Re-ejecutar inferencias con Gemini AI en un clic.

#### Opción B: Motor de Extracción por CLI (Fase 1)
```powershell
# Extraer publicaciones del perfil
python extraer_playwright.py --auto
```

#### Opción C: Motor de Enriquecimiento Psicométrico por CLI (Fase 2)
```powershell
# Analiza los 10 primeros posts y bio con Gemini AI bajo el modelo OCEAN
python analizar_personalidad_gemini.py
```
Genera el reporte en consola con barras de progreso y guarda los resultados en `analisis_bigfive_sausage_player.json` y `datos_sausage_player.json`.

---

## Seguridad y Buenas Prácticas para Git

Al mantener este repositorio en Git:

* **Archivos para control de versiones (incluidos):** `extraer_playwright.py`, `analizar_personalidad_gemini.py`, `app.py`, `requirements.txt`, `.env.example`, `.gitignore`, `README.md`, `ejemplo_datos.json` e informes técnicos.
* **Archivos que no se suben al repositorio (ignorados en `.gitignore`):**
  * `.env` (contiene cookies de Instagram y GEMINI_API_KEY privada).
  * `datos_*.json` y `analisis_bigfive_*.json` (datos reales recolectados).
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
