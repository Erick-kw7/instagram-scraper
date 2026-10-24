"""
=============================================================================
FASE 2: ENRIQUECIMIENTO Y PROCESAMIENTO DE INFORMACIÓN
Módulo: Análisis de Personalidad Psicométrica (Modelo Big Five / OCEAN) con Gemini AI
=============================================================================

Descripción:
    Este script toma la información extraída en la Fase 1 (perfil y las primeras
    10 publicaciones) y utiliza el modelo de lenguaje de Google Gemini para realizar
    un análisis psicológico computacional basado en los Cinco Grandes Factores
    de la Personalidad (OCEAN):
      1. Openness (Apertura a la Experiencia)
      2. Conscientiousness (Responsabilidad / Escrupulosidad)
      3. Extraversion (Extraversión / Energía Social)
      4. Agreeableness (Amabilidad / Cooperación)
      5. Neuroticism (Neuroticismo / Estabilidad Emocional)

Seguridad:
    La clave de API (GEMINI_API_KEY) se carga de forma estrictamente local desde el
    archivo `.env` y NUNCA se expone públicamente ni se envía a repositorios.
=============================================================================
"""

import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# Asegurar codificación UTF-8 en consola de Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Cargar variables de entorno locales
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DIR_DATOS = BASE_DIR / "Datos Extraídos"
DIR_ANALISIS = BASE_DIR / "Análisis BigFive"

DIR_DATOS.mkdir(parents=True, exist_ok=True)
DIR_ANALISIS.mkdir(parents=True, exist_ok=True)

# Lista preferida de modelos modernos y activos de Gemini (evita modelos obsoletos)
MODELOS_GEMINI = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-flash-latest"
]

def obtener_modelos_disponibles(api_key):
    """Consulta dinámicamente los modelos que admiten generateContent."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            modelos = r.json().get("models", [])
            disponibles = []
            for m in modelos:
                metodos = m.get("supportedGenerationMethods", [])
                if "generateContent" in metodos:
                    nombre = m.get("name", "").replace("models/", "")
                    if "flash" in nombre and "preview" not in nombre and "tts" not in nombre and "image" not in nombre:
                        disponibles.append(nombre)
            if disponibles:
                # Priorizar versiones más recientes (3.8, 3.5, 3.1)
                disponibles.sort(reverse=True)
                return disponibles
    except Exception:
        pass
    return MODELOS_GEMINI

def obtener_api_key():
    """Obtiene y valida la API Key de Gemini desde el entorno local."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "tu_api_key_de_gemini_aqui":
        print("\n" + "=" * 70)
        print("[ERROR] No se encontró una GEMINI_API_KEY válida en el archivo .env")
        print("=" * 70)
        print("Por favor:")
        print(" 1. Abre el archivo '.env' en tu editor local.")
        print(" 2. Agrega tu clave en la línea: GEMINI_API_KEY=AIzaSy...")
        print(" 3. Guarda el archivo y vuelve a ejecutar este script.")
        print("=" * 70 + "\n")
        return None
    return api_key


def cargar_datos_perfil(nombre_usuario):
    """Carga el JSON con los datos del perfil extraídos en la Fase 1."""
    # Buscar primero en la carpeta 'Datos Extraídos'
    ruta_archivo = DIR_DATOS / f"datos_{nombre_usuario}.json"
    if not ruta_archivo.exists():
        # Fallback a 'Datos Extraidos' sin tilde
        ruta_archivo = BASE_DIR / "Datos Extraidos" / f"datos_{nombre_usuario}.json"
        if not ruta_archivo.exists():
            # Fallback a raíz
            ruta_archivo = BASE_DIR / f"datos_{nombre_usuario}.json"
            if not ruta_archivo.exists():
                archivos = (
                    list(DIR_DATOS.glob(f"*{nombre_usuario}*.json"))
                    or list((BASE_DIR / "Datos Extraidos").glob(f"*{nombre_usuario}*.json"))
                    or list(BASE_DIR.glob(f"*{nombre_usuario}*.json"))
                )
                if archivos:
                    ruta_archivo = archivos[0]
                else:
                    print(f"[ERROR] No se encontró el archivo 'datos_{nombre_usuario}.json' en '{DIR_DATOS.name}' ni en la raíz.")
                    print("Ejecuta primero 'python extraer_playwright.py' para recopilar los datos.")
                    return None, None

    with open(ruta_archivo, "r", encoding="utf-8") as f:
        datos = json.load(f)

    return datos, ruta_archivo


def seleccionar_diez_posts(datos):
    """
    Selecciona exactamente los 10 primeros posts y sintetiza la información
    relevante para el análisis psicométrico.
    """
    posts_crudos = datos.get("publicaciones", [])[:10]
    posts_sintetizados = []

    for idx, p in enumerate(posts_crudos, 1):
        posts_sintetizados.append({
            "numero": idx,
            "shortcode": p.get("shortcode"),
            "tipo": p.get("tipo"),
            "fecha": p.get("fecha"),
            "descripcion": (p.get("descripcion") or "").strip()[:500],
            "likes": p.get("likes") if p.get("likes") is not None else ("Ocultos" if p.get("likes_ocultos") else 0),
            "comentarios": p.get("comentarios", 0)
        })

    return posts_sintetizados


def construir_prompt_psicometrico(perfil_info, diez_posts):
    """Construye un prompt riguroso de psicometría computacional."""
    usuario = perfil_info.get("usuario") or perfil_info.get("username") or os.getenv("TARGET_USER", "sausage_player")
    nombre = perfil_info.get("nombre_completo") or perfil_info.get("nombre") or usuario
    bio = perfil_info.get("biografia", "")
    enlace = perfil_info.get("enlace_externo", "")
    seguidores = perfil_info.get("seguidores") if perfil_info.get("seguidores") is not None else 0
    seguidos = (
        perfil_info.get("seguidos")
        if perfil_info.get("seguidos") is not None
        else (perfil_info.get("siguiendo") if perfil_info.get("siguiendo") is not None else 0)
    )
    total_posts = (
        perfil_info.get("total_publicaciones")
        if perfil_info.get("total_publicaciones") is not None
        else 0
    )

    prompt = f"""Eres un experto en Psicometría Computacional, Psicología de la Personalidad y Análisis de Contenido Digital en Redes Sociales.

Tu tarea es evaluar el perfil público del usuario de Instagram @{usuario} aplicando el Modelo de los Cinco Grandes Factores de la Personalidad (Big Five / OCEAN).

DATOS DEL PERFIL:
- Nombre visible: {nombre}
- Biografía: {bio if bio else '(Sin biografía)'}
- Enlace externo: {enlace if enlace else '(Sin enlace)'}
- Métricas: {seguidores} seguidores, {seguidos} seguidos (cuentas que sigue activamente), {total_posts} publicaciones totales.

MUESTRA DE LAS 10 PUBLICACIONES ANALIZADAS:
{json.dumps(diez_posts, ensure_ascii=False, indent=2)}

INSTRUCCIONES DE ANÁLISIS:
Analiza el tono discursivo, temas recurrentes, sentido del humor, interacción con la audiencia, estética y creatividad mostrada en estas 10 publicaciones y la biografía.
Debes devolver OBLIGATORIAMENTE un objeto JSON válido con la siguiente estructura exacta:

{{
  "usuario": "{usuario}",
  "resumen_ejecutivo": "Explicación en 2 párrafos concisos del perfil psicológico proyectado por el usuario en su contenido.",
  "arquetipo_dominante": "Nombre creativo del arquetipo (ej: 'El Creador Lúdico', 'El Observador Pragmático', 'El Conector Comunitario')",
  "rasgo_predominante": "Nombre del rasgo Big Five con mayor puntuación",
  "dimensiones_ocean": {{
    "openness": {{
      "nombre_es": "Apertura a la Experiencia",
      "puntuacion": 0,
      "nivel": "Alto | Medio | Bajo",
      "interpretacion": "Evaluación detallada de creatividad, curiosidad intelectual, estética, variedad temática y originalidad.",
      "evidencias": ["Evidencia 1 citando posts o bio", "Evidencia 2"]
    }},
    "conscientiousness": {{
      "nombre_es": "Responsabilidad (Tesón)",
      "puntuacion": 0,
      "nivel": "Alto | Medio | Bajo",
      "interpretacion": "Evaluación de disciplina, consistencia temática, atención al detalle y enfoque a metas.",
      "evidencias": ["Evidencia 1", "Evidencia 2"]
    }},
    "extraversion": {{
      "nombre_es": "Extraversión",
      "puntuacion": 0,
      "nivel": "Alto | Medio | Bajo",
      "interpretacion": "Evaluación de sociabilidad, dinamismo, energía expresiva, búsqueda de estímulos e interacción.",
      "evidencias": ["Evidencia 1", "Evidencia 2"]
    }},
    "agreeableness": {{
      "nombre_es": "Amabilidad (Afabilidad)",
      "puntuacion": 0,
      "nivel": "Alto | Medio | Bajo",
      "interpretacion": "Evaluación de calidez, empatía, tono conciliador o cooperativo hacia su comunidad.",
      "evidencias": ["Evidencia 1", "Evidencia 2"]
    }},
    "neuroticism": {{
      "nombre_es": "Neuroticismo (Reactividad Emocional)",
      "puntuacion": 0,
      "nivel": "Alto | Medio | Bajo",
      "interpretacion": "Evaluación de serenidad vs vulnerabilidad, estabilidad emocional, ironía o expresiones de estrés.",
      "evidencias": ["Evidencia 1", "Evidencia 2"]
    }}
  }},
  "conclusion_academica": "Párrafo final sintetizando las implicaciones arquitectónicas y éticas de extraer rasgos psicológicos a partir de huellas digitales públicas."
}}

NOTAS TÉCNICAS:
- 'puntuacion' debe ser un número entero entre 0 y 100.
- 'nivel' debe ser 'Alto' (70-100), 'Medio' (40-69) o 'Bajo' (0-39).
- Basa tus deducciones y evidencias estrictamente en las métricas y contenidos provistos; respeta fielmente los números reales de seguidores, seguidos y publicaciones.
- Sé profesional, analítico y riguroso.
- No incluyas bloques markdown ni texto antes o después del JSON. Solo el JSON.
"""
    return prompt


def llamar_gemini_api(prompt, api_key):
    """
    Envía la solicitud a la API de Gemini vía REST utilizando `requests`.
    Realiza fallback automático de modelos si uno no está disponible.
    """
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    ultimo_error = None
    modelos_a_probar = obtener_modelos_disponibles(api_key)
    for modelo in modelos_a_probar:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
        print(f"[INFO] Consultando modelo de Gemini: [{modelo}]...")
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=45)
            if resp.status_code == 200:
                data = resp.json()
                try:
                    texto_generado = data["candidates"][0]["content"]["parts"][0]["text"]
                    texto_limpio = texto_generado.strip()
                    if texto_limpio.startswith("```json"):
                        texto_limpio = texto_limpio[7:]
                    elif texto_limpio.startswith("```"):
                        texto_limpio = texto_limpio[3:]
                    if texto_limpio.endswith("```"):
                        texto_limpio = texto_limpio[:-3]
                    return json.loads(texto_limpio.strip()), modelo
                except (KeyError, IndexError, json.JSONDecodeError) as e:
                    ultimo_error = f"Error al decodificar respuesta JSON de {modelo}: {e}"
                    continue
            else:
                detalle = resp.text[:200]
                ultimo_error = f"HTTP {resp.status_code} en {modelo}: {detalle}"
                print(f"   [AVISO] {ultimo_error}")
        except Exception as e:
            ultimo_error = str(e)
            print(f"   [AVISO] Excepción de conexión con {modelo}: {e}")

    raise RuntimeError(f"No se pudo completar la inferencia con ningún modelo de Gemini. Último error: {ultimo_error}")


def imprimir_reporte_terminal(resultado, modelo_usado):
    """Muestra un reporte elegante en la terminal con barras de progreso."""
    print("\n" + "=" * 76)
    print("REPORTE DE ENRIQUECIMIENTO PSICOMÉTRICO (BIG FIVE / OCEAN) - GEMINI AI")
    print("=" * 76)
    print(f"Usuario analizado   : @{resultado.get('usuario')}")
    print(f"Arquetipo           : {resultado.get('arquetipo_dominante')}")
    print(f"Rasgo predominante  : {resultado.get('rasgo_predominante')}")
    print(f"Modelo utilizado    : {modelo_usado}")
    print("-" * 76)
    print("RESUMEN:")
    print(resultado.get("resumen_ejecutivo", "").strip())
    print("-" * 76)
    print("PUNTUACIONES DEL MODELO OCEAN:")

    dimensiones = resultado.get("dimensiones_ocean", {})
    for clave, datos in dimensiones.items():
        nombre = datos.get("nombre_es", clave.capitalize())
        score = datos.get("puntuacion", 0)
        nivel = datos.get("nivel", "N/D")

        llenos = int(score / 5)
        vacios = 20 - llenos
        barra = "█" * llenos + "░" * vacios

        print(f"\n • {nombre:<32} [{barra}] {score:>3}%  ({nivel})")
        print(f"   Interpretación: {datos.get('interpretacion')}")
        evidencias = datos.get("evidencias", [])
        if evidencias:
            print("   Evidencias:")
            for ev in evidencias:
                print(f"     - {ev}")

    print("-" * 76)
    print("CONCLUSIÓN ACADÉMICA:")
    print(resultado.get("conclusion_academica", "").strip())
    print("=" * 76 + "\n")


def ejecutar_analisis_bigfive(nombre_usuario=None, api_key=None):
    """
    Función principal ejecutable o importable desde app.py.
    """
    if not api_key:
        api_key = obtener_api_key()
        if not api_key:
            return None

    if not nombre_usuario:
        nombre_usuario = os.getenv("TARGET_USER", "sausage_player")

    print(f"\n[INFO] Cargando datos locales para @{nombre_usuario}...")
    datos, ruta_json = cargar_datos_perfil(nombre_usuario)
    if not datos:
        return None

    perfil = datos.get("perfil") if isinstance(datos.get("perfil"), dict) else datos
    diez_posts = seleccionar_diez_posts(datos)
    total_disponibles = len(datos.get("publicaciones", []))

    print(f"[OK] Se cargó el perfil con {total_disponibles} publicaciones.")
    print(f"[INFO] Seleccionadas las {len(diez_posts)} primeras publicaciones para la inferencia.")

    prompt = construir_prompt_psicometrico(perfil, diez_posts)
    print("[INFO] Enviando solicitud a la API de Gemini...")
    resultado, modelo_usado = llamar_gemini_api(prompt, api_key)

    resultado["metadata_enriquecimiento"] = {
        "modelo_gemini": modelo_usado,
        "posts_analizados": len(diez_posts),
        "total_posts_perfil": total_disponibles,
        "fecha_analisis": "2026-10-20"
    }

    # Guardar archivo independiente en 'Análisis BigFive'
    DIR_ANALISIS.mkdir(parents=True, exist_ok=True)
    ruta_salida = DIR_ANALISIS / f"analisis_bigfive_{nombre_usuario}.json"
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Análisis independiente guardado en: {DIR_ANALISIS.name}/{ruta_salida.name}")

    # Enriquecer el JSON principal
    datos["analisis_bigfive"] = resultado
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print(f"[OK] Archivo principal '{ruta_json.name}' enriquecido con campo 'analisis_bigfive'.")

    imprimir_reporte_terminal(resultado, modelo_usado)
    return resultado


if __name__ == "__main__":
    usuario = sys.argv[1] if len(sys.argv) > 1 else None
    ejecutar_analisis_bigfive(usuario)
