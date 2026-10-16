"""Extrae bio, conteos y las publicaciones de un perfil abriéndolo en un navegador real.

Instalación (una vez):
    pip install playwright python-dotenv
    playwright install chromium

Uso:
    python extraer_playwright.py              # abre el navegador y extrae
    python extraer_playwright.py --reparsear  # recalcula bio/conteos del JSON guardado (sin Instagram)

- Usa un perfil de navegador propio en .pw_profile/ (guarda tu sesión: está en
  .gitignore, NUNCA lo subas a GitHub).
- Hace scroll lento para cargar las publicaciones (hasta el total que indica el perfil).
- Sin sesión, Instagram suele mostrar solo las primeras ~12. Si faltan, el script te
  pregunta si quieres iniciar sesión A MANO (cuenta secundaria) y continúa.
  No escribe usuario ni contraseña.
- Se detiene ante 429, verificación o login que no se resuelve. No reintenta.
"""
import json
import os
import random
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

TARGET = os.getenv("TARGET_USER", "sausage_player").strip().lstrip("@")
PERFIL_DIR = BASE / ".pw_profile"
SALIDA = BASE / "datos_sausage_player.json"
MAX_SCROLLS = 30

# ---------------------------------------------------------------- parsing (puro)
_NUM = r"(\d[\d.,]*(?:\s?(?:[KMB]|mil|mill\.?))?)"
RE_CONTEOS = re.compile(
    rf"{_NUM}\s+(?:followers|seguidores),\s*{_NUM}\s+(?:following|seguidos|siguiendo),"
    rf"\s*{_NUM}\s+(?:posts|publicaciones)",
    re.IGNORECASE,
)
RE_BIO_OG = re.compile(r"(?:on|en) Instagram:\s*[\"“«](.*)[\"”»]\s*$", re.DOTALL)
RE_SOLO_NUMERO = re.compile(r"^\d[\d.,]*\s?(?:[KMB]|mil|mill\.?)?$", re.IGNORECASE)
ETIQUETAS = {"posts", "post", "followers", "following", "publicaciones", "publicación",
             "seguidores", "seguidos", "siguiendo"}
BOTONES = {"follow", "seguir", "message", "mensaje", "enviar mensaje", "more", "más",
           "… more", "... more", "… más", "... más", "contact", "contacto"}


def a_numero(txt: str) -> int | None:
    """'1,234' -> 1234 | '1.2M' -> 1200000 | '1,2 M' -> 1200000 | '15 mil' -> 15000."""
    t = txt.strip().lower().replace("\xa0", " ")
    m = re.fullmatch(r"(\d[\d.,]*)\s?([kmb]|mil|mill\.?)?", t)
    if not m:
        return None
    cuerpo, sufijo = m.groups()
    if sufijo:
        mult = {"k": 1e3, "mil": 1e3, "m": 1e6, "mill": 1e6, "mill.": 1e6, "b": 1e9}[sufijo]
        return int(round(float(cuerpo.replace(",", ".")) * mult))
    return int(re.sub(r"[.,]", "", cuerpo))


def parsear_og(texto: str | None) -> dict:
    """Lee og:description: '1,234 Followers, 56 Following, 78 Posts - ... "bio"'."""
    salida = {"seguidores": None, "seguidos": None, "total_publicaciones": None, "biografia": None}
    if not texto:
        return salida
    m = RE_CONTEOS.search(texto)
    if m:
        salida["seguidores"], salida["seguidos"], salida["total_publicaciones"] = (
            a_numero(g) for g in m.groups()
        )
    b = RE_BIO_OG.search(texto)
    if b:
        salida["biografia"] = b.group(1).strip()
    return salida


def conteos_desde_cabecera(texto: str | None) -> dict:
    """Lee '50 publicaciones / 956 seguidores / 185 seguidos' del texto visible de la cabecera."""
    t = texto or ""

    def buscar(palabras: str) -> int | None:
        m = re.search(rf"{_NUM}\s+(?:{palabras})\b", t, re.IGNORECASE)
        return a_numero(m.group(1)) if m else None

    return {
        "seguidores": buscar("followers|seguidores"),
        "seguidos": buscar("following|seguidos|siguiendo"),
        "total_publicaciones": buscar("posts|publicaciones"),
    }


def aplicar_cabecera(datos: dict, cabecera: str | None) -> dict:
    """Los conteos de la cabecera (lo que ve el usuario) mandan sobre el meta og:description,
    que puede estar en caché y desactualizado. Se guardan ambos para poder compararlos."""
    CLAVES = ("seguidores", "seguidos", "total_publicaciones")
    datos["_conteos_og"] = {k: datos.get(k) for k in CLAVES}
    for k, v in conteos_desde_cabecera(cabecera).items():
        if v is not None:
            datos[k] = v
    nombre, bio_cab = nombre_y_bio_desde_cabecera(cabecera, datos.get("usuario") or TARGET)
    datos["nombre_completo"] = nombre or datos.get("nombre_completo")
    datos["biografia"] = datos.get("biografia") or bio_cab
    return datos


def nombre_y_bio_desde_cabecera(texto: str | None, usuario: str) -> tuple[str | None, str | None]:
    """Heurística: quita usuario, botones y conteos; la 1.ª línea restante es el nombre
    y las demás la biografía. Verifícalo contra lo que ves en el perfil."""
    lineas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    resto = [
        l for l in lineas
        if l.lower() != usuario.lower()
        and l.lower() not in BOTONES
        and l.lower() not in ETIQUETAS
        and not RE_SOLO_NUMERO.match(l)
        and not re.match(rf"^{_NUM}\s+(?:{'|'.join(ETIQUETAS)})$", l, re.IGNORECASE)
    ]
    if not resto:
        return None, None
    return resto[0], ("\n".join(resto[1:]) or None)


def tipo_y_codigo(url: str) -> tuple[str | None, str | None]:
    m = re.search(r"/(p|reel)/([^/?#]+)", url)
    return (("publicacion" if m.group(1) == "p" else "reel"), m.group(2)) if m else (None, None)


# ---------------------------------------------------------------- navegador
JS_CUADRICULA = """els => els.map(a => ({url: a.href, texto_alt: (a.querySelector('img') || {}).alt || ''}))"""


def hay_muro_de_login(page) -> bool:
    return "accounts/login" in page.url or page.locator('input[name="username"]').count() > 0


SENALES_VERIFICACION = ("challenge", "checkpoint", "recaptcha", "auth_platform")
MSG_VERIFICACION = (
    "[!] Instagram pidió una verificación (reCAPTCHA/challenge). Me detengo aquí.\n"
    "    No sigas con el script: ya es una señal de que la sesión o la red están en observación.\n"
    "    Cierra la ventana, espera varias horas y revisa la cuenta en tu navegador normal."
)


def hay_verificacion(page, texto_extra: str = "") -> bool:
    return any(s in (page.url + texto_extra) for s in SENALES_VERIFICACION)


def cargar_perfil(page) -> None:
    from playwright.sync_api import Error as PlaywrightError

    try:
        resp = page.goto(f"https://www.instagram.com/{TARGET}/", wait_until="domcontentloaded")
    except PlaywrightError as e:
        # Típico: la navegación fue interrumpida por una redirección a un reCAPTCHA.
        if hay_verificacion(page, str(e)):
            sys.exit(MSG_VERIFICACION)
        raise
    if resp is not None and resp.status == 429:
        sys.exit("[!] 429: Instagram está limitando las peticiones. Cierra y espera varias horas.")
    if resp is not None and resp.status == 404:
        sys.exit(f"[!] 404: no existe @{TARGET} o el nombre está mal escrito.")
    page.wait_for_timeout(4000)
    if hay_verificacion(page):
        sys.exit(MSG_VERIFICACION)


def leer_basico(page) -> dict:
    try:
        og = page.locator('meta[property="og:description"]').first.get_attribute("content", timeout=5000)
    except Exception:
        og = None
    try:
        cabecera = page.locator("header").first.inner_text(timeout=5000)
    except Exception:
        cabecera = None
    datos = aplicar_cabecera(parsear_og(og), cabecera)
    datos["_og_description"], datos["_texto_cabecera"] = og, cabecera
    return datos


def leer_cuadricula(page) -> list[dict]:
    return page.eval_on_selector_all('a[href*="/p/"], a[href*="/reel/"]', JS_CUADRICULA)


def recolectar_publicaciones(page, objetivo: int | None) -> list[dict]:
    """Scroll lento hasta alcanzar `objetivo` o hasta que dejen de aparecer nuevas."""
    encontradas: dict[str, dict] = {}
    sin_nuevas = 0
    for paso in range(MAX_SCROLLS):
        antes = len(encontradas)
        for it in leer_cuadricula(page):
            tipo, codigo = tipo_y_codigo(it["url"])
            encontradas.setdefault(it["url"], {"tipo": tipo, "shortcode": codigo, **it})
        print(f"    paso {paso + 1}: {len(encontradas)} publicaciones" + (f" de {objetivo}" if objetivo else ""))
        if objetivo and len(encontradas) >= objetivo:
            break
        sin_nuevas = sin_nuevas + 1 if len(encontradas) == antes else 0
        if sin_nuevas >= 3:
            break
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        page.wait_for_timeout(random.randint(2500, 4500))
    return list(encontradas.values())


def reparsear() -> None:
    """Recalcula conteos/bio desde el JSON ya guardado, SIN abrir Instagram."""
    d = json.loads(SALIDA.read_text(encoding="utf-8"))
    d["usuario"] = d.get("usuario") or TARGET
    og = parsear_og(d.get("_og_description"))
    d["biografia"] = og["biografia"]            # se recalcula con la heurística actual
    d.update({k: og[k] for k in ("seguidores", "seguidos", "total_publicaciones")})
    d = aplicar_cabecera(d, d.get("_texto_cabecera"))
    shutil.copy(SALIDA, SALIDA.with_suffix(".prev.json"))
    SALIDA.write_text(json.dumps(d, ensure_ascii=False, indent=4), encoding="utf-8")
    print("[OK] JSON recalculado sin abrir Instagram")
    for k in ("nombre_completo", "biografia", "seguidores", "seguidos", "total_publicaciones"):
        print(f"    {k}: {d[k]}")
    print(f"    (conteos según og:description: {d['_conteos_og']})")


def main() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PERFIL_DIR), headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            cargar_perfil(page)
            if hay_muro_de_login(page):
                print("[*] Instagram pide iniciar sesión. Hazlo a mano en la ventana (cuenta secundaria).")
                input("    Cuando veas tu feed, presiona Enter aquí para continuar... ")
                cargar_perfil(page)
                if hay_muro_de_login(page):
                    sys.exit("[!] Sigue pidiendo login. Me detengo aquí; no insistas.")

            basico = leer_basico(page)
            objetivo = basico["total_publicaciones"]
            print(f"[*] Perfil leído. Cargando publicaciones (objetivo: {objetivo})...")
            pubs = recolectar_publicaciones(page, objetivo)

            if objetivo and len(pubs) < objetivo:
                print(f"\n[!] Solo aparecieron {len(pubs)} de {objetivo}. Sin sesión Instagram limita lo que muestra.")
                if input("    ¿Iniciar sesión ahora (a mano) para cargar el resto? Enter = sí, n = no: ").strip().lower() != "n":
                    input("    Inicia sesión en la ventana y presiona Enter cuando termines... ")
                    cargar_perfil(page)
                    if hay_muro_de_login(page):
                        sys.exit("[!] Sigue pidiendo login. Me detengo aquí; no insistas.")
                    nuevo = leer_basico(page)
                    for k, v in nuevo.items():          # lo leído con sesión completa lo que faltaba
                        if v is not None:
                            basico[k] = v
                    pubs = recolectar_publicaciones(page, objetivo)
        finally:
            ctx.close()

    resultado = {
        "usuario": TARGET,
        "fuente": "playwright (perfil cargado en navegador real)",
        "extraido_el": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **{k: basico[k] for k in ("nombre_completo", "biografia", "seguidores", "seguidos", "total_publicaciones")},
        "publicaciones_extraidas": pubs,
        "_conteos_og": basico["_conteos_og"],
        "_og_description": basico["_og_description"],
        "_texto_cabecera": basico["_texto_cabecera"],
    }
    if SALIDA.exists():
        shutil.copy(SALIDA, SALIDA.with_suffix(".prev.json"))
    SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=4), encoding="utf-8")

    print("\n[OK] Resultado")
    for k in ("usuario", "nombre_completo", "biografia", "seguidores", "seguidos", "total_publicaciones"):
        print(f"    {k}: {resultado[k]}")
    print(f"    publicaciones guardadas: {len(pubs)}")
    print(f"    Guardado en: {SALIDA.name}")
    if resultado["biografia"] is None:
        print("[AVISO] No pude leer la biografía. Revisa _texto_cabecera en el JSON.")


if __name__ == "__main__":
    reparsear() if "--reparsear" in sys.argv else main()