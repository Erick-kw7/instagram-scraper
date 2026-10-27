# Instagram Profile Scraper con Playwright & Panel de Control

> **Proyecto Académico — Arquitectura de Software**  
> **Carrera de Ingeniería en Sistemas | 7.º Semestre**  
> **Universidad Central del Ecuador (UCE)**  
> **Autor:** Erick Simbaña  
> **Cuenta objetivo de la consigna:** `@sausage_player`

Este proyecto permite extraer, guardar y analizar la información de perfiles de Instagram de forma automatizada con **Playwright** en Python. Cuenta con un **Panel de Control Web** interactivo y fácil de usar, un módulo de **Análisis de Personalidad con Inteligencia Artificial (Google Gemini)** y un sistema para **Detectar Cuentas Falsas y Bots mediante la Ley de Benford**.

---

## Evolución del Proyecto: De Pruebas Previas a la Versión Final

Para fines de evaluación en la materia de **Arquitectura de Software**, se muestra la evolución desde las primeras pruebas iniciales hasta la versión final completa:

| Característica | Versión Inicial (Pruebas Previas) | Versión Final (Actual) |
|---|---|---|
| **Acceso a Instagram** | Sin sesión o inicio manual que causaba bloqueos y verificación constante. | **Inicio automático mediante cookies en `.env`**, navegando como un usuario real sin bloqueos ni ventanas molestas. |
| **Publicaciones** | Limitado a 12 o 24 publicaciones. | **100% de las publicaciones extraídas** (50 de 50 en la cuenta `@sausage_player`), revisadas una por una. |
| **Descarga de Fotos y Videos** | Ninguna (solo se guardaban textos). | **Descarga completa al disco**: fotos en alta resolución (`.jpg`), carruseles y videos reales (`.mp4`) listos para ver. |
| **Videos y Reels** | No se podían descargar por restricciones del navegador (`blob`). | **Descarga directa del video MP4 original**, inspeccionando los elementos internos de la página. |
| **Likes y Reacciones** | No estaban disponibles. | **Conteo real y detección de likes ocultos**, distinguiendo cuando el autor decidió no mostrarlos. |
| **Comentarios** | No estaban disponibles. | **Conteo oficial y muestra de comentarios**, separando las respuestas de la descripción del autor. |
| **Seguidores y Seguidos** | Solo el número total que aparece en la cabecera. | **Listas completas de usuarios**, guardando el nombre, usuario, enlace al perfil y foto de avatar. |
| **Interfaz de Usuario** | Solo mensajes en la consola de comandos. | **Panel de Control Web (`app.py`)**, con visor de fotos, reproductor de video, terminal de mensajes en vivo y botones sencillos. |
| **Personalidad con IA** | Sin análisis inteligente. | **Fase 2: Análisis con Google Gemini**, evaluando 5 rasgos de personalidad a partir de lo que publica el usuario. |
| **Detección de Bots** | Sin verificación de seguidores. | **Fase 3: Detección de Cuentas Falsas con Ley de Benford**, comparando números reales vs. esperados en gráfico de barras, líneas y reporte en Excel. |

---

## Qué Hace el Sistema

El programa guarda toda la información en un archivo ordenado `datos_<usuario>.json` y descarga el contenido multimedia en carpetas locales:

- **Datos del perfil**: Nombre de usuario, nombre visible, biografía, foto de perfil y si la cuenta es verificada o privada.
- **Números de la cuenta**: Total de publicaciones, seguidores y seguidos.
- **Publicaciones completas**:
  - Tipo de publicación: foto simple, carrusel (varias fotos) o reel/video.
  - Fecha, enlace permanente y descripción del texto.
  - Conteo de likes (o si están ocultos) y comentarios reales.
  - Fotos guardadas en `.jpg` y videos guardados en `.mp4`.
- **Listas de usuarios**: Nombres, perfiles y fotos de seguidores y seguidos.
- **Análisis de personalidad (Fase 2)**: Diagnóstico del estilo de la persona a partir de sus publicaciones usando Inteligencia Artificial.
- **Detección de cuentas falsas (Fase 3)**: Revisión matemática de los seguidores con la Ley de Benford para saber si la audiencia es real o comprada.

> **Nota sobre privacidad:** Los datos extraídos reales de la cuenta evaluada no se publican en internet y se mantienen protegidos localmente mediante `.gitignore`. Para referencia de la estructura, se incluye el archivo [ejemplo_datos.json](ejemplo_datos.json).

---

## Tecnologías Utilizadas

| Herramienta | Función en el Proyecto |
|---|---|
| **Python 3.10+** | Lenguaje principal del proyecto para organizar datos, cálculos y archivos. |
| **Playwright (Chromium)** | Navegador automatizado para entrar a Instagram, hacer scroll y descargar contenido como una persona real. |
| **Google Gemini API** | Inteligencia Artificial para leer las publicaciones y describir los rasgos de personalidad. |
| **SciPy y NumPy** | Cálculos matemáticos sencillos para comparar la distribución de seguidores con la Ley de Benford. |
| **Matplotlib** | Creación de gráficos comparativos claros con barras y líneas. |
| **OpenPyXL** | Creación del archivo de Excel (`.xlsx`) con las tablas de seguidores y el gráfico insertado. |
| **python-dotenv** | Manejo seguro de credenciales (cookies y claves API) mediante el archivo local `.env`. |
| **HTML, CSS y JavaScript** | Diseño visual del Panel de Control Web interactivo que corre en `localhost:5000`. |

---

## Fase 2: Análisis de Personalidad con Inteligencia Artificial (Big Five / OCEAN)

En esta fase, el sistema utiliza **Google Gemini** para entender cómo se comunica la persona y cuál es su estilo de personalidad basándose en lo que comparte en sus redes.

### 1. Los 5 Rasgos de la Personalidad Explicados de Forma Simple
El sistema analiza 5 dimensiones básicas de la personalidad humana:
1. **Apertura a nuevas experiencias (O)**: Qué tan curiosa, creativa y abierta al arte o nuevas ideas es la persona.
2. **Organización y responsabilidad (C)**: Qué tan enfocada, ordenada y disciplinada se muestra en sus metas y proyectos.
3. **Extraversión y energía (E)**: Qué tan sociable, activa y expresiva es al interactuar con el público.
4. **Amabilidad y empatía (A)**: Qué tan cálida, solidaria y respetuosa es en sus mensajes y respuestas.
5. **Calma y sensibilidad emocional (N)**: Cómo gestiona sus emociones y qué tan tranquila o reactiva se expresa ante las situaciones cotidianas.

### 2. Cómo Funciona la Conexión con Gemini
- El script selecciona las 10 publicaciones más representativas y la biografía del usuario.
- Envía este contenido a Gemini con una instrucción clara para que evalúe cada rasgo con una puntuación del 0% al 100%.
- Gemini entrega un resumen en español, identifica el rasgo dominante, sugiere un arquetipo (por ejemplo: "Creador Creativo" o "Conector Social") y cita frases textuales de los posts como prueba de cada rasgo.
- Los resultados se guardan en `Análisis BigFive/analisis_bigfive_<usuario>.json` y se pueden ver directamente en la pestaña del Panel Web con barras de progreso de colores.

---

## Fase 3: Detección de Bots y Cuentas Falsas con la Ley de Benford

El módulo [analizar_benford.py](analizar_benford.py) revisa la lista de seguidores de la cuenta para comprobar si son personas reales o cuentas automáticas / compradas.

### 1. ¿Qué es la Ley de Benford en Palabras Sencillas?
En la vida real, cuando las cosas crecen de forma natural (como la población de ciudades, precios en tiendas o el número de seguidores que acumulan las personas reales), los números no empiezan con cualquier dígito con la misma probabilidad.

Existe una regla matemática natural muy curiosa llamada **Ley de Benford**:
- Alrededor del **30.1%** de los números empiezan con el dígito **1**.
- Cerca del **17.6%** empiezan con el **2**.
- Conforme el dígito sube, la frecuencia baja: el **3** aparece el 12.5%, el **4** el 9.7%, y así sucesivamente...
- Menos del **4.6%** de los números empiezan con el dígito **9**.

### 2. ¿Cómo se Descubren los Bots con Esta Regla?
- **Seguidores Reales**: Cada persona que sigue una cuenta tiene su propia cantidad de seguidores (unos tienen 15, otros 120, otros 1400, otros 25, otros 350). Como crecen de forma orgánica, la primera cifra de esos números cumple casi a la perfección la curva de Benford (muchos empiezan con 1, menos con 2, y muy pocos con 9).
- **Cuentas Falsas o Bots Comprados**: Cuando alguien compra seguidores o utiliza redes de bots, las cuentas falsas suelen tener números inventados por un programa de computadora, repartidos de forma pareja o en bloques fijos (por ejemplo, muchas cuentas creadas con 50, 100 o números aleatorios planos). Esto rompe por completo la regla natural de Benford, haciendo saltar las alertas de manipulación.

### 3. Explicación Natural de los Perfiles con 0 Seguidores y Cuentas sin Datos
Durante el análisis de la cuenta `@sausage_player` se revisaron los seguidores extraídos y el sistema clasifica los casos de la siguiente manera:

- **Perfiles válidos analizados (678 cuentas)**: Son perfiles activos cuyos seguidores son mayores a 0 (por ejemplo: 14, 250, 1300). En todos ellos se puede identificar claramente el primer dígito (1, 2, 3... hasta 9) para construir la gráfica.
- **Cuentas con 0 seguidores (7 perfiles)**: Son cuentas completamente nuevas o que nunca han tenido seguidores. El número cero (0) no empieza con ningún dígito del 1 al 9, por lo que no es posible ubicarlo en las barras del 1 al 9.
- **Cuentas sin datos visibles (4 perfiles)**: Cuentas privadas, restringidas o con contadores no disponibles al momento de la consulta.

**¿Por qué es importante mostrarlos?**  
Para mantener una total claridad y honestidad en el informe, el sistema no borra estos perfiles en silencio: cuenta exactamente cuántos ceros y cuántos vacíos existen, y los presenta en tarjetas visibles en el panel web. Así el usuario sabe exactamente de dónde salieron los datos y por qué la gráfica trabaja con los 678 perfiles con número mayor a cero.

### 4. Gráfico Comparativo: Barras y Líneas
Para que la interpretación sea inmediata y visual, el sistema genera una imagen con:
- **Barras Azules y Línea Azul con Cuadrados**: Representan la distribución real de los seguidores de la cuenta.
- **Barras Rojas y Línea Roja con Círculos**: Representan la expectativa teórica que dicta la Ley de Benford.
- **Resultado del diagnóstico**: Si la línea azul sigue de cerca a la línea roja (empezando cerca del 30% en el dígito 1 y bajando suavemente hasta el 9), el sistema concluye con **Comportamiento Orgánico**, confirmando que la audiencia es real.

El gráfico se guarda automáticamente en:
`Análisis Benford/grafico_benford_seguidores_sausage_player.png`

### 5. Reporte en Hoja de Excel (.xlsx)
El sistema genera un archivo de Excel completo y ordenado con diseño profesional:
- **Lista de usuarios**: Tabla detallada con cada seguidor analizado, su nombre de usuario, cantidad de seguidores, cantidad de seguidos y el primer dígito identificado.
- **Tabla de frecuencias**: Cuántos seguidores empezaron con 1, cuántos con 2, hasta el 9, comparando el porcentaje real frente al teórico.
- **Gráfico insertado**: La imagen comparativa viene incrustada dentro de la misma hoja para poder revisarla o presentarla de inmediato.

El archivo se guarda en:
`Análisis Benford/benford_seguidores_sausage_player.xlsx`

---

## Estructura del Repositorio

```text
instagram_scraper_final/
├── Datos Extraídos/                        # Archivos JSON con los datos del perfil (datos_*.json)
├── Análisis BigFive/                       # Reportes de personalidad de Gemini AI (analisis_bigfive_*.json)
├── Análisis Benford/                       # Libros Excel (.xlsx), gráficos (.png) y resúmenes JSON
├── Descargas Multimedia/                   # Fotos (.jpg) y videos (.mp4) descargados localmente
├── app.py                                  # Panel de Control Web y servidor local (localhost:5000)
├── extraer_playwright.py                   # Fase 1: Extracción de posts, fotos, videos y listas
├── analizar_personalidad_gemini.py         # Fase 2: Análisis de personalidad con Inteligencia Artificial
├── analizar_benford.py                     # Fase 3: Detección de bots con Ley de Benford y reporte Excel
├── ejemplo_datos.json                      # Ejemplo de referencia de la estructura de datos
├── requirements.txt                        # Lista de librerías necesarias de Python
├── .env.example                            # Plantilla para configurar cookies y clave de Gemini
├── .gitignore                              # Archivos privados y descargas que no se suben a Git
└── README.md                               # Documentación general del proyecto
```

---

## Guía de Instalación y Uso

### 1. Preparar el Entorno en Windows PowerShell

```powershell
# Crear y activar el entorno virtual
python -m venv .venv
.venv\Scripts\Activate.ps1

# Instalar las librerías necesarias
pip install -r requirements.txt

# Instalar el navegador de Playwright
playwright install chromium
```

### 2. Configurar las Claves en `.env`

Copia el archivo de ejemplo `.env.example` y crea tu archivo `.env`:

```powershell
copy .env.example .env
```

Edita el archivo `.env` con las cookies de tu navegador y tu clave de Gemini:
```ini
TARGET_USER=sausage_player
IG_SESSIONID=tu_sessionid_aqui
IG_DS_USER_ID=tu_ds_user_id_aqui
IG_CSRFTOKEN=tu_csrftoken_aqui
GEMINI_API_KEY=tu_clave_de_gemini_aqui
```

---

### 3. Cómo Ejecutar el Proyecto

#### Opción 1: Desde el Panel de Control Web (Recomendado)

```powershell
python app.py
```

Abre en tu navegador `http://localhost:5000` donde podrás:
- Iniciar la extracción de publicaciones, fotos y videos viendo los mensajes en tiempo real.
- Ver la galería de fotos y reproducir los videos descargados.
- Consultar la pestaña de **Psicología Big Five (IA)** con los gráficos de personalidad.
- Entrar a la pestaña **Detección de Bots (Ley de Benford)**, ver la gráfica comparativa con dos líneas y dos barras, y descargar el reporte en Excel con un solo clic.

#### Opción 2: Desde la Consola de Comandos (Scripts Individuales)

```powershell
# Fase 1: Extraer publicaciones y seguidores
python extraer_playwright.py --auto

# Fase 2: Analizar personalidad con Gemini AI
python analizar_personalidad_gemini.py sausage_player

# Fase 3: Analizar seguidores con la Ley de Benford
python analizar_benford.py --usuario sausage_player --tipo seguidores --from-json
```

---

## Aprendizajes Principales en Arquitectura de Software

1. **Navegación moderna en páginas dinámicas**: Comprensión de cómo plataformas como Instagram cargan su contenido en vivo con JavaScript, requiriendo un navegador real en lugar de simples descargas de texto.
2. **Uso seguro de sesiones con cookies**: Conectar sesiones existentes sin tener que escribir contraseñas repetidamente, evitando bloqueos y verificaciones.
3. **Descarga de videos reales**: Superar las limitaciones de los enlaces temporales en memoria para ubicar y guardar los archivos MP4 originales.
4. **Integración práctica de Inteligencia Artificial**: Conectar APIs de lenguaje natural (Gemini) para transformar textos no estructurados en perfiles ordenados y comprensibles.
5. **Detección de patrones con matemáticas naturales**: Uso de reglas universales como la Ley de Benford para evaluar si los datos de una red social son legítimos o inventados.
6. **Diseño modular y ordenado**: Organización del código en componentes independientes: extracción de datos (`extraer_playwright.py`), análisis inteligente (`analizar_personalidad_gemini.py`), detección de bots (`analizar_benford.py`) e interfaz de usuario (`app.py`).

---

## Autor

**Erick Simbaña**  
*Ingeniería en Sistemas, 7.º semestre*  
*Facultad de Ingeniería y Ciencias Aplicadas*  
*Universidad Central del Ecuador (UCE) — 2026*