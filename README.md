# Instagram Profile Scraper con Playwright

Proyecto académico — Arquitectura de Software, 7.º semestre, Ingeniería en Sistemas, Universidad Central del Ecuador.

Este proyecto explora Playwright con Python para leer el contenido que muestra la página pública de un perfil de Instagram (la cuenta asignada en la consigna, @sausage_player) y guardarlo en JSON.

> **Los resultados son una captura tomada en una fecha concreta, no datos en tiempo real.**
> Una respuesta HTTP 429 indica que el servidor limitó la solicitud; por sí sola no permite determinar la causa.

## Objetivo

Organizar en JSON los campos disponibles durante la consulta:

- Usuario y nombre visible
- Biografía
- Conteos de seguidores, seguidos y publicaciones
- Enlaces de publicaciones y reels detectados
- Texto alternativo de las imágenes (cuando está disponible)

El resultado real (`datos_sausage_player.json`) **no se incluye en este repositorio**. El archivo `ejemplo_datos.json` contiene datos ficticios que muestran la estructura.

## Resultados observados

| Método | Resultado |
|---|---|
| Requests (endpoint interno `web_profile_info`, con cookies de una cuenta secundaria) | HTTP 429; no se obtuvieron datos. La causa no se pudo determinar. |
| Scrapy | Practicado sobre `quotes.toscrape.com` (100 registros). No se usó contra Instagram. Los archivos de esa práctica no se incluyen en este repositorio. |
| Playwright (navegador real) | En la primera captura se obtuvieron nombre, biografía, conteos y 50 publicaciones, **iniciando sesión**. |
| Playwright (capturas posteriores) | Sin sesión aparecieron menos publicaciones (24 y luego 12) y en uno de los intentos Instagram mostró una verificación (reCAPTCHA). El script se detiene en ese caso. No se determinó la causa. |

## Herramientas

| Herramienta | Uso en el proyecto |
|---|---|
| Python 3.12 | Lenguaje de programación |
| Playwright | Abre Chromium y permite leer el DOM que muestra el navegador |
| python-dotenv | Lee configuración local desde `.env` (usuario objetivo) |

`requests`, `beautifulsoup4` y `Scrapy` están en `requirements.txt` por las pruebas descritas arriba, pero **no forman parte de la ejecución principal**. Selenium y Puppeteer no se usaron.

## Cómo funciona

1. Playwright abre Chromium con un perfil de navegador persistente (`.pw_profile/`).
2. Carga la página del perfil. Se detiene si recibe 429, 404 o una verificación (reCAPTCHA/challenge).
3. Lee dos fuentes de texto de la página: el metadato `og:description` y el texto visible de la cabecera.
4. Obtiene los conteos de la cabecera (lo que ve el usuario) y, si no están, del metadato. El nombre y la biografía salen de la cabecera con una heurística: se quitan usuario, botones y conteos.
5. Hace scroll lento (pausas aleatorias de 2,5 a 4,5 s, máximo 30 pasos) y recolecta los enlaces `/p/` y `/reel/` con el texto alternativo de cada imagen.
6. Guarda el resultado en JSON. Antes de sobrescribir, copia el archivo anterior a `datos_sausage_player.prev.json`.

Si Instagram pide iniciar sesión, el script espera a que el usuario lo haga **a mano**. No escribe usuario ni contraseña.

## Estructura del proyecto

```
instagram-scraper/
├── extraer_playwright.py   # Script principal
├── ejemplo_datos.json      # Estructura de salida con datos ficticios
├── requirements.txt        # Dependencias
├── .env.example            # Plantilla de variables de entorno
├── .gitignore              # Excluye .env, .pw_profile/, entornos, datos reales
└── README.md
```

## Instalación y uso

```powershell
git clone <url-del-repositorio>
cd instagram-scraper
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
python extraer_playwright.py
```

- Si aparece una verificación (reCAPTCHA), **no repitas la ejecución**: el script ya se detuvo y volver a intentarlo no es recomendable.
- Para recalcular bio y conteos desde un JSON ya guardado, sin abrir Instagram:

```powershell
python extraer_playwright.py --reparsear
```

## Formato de salida

Ver `ejemplo_datos.json`. Campos principales:

| Campo | Contenido |
|---|---|
| `usuario`, `nombre_completo`, `biografia` | Identificación y texto del perfil |
| `seguidores`, `seguidos`, `total_publicaciones` | Conteos (preferencia: cabecera visible) |
| `publicaciones_extraidas` | Lista con `tipo`, `shortcode`, `url`, `texto_alt` |
| `extraido_el` | Fecha y hora UTC de la captura |
| `_conteos_og` | Conteos leídos del metadato, para comparar |
| `_og_description`, `_texto_cabecera` | Texto crudo, para revisar o ajustar el parseo |

## Limitaciones

- Es una captura puntual: los conteos y las publicaciones visibles cambian con el tiempo.
- **Conteos:** el metadato `og:description` y la cabecera visible pueden diferir. En las capturas realizadas, el valor de «seguidos» del metadato difirió del de la cabecera, y una revisión manual coincidió con la cabecera. Por eso se prefiere la cabecera y se guardan ambas lecturas.
- La biografía se obtiene con una heurística; conviene verificarla contra el perfil.
- Seguidores y seguidos son solo totales, no listas de usuarios.
- De cada publicación solo se guardan enlace, tipo, shortcode y texto alternativo; no hay fecha, likes ni comentarios.
- Sin sesión, Instagram limita cuántas publicaciones muestra, y ese límite no fue constante entre capturas.
- El script depende de la estructura actual de la página; un cambio en Instagram puede romperlo.
- No se determinó la causa del HTTP 429 ni de la verificación reCAPTCHA.

## Seguridad y ética

- `.env` y `.pw_profile/` (que puede guardar cookies de sesión) están en `.gitignore`. **Nunca se suben.**
- Se usó una cuenta secundaria y una sola sesión de navegador con pausas entre scrolls.
- El script se detiene ante 429, verificación o un login que no se resuelve. No reintenta.
- Los datos reales pertenecen a una persona real y **no se publican** en este repositorio.
- Instagram restringe la recolección automatizada sin permiso (ver referencias). Este trabajo es académico y no se redistribuyen los datos.
- Al terminar, borrar `.pw_profile/` elimina la sesión guardada.

## Conceptos aprendidos

- **SPA y renderizado dinámico:** la página se arma con JavaScript, por eso se usa un navegador real.
- **HTTP 429:** el servidor limitó las solicitudes; no explica por sí solo el motivo.
- **Perfil persistente de Playwright:** `launch_persistent_context` guarda el estado del navegador en disco.
- **Scroll lento y condiciones de parada:** hasta el total esperado, sin novedades o un máximo de pasos.
- **Selectores CSS:** `a[href*="/p/"]`, `a[href*="/reel/"]` y el `alt` de las imágenes.
- **Parseo heurístico y expresiones regulares:** lectura de conteos y biografía desde texto.
- **Verificar contra otra fuente:** comparar metadato y cabecera reveló una discrepancia.
- **Separar configuración y código:** `python-dotenv` y `.env`.

## Referencias

- Playwright para Python: https://playwright.dev/python/docs/intro
- Instagram, términos de recolección automatizada de datos: https://www.facebook.com/legal/automated_data_collection_terms
- MDN, código de estado HTTP 429: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- Tutorial de Scrapy: https://docs.scrapy.org/en/latest/intro/tutorial.html

## Autor

Erick Simbaña— Ingeniería en Sistemas, 7.º semestre, UCE — 2026
