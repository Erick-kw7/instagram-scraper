"""
=============================================================================
INSTAGRAM SCRAPER - PANEL DE CONTROL WEB INTERACTIVO
=============================================================================
Servidor web local (sin dependencias adicionales, usa librería estándar de Python)
para controlar la extracción de Instagram, verificar cookies y visualizar
todo el contenido extraído: perfil, conteos, publicaciones con fotos/videos,
seguidores y seguidos.

USO:
    python app.py
    # o bien:
    python extraer_playwright.py --ui
=============================================================================
"""

import json
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Soporte UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

# Importar funciones del scraper definitivo
from extraer_playwright import (
    extraer_perfil_completo,
    verificar_estado_cookies,
    TARGET_DEFAULT,
    SESSIONID,
    DS_USER_ID,
    CSRFTOKEN,
)

# Estado global de extracción en memoria
ESTADO_TRABAJO = {
    "activo": False,
    "usuario": None,
    "paso": "Listo para iniciar",
    "logs": [],
    "resultado": None,
    "error": None,
    "hora_inicio": None,
    "hora_fin": None,
}
LOCK_ESTADO = threading.Lock()


def registrar_log(mensaje: str):
    """Agrega un mensaje con timestamp al buffer de logs y a la consola."""
    hora = datetime.now().strftime("%H:%M:%S")
    linea = f"[{hora}] {mensaje}"
    print(linea)
    with LOCK_ESTADO:
        ESTADO_TRABAJO["logs"].append(linea)
        # Mantener últimos 1000 logs
        if len(ESTADO_TRABAJO["logs"]) > 1000:
            ESTADO_TRABAJO["logs"] = ESTADO_TRABAJO["logs"][-1000:]
        
        # Actualizar paso actual según el mensaje
        if "Navegando a:" in mensaje:
            ESTADO_TRABAJO["paso"] = "Conectando y cargando perfil..."
        elif "Perfil cargado exitosamente:" in mensaje:
            ESTADO_TRABAJO["paso"] = "Perfil analizado. Iniciando publicaciones..."
        elif "Post " in mensaje:
            ESTADO_TRABAJO["paso"] = mensaje.strip()
        elif "Abriendo lista de seguidores" in mensaje:
            ESTADO_TRABAJO["paso"] = "Extrayendo lista de seguidores..."
        elif "Abriendo lista de seguidos" in mensaje:
            ESTADO_TRABAJO["paso"] = "Extrayendo lista de seguidos..."
        elif "EXTRACCIÓN COMPLETADA" in mensaje:
            ESTADO_TRABAJO["paso"] = "¡Extracción completada con éxito!"


def hilo_extraccion(target: str, max_posts: int, modo_auto: bool, headless: bool, sin_descarga: bool, solo_perfil: bool):
    """Ejecuta el scraper en un hilo en segundo plano."""
    global ESTADO_TRABAJO
    with LOCK_ESTADO:
        ESTADO_TRABAJO["activo"] = True
        ESTADO_TRABAJO["usuario"] = target
        ESTADO_TRABAJO["paso"] = "Iniciando navegador Playwright..."
        ESTADO_TRABAJO["logs"] = []
        ESTADO_TRABAJO["resultado"] = None
        ESTADO_TRABAJO["error"] = None
        ESTADO_TRABAJO["hora_inicio"] = datetime.now().isoformat()
        ESTADO_TRABAJO["hora_fin"] = None

    try:
        registrar_log(f"Iniciando extracción para @{target} (Límite posts: {max_posts or 'Todos'})...")
        res = extraer_perfil_completo(
            target=target,
            max_posts=max_posts,
            modo_auto=modo_auto,
            headless=headless,
            sin_descarga=sin_descarga,
            solo_perfil=solo_perfil,
            log_fn=registrar_log,
        )
        with LOCK_ESTADO:
            ESTADO_TRABAJO["resultado"] = res
            ESTADO_TRABAJO["paso"] = "Finalizado exitosamente"
    except Exception as e:
        registrar_log(f"[ERROR CRÍTICO] {e}")
        with LOCK_ESTADO:
            ESTADO_TRABAJO["error"] = str(e)
            ESTADO_TRABAJO["paso"] = f"Error: {e}"
    finally:
        with LOCK_ESTADO:
            ESTADO_TRABAJO["activo"] = False
            ESTADO_TRABAJO["hora_fin"] = datetime.now().isoformat()


def listar_perfiles_guardados() -> list[dict]:
    """Busca archivos datos_*.json en el directorio actual."""
    perfiles = []
    for f in BASE.glob("datos_*.json"):
        if f.name.endswith(".prev.json"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            perfiles.append({
                "archivo": f.name,
                "usuario": d.get("usuario", f.stem.replace("datos_", "")),
                "nombre_completo": d.get("nombre_completo"),
                "seguidores": d.get("seguidores"),
                "seguidos": d.get("seguidos"),
                "total_publicaciones": d.get("total_publicaciones"),
                "publicaciones_extraidas": len(d.get("publicaciones", [])),
                "es_privado": d.get("es_privado", False),
                "extraido_el": d.get("extraido_el"),
                "tamano_kb": f.stat().st_size // 1024,
            })
        except Exception:
            continue
    perfiles.sort(key=lambda x: x.get("extraido_el") or "", reverse=True)
    return perfiles


# ============================================================
# Servidor HTTP Customizado
# ============================================================
class InstagramScraperHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silenciar logs excesivos de peticiones estáticas
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # 1. Página principal
        if path == "/" or path == "/index.html":
            html_content = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content)))
            self.end_headers()
            self.wfile.write(html_content)
            return

        # 2. API Estado de cookies y configuración
        if path == "/api/status":
            cookies_status = verificar_estado_cookies()
            perfiles = listar_perfiles_guardados()
            self.send_json({
                "cookies": cookies_status,
                "target_default": TARGET_DEFAULT,
                "ds_user_id": DS_USER_ID,
                "tiene_sessionid": bool(SESSIONID),
                "perfiles_guardados": perfiles,
                "trabajo_actual": {
                    "activo": ESTADO_TRABAJO["activo"],
                    "usuario": ESTADO_TRABAJO["usuario"],
                    "paso": ESTADO_TRABAJO["paso"],
                }
            })
            return

        # 3. API Verificación activa de cookies
        if path == "/api/check_cookies":
            res = verificar_estado_cookies()
            self.send_json(res)
            return

        # 4. API Listar perfiles guardados
        if path == "/api/profiles":
            perfiles = listar_perfiles_guardados()
            self.send_json({"perfiles": perfiles})
            return

        # 5. API Obtener datos de un usuario
        if path == "/api/data":
            usuario = qs.get("usuario", [TARGET_DEFAULT])[0].strip().lstrip("@")
            archivo = BASE / f"datos_{usuario}.json"
            if not archivo.exists():
                self.send_json({"error": f"No se encontró el archivo {archivo.name}"}, status=404)
                return
            try:
                data = json.loads(archivo.read_text(encoding="utf-8"))
                self.send_json(data)
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        # 6. API Progreso de extracción
        if path == "/api/progress":
            with LOCK_ESTADO:
                self.send_json({
                    "activo": ESTADO_TRABAJO["activo"],
                    "usuario": ESTADO_TRABAJO["usuario"],
                    "paso": ESTADO_TRABAJO["paso"],
                    "logs": ESTADO_TRABAJO["logs"][-150:],  # Últimos 150 logs para el cliente
                    "resultado_disponible": ESTADO_TRABAJO["resultado"] is not None,
                    "error": ESTADO_TRABAJO["error"],
                    "hora_inicio": ESTADO_TRABAJO["hora_inicio"],
                    "hora_fin": ESTADO_TRABAJO["hora_fin"],
                })
            return

        # 7. Servir archivos multimedia locales (descargas_{target}/...)
        if path.startswith("/media/"):
            # Formato esperado: /media/<usuario>/<archivo>
            partes = path[len("/media/"):].split("/", 1)
            if len(partes) == 2:
                user, filename = partes
                safe_filename = Path(filename).name
                file_path = BASE / f"descargas_{user}" / safe_filename
                if file_path.exists() and file_path.is_file():
                    ext = file_path.suffix.lower()
                    mime_types = {
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".png": "image/png",
                        ".mp4": "video/mp4",
                        ".webp": "image/webp",
                    }
                    content_type = mime_types.get(ext, "application/octet-stream")
                    content = file_path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(content)
                    return
            self.send_response(404)
            self.end_headers()
            return

        # 8. Descargar JSON directamente como attachment
        if path == "/api/download_json":
            usuario = qs.get("usuario", [TARGET_DEFAULT])[0].strip().lstrip("@")
            archivo = BASE / f"datos_{usuario}.json"
            if archivo.exists():
                content = archivo.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="datos_{usuario}.json"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            self.send_json({"error": "Archivo no encontrado"}, status=404)
            return

        # 9. Abrir carpeta en el explorador de Windows
        if path == "/api/open_folder":
            usuario = qs.get("usuario", [TARGET_DEFAULT])[0].strip().lstrip("@")
            carpeta = BASE / f"descargas_{usuario}"
            carpeta.mkdir(parents=True, exist_ok=True)
            try:
                if sys.platform == "win32":
                    os.startfile(str(carpeta))
                self.send_json({"ok": True, "ruta": str(carpeta.resolve())})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/start_extract":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                params = json.loads(post_data.decode("utf-8")) if post_data else {}
            except Exception:
                params = {}

            target = params.get("usuario", TARGET_DEFAULT).strip().lstrip("@")
            max_posts = int(params.get("max_posts", 0))
            modo_auto = bool(params.get("auto", True))
            headless = bool(params.get("headless", False))
            sin_descarga = bool(params.get("sin_descarga", False))
            solo_perfil = bool(params.get("solo_perfil", False))

            with LOCK_ESTADO:
                if ESTADO_TRABAJO["activo"]:
                    self.send_json({
                        "error": "Ya hay una extracción en ejecución. Espera a que termine.",
                        "usuario_activo": ESTADO_TRABAJO["usuario"]
                    }, status=409)
                    return

            # Lanzar hilo de extracción
            t = threading.Thread(
                target=hilo_extraccion,
                args=(target, max_posts, modo_auto, headless, sin_descarga, solo_perfil),
                daemon=True
            )
            t.start()

            self.send_json({
                "ok": True,
                "mensaje": f"Extracción iniciada para @{target}",
                "config": {
                    "usuario": target,
                    "max_posts": max_posts,
                    "auto": modo_auto,
                    "headless": headless,
                    "sin_descarga": sin_descarga,
                    "solo_perfil": solo_perfil,
                }
            })
            return

        self.send_response(404)
        self.end_headers()


# ============================================================
# Interfaz Web Completa (HTML5 + CSS Moderno + Vanilla JS)
# ============================================================
HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Instagram Scraper Pro - Panel de Control</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-primary: #0a0d14;
      --bg-secondary: #121722;
      --bg-card: rgba(21, 27, 39, 0.75);
      --bg-glass: rgba(255, 255, 255, 0.03);
      --border-subtle: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(253, 29, 29, 0.4);
      --ig-gradient: linear-gradient(135deg, #833AB4 0%, #FD1D1D 50%, #FCB045 100%);
      --ig-gradient-soft: linear-gradient(135deg, rgba(131, 58, 180, 0.15) 0%, rgba(253, 29, 29, 0.15) 50%, rgba(252, 176, 69, 0.15) 100%);
      --accent-purple: #833ab4;
      --accent-pink: #fd1d1d;
      --accent-orange: #fcb045;
      --text-main: #f0f3f8;
      --text-muted: #8e9bb0;
      --text-dim: #5a667a;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --radius-sm: 8px;
      --radius-md: 14px;
      --radius-lg: 20px;
      --shadow-card: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-primary);
      color: var(--text-main);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      line-height: 1.5;
      background-image: 
        radial-gradient(circle at 10% 20%, rgba(131, 58, 180, 0.12) 0%, transparent 40%),
        radial-gradient(circle at 90% 80%, rgba(253, 29, 29, 0.08) 0%, transparent 40%);
      background-attachment: fixed;
      padding-bottom: 60px;
    }

    /* Contenedor Principal */
    .container {
      max-width: 1240px;
      margin: 0 auto;
      padding: 24px 20px;
    }

    /* Header Superior */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 24px;
      background: var(--bg-card);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      margin-bottom: 28px;
      box-shadow: var(--shadow-card);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    .brand-icon {
      width: 44px;
      height: 44px;
      background: var(--ig-gradient);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 6px 16px rgba(253, 29, 29, 0.3);
    }

    .brand-icon svg {
      width: 26px;
      height: 26px;
      fill: #ffffff;
    }

    .brand-text h1 {
      font-size: 1.25rem;
      font-weight: 700;
      background: linear-gradient(135deg, #ffffff 40%, #fd1d1d 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .brand-text p {
      font-size: 0.8rem;
      color: var(--text-muted);
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .cookie-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #34d399;
      border-radius: 50px;
      font-size: 0.82rem;
      font-weight: 600;
    }

    .cookie-badge.invalid {
      background: rgba(239, 68, 68, 0.1);
      border-color: rgba(239, 68, 68, 0.3);
      color: #f87171;
    }

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: currentColor;
    }

    /* Botones */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 10px 18px;
      border-radius: var(--radius-sm);
      font-size: 0.88rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
      border: none;
      font-family: inherit;
    }

    .btn-gradient {
      background: var(--ig-gradient);
      color: #ffffff;
      box-shadow: 0 4px 14px rgba(253, 29, 29, 0.35);
    }

    .btn-gradient:hover {
      opacity: 0.95;
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(253, 29, 29, 0.45);
    }

    .btn-secondary {
      background: var(--bg-secondary);
      border: 1px solid var(--border-subtle);
      color: var(--text-main);
    }

    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.08);
      border-color: rgba(255, 255, 255, 0.2);
    }

    .btn-sm {
      padding: 6px 12px;
      font-size: 0.8rem;
      border-radius: 6px;
    }

    /* Grid Principal de 2 Columnas */
    .main-grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 24px;
      align-items: start;
    }

    @media (max-width: 960px) {
      .main-grid {
        grid-template-columns: 1fr;
      }
    }

    /* Tarjetas */
    .card {
      background: var(--bg-card);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 22px;
      box-shadow: var(--shadow-card);
      margin-bottom: 24px;
    }

    .card-title {
      font-size: 1.05rem;
      font-weight: 700;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: #ffffff;
    }

    /* Formulario */
    .form-group {
      margin-bottom: 18px;
    }

    .form-label {
      display: block;
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 8px;
    }

    .input-wrapper {
      position: relative;
      display: flex;
      align-items: center;
    }

    .input-prefix {
      position: absolute;
      left: 14px;
      color: var(--text-dim);
      font-weight: 600;
      font-size: 1rem;
    }

    .form-input {
      width: 100%;
      background: var(--bg-secondary);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 12px 14px;
      color: var(--text-main);
      font-size: 0.95rem;
      font-family: inherit;
      outline: none;
      transition: all 0.2s ease;
    }

    .form-input.has-prefix {
      padding-left: 32px;
    }

    .form-input:focus {
      border-color: var(--accent-pink);
      box-shadow: 0 0 0 3px rgba(253, 29, 29, 0.2);
    }

    /* Chips de Selección Rápida */
    .chips-group {
      display: flex;
      gap: 6px;
      margin-top: 8px;
      flex-wrap: wrap;
    }

    .chip {
      background: var(--bg-secondary);
      border: 1px solid var(--border-subtle);
      padding: 5px 11px;
      border-radius: 20px;
      font-size: 0.78rem;
      color: var(--text-muted);
      cursor: pointer;
      font-weight: 500;
      transition: all 0.15s ease;
    }

    .chip:hover, .chip.active {
      background: var(--ig-gradient);
      color: #ffffff;
      border-color: transparent;
    }

    /* Opciones Toggle / Switches */
    .toggle-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }

    .toggle-info {
      font-size: 0.85rem;
    }

    .toggle-info span {
      display: block;
      color: var(--text-main);
      font-weight: 500;
    }

    .toggle-info small {
      color: var(--text-dim);
      font-size: 0.75rem;
    }

    .switch {
      position: relative;
      display: inline-block;
      width: 42px;
      height: 24px;
    }

    .switch input {
      opacity: 0;
      width: 0;
      height: 0;
    }

    .slider {
      position: absolute;
      cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background-color: var(--bg-secondary);
      border: 1px solid var(--border-subtle);
      transition: .3s;
      border-radius: 34px;
    }

    .slider:before {
      position: absolute;
      content: "";
      height: 16px;
      width: 16px;
      left: 3px;
      bottom: 3px;
      background-color: white;
      transition: .3s;
      border-radius: 50%;
    }

    input:checked + .slider {
      background: var(--ig-gradient);
      border-color: transparent;
    }

    input:checked + .slider:before {
      transform: translateX(18px);
    }

    /* Panel de Perfil Extraído (Cabecera) */
    .profile-hero {
      display: flex;
      gap: 22px;
      align-items: flex-start;
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border-subtle);
    }

    .avatar-wrapper {
      position: relative;
      width: 90px;
      height: 90px;
      border-radius: 50%;
      padding: 3px;
      background: var(--ig-gradient);
      flex-shrink: 0;
    }

    .avatar-img {
      width: 100%;
      height: 100%;
      border-radius: 50%;
      object-fit: cover;
      background: var(--bg-secondary);
      display: block;
    }

    .avatar-placeholder {
      width: 100%;
      height: 100%;
      border-radius: 50%;
      background: var(--bg-secondary);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.8rem;
      font-weight: 700;
      color: var(--accent-orange);
    }

    .profile-info {
      flex: 1;
    }

    .profile-header-line {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 6px;
      flex-wrap: wrap;
    }

    .profile-username {
      font-size: 1.4rem;
      font-weight: 800;
      color: #ffffff;
    }

    .badge-privacy {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 3px 10px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
    }

    .badge-privacy.public {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }

    .badge-privacy.private {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }

    .profile-fullname {
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--text-main);
      margin-bottom: 8px;
    }

    .profile-bio {
      font-size: 0.88rem;
      color: var(--text-muted);
      white-space: pre-line;
      line-height: 1.45;
      background: rgba(0, 0, 0, 0.2);
      padding: 10px 14px;
      border-radius: var(--radius-sm);
      border-left: 3px solid var(--accent-pink);
    }

    /* Métrica Cards Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 24px;
    }

    @media (max-width: 680px) {
      .stats-grid {
        grid-template-columns: repeat(2, 1fr);
      }
    }

    .stat-card {
      background: var(--bg-secondary);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 14px 16px;
      text-align: center;
      transition: transform 0.15s ease;
    }

    .stat-card:hover {
      transform: translateY(-2px);
      border-color: rgba(253, 29, 29, 0.3);
    }

    .stat-number {
      font-size: 1.5rem;
      font-weight: 800;
      color: #ffffff;
      line-height: 1.1;
      margin-bottom: 4px;
    }

    .stat-label {
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    /* Banner de Almacenamiento (Dónde se guardó) */
    .storage-banner {
      background: var(--ig-gradient-soft);
      border: 1px solid rgba(253, 29, 29, 0.25);
      border-radius: var(--radius-sm);
      padding: 14px 18px;
      margin-bottom: 24px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .storage-title {
      font-size: 0.85rem;
      font-weight: 700;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .storage-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.82rem;
      background: rgba(0, 0, 0, 0.25);
      padding: 8px 12px;
      border-radius: 6px;
      gap: 10px;
    }

    .storage-path {
      font-family: 'JetBrains Mono', monospace;
      color: #cbd5e1;
      word-break: break-all;
      font-size: 0.78rem;
    }

    /* Pestañas de Contenido */
    .tabs-nav {
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--border-subtle);
      margin-bottom: 20px;
      padding-bottom: 2px;
      overflow-x: auto;
    }

    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 10px 18px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      position: relative;
      transition: color 0.2s ease;
      font-family: inherit;
      white-space: nowrap;
    }

    .tab-btn:hover {
      color: #ffffff;
    }

    .tab-btn.active {
      color: #ffffff;
    }

    .tab-btn.active::after {
      content: '';
      position: absolute;
      bottom: -3px;
      left: 0;
      right: 0;
      height: 3px;
      background: var(--ig-gradient);
      border-radius: 3px;
    }

    .tab-pane {
      display: none;
    }

    .tab-pane.active {
      display: block;
    }

    /* Galería de Publicaciones */
    .posts-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 20px;
    }

    .post-card {
      background: var(--bg-secondary);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      overflow: hidden;
      display: flex;
      flex-direction: column;
      transition: all 0.2s ease;
    }

    .post-card:hover {
      transform: translateY(-3px);
      box-shadow: 0 12px 28px rgba(0, 0, 0, 0.4);
      border-color: rgba(253, 29, 29, 0.3);
    }

    .post-media-box {
      position: relative;
      width: 100%;
      padding-top: 100%; /* Cuadrado 1:1 */
      background: #000000;
      overflow: hidden;
    }

    .post-media-box img, .post-media-box video {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .post-badge-type {
      position: absolute;
      top: 10px;
      right: 10px;
      background: rgba(0, 0, 0, 0.65);
      backdrop-filter: blur(8px);
      color: #ffffff;
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 600;
    }

    .post-body {
      padding: 14px;
      display: flex;
      flex-direction: column;
      flex: 1;
    }

    .post-stats-row {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 10px;
      font-size: 0.88rem;
      font-weight: 700;
    }

    .post-stat-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .stat-likes {
      color: #f43f5e;
    }

    .stat-comments {
      color: #38bdf8;
    }

    .post-caption {
      font-size: 0.84rem;
      color: var(--text-main);
      line-height: 1.4;
      margin-bottom: 12px;
      flex: 1;
      word-break: break-word;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .post-meta-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      padding-top: 10px;
      margin-top: auto;
      font-size: 0.75rem;
      color: var(--text-dim);
    }

    .post-link {
      color: var(--accent-orange);
      text-decoration: none;
      font-weight: 600;
    }

    .post-link:hover {
      text-decoration: underline;
    }

    /* Lista de Usuarios (Seguidores / Seguidos) */
    .users-list-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 12px;
    }

    .user-chip-card {
      display: flex;
      align-items: center;
      gap: 12px;
      background: var(--bg-secondary);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 10px 14px;
      transition: transform 0.15s ease;
    }

    .user-chip-card:hover {
      transform: translateY(-1px);
      border-color: rgba(253, 29, 29, 0.3);
    }

    .user-avatar-small {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: #000;
      object-fit: cover;
      flex-shrink: 0;
    }

    .user-avatar-fallback {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: var(--ig-gradient-soft);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      color: #fff;
      font-size: 0.9rem;
      flex-shrink: 0;
    }

    .user-info-text {
      overflow: hidden;
    }

    .user-username-link {
      display: block;
      color: #ffffff;
      font-weight: 700;
      font-size: 0.88rem;
      text-decoration: none;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .user-username-link:hover {
      color: var(--accent-orange);
    }

    .user-fullname-text {
      font-size: 0.78rem;
      color: var(--text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* Terminal de Logs en Vivo */
    .terminal-card {
      background: #080a0f;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: var(--radius-md);
      overflow: hidden;
      margin-bottom: 24px;
    }

    .terminal-header {
      background: #10141d;
      padding: 10px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }

    .terminal-dots {
      display: flex;
      gap: 6px;
    }

    .terminal-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }

    .terminal-title {
      font-size: 0.78rem;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-muted);
    }

    .terminal-body {
      padding: 14px;
      height: 220px;
      overflow-y: auto;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      line-height: 1.6;
      color: #a6b5cc;
    }

    .log-line {
      white-space: pre-wrap;
      word-break: break-all;
    }

    .log-success { color: #34d399; }
    .log-warn { color: #fbbf24; }
    .log-error { color: #f87171; }
    .log-info { color: #60a5fa; }

    /* Barra de Progreso */
    .progress-bar-container {
      width: 100%;
      height: 4px;
      background: rgba(255, 255, 255, 0.06);
      overflow: hidden;
      position: relative;
    }

    .progress-bar-anim {
      width: 100%;
      height: 100%;
      background: var(--ig-gradient);
      position: absolute;
      animation: indeterminate 1.8s infinite ease-in-out;
    }

    @keyframes indeterminate {
      0% { transform: translateX(-100%); }
      100% { transform: translateX(100%); }
    }

    /* Filtro de Búsqueda */
    .filter-bar {
      display: flex;
      gap: 12px;
      margin-bottom: 16px;
    }

    .filter-input {
      flex: 1;
      background: var(--bg-secondary);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-sm);
      padding: 8px 12px;
      color: #ffffff;
      font-size: 0.85rem;
      outline: none;
    }

    .filter-input:focus {
      border-color: var(--accent-pink);
    }

    /* Estado Vacío */
    .empty-state {
      text-align: center;
      padding: 40px 20px;
      color: var(--text-muted);
    }

    .empty-state svg {
      width: 48px;
      height: 48px;
      stroke: var(--text-dim);
      margin-bottom: 12px;
    }

    /* Spinner */
    .spinner {
      width: 16px;
      height: 16px;
      border: 2px solid rgba(255, 255, 255, 0.3);
      border-top-color: #ffffff;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  </style>
</head>
<body>

  <div class="container">
    <!-- Header -->
    <header>
      <div class="brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24">
            <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
          </svg>
        </div>
        <div class="brand-text">
          <h1>Instagram Scraper Pro</h1>
          <p>Panel de Control y Extractor Playwright</p>
        </div>
      </div>

      <div class="header-actions">
        <div id="cookieBadge" class="cookie-badge">
          <span class="dot"></span>
          <span id="cookieText">Comprobando cookies...</span>
        </div>
        <button id="btnCheckCookies" class="btn btn-secondary btn-sm" onclick="verificarCookiesManual()">
          🔄 Comprobar
        </button>
      </div>
    </header>

    <!-- Terminal de Logs en Vivo (Se muestra al extraer) -->
    <div id="terminalCard" class="terminal-card" style="display: none;">
      <div class="terminal-header">
        <div class="terminal-dots">
          <div class="terminal-dot" style="background: #ef4444;"></div>
          <div class="terminal-dot" style="background: #f59e0b;"></div>
          <div class="terminal-dot" style="background: #10b981;"></div>
        </div>
        <span class="terminal-title">PLAYWRIGHT SCRAPER LOGS</span>
        <span id="logStatusText" style="font-size: 0.75rem; color: #34d399; font-weight: 600;">EN EJECUCIÓN</span>
      </div>
      <div id="progressBar" class="progress-bar-container">
        <div class="progress-bar-anim"></div>
      </div>
      <div id="terminalLogs" class="terminal-body"></div>
    </div>

    <!-- Grid Principal -->
    <div class="main-grid">

      <!-- Columna Izquierda: Formulario de Control -->
      <div>
        <div class="card">
          <div class="card-title">
            <span>⚙️ Parámetros de Extracción</span>
          </div>

          <!-- Usuario objetivo -->
          <div class="form-group">
            <label class="form-label">Usuario de Instagram a extraer:</label>
            <div class="input-wrapper">
              <span class="input-prefix">@</span>
              <input type="text" id="inputUsuario" class="form-input has-prefix" placeholder="ej. sausage_player" value="">
            </div>
          </div>

          <!-- Cantidad de publicaciones -->
          <div class="form-group">
            <label class="form-label">Cantidad de publicaciones a extraer:</label>
            <input type="number" id="inputMaxPosts" class="form-input" min="0" max="500" value="10" placeholder="0 = Todas">
            <div class="chips-group">
              <span class="chip" onclick="setMaxPosts(5)">5 posts</span>
              <span class="chip active" onclick="setMaxPosts(10)">10 posts</span>
              <span class="chip" onclick="setMaxPosts(20)">20 posts</span>
              <span class="chip" onclick="setMaxPosts(50)">50 posts</span>
              <span class="chip" onclick="setMaxPosts(0)">Todas (0)</span>
            </div>
            <small style="color: var(--text-dim); font-size: 0.74rem; margin-top: 4px; display: block;">
              💡 0 extraerá todas las del perfil. Usa 5 o 10 para una prueba veloz.
            </small>
          </div>

          <!-- Toggles -->
          <div class="form-group" style="margin-top: 20px;">
            <label class="form-label">Opciones Avanzadas:</label>

            <div class="toggle-row">
              <div class="toggle-info">
                <span>Descargar Multimedia</span>
                <small>Guarda imágenes (.jpg) y videos (.mp4) a disco</small>
              </div>
              <label class="switch">
                <input type="checkbox" id="checkDescargar" checked>
                <span class="slider"></span>
              </label>
            </div>

            <div class="toggle-row">
              <div class="toggle-info">
                <span>Auto-scroll Inteligente</span>
                <small>Recorre seguidores/seguidos sin pausas manuales</small>
              </div>
              <label class="switch">
                <input type="checkbox" id="checkAuto" checked>
                <span class="slider"></span>
              </label>
            </div>

            <div class="toggle-row">
              <div class="toggle-info">
                <span>Modo en Segundo Plano</span>
                <small>Oculta la ventana gráfica de Chromium (headless)</small>
              </div>
              <label class="switch">
                <input type="checkbox" id="checkHeadless">
                <span class="slider"></span>
              </label>
            </div>

            <div class="toggle-row">
              <div class="toggle-info">
                <span>Solo Información de Perfil</span>
                <small>Extrae conteos y bio (sin posts ni listas)</small>
              </div>
              <label class="switch">
                <input type="checkbox" id="checkSoloPerfil">
                <span class="slider"></span>
              </label>
            </div>
          </div>

          <!-- Botón de Ejecutar -->
          <button id="btnEjecutar" class="btn btn-gradient" style="width: 100%; margin-top: 10px; padding: 13px;" onclick="iniciarExtraccion()">
            <span id="btnIcon">🚀</span>
            <span id="btnText">Iniciar Extracción</span>
          </button>
        </div>

        <!-- Tarjeta de Perfiles Guardados en Disco -->
        <div class="card">
          <div class="card-title">
            <span>📁 Perfiles Guardados</span>
            <button class="btn btn-secondary btn-sm" onclick="cargarListaPerfiles()">Recargar</button>
          </div>
          <div id="listaPerfilesGuardados" style="display: flex; flex-direction: column; gap: 8px;">
            <small style="color: var(--text-dim);">Cargando perfiles...</small>
          </div>
        </div>
      </div>

      <!-- Columna Derecha: Vista de Resultados -->
      <div>
        <div id="vistaResultados">

          <!-- Estado inicial si no hay datos cargados -->
          <div id="placeholderResultados" class="card empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect>
              <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path>
              <line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line>
            </svg>
            <h3 style="color: #fff; margin-bottom: 6px;">No hay perfil cargado</h3>
            <p>Selecciona un perfil guardado a la izquierda o haz clic en "Iniciar Extracción" para comenzar.</p>
          </div>

          <!-- Contenido del Perfil Extraído -->
          <div id="contenidoPerfil" style="display: none;">

            <!-- Hero del Perfil -->
            <div class="card">
              <div class="profile-hero">
                <div class="avatar-wrapper">
                  <img id="profileAvatar" class="avatar-img" src="" alt="Avatar" style="display: none;">
                  <div id="profileAvatarFallback" class="avatar-placeholder">?</div>
                </div>
                <div class="profile-info">
                  <div class="profile-header-line">
                    <span id="profileUsername" class="profile-username">@usuario</span>
                    <span id="badgePrivacidad" class="badge-privacy public">🌐 Pública</span>
                    <span id="badgeVerificado" class="badge-privacy public" style="display: none;">✓ Verificado</span>
                  </div>
                  <div id="profileFullname" class="profile-fullname">Nombre Completo</div>
                  <div id="profileBio" class="profile-bio">Biografía del usuario...</div>
                </div>
              </div>

              <!-- Estadísticas de Conteos -->
              <div class="stats-grid">
                <div class="stat-card">
                  <div id="statPublicaciones" class="stat-number">0</div>
                  <div class="stat-label">Publicaciones Totales</div>
                </div>
                <div class="stat-card">
                  <div id="statSeguidores" class="stat-number">0</div>
                  <div class="stat-label">Seguidores</div>
                </div>
                <div class="stat-card">
                  <div id="statSeguidos" class="stat-number">0</div>
                  <div class="stat-label">Seguidos</div>
                </div>
                <div class="stat-card" style="border-color: rgba(253, 29, 29, 0.4);">
                  <div id="statExtraidas" class="stat-number" style="color: #fd1d1d;">0</div>
                  <div class="stat-label">Posts Extraídos</div>
                </div>
              </div>

              <!-- Dónde se guardó todo (Banner de Almacenamiento) -->
              <div class="storage-banner">
                <div class="storage-title">
                  <span>📂 Dónde se guardó la información:</span>
                </div>
                <div class="storage-row">
                  <div>
                    <span style="font-weight: 600; color: #fff;">Base de Datos JSON:</span>
                    <div id="rutaJson" class="storage-path">datos_usuario.json</div>
                  </div>
                  <button class="btn btn-secondary btn-sm" onclick="descargarJsonActual()">⬇️ Descargar</button>
                </div>
                <div class="storage-row">
                  <div>
                    <span style="font-weight: 600; color: #fff;">Multimedia Descargada:</span>
                    <div id="rutaMultimedia" class="storage-path">descargas_usuario/</div>
                  </div>
                  <button class="btn btn-secondary btn-sm" onclick="abrirCarpetaDescargas()">📂 Abrir Carpeta</button>
                </div>
              </div>

              <!-- Navegación por Pestañas -->
              <div class="tabs-nav">
                <button class="tab-btn active" onclick="cambiarTab('tabPublicaciones', this)">
                  📸 Publicaciones (<span id="tabCountPosts">0</span>)
                </button>
                <button class="tab-btn" onclick="cambiarTab('tabSeguidores', this)">
                  👥 Seguidores (<span id="tabCountFollowers">0</span>)
                </button>
                <button class="tab-btn" onclick="cambiarTab('tabSeguidos', this)">
                  👤 Seguidos (<span id="tabCountFollowing">0</span>)
                </button>
                <button class="tab-btn" onclick="cambiarTab('tabJson', this)">
                  💻 JSON Crudo
                </button>
              </div>

              <!-- Contenido Tab 1: Galería de Publicaciones -->
              <div id="tabPublicaciones" class="tab-pane active">
                <div class="filter-bar">
                  <input type="text" id="filtroCaption" class="filter-input" placeholder="🔍 Buscar en descripciones de posts..." oninput="filtrarPosts()">
                </div>
                <div id="galeriaPosts" class="posts-grid"></div>
              </div>

              <!-- Contenido Tab 2: Seguidores -->
              <div id="tabSeguidores" class="tab-pane">
                <div class="filter-bar">
                  <input type="text" id="filtroSeguidores" class="filter-input" placeholder="🔍 Filtrar seguidores por usuario o nombre..." oninput="filtrarSeguidores()">
                </div>
                <div id="listaSeguidoresGrid" class="users-list-grid"></div>
              </div>

              <!-- Contenido Tab 3: Seguidos -->
              <div id="tabSeguidos" class="tab-pane">
                <div class="filter-bar">
                  <input type="text" id="filtroSeguidos" class="filter-input" placeholder="🔍 Filtrar seguidos..." oninput="filtrarSeguidos()">
                </div>
                <div id="listaSeguidosGrid" class="users-list-grid"></div>
              </div>

              <!-- Contenido Tab 4: JSON Crudo -->
              <div id="tabJson" class="tab-pane">
                <pre id="jsonViewer" style="background: #080a0f; padding: 16px; border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #cbd5e1; max-height: 480px; overflow: auto;"></pre>
              </div>

            </div>
          </div>

        </div>
      </div>

    </div>
  </div>

  <script>
    // Variables de Estado en Frontend
    let datosActuales = null;
    let usuarioActual = "";
    let pollingInterval = null;

    // Inicializar al cargar
    document.addEventListener("DOMContentLoaded", () => {
      cargarEstadoInicial();
      cargarListaPerfiles();
    });

    async function cargarEstadoInicial() {
      try {
        const res = await fetch("/api/status");
        const data = await res.json();
        
        // Estado de cookies
        actualizarBadgeCookies(data.cookies);

        // Pre-llenar usuario por defecto
        if (data.target_default && !document.getElementById("inputUsuario").value) {
          document.getElementById("inputUsuario").value = data.target_default;
        }

        // Si ya hay un trabajo activo, iniciar polling de logs
        if (data.trabajo_actual && data.trabajo_actual.activo) {
          iniciarPollingLogs();
        } else if (data.perfiles_guardados && data.perfiles_guardados.length > 0) {
          // Cargar el perfil más reciente automáticamente
          cargarDatosPerfil(data.perfiles_guardados[0].usuario);
        }
      } catch (err) {
        console.error("Error al cargar estado inicial:", err);
      }
    }

    function actualizarBadgeCookies(info) {
      const badge = document.getElementById("cookieBadge");
      const text = document.getElementById("cookieText");
      if (info && info.valido) {
        badge.className = "cookie-badge";
        text.innerText = info.ds_user_id ? `Cookies Válidas (${info.ds_user_id})` : "Cookies Válidas";
      } else {
        badge.className = "cookie-badge invalid";
        text.innerText = "Cookies Expiradas / No .env";
      }
    }

    async function verificarCookiesManual() {
      const btn = document.getElementById("btnCheckCookies");
      btn.innerText = "⏳ Comprobando...";
      btn.disabled = true;
      try {
        const res = await fetch("/api/check_cookies");
        const data = await res.json();
        actualizarBadgeCookies(data);
        alert(data.valido ? "✓ Cookies de sesión válidas en .env" : "✗ Error: " + data.motivo);
      } catch (err) {
        alert("Error de conexión al comprobar cookies.");
      } finally {
        btn.innerText = "🔄 Comprobar";
        btn.disabled = false;
      }
    }

    function setMaxPosts(num) {
      document.getElementById("inputMaxPosts").value = num;
      document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
      event.target.classList.add("active");
    }

    async function cargarListaPerfiles() {
      try {
        const res = await fetch("/api/profiles");
        const data = await res.json();
        const container = document.getElementById("listaPerfilesGuardados");
        container.innerHTML = "";

        if (!data.perfiles || data.perfiles.length === 0) {
          container.innerHTML = '<small style="color: var(--text-dim);">No hay perfiles extraídos aún.</small>';
          return;
        }

        data.perfiles.forEach(p => {
          const item = document.createElement("div");
          item.style.cssText = "display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); cursor: pointer;";
          item.onclick = () => cargarDatosPerfil(p.usuario);
          
          item.innerHTML = `
            <div>
              <div style="font-weight: 700; color: #fff; font-size: 0.88rem;">@${p.usuario}</div>
              <small style="color: var(--text-dim); font-size: 0.75rem;">${p.publicaciones_extraidas} posts • ${p.seguidores || 0} seguidores</small>
            </div>
            <button class="btn btn-secondary btn-sm" style="padding: 4px 8px; font-size: 0.75rem;">Ver</button>
          `;
          container.appendChild(item);
        });
      } catch (err) {
        console.error("Error al cargar lista de perfiles:", err);
      }
    }

    async function cargarDatosPerfil(usuario) {
      try {
        const res = await fetch(`/api/data?usuario=${encodeURIComponent(usuario)}`);
        if (!res.ok) throw new Error("No se pudo cargar el perfil");
        const data = await res.json();
        renderizarPerfil(data);
      } catch (err) {
        console.error(err);
      }
    }

    function renderizarPerfil(data) {
      datosActuales = data;
      usuarioActual = data.usuario || "";

      // Mostrar contenedor de contenido
      document.getElementById("placeholderResultados").style.display = "none";
      document.getElementById("contenidoPerfil").style.display = "block";

      // Formulario: sincronizar input con usuario cargado
      document.getElementById("inputUsuario").value = usuarioActual;

      // Header del Perfil
      document.getElementById("profileUsername").innerText = `@${usuarioActual}`;
      document.getElementById("profileFullname").innerText = data.nombre_completo || "(Sin nombre especificado)";
      document.getElementById("profileBio").innerText = data.biografia || "(Sin biografía)";

      // Avatar
      const imgAvatar = document.getElementById("profileAvatar");
      const fallbackAvatar = document.getElementById("profileAvatarFallback");
      if (data.avatar_url) {
        imgAvatar.src = data.avatar_url;
        imgAvatar.style.display = "block";
        fallbackAvatar.style.display = "none";
      } else {
        imgAvatar.style.display = "none";
        fallbackAvatar.style.display = "flex";
        fallbackAvatar.innerText = (usuarioActual[0] || "?").toUpperCase();
      }

      // Badges
      const badgePriv = document.getElementById("badgePrivacidad");
      if (data.es_privado) {
        badgePriv.className = "badge-privacy private";
        badgePriv.innerText = "🔒 Cuenta Privada";
      } else {
        badgePriv.className = "badge-privacy public";
        badgePriv.innerText = "🌐 Cuenta Pública";
      }

      const badgeVerif = document.getElementById("badgeVerificado");
      badgeVerif.style.display = data.es_verificado ? "inline-flex" : "none";

      // Métricas
      document.getElementById("statPublicaciones").innerText = data.total_publicaciones != null ? data.total_publicaciones : "-";
      document.getElementById("statSeguidores").innerText = data.seguidores != null ? data.seguidores.toLocaleString() : "-";
      document.getElementById("statSeguidos").innerText = data.seguidos != null ? data.seguidos.toLocaleString() : "-";
      const totalPostsExtraidos = (data.publicaciones || []).length;
      document.getElementById("statExtraidas").innerText = totalPostsExtraidos;

      // Dónde se guardó
      document.getElementById("rutaJson").innerText = data.ruta_json || `datos_${usuarioActual}.json`;
      document.getElementById("rutaMultimedia").innerText = data.carpeta_descargas || `descargas_${usuarioActual}/`;

      // Conteos de pestañas
      document.getElementById("tabCountPosts").innerText = totalPostsExtraidos;
      document.getElementById("tabCountFollowers").innerText = (data.seguidores_lista || []).length;
      document.getElementById("tabCountFollowing").innerText = (data.seguidos_lista || []).length;

      // Renderizar listas
      renderizarPosts(data.publicaciones || []);
      renderizarUsuariosLista(data.seguidores_lista || [], "listaSeguidoresGrid");
      renderizarUsuariosLista(data.seguidos_lista || [], "listaSeguidosGrid");

      // JSON Crudo
      document.getElementById("jsonViewer").innerText = JSON.stringify(data, null, 2);
    }

    function renderizarPosts(posts) {
      const container = document.getElementById("galeriaPosts");
      container.innerHTML = "";

      if (!posts || posts.length === 0) {
        container.innerHTML = '<div class="empty-state" style="grid-column: 1/-1;"><p>No se extrajeron publicaciones.</p></div>';
        return;
      }

      posts.forEach(p => {
        const card = document.createElement("div");
        card.className = "post-card";

        // Determinar media preview (local primero, fallback a remote)
        let mediaHtml = "";
        const archivoLocal = (p.archivos_descargados && p.archivos_descargados.length > 0) ? p.archivos_descargados[0] : "";
        const esVideo = p.tipo === "reel" || (p.media_urls && p.media_urls.some(u => u.includes(".mp4") || u.startsWith("blob:")));

        let mediaSrc = "";
        if (archivoLocal) {
          // Servir desde /media/
          const cleanLocal = archivoLocal.replace(/\\\\/g, "/");
          const parts = cleanLocal.split("/");
          const fname = parts[parts.length - 1];
          mediaSrc = `/media/${usuarioActual}/${fname}`;
        } else if (p.media_urls && p.media_urls.length > 0) {
          mediaSrc = p.media_urls[0];
        }

        if (esVideo && mediaSrc.endsWith(".mp4")) {
          mediaHtml = `
            <div class="post-media-box">
              <span class="post-badge-type">🎬 Video</span>
              <video src="${mediaSrc}" controls preload="metadata"></video>
            </div>
          `;
        } else if (mediaSrc) {
          mediaHtml = `
            <div class="post-media-box">
              <span class="post-badge-type">${p.tipo === 'reel' ? '🎬 Reel' : '📸 Foto'}</span>
              <img src="${mediaSrc}" alt="Post media" loading="lazy">
            </div>
          `;
        } else {
          mediaHtml = `
            <div class="post-media-box" style="display:flex;align-items:center;justify-content:center;color:var(--text-dim);">
              <span class="post-badge-type">Post</span>
              Sin multimedia
            </div>
          `;
        }

        // Formato de fecha
        let fechaStr = "";
        if (p.fecha) {
          try {
            const d = new Date(p.fecha);
            fechaStr = d.toLocaleDateString();
          } catch(e) {
            fechaStr = p.fecha.split("T")[0] || "";
          }
        }

        // Formato para Likes (Normales u Ocultos)
        const likesHtml = p.likes_ocultos
          ? `<span title="${(p.likes_texto || 'Likes ocultados por el autor').replace(/"/g, '&quot;')}" style="color: #fbbf24; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 4px; padding: 2px 7px; font-size: 0.78rem; font-weight: 600; cursor: help;">🔒 Oculto</span>`
          : `<span>${p.likes_texto || ((p.likes !== undefined && p.likes !== null ? p.likes : 0) + ' likes')}</span>`;

        // Formato para Comentarios (Conteo real o Desactivados)
        const commentsHtml = p.comentarios_desactivados
          ? `<span title="Comentarios desactivados en esta publicación" style="color: #94a3b8; font-size: 0.78rem; font-style: italic;">Desactivados</span>`
          : `<span>${p.comentarios !== undefined && p.comentarios !== null ? p.comentarios : 0}</span>`;

        card.innerHTML = `
          ${mediaHtml}
          <div class="post-body">
            <div class="post-stats-row">
              <div class="post-stat-item stat-likes">
                <span>❤️</span>
                ${likesHtml}
              </div>
              <div class="post-stat-item stat-comments">
                <span>💬</span>
                ${commentsHtml}
              </div>
            </div>
            <div class="post-caption" title="${(p.descripcion || '').replace(/"/g, '&quot;')}">
              ${p.descripcion || '<em style="color:var(--text-dim)">(Sin descripción)</em>'}
            </div>
            <div class="post-meta-footer">
              <span>${fechaStr || p.shortcode}</span>
              <a href="${p.url}" target="_blank" rel="noopener" class="post-link">Ver en Instagram ↗</a>
            </div>
          </div>
        `;
        container.appendChild(card);
      });
    }

    function renderizarUsuariosLista(usuarios, containerId) {
      const container = document.getElementById(containerId);
      container.innerHTML = "";

      if (!usuarios || usuarios.length === 0) {
        container.innerHTML = '<div class="empty-state" style="grid-column: 1/-1;"><p>No se encontraron usuarios en esta lista.</p></div>';
        return;
      }

      usuarios.forEach(u => {
        const item = document.createElement("div");
        item.className = "user-chip-card";

        const avatarHtml = u.avatar ? 
          `<img src="${u.avatar}" class="user-avatar-small" alt="${u.usuario}" onerror="this.outerHTML='<div class=\\'user-avatar-fallback\\'>${(u.usuario[0]||'?').toUpperCase()}</div>'">` :
          `<div class="user-avatar-fallback">${(u.usuario[0] || '?').toUpperCase()}</div>`;

        item.innerHTML = `
          ${avatarHtml}
          <div class="user-info-text">
            <a href="https://www.instagram.com/${u.usuario}/" target="_blank" rel="noopener" class="user-username-link">@${u.usuario}</a>
            <div class="user-fullname-text">${u.nombre || ''}</div>
          </div>
        `;
        container.appendChild(item);
      });
    }

    // Filtrado en vivo
    function filtrarPosts() {
      if (!datosActuales) return;
      const q = document.getElementById("filtroCaption").value.toLowerCase().trim();
      const filtrados = (datosActuales.publicaciones || []).filter(p => {
        return (p.descripcion || "").toLowerCase().includes(q) || (p.shortcode || "").toLowerCase().includes(q);
      });
      renderizarPosts(filtrados);
    }

    function filtrarSeguidores() {
      if (!datosActuales) return;
      const q = document.getElementById("filtroSeguidores").value.toLowerCase().trim();
      const filtrados = (datosActuales.seguidores_lista || []).filter(u => {
        return (u.usuario || "").toLowerCase().includes(q) || (u.nombre || "").toLowerCase().includes(q);
      });
      renderizarUsuariosLista(filtrados, "listaSeguidoresGrid");
    }

    function filtrarSeguidos() {
      if (!datosActuales) return;
      const q = document.getElementById("filtroSeguidos").value.toLowerCase().trim();
      const filtrados = (datosActuales.seguidos_lista || []).filter(u => {
        return (u.usuario || "").toLowerCase().includes(q) || (u.nombre || "").toLowerCase().includes(q);
      });
      renderizarUsuariosLista(filtrados, "listaSeguidosGrid");
    }

    function cambiarTab(tabId, btn) {
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.getElementById(tabId).classList.add("active");
      btn.classList.add("active");
    }

    // Iniciar extracción
    async function iniciarExtraccion() {
      const usuario = document.getElementById("inputUsuario").value.trim().replace(/^@/, "");
      if (!usuario) {
        alert("Por favor ingresa un nombre de usuario de Instagram.");
        return;
      }

      const maxPosts = parseInt(document.getElementById("inputMaxPosts").value, 10) || 0;
      const auto = document.getElementById("checkAuto").checked;
      const headless = document.getElementById("checkHeadless").checked;
      const sinDescarga = !document.getElementById("checkDescargar").checked;
      const soloPerfil = document.getElementById("checkSoloPerfil").checked;

      const payload = {
        usuario: usuario,
        max_posts: maxPosts,
        auto: auto,
        headless: headless,
        sin_descarga: sinDescarga,
        solo_perfil: soloPerfil
      };

      const btn = document.getElementById("btnEjecutar");
      btn.disabled = true;
      document.getElementById("btnIcon").innerHTML = '<div class="spinner"></div>';
      document.getElementById("btnText").innerText = "Extrayendo...";

      // Mostrar terminal de logs
      document.getElementById("terminalCard").style.display = "block";
      document.getElementById("terminalLogs").innerHTML = "";
      document.getElementById("logStatusText").innerText = "INICIANDO...";
      document.getElementById("logStatusText").style.color = "#34d399";

      try {
        const res = await fetch("/api/start_extract", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "No se pudo iniciar la extracción");

        iniciarPollingLogs();
      } catch (err) {
        alert("Error: " + err.message);
        btn.disabled = false;
        document.getElementById("btnIcon").innerText = "🚀";
        document.getElementById("btnText").innerText = "Iniciar Extracción";
      }
    }

    function iniciarPollingLogs() {
      if (pollingInterval) clearInterval(pollingInterval);

      document.getElementById("terminalCard").style.display = "block";

      pollingInterval = setInterval(async () => {
        try {
          const res = await fetch("/api/progress");
          const data = await res.json();

          // Renderizar logs
          const term = document.getElementById("terminalLogs");
          term.innerHTML = (data.logs || []).map(l => {
            let cls = "log-line";
            if (l.includes("[✓]") || l.includes("🎉") || l.includes("EXITO")) cls += " log-success";
            else if (l.includes("[!]") || l.includes("Aviso")) cls += " log-warn";
            else if (l.includes("[ERROR]")) cls += " log-error";
            else if (l.includes("[*]")) cls += " log-info";
            return `<div class="${cls}">${l}</div>`;
          }).join("");
          term.scrollTop = term.scrollHeight;

          // Estado del encabezado
          document.getElementById("logStatusText").innerText = data.paso || "EN EJECUCIÓN";

          // Si terminó
          if (!data.activo) {
            clearInterval(pollingInterval);
            pollingInterval = null;

            const btn = document.getElementById("btnEjecutar");
            btn.disabled = false;
            document.getElementById("btnIcon").innerText = "🚀";
            document.getElementById("btnText").innerText = "Iniciar Extracción";
            document.getElementById("progressBar").style.display = "none";

            if (data.error) {
              document.getElementById("logStatusText").innerText = "ERROR EN EXTRACCIÓN";
              document.getElementById("logStatusText").style.color = "#f87171";
              alert("Ocurrió un error en la extracción: " + data.error);
            } else {
              document.getElementById("logStatusText").innerText = "COMPLETADO";
              document.getElementById("logStatusText").style.color = "#34d399";
              // Cargar datos recién extraídos
              if (data.usuario) {
                cargarDatosPerfil(data.usuario);
                cargarListaPerfiles();
              }
            }
          }
        } catch (err) {
          console.error("Error polling logs:", err);
        }
      }, 1000);
    }

    function descargarJsonActual() {
      if (!usuarioActual) return;
      window.location.href = `/api/download_json?usuario=${encodeURIComponent(usuarioActual)}`;
    }

    async function abrirCarpetaDescargas() {
      if (!usuarioActual) return;
      try {
        const res = await fetch(`/api/open_folder?usuario=${encodeURIComponent(usuarioActual)}`);
        const data = await res.json();
        if (data.ok) {
          alert(`Carpeta abierta en Windows Explorer:\n${data.ruta}`);
        } else {
          alert("Error: " + data.error);
        }
      } catch (err) {
        alert("No se pudo abrir la carpeta en el explorador.");
      }
    }
  </script>
</body>
</html>
"""


# ============================================================
# Arranque del Servidor
# ============================================================
def iniciar_servidor_web(puerto: int = 5000, abrir_navegador: bool = True):
    """Inicia el servidor HTTP multihilo y opcionalmente abre el navegador."""
    # Buscar puerto libre si el 5000 está ocupado
    for p in range(puerto, puerto + 10):
        try:
            servidor = HTTPServer(("127.0.0.1", p), InstagramScraperHandler)
            puerto = p
            break
        except OSError:
            continue
    else:
        print("[!] No se encontró un puerto libre entre 5000 y 5010.")
        return

    url = f"http://localhost:{puerto}"
    print("=" * 65)
    print("🚀 INSTAGRAM SCRAPER - PANEL DE CONTROL WEB")
    print("=" * 65)
    print(f"Servidor iniciado exitosamente en:")
    print(f"👉 {url}")
    print("\nCaracterísticas activas:")
    print("  ✓ Comprobación en vivo del estado de cookies (.env)")
    print("  ✓ Selector de cantidad de publicaciones (ej. 5, 10, todas)")
    print("  ✓ Extracción automática de perfil, bio, posts, seguidores y seguidos")
    print("  ✓ Descarga y previsualización de imágenes y videos (.mp4)")
    print("  ✓ Explorador de archivos guardados y apertura directa en Explorer")
    print("\n[Presiona Ctrl+C en esta consola para detener el servidor]")
    print("=" * 65)

    if abrir_navegador:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Servidor web detenido correctamente.")
        servidor.server_close()


if __name__ == "__main__":
    iniciar_servidor_web()
