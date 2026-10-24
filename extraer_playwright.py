"""
=============================================================================
INSTAGRAM SCRAPER  (PLAYWRIGHT)
=============================================================================
Script único y consolidado para la extracción de perfiles de Instagram:
1. Información del Perfil: Bio, nombre, conteos oficiales (posts, seguidores, seguidos).
2. Publicaciones Completas:
   - Descripción (caption) de cada publicación.
   - Reacciones (conteo de Likes / Me gusta).
   - Conteo de comentarios y fecha.
   - Descarga directa de multimedia: Imágenes (.jpg) y Reels/Videos (.mp4) a disco.
   - Enlace directo (URL) y shortcode.
3. Listas de Seguidores y Seguidos:
   - Hace clic en el botón de seguidores en el encabezado y scrollea el modal para
     revisar de uno en uno y capturar usuario, nombre completo, URL y avatar.
   - Hace clic en el botón de seguidos y repite el mismo proceso de scroll.
4. Autenticación transparente con cookies desde archivo .env:
   - Sin inicio de sesión manual en cada ejecución.

USO RÁPIDO:
    python extraer_playwright.py                       # Modo visible interactivo (con scroll y descargas)
    python extraer_playwright.py --auto                # Modo automático completo
    python extraer_playwright.py --headless            # Modo en segundo plano
    python extraer_playwright.py --max-posts 10        # Limitar número de publicaciones a descargar
    python extraer_playwright.py --solo-perfil         # Solo bio y conteos rápidos
    python extraer_playwright.py usuario_a_extraer     # Extraer otro perfil distinto al .env
=============================================================================
"""

import argparse
import base64
import json
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

# Soporte UTF-8 obligatorio en consolas Windows (evita UnicodeEncodeError con emojis)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# ============================================================
# Carga de Configuración y Variables de Entorno (.env)
# ============================================================
BASE = Path(__file__).resolve().parent
DIR_DATOS = BASE / "Datos Extraídos"
DIR_MEDIA = BASE / "Descargas Multimedia"
DIR_DATOS.mkdir(parents=True, exist_ok=True)
DIR_MEDIA.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE / ".env")

TARGET_DEFAULT = os.getenv("TARGET_USER", "sausage_player").strip().lstrip("@")
SESSIONID = os.getenv("IG_SESSIONID", "").strip()
DS_USER_ID = os.getenv("IG_DS_USER_ID", "").strip()
CSRFTOKEN = os.getenv("IG_CSRFTOKEN", "").strip()
USER_AGENT = os.getenv(
    "IG_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
).strip()

# ============================================================
# Verificación de Cookies (.env)
# ============================================================
def verificar_estado_cookies() -> dict:
    """
    Verifica si las cookies configuradas en .env son válidas contra Instagram.
    Retorna un diccionario con el estado, motivo y usuario si está disponible.
    """
    sessionid = os.getenv("IG_SESSIONID", "").strip()
    ds_user_id = os.getenv("IG_DS_USER_ID", "").strip()
    csrftoken = os.getenv("IG_CSRFTOKEN", "").strip()

    if not sessionid:
        return {
            "valido": False,
            "motivo": "No se encontró IG_SESSIONID en el archivo .env",
            "detalles": "Debes agregar tus cookies en el archivo .env siguiendo las instrucciones del README.",
            "ds_user_id": None
        }

    s = requests.Session()
    s.cookies.set("sessionid", sessionid, domain=".instagram.com")
    if ds_user_id:
        s.cookies.set("ds_user_id", ds_user_id, domain=".instagram.com")
    if csrftoken:
        s.cookies.set("csrftoken", csrftoken, domain=".instagram.com")

    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    })

    try:
        r = s.get("https://www.instagram.com/", allow_redirects=False, timeout=12)
        loc = r.headers.get("Location") or ""
        
        if r.status_code == 200 and "accounts/login" not in loc:
            return {
                "valido": True,
                "motivo": "Sesión activa y cookies válidas",
                "ds_user_id": ds_user_id,
                "status_code": r.status_code
            }
        elif "accounts/login" in loc or r.status_code in (301, 302):
            return {
                "valido": False,
                "motivo": "Las cookies han expirado o fueron invalidadas por Instagram.",
                "ds_user_id": ds_user_id,
                "status_code": r.status_code
            }
        else:
            return {
                "valido": True,
                "motivo": f"Conexión exitosa (HTTP {r.status_code})",
                "ds_user_id": ds_user_id,
                "status_code": r.status_code
            }
    except Exception as e:
        return {
            "valido": False,
            "motivo": f"Error de red al conectar con Instagram: {str(e)}",
            "ds_user_id": ds_user_id
        }


# ============================================================
# Expresiones Regulares para Conteos y Biografía
# ============================================================
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

# ============================================================
# Scripts en el Navegador (JavaScript DOM)
# ============================================================

# Extracción de usuarios desde el diálogo modal de seguidores / seguidos
JS_EXTRAER_USUARIOS_DIALOG = """() => {
    const dialog = document.querySelector('div[role="dialog"]');
    if (!dialog) return [];
    
    const results = [];
    const seen = new Set();
    const exclude = [
        'accounts', 'stories', 'explore', 'legal', 'reels', 'saved', 'settings',
        'privacy', 'terms', 'locations', 'directory', 'about', 'blog', 'help',
        'api', 'jobs', 'brand', 'marketing', 'developers', 'threads', 'meta',
        'verified', 'popular', 'web', 'lite', 'sequencia', 'instagram'
    ];
    
    const links = dialog.querySelectorAll('a[href^="/"]');
    for (const a of links) {
        const href = a.getAttribute('href') || '';
        const match = href.match(/^\\/([a-zA-Z0-9_\\.]+)\\/?$/);
        if (!match) continue;
        
        const username = match[1];
        const lower = username.toLowerCase();
        if (exclude.includes(lower)) continue;
        if (seen.has(lower)) continue;
        
        // Fila contenedora
        const row = a.closest('div[style*="flex"], li, div[role="button"]') || a.parentElement;
        let nombre = '';
        let avatar = '';
        
        if (row) {
            const img = row.querySelector('img');
            if (img) avatar = img.src || '';
            
            // Buscar spans con el nombre visible de la persona
            const spans = row.querySelectorAll('span, div');
            for (const sp of spans) {
                const t = (sp.textContent || '').trim();
                if (t && t.toLowerCase() !== lower && !t.includes('Seguir') && !t.includes('Follow') && !t.includes('Eliminar')) {
                    if (t.length > nombre.length && t.length < 60) {
                        nombre = t;
                    }
                }
            }
        }
        
        seen.add(lower);
        results.push({
            usuario: username,
            nombre: nombre || null,
            url: `https://www.instagram.com/${username}/`,
            avatar: avatar || null
        });
    }
    return results;
}"""

# Scroll hacia abajo dentro del modal de seguidores / seguidos
JS_SCROLL_DIALOG = """() => {
    const dialog = document.querySelector('div[role="dialog"]');
    if (!dialog) return {scrolled: false, error: 'no_dialog'};
    
    const all = dialog.querySelectorAll('*');
    for (const el of all) {
        const style = window.getComputedStyle(el);
        if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
            const before = el.scrollTop;
            el.scrollTop = el.scrollHeight;
            return {
                scrolled: true,
                before: before,
                now: el.scrollTop,
                max: el.scrollHeight - el.clientHeight
            };
        }
    }
    return {scrolled: false, error: 'no_scrollable_container'};
}"""

# Extracción de datos detallados de la publicación actual en el modal
JS_EXTRAER_DATOS_POST = r"""() => {
    const dialog = document.querySelector('div[role="dialog"]') || document.querySelector('article') || document.querySelector('main');
    if (!dialog) return null;
    
    // 1. Multimedia (Imágenes y Videos)
    const imgs = [];
    dialog.querySelectorAll('img').forEach(img => {
        const src = img.src || '';
        // Descartar avatares de perfil
        if (src && !src.includes('profile') && !src.includes('150x150') && !src.includes('s150x150')) {
            if (!imgs.includes(src)) imgs.push(src);
        }
    });
    
    const vids = [];
    const v = dialog.querySelector('video');
    if (v) {
        // Extraer la URL exacta y única del video desde el manifiesto de su componente React
        function findVideoInReact(obj, seen = new Set(), depth = 0) {
            if (!obj || depth > 7 || seen.has(obj)) return null;
            if (typeof obj === 'string') {
                if (obj.includes('<BaseURL>http') || (obj.includes('.mp4') && obj.includes('fbcdn.net') && !obj.includes('blob:'))) {
                    return obj;
                }
                return null;
            }
            if (typeof obj !== 'object') return null;
            seen.add(obj);
            for (const key of Object.getOwnPropertyNames(obj)) {
                try {
                    const res = findVideoInReact(obj[key], seen, depth + 1);
                    if (res) return res;
                } catch(e) {}
            }
            return null;
        }

        const reactKey = Object.keys(v).find(k => k.startsWith('__reactProps') || k.startsWith('__reactFiber'));
        let found = null;
        if (reactKey) {
            let curr = v[reactKey];
            for (let i = 0; i < 20 && curr && !found; i++) {
                found = findVideoInReact(curr.memoizedProps) || findVideoInReact(curr.pendingProps);
                curr = curr.return;
            }
        }

        if (found) {
            if (found.includes('<BaseURL>')) {
                const matchBase = found.match(/<BaseURL>(https:\/\/[^<]+)<\/BaseURL>/i);
                if (matchBase) {
                    vids.push(matchBase[1].replace(/&amp;/g, '&'));
                }
            } else if (found.startsWith('http')) {
                vids.push(found);
            }
        }

        if (v.src && v.src.startsWith('http') && !v.src.startsWith('blob:') && !vids.includes(v.src)) {
            vids.push(v.src);
        }

        const poster = v.poster || v.getAttribute('poster') || '';
        if (poster && !imgs.includes(poster)) imgs.push(poster);
    }
    
    // 2. Descripción (Caption)
    let caption = '';
    const h1 = dialog.querySelector('h1');
    if (h1 && h1.innerText && h1.innerText.trim()) {
        caption = h1.innerText.trim();
    } else {
        // En algunos posts la descripción se muestra en el primer contenedor de comentarios
        const authorEl = dialog.querySelector('header a, h2 a, h3 a, a[role="link"]');
        if (authorEl) {
            const authorName = authorEl.innerText.trim();
            const commentLis = dialog.querySelectorAll('ul > div > li, ul > li');
            for (const li of commentLis) {
                const t = (li.innerText || '').trim();
                // Si contiene el nombre del autor al inicio y no tiene botón Responder/Reply, es el caption
                if (t && t.toLowerCase().startsWith(authorName.toLowerCase()) && !/reply|responder/i.test(t)) {
                    caption = t.replace(new RegExp('^' + authorName + '(\\n|\\s)+', 'i'), '').trim();
                    break;
                }
            }
        }
    }
    
    // 3. Reacciones / Likes (con soporte para Likes Ocultos)
    let likes = 0;
    let likesText = '';
    let likesOcultos = false;

    const likeCandidates = [];
    dialog.querySelectorAll('section, span, div, a, button').forEach(el => {
        const t = (el.innerText || '').trim();
        if (t && t.length < 120 && /likes?|me gusta|liked by|les gusta|gusta a|reproducc|views?/i.test(t)) {
            if (!likeCandidates.includes(t)) likeCandidates.push(t);
        }
    });

    for (const t of likeCandidates) {
        const line = t.split(/\r?\n/)[0].trim();
        
        // A. Ocultos explícitamente por el autor (ej: "Liked by mateo_cr_ and others", "Le gusta a user y a otras personas", "Liked by others")
        if (/\b(?:and others|y a otras personas|liked by others|les gusta a otras personas|ver me gusta|view likes)\b/i.test(line)) {
            likesOcultos = true;
            likes = null;
            likesText = `Oculto (${line})`;
            break;
        }

        // B. Conteo explícito directo (ej: "16 likes", "1.234 Me gusta", "1 like")
        const mDirecto = line.match(/^([\d.,]+)\s*(?:likes?|me gusta)\b/i);
        if (mDirecto) {
            likes = parseInt(mDirecto[1].replace(/[.,]/g, ''), 10) || 0;
            likesText = line;
            likesOcultos = false;
            break;
        }

        // C. Mención con conteo de otros (ej: "Liked by user and 15 others" / "Le gusta a user y a 15 personas más")
        const mOthers = line.match(/(?:and|y a)\s*([\d.,]+)\s*(?:others|personas más|más)\b/i);
        if (mOthers) {
            const extra = parseInt(mOthers[1].replace(/[.,]/g, ''), 10) || 0;
            likes = extra + 1;
            likesText = line;
            likesOcultos = false;
            break;
        }

        // D. 0 likes inicial ("Sé el primero en indicar que te gusta" / "Be the first to like this")
        if (/be the first|sé el primero/i.test(line)) {
            likes = 0;
            likesText = '0 likes';
            likesOcultos = false;
            break;
        }

        // E. Reproducciones de Reels / Videos
        const mViews = line.match(/^([\d.,]+)\s*(?:reproducciones|views)\b/i);
        if (mViews) {
            likes = parseInt(mViews[1].replace(/[.,]/g, ''), 10) || 0;
            likesText = line;
            likesOcultos = false;
            break;
        }
    }

    if (!likesText) {
        likesText = likesOcultos ? 'Oculto por el autor' : `${likes || 0} likes`;
    }
    
    // 4. Comentarios Reales (evita contar pie de foto, dots de carrusel o elementos decorativos)
    let commentsCount = 0;
    let commentsSample = [];
    let commentsDisabled = false;
    const textAll = dialog.innerText || '';

    if (/comments on this post have been limited|se desactivaron los comentarios|comments are disabled|se han limitado los comentarios/i.test(textAll)) {
        commentsCount = 0;
        commentsDisabled = true;
    } else {
        let encontradoTotal = false;
        const allSpansAndButtons = Array.from(dialog.querySelectorAll('span, button, a, div'))
            .map(el => (el.innerText || '').trim())
            .filter(t => t.length > 0 && t.length < 80);

        for (const t of allSpansAndButtons) {
            const m = t.match(/(?:view all|ver los|ver el|view)\s*([\d.,]+)\s*(?:comments?|comentarios?)\b/i);
            if (m) {
                commentsCount = parseInt(m[1].replace(/[.,]/g, ''), 10) || 0;
                encontradoTotal = true;
                break;
            }
        }

        if (!encontradoTotal) {
            if (/no comments yet|aún no hay comentarios|sin comentarios|start the conversation|inicia la conversación/i.test(textAll)) {
                commentsCount = 0;
            } else {
                const lis = Array.from(dialog.querySelectorAll('ul li'));
                const comentariosReales = [];
                for (const li of lis) {
                    const txt = (li.innerText || '').replace(/\s+/g, ' ').trim();
                    if (!txt) continue;
                    // Solo son comentarios legítimos si tienen control de respuesta o interacción
                    const tieneReply = Boolean(
                        li.querySelector('button, span, div[role="button"]') &&
                        /reply|responder/i.test(li.innerText)
                    );
                    if (tieneReply) {
                        const limpio = txt.replace(/\b(?:reply|responder|\d+[smhdw]|me gusta|like)\b.*$/i, '').trim();
                        comentariosReales.push(limpio || txt);
                    }
                }
                commentsCount = comentariosReales.length;
                commentsSample = comentariosReales.slice(0, 3).map(c => c.substring(0, 140));
            }
        }
    }

    if (commentsCount > 0 && commentsSample.length === 0) {
        const lis = Array.from(dialog.querySelectorAll('ul li'));
        for (const li of lis) {
            const txt = (li.innerText || '').replace(/\s+/g, ' ').trim();
            if (txt && /reply|responder/i.test(li.innerText)) {
                const limpio = txt.replace(/\b(?:reply|responder|\d+[smhdw]|me gusta|like)\b.*$/i, '').trim();
                commentsSample.push((limpio || txt).substring(0, 140));
                if (commentsSample.length >= 3) break;
            }
        }
    }
    
    // 5. Fecha de publicación
    let fecha = '';
    const timeEl = dialog.querySelector('time');
    if (timeEl) {
        fecha = timeEl.getAttribute('datetime') || timeEl.innerText.trim() || '';
    }
    
    return {
        caption: caption,
        likes: likes,
        likes_ocultos: likesOcultos,
        likes_texto: likesText,
        comentarios: commentsCount,
        comentarios_desactivados: commentsDisabled,
        comentarios_muestra: commentsSample,
        fecha: fecha,
        imagenes: imgs,
        videos: vids
    };
}"""


# ============================================================
# Funciones Auxiliares de Parseo
# ============================================================
def a_numero(txt: str) -> int | None:
    """Convierte cadenas como '1,234', '1.2M', '15 mil' a enteros."""
    if not txt:
        return None
    t = txt.strip().lower().replace("\xa0", " ")
    m = re.fullmatch(r"(\d[\d.,]*)\s?([kmb]|mil|mill\.?)?", t)
    if not m:
        return None
    cuerpo, sufijo = m.groups()
    if sufijo:
        mult = {"k": 1e3, "mil": 1e3, "m": 1e6, "mill": 1e6, "mill.": 1e6, "b": 1e9}.get(sufijo, 1)
        return int(round(float(cuerpo.replace(",", ".")) * mult))
    return int(re.sub(r"[.,]", "", cuerpo))


def parsear_og(texto: str | None) -> dict:
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
    t = texto or ""
    def buscar(palabras: str) -> int | None:
        m = re.search(rf"{_NUM}\s+(?:{palabras})\b", t, re.IGNORECASE)
        return a_numero(m.group(1)) if m else None
    return {
        "seguidores": buscar("followers|seguidores"),
        "seguidos": buscar("following|seguidos|siguiendo"),
        "total_publicaciones": buscar("posts|publicaciones"),
    }


def nombre_y_bio_desde_cabecera(texto: str | None, usuario: str) -> tuple[str | None, str | None]:
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


# ============================================================
# Extracción de Seguidores y Seguidos (Modal + Scroll)
# ============================================================
def extraer_lista_modal(page, selector_or_locator, titulo: str, modo_auto: bool = False, max_items: int = 500, log_fn=print) -> list[dict]:
    """Abre el diálogo modal de seguidores/seguidos, scrollea de uno en uno y extrae los usuarios."""
    log_fn(f"\n[*] Abriendo lista de {titulo}...")
    
    if isinstance(selector_or_locator, str):
        elem = page.locator(selector_or_locator).first
    else:
        elem = selector_or_locator.first
        
    if elem.count() == 0:
        log_fn(f"[!] No se encontró el botón de {titulo} en la cabecera.")
        return []
    
    try:
        elem.click()
    except Exception as e:
        log_fn(f"[!] Error al hacer clic en {titulo}: {e}")
        return []
    
    page.wait_for_timeout(3000)
    
    dialog = page.locator('div[role="dialog"]').first
    if dialog.count() == 0 or not dialog.is_visible():
        log_fn(f"[!] El diálogo de {titulo} no se abrió o no está visible.")
        return []
    
    # Si aparece 'Ver todos' o 'See all' (en caso de seguidores mutuos prioritarios)
    see_all = dialog.locator('a[href*="mutualFirst"], a:has-text("See all"), a:has-text("Ver todos")')
    if see_all.count() > 0 and see_all.first.is_visible():
        log_fn("    Haciendo clic en 'Ver todos los seguidores'...")
        try:
            see_all.first.click()
            page.wait_for_timeout(2000)
        except Exception:
            pass

    usuarios_dict = {}

    if not modo_auto:
        log_fn("\n" + "=" * 65)
        log_fn(f"[MODO MANUAL] Activo para: {titulo.upper()}")
        log_fn("   - Se ha abierto la ventana con la lista de usuarios.")
        log_fn("   - Puedes usar la rueda del ratón en la ventana para hacer scroll")
        log_fn("     hacia abajo y revisar de uno en uno.")
        log_fn("   - Cuando hayas revisado/cargado los que desees, presiona [ENTER] aquí.")
        log_fn("=" * 65)
        
        try:
            input("Presiona [ENTER] en esta consola cuando termines de scrollear... ")
        except Exception:
            pass
        
        usuarios = page.evaluate(JS_EXTRAER_USUARIOS_DIALOG)
        for u in usuarios:
            usuarios_dict[u["usuario"]] = u
            
    else:
        # Modo automático: scroll progresivo con pausas naturales
        log_fn(f"[*] Auto-scroll activo para {titulo} (máximo {max_items} o fin de lista)...")
        sin_cambios = 0
        ultimo_total = 0
        
        for paso in range(60):
            usuarios = page.evaluate(JS_EXTRAER_USUARIOS_DIALOG)
            for u in usuarios:
                usuarios_dict[u["usuario"]] = u
            
            log_fn(f"    Paso {paso + 1}: {len(usuarios_dict)} usuarios detectados")
            
            if len(usuarios_dict) >= max_items:
                log_fn(f"    Llegamos al límite configurado de {max_items}.")
                break
                
            if len(usuarios_dict) == ultimo_total:
                sin_cambios += 1
                if sin_cambios >= 5:
                    log_fn("    Fin de la lista alcanzado.")
                    break
            else:
                sin_cambios = 0
            ultimo_total = len(usuarios_dict)
            
            page.evaluate(JS_SCROLL_DIALOG)
            page.wait_for_timeout(random.randint(1800, 3000))

    # Cerrar diálogo modal
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
    except Exception:
        pass

    lista_final = list(usuarios_dict.values())
    log_fn(f"[+] Total {titulo} extraídos: {len(lista_final)}")
    return lista_final


# ============================================================
# Extracción y Descarga de Publicaciones (Media + Likes + Comments)
# ============================================================
def extraer_publicaciones_completas(page, context, target: str, max_posts: int = 15, descargar: bool = True, log_fn=print) -> list[dict]:
    """
    Abre las publicaciones una a una (usando navegación con flechas),
    extrae descripción, likes, comentarios y descarga imágenes/videos a disco.
    """
    log_fn(f"\n[*] Extrayendo publicaciones detalladas y descargando multimedia (hasta {max_posts})...")
    
    # Crear carpeta para descargas de este usuario
    descargas_dir = BASE / f"descargas_{target}"
    if descargar:
        descargas_dir.mkdir(parents=True, exist_ok=True)
        log_fn(f"    Carpeta de descargas: {descargas_dir.name}/")

    # Localizar primera publicación en la cuadrícula
    primer_post = page.locator('a[href*="/p/"], a[href*="/reel/"]').first
    tiene_posts_feed = primer_post.count() > 0

    posts_extraidos = []
    urls_vistas = set()

    if tiene_posts_feed:
        try:
            primer_post.click()
            page.wait_for_timeout(3000)
        except Exception as e:
            log_fn(f"[!] Error al abrir primera publicación del feed: {e}")
            tiene_posts_feed = False

    if tiene_posts_feed:
        for idx in range(max_posts):
            curr_url = page.url
            if curr_url in urls_vistas:
                log_fn("    Llegamos al final de las publicaciones del feed principal.")
                break
            urls_vistas.add(curr_url)

            # Extraer shortcode de la URL
            match_sc = re.search(r"/(p|reel)/([^/?#]+)", curr_url)
            shortcode = match_sc.group(2) if match_sc else f"post_{idx+1}"

            # Extraer datos del DOM del post actual
            datos = page.evaluate(JS_EXTRAER_DATOS_POST) or {}
            caption = datos.get("caption", "")
            likes = datos.get("likes", 0)
            comentarios = datos.get("comentarios", 0)
            fecha = datos.get("fecha", "")
            imagenes = datos.get("imagenes", [])
            videos = datos.get("videos", [])

            # Clasificación precisa del tipo de contenido
            es_reel_url = bool(match_sc and match_sc.group(1) == "reel")
            tiene_video = len(videos) > 0

            if es_reel_url:
                tipo = "reel"
            elif tiene_video:
                tipo = "video"
            elif len(imagenes) > 1:
                tipo = "carrusel"
            else:
                tipo = "publicacion"

            archivos_locales = []

            if descargar:
                # 1. Descargar video ÚNICAMENTE si la publicación contiene video legítimo
                if tiene_video:
                    for v_idx, v_url in enumerate(videos):
                        try:
                            filename = f"{shortcode}_{v_idx}.mp4" if len(videos) > 1 else f"{shortcode}.mp4"
                            dest = descargas_dir / filename
                            clean_v_url = re.sub(r"&bytestart=\d+&byteend=\d+", "", v_url)
                            resp = context.request.get(clean_v_url, timeout=35000)
                            if resp.ok and len(resp.body()) > 15000:
                                dest.write_bytes(resp.body())
                                archivos_locales.append(str(dest.relative_to(BASE)))
                                log_fn(f"      [OK] Video MP4 descargado: {filename} ({dest.stat().st_size // 1024} KB)")
                                break
                        except Exception as err:
                            log_fn(f"      [!] Aviso en descarga de video: {err}")

                # 2. Descargar imágenes fijas o carrusel
                for img_idx, img_url in enumerate(imagenes):
                    try:
                        filename = f"{shortcode}_{img_idx}.jpg" if len(imagenes) > 1 else f"{shortcode}.jpg"
                        dest = descargas_dir / filename
                        resp = context.request.get(img_url, timeout=30000)
                        if resp.ok:
                            dest.write_bytes(resp.body())
                            archivos_locales.append(str(dest.relative_to(BASE)))
                            log_fn(f"      [OK] Imagen descargada: {filename} ({dest.stat().st_size // 1024} KB)")
                    except Exception as err:
                        log_fn(f"      [!] Error descargando imagen {img_url[:30]}: {err}")

            post_item = {
                "shortcode": shortcode,
                "url": curr_url,
                "tipo": tipo,
                "descripcion": caption,
                "likes": likes,
                "likes_ocultos": datos.get("likes_ocultos", False),
                "likes_texto": datos.get("likes_texto", f"{likes} likes"),
                "comentarios": comentarios,
                "comentarios_desactivados": datos.get("comentarios_desactivados", False),
                "comentarios_muestra": datos.get("comentarios_muestra", []),
                "fecha": fecha,
                "media_urls": (videos if tiene_video else []) + imagenes,
                "archivos_descargados": archivos_locales
            }
            posts_extraidos.append(post_item)

            desc_corta = (caption[:45] + "...") if len(caption) > 45 else (caption or "(Sin descripción)")
            likes_str = datos.get("likes_texto") or f"{likes} likes"
            log_fn(f"    Post {idx + 1}/{max_posts} [{tipo}]: [{shortcode}] Reacciones: {likes_str} | Comentarios: {comentarios} | \"{desc_corta}\"")

            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(random.randint(1800, 2600))

        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)
        except Exception:
            pass

    # 3. Si aún no alcanzamos el límite o max_posts == 0, revisar pestaña /reels/
    if len(posts_extraidos) < max_posts or max_posts == 0:
        limite_reels = (max_posts - len(posts_extraidos)) if max_posts > 0 else 50
        try:
            url_reels = f"https://www.instagram.com/{target}/reels/"
            page.goto(url_reels, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)

            primer_reel = page.locator('a[href*="/reel/"]').first
            if primer_reel.count() > 0:
                log_fn(f"\n[*] Extrayendo Reels de la pestaña /reels/ (hasta {limite_reels})...")
                primer_reel.click()
                page.wait_for_timeout(3500)

                for r_idx in range(limite_reels):
                    curr_url = page.url
                    if curr_url in urls_vistas:
                        break
                    urls_vistas.add(curr_url)

                    match_sc = re.search(r"/(reel|p)/([^/?#]+)", curr_url)
                    shortcode = match_sc.group(2) if match_sc else f"reel_{r_idx+1}"

                    datos = page.evaluate(JS_EXTRAER_DATOS_POST) or {}
                    caption = datos.get("caption", "")
                    likes = datos.get("likes", 0)
                    comentarios = datos.get("comentarios", 0)
                    fecha = datos.get("fecha", "")
                    imagenes = datos.get("imagenes", [])
                    videos = datos.get("videos", [])
                    tiene_video = len(videos) > 0

                    archivos_locales = []
                    if descargar and tiene_video:
                        for v_idx, v_url in enumerate(videos):
                            try:
                                filename = f"{shortcode}.mp4"
                                dest = descargas_dir / filename
                                clean_v_url = re.sub(r"&bytestart=\d+&byteend=\d+", "", v_url)
                                resp = context.request.get(clean_v_url, timeout=35000)
                                if resp.ok and len(resp.body()) > 15000:
                                    dest.write_bytes(resp.body())
                                    archivos_locales.append(str(dest.relative_to(BASE)))
                                    log_fn(f"      [OK] Reel MP4 descargado exitosamente: {filename} ({dest.stat().st_size // 1024} KB)")
                                    break
                            except Exception as err:
                                log_fn(f"      [!] Aviso en descarga de video: {err}")

                        # Miniatura del reel
                        for img_idx, img_url in enumerate(imagenes[:1]):
                            try:
                                filename = f"{shortcode}_thumb.jpg"
                                dest = descargas_dir / filename
                                resp = context.request.get(img_url, timeout=25000)
                                if resp.ok:
                                    dest.write_bytes(resp.body())
                                    archivos_locales.append(str(dest.relative_to(BASE)))
                            except Exception:
                                pass

                    post_item = {
                        "shortcode": shortcode,
                        "url": curr_url,
                        "tipo": "reel",
                        "descripcion": caption,
                        "likes": likes,
                        "likes_ocultos": datos.get("likes_ocultos", False),
                        "likes_texto": datos.get("likes_texto", f"{likes} likes"),
                        "comentarios": comentarios,
                        "comentarios_desactivados": datos.get("comentarios_desactivados", False),
                        "comentarios_muestra": datos.get("comentarios_muestra", []),
                        "fecha": fecha,
                        "media_urls": videos + imagenes,
                        "archivos_descargados": archivos_locales
                    }
                    posts_extraidos.append(post_item)
                    desc_corta = (caption[:45] + "...") if len(caption) > 45 else (caption or "(Sin descripción)")
                    likes_str = datos.get("likes_texto") or f"{likes} likes"
                    log_fn(f"    Reel {len(posts_extraidos)}: [{shortcode}] Reacciones: {likes_str} | Comentarios: {comentarios} | \"{desc_corta}\"")

                    page.keyboard.press("ArrowRight")
                    page.wait_for_timeout(random.randint(2000, 3000))
        except Exception as e:
            log_fn(f"[!] Aviso al buscar en pestaña Reels: {e}")

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
    except Exception:
        pass

    if f"/{target}/" not in page.url or "/p/" in page.url or "/reel/" in page.url:
        try:
            page.goto(f"https://www.instagram.com/{target}/", wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
        except Exception:
            pass

    log_fn(f"[+] Total publicaciones procesadas: {len(posts_extraidos)}")
    return posts_extraidos


# ============================================================
# Motor de Extracción Principal
# ============================================================
def extraer_perfil_completo(
    target: str = TARGET_DEFAULT,
    max_posts: int = 0,
    modo_auto: bool = True,
    headless: bool = False,
    sin_descarga: bool = False,
    solo_perfil: bool = False,
    log_fn=print
) -> dict:
    """
    Función integral para extraer toda la información de un perfil de Instagram:
    Perfil, conteos, publicaciones (con descripción, likes, comentarios, archivos),
    seguidores y seguidos.
    """
    target = target.strip().lstrip("@")
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    DIR_MEDIA.mkdir(parents=True, exist_ok=True)
    salida_path = DIR_DATOS / f"datos_{target}.json"
    descargas_dir = DIR_MEDIA / f"descargas_{target}"

    log_fn("=" * 65)
    log_fn("INSTAGRAM SCRAPER DEFINITIVO (PLAYWRIGHT)")
    log_fn(f"Objetivo:           @{target}")
    log_fn(f"Modo ventana:       {'Segundo plano (headless)' if headless else 'Visible (con ventana)'}")
    log_fn(f"Modo scroll:        {'Automático (--auto)' if modo_auto else 'Manual interactivo ([ENTER])'}")
    log_fn(f"Descarga media:     {'Desactivada' if sin_descarga else f'Activada (en {descargas_dir.name}/)'}")
    log_fn(f"Límite posts:       {'Todas las publicaciones' if max_posts == 0 else max_posts}")
    log_fn("=" * 65)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport=None if not headless else {"width": 1280, "height": 800}
        )

        # Inyectar cookies de sesión desde .env
        cookies_a_inyectar = []
        if SESSIONID:
            cookies_a_inyectar.append({"name": "sessionid", "value": SESSIONID, "domain": ".instagram.com", "path": "/"})
        if DS_USER_ID:
            cookies_a_inyectar.append({"name": "ds_user_id", "value": DS_USER_ID, "domain": ".instagram.com", "path": "/"})
        if CSRFTOKEN:
            cookies_a_inyectar.append({"name": "csrftoken", "value": CSRFTOKEN, "domain": ".instagram.com", "path": "/"})

        if cookies_a_inyectar:
            context.add_cookies(cookies_a_inyectar)
            log_fn(f"[+] {len(cookies_a_inyectar)} cookies cargadas desde .env")
        else:
            log_fn("[!] Aviso: No se encontraron cookies en .env. Revisa el archivo README.md para agregarlas.")

        page = context.new_page()

        try:
            log_fn(f"\n[*] Navegando a: https://www.instagram.com/{target}/")
            resp = page.goto(f"https://www.instagram.com/{target}/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)

            if resp and resp.status == 404:
                raise RuntimeError(f"Error 404: El usuario @{target} no existe en Instagram.")

            if "accounts/login" in page.url:
                log_fn("[!] Redirigido al login. Las cookies expiraron o son inválidas.")
                if not headless:
                    log_fn("    Inicia sesión en la ventana abierta y luego presiona [ENTER] aquí...")
                    try:
                        input()
                    except Exception:
                        pass
                else:
                    raise RuntimeError("Las cookies de sesión expiraron. Actualiza IG_SESSIONID en .env.")

            # 1. Leer Encabezado y Metadatos
            try:
                og_desc = page.locator('meta[property="og:description"]').first.get_attribute("content", timeout=4000)
            except Exception:
                og_desc = None

            try:
                header_text = page.locator("header").first.inner_text(timeout=5000)
            except Exception:
                header_text = None

            datos_og = parsear_og(og_desc)
            datos_cab = conteos_desde_cabecera(header_text)
            nombre_v, bio_v = nombre_y_bio_desde_cabecera(header_text, target)

            seguidores_count = datos_cab["seguidores"] or datos_og["seguidores"]
            seguidos_count = datos_cab["seguidos"] or datos_og["seguidos"]
            pubs_count = datos_cab["total_publicaciones"] or datos_og["total_publicaciones"]
            biografia = bio_v or datos_og["biografia"]

            # Detección de cuenta privada o pública
            es_privado = False
            try:
                indicadores_privado = [
                    'text="This Account is Private"',
                    'text="Esta cuenta es privada"',
                    'text="This account is private"',
                    'h2:has-text("This Account is Private")',
                    'h2:has-text("Esta cuenta es privada")',
                    'svg[aria-label*="Privad"]',
                    'svg[aria-label*="Private"]',
                ]
                for sel in indicadores_privado:
                    if page.locator(sel).count() > 0:
                        es_privado = True
                        break
                if not es_privado and og_desc and ("private" in og_desc.lower() or "privada" in og_desc.lower()):
                    es_privado = True
            except Exception:
                pass

            # Foto de perfil / Avatar
            avatar_url = None
            try:
                avatar_el = page.locator("header img").first
                if avatar_el.count() > 0:
                    avatar_url = avatar_el.get_attribute("src")
            except Exception:
                pass

            # Verificado
            es_verificado = False
            try:
                es_verificado = page.locator('header svg[aria-label*="Verificad"], header svg[aria-label*="Verified"]').count() > 0
            except Exception:
                pass

            tipo_cuenta_str = "Cuenta Privada" if es_privado else "Cuenta Pública"
            verif_str = " (Verificado)" if es_verificado else ""

            log_fn(f"\n[+] Perfil cargado exitosamente:")
            log_fn(f"    Usuario:        @{target}{verif_str}")
            log_fn(f"    Nombre:         {nombre_v or '(No especificado)'}")
            log_fn(f"    Estado:         {tipo_cuenta_str}")
            log_fn(f"    Biografía:      {biografia or '(Sin biografía)'}")
            log_fn(f"    Seguidores:     {seguidores_count or 0}")
            log_fn(f"    Seguidos:       {seguidos_count or 0}")
            log_fn(f"    Publicaciones:  {pubs_count or 0}")

            seguidores_lista = []
            seguidos_lista = []
            publicaciones_lista = []

            if not solo_perfil and not (es_privado and not pubs_count):
                # 2. Extraer Publicaciones con descripción, likes, comentarios y descarga
                limite_posts = (pubs_count or 50) if (max_posts == 0) else min(max_posts, pubs_count or max_posts)
                if limite_posts > 0:
                    publicaciones_lista = extraer_publicaciones_completas(
                        page, context, target, max_posts=limite_posts, descargar=not sin_descarga, log_fn=log_fn
                    )

                # 3. Extraer Seguidores (Modal + Scroll)
                sel_seguidores = 'header a, header button, header span'
                regex_seguidores = re.compile(r'\d+\s*(?:followers|seguidores)', re.IGNORECASE)
                elem_seg = page.locator(sel_seguidores).filter(has_text=regex_seguidores)
                if elem_seg.count() > 0:
                    seguidores_lista = extraer_lista_modal(
                        page, elem_seg, "seguidores", modo_auto=modo_auto, max_items=seguidores_count or 500, log_fn=log_fn
                    )

                # 4. Extraer Seguidos (Modal + Scroll)
                regex_seguidos = re.compile(r'\d+\s*(?:following|seguidos|siguiendo)', re.IGNORECASE)
                elem_sig = page.locator(sel_seguidores).filter(has_text=regex_seguidos)
                if elem_sig.count() > 0:
                    seguidos_lista = extraer_lista_modal(
                        page, elem_sig, "seguidos", modo_auto=modo_auto, max_items=seguidos_count or 500, log_fn=log_fn
                    )

        finally:
            browser.close()

    resultado = {
        "usuario": target,
        "nombre_completo": nombre_v,
        "biografia": biografia,
        "avatar_url": avatar_url,
        "es_privado": es_privado,
        "es_verificado": es_verificado,
        "seguidores": seguidores_count,
        "seguidos": seguidos_count,
        "total_publicaciones": pubs_count,
        "publicaciones_extraidas": len(publicaciones_lista),
        "ruta_json": str(salida_path.resolve()),
        "carpeta_descargas": str(descargas_dir.resolve()) if not sin_descarga else None,
        "extraido_el": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": "Playwright con cookies de .env",
        "publicaciones": publicaciones_lista,
        "seguidores_lista": seguidores_lista,
        "seguidos_lista": seguidos_lista,
        "_conteos_og": datos_og,
        "_og_description": og_desc,
        "_texto_cabecera": header_text,
    }

    # Guardar copia de respaldo previa
    if salida_path.exists():
        try:
            shutil.copy(salida_path, salida_path.with_suffix(".prev.json"))
        except Exception:
            pass

    salida_path.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    log_fn("\n" + "=" * 65)
    log_fn("EXTRACCIÓN COMPLETADA CON ÉXITO")
    log_fn(f"Archivo JSON generado:   {salida_path.name}")
    log_fn(f"Ruta completa JSON:      {salida_path.resolve()}")
    if not sin_descarga:
        log_fn(f"Multimedia descargada:   {descargas_dir.resolve()}/")
    log_fn(f"  - Publicaciones procesadas: {len(publicaciones_lista)}")
    log_fn(f"  - Seguidores en lista:      {len(seguidores_lista)}")
    log_fn(f"  - Seguidos en lista:        {len(seguidos_lista)}")
    log_fn("=" * 65)

    return resultado


# ============================================================
# Función Principal CLI / Lanzador UI
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Instagram Scraper Definitivo (Playwright + Cookies en .env)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EJEMPLOS DE USO:
    python extraer_playwright.py                     # Modo interactivo (ventana visible)
    python extraer_playwright.py --auto              # Auto-scroll 100% automático
    python extraer_playwright.py --max-posts 10      # Extraer solo 10 publicaciones
    python extraer_playwright.py --check-cookies     # Comprobar validez de cookies en .env
    python extraer_playwright.py --ui                # Iniciar la interfaz web gráfica
    python extraer_playwright.py usuario_a_extraer   # Extraer un usuario específico
        """
    )
    parser.add_argument("usuario", nargs="?", default=TARGET_DEFAULT, help="Usuario objetivo de Instagram (sin @)")
    parser.add_argument("--auto", action="store_true", help="Realizar scroll 100%% automático sin pausas manuales")
    parser.add_argument("--headless", action="store_true", help="Ejecutar en segundo plano sin ventana gráfica")
    parser.add_argument("--solo-perfil", action="store_true", help="Extraer únicamente información del perfil (sin listas ni publicaciones)")
    parser.add_argument("--sin-descarga", action="store_true", help="No descargar archivos de imagen/video (solo guardar URLs y datos)")
    parser.add_argument("--max-posts", type=int, default=0, help="Máximo de publicaciones a procesar y descargar (0 = todas, default: 0)")
    parser.add_argument("--check-cookies", action="store_true", help="Verificar si las cookies de sesión en .env son válidas")
    parser.add_argument("--ui", action="store_true", help="Iniciar el panel de control web en el navegador")
    args = parser.parse_args()

    if args.check_cookies:
        print("[*] Comprobando cookies de sesión en .env contra Instagram...")
        estado = verificar_estado_cookies()
        if estado["valido"]:
            print(f"[OK] COOKIES VÁLIDAS: {estado['motivo']}")
            if estado.get("ds_user_id"):
                print(f"    ID de usuario autenticado: {estado['ds_user_id']}")
        else:
            print(f"[ERROR] COOKIES INVÁLIDAS O EXPIRADAS: {estado['motivo']}")
            if estado.get("detalles"):
                print(f"    {estado['detalles']}")
        return

    if args.ui:
        try:
            from app import iniciar_servidor_web
            iniciar_servidor_web()
        except ImportError:
            import app
            app.iniciar_servidor_web()
        return

    extraer_perfil_completo(
        target=args.usuario,
        max_posts=args.max_posts,
        modo_auto=args.auto,
        headless=args.headless,
        sin_descarga=args.sin_descarga,
        solo_perfil=args.solo_perfil,
        log_fn=print
    )


if __name__ == "__main__":
    main()

