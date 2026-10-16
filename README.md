# Instagram Profile Scraper - @sausage_player
> Proyecto academico - Arquitectura de Software, 7mo semestre, UCE
> Extraccion de datos públicos de Instagram usando Playwright (navegador real) con persistencia de sesión.

## Objetivo
Extraer en JSON: usuario, nombre_completo, biografia, seguidores, seguidos, total_publicaciones, publicaciones_extraidas.
Resultado real (local, no versionado): datos_sausage_player.json
Ejemplo de formato (versionado): ejemplo_datos.json

## Stack tecnico
| Herramienta | Version | Uso |
|-------------|---------|-----|
| Python | 3.12 | Lenguaje base |
| Playwright | 1.40+ | Navegador real (Chromium) - renderiza JS, cookies, scroll, maneja login |
| python-dotenv | 1.0+ | Variables de entorno (.env) |
| Scrapy | 2.11+ | Framework scraping - FUNCIONA en sitios estaticos (practica: quotes.toscrape.com) |
| Requests | 2.31+ | HTTP simple - NO sirve para Instagram (API privada da HTTP 429) |
| BeautifulSoup4 | 4.12+ | Parsing HTML - complemento util

Leccion clave: Instagram es SPA que carga datos via JS. requests + API privada (/api/v1/users/web_profile_info/) devuelve HTTP 429 inmediato. Playwright con navegador real y sesion persistente funciono en este intento, pero NO garantiza acceso permanente ni elimina restricciones de Instagram; el perfil persistente guarda cookies de sesion.

## Estructura
instagram-scraper/
├── extraer_playwright.py       # Script principal (Playwright + scroll + parsing)
├── ejemplo_datos.json          # Ejemplo de formato con datos FICTICIOS (versionado)
├── requirements.txt            # Dependencias Python
├── .env.example                # Plantilla de variables de entorno
├── .gitignore                  # Protege .env, .pw_profile/, venv/, caches
└── README.md                   # Este archivo

NOTA: datos_sausage_player.json (datos reales) NO se sube a GitHub publico sin autorizacion.

## Instalacion y uso
1. git clone <url> && cd instagram-scraper
2. python -m venv .venv && .venv\Scripts\Activate.ps1
3. pip install -r requirements.txt && playwright install chromium
4. Primera vez: python extraer_playwright.py (abre ventana, login manual, Enter)
5. Ejecuciones siguientes: python extraer_playwright.py (usa perfil guardado)

## Seguridad y etica
- .pw_profile/ (sesion/cookies) en .gitignore - NUNCA subir
- .env (credenciales) en .gitignore - NUNCA subir
- Usar cuenta secundaria
- Delays aleatorios 2.5-4.5s entre scrolls
- Si Instagram muestra verificacion (challenge) o login wall, el script se detiene
- Datos extraidos: solo informacion publica del perfil (bio, conteos, captions visibles)

## Sobre Scrapy (para el informe)
Se probo Scrapy (spider en insta_project/) contra la API privada de Instagram y recibio HTTP 429 en todos los intentos. Scrapy FUNCIONA correctamente en sitios estaticos (ej. quotes.toscrape.com, carpeta practica_scrapy/). Los archivos de Scrapy no se incluyen en este repo; se pueden recuperar si la rubrica exige mostrar esa implementacion.

## Conceptos aprendidos
- SPA / Renderizado dinamico: Instagram carga DOM via JS
- HTTP 429: API privada bloquea sin fingerprint de navegador
- Persistencia de sesion: Playwright launch_persistent_context guarda cookies en disco
- Scroll infinito: window.scrollBy + espera + deteccion fin
- Selectores CSS: a[href*=/p/], a[href*=/reel/] + img[alt] para captions
- Parsing heuristico: og:description meta tag + header text para bio/conteos
- Variables de entorno: python-dotenv separa configuracion de codigo

## Referencias
- Playwright Python Docs: https://playwright.dev/python/docs/intro
- Instagram Automated Data Collection Terms: https://www.facebook.com/legal/automated_data_collection_terms
- MDN HTTP 429: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429
- Scrapy Tutorial: https://docs.scrapy.org/en/latest/intro/tutorial.html

## Autor
Erick - Ingenieria en Sistemas, 7mo semestre, UCE - 2026
