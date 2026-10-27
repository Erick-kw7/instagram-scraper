"""
=============================================================================
LEY DE BENFORD Y DETECCIÓN DE BOTS EN INSTAGRAM
=============================================================================
Análisis de la Ley de Benford aplicado a listas de seguidores o seguidos de Instagram.
Compara la distribución real del primer dígito de los followers de cada cuenta
con la distribución teórica de Benford para detectar patrones artificiales.

Uso:
    python analizar_benford.py --usuario sausage_player --tipo seguidores --limite 50
    python analizar_benford.py --usuario sausage_player --tipo seguidos --limite 50
"""

import argparse
import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Soporte UTF-8 en consola de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from scipy.stats import chi2 as chi2_dist

# ============================================================
# Rutas y Directorios del Proyecto
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
DIR_DATOS = BASE_DIR / "Datos Extraídos"
DIR_BENFORD = BASE_DIR / "Análisis Benford"

DIR_DATOS.mkdir(parents=True, exist_ok=True)
DIR_BENFORD.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")

TARGET_DEFAULT = os.getenv("TARGET_USER", "sausage_player").strip().lstrip("@")
SESSIONID = os.getenv("IG_SESSIONID", "").strip()
DS_USER_ID = os.getenv("IG_DS_USER_ID", "").strip()
CSRFTOKEN = os.getenv("IG_CSRFTOKEN", "").strip()
USER_AGENT = os.getenv(
    "IG_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
).strip()

# ============================================================
# Probabilidades Teóricas de la Ley de Benford
# P(d) = log10(1 + 1/d) para d en {1, 2, ..., 9}
# ============================================================
BENFORD_THEORETICAL = {
    d: math.log10(1.0 + 1.0 / d) * 100.0 for d in range(1, 10)
}


# -- Conversión de texto a número y extracción del primer dígito --
def texto_a_entero(val) -> int | None:
    """Convierte un valor (texto con K/M, float o int) a entero positivo. Retorna None si no es parseable."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    txt = str(val).strip().replace(",", "").replace(".", "").upper()
    if not txt:
        return None
    try:
        txt_raw = str(val).strip().replace(",", ".")
        if txt_raw.lower().endswith("k"):
            return int(float(txt_raw[:-1]) * 1000)
        elif txt_raw.lower().endswith("m"):
            return int(float(txt_raw[:-1]) * 1000000)
        
        # Extraer solo dígitos
        m = re.search(r"(\d+)", txt)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def primer_digito_de(conteo: int | None) -> int | None:
    """Retorna el primer dígito (1-9) de un número entero. Si es 0 o None retorna None."""
    if conteo is None:
        return None
    try:
        c_int = int(conteo)
        if c_int <= 0:
            return None
        primer_caracter = str(c_int)[0]
        digito = int(primer_caracter)
        if 1 <= digito <= 9:
            return digito
    except Exception:
        pass
    return None


def calcular_benford(usuarios_stats: list[dict], campo: str = "followers") -> dict:
    """Calcula la distribución del primer dígito y la compara con Benford via Chi-cuadrado (χ²)."""
    conteo_digitos = {d: 0 for d in range(1, 10)}
    total_ceros = 0
    total_sin_datos = 0
    usuarios_validos = []

    for item in usuarios_stats:
        val = item.get(campo)
        digito = item.get("primer_digito")
        if digito is None:
            c_norm = texto_a_entero(val)
            digito = primer_digito_de(c_norm)
            item["primer_digito"] = digito
            item[campo] = c_norm

        if digito and 1 <= digito <= 9:
            conteo_digitos[digito] += 1
            usuarios_validos.append(item)
        elif val == 0 or item.get(campo) == 0:
            total_ceros += 1
        else:
            total_sin_datos += 1

    total_validos = sum(conteo_digitos.values())
    
    # Sin datos válidos, devolver estructura vacía sin lanzar excepción aquí
    if total_validos == 0:
        return {
            "total_analizados": len(usuarios_stats),
            "total_validos": 0,
            "total_ceros": total_ceros,
            "total_sin_datos": total_sin_datos,
            "conteo_digitos": conteo_digitos,
            "porcentaje_observado": {d: 0.0 for d in range(1, 10)},
            "porcentaje_benford": BENFORD_THEORETICAL,
            "esperado_conteo": {d: 0.0 for d in range(1, 10)},
            "chi2_por_digito": {d: 0.0 for d in range(1, 10)},
            "chi2_total": 0.0,
            "grados_libertad": 8,
            "valor_critico_95": 15.507,
            "p_valor": 1.0,
            "distancia_mad": 0.0,
            "distancia_euclidiana": 0.0,
            "es_organico": False,
            "veredicto": "DATOS INSUFICIENTES",
            "explicacion": "No se encontraron registros numéricos válidos mayores a cero para realizar la prueba."
        }

    # Porcentaje observado y conteo esperado según Benford
    pct_observado = {
        d: (conteo_digitos[d] / total_validos) * 100.0 for d in range(1, 10)
    }
    conteo_esperado = {
        d: total_validos * (BENFORD_THEORETICAL[d] / 100.0) for d in range(1, 10)
    }

    # Contribucion chi-cuadrado por digito: (Observado - Esperado)^2 / Esperado
    chi2_por_digito = {}
    for d in range(1, 10):
        o = conteo_digitos[d]
        e = conteo_esperado[d]
        chi2_por_digito[d] = ((o - e) ** 2) / e if e > 0 else 0.0

    chi2_total = float(sum(chi2_por_digito.values()))
    df = 8  # grados de libertad: 9 digitos - 1
    valor_critico_95 = 15.507  # valor critico chi2 con alpha=0.05 y df=8
    p_val = float(chi2_dist.sf(chi2_total, df))

    # MAD: promedio de diferencias absolutas entre distribuciones (%)
    mad = sum(abs(pct_observado[d] - BENFORD_THEORETICAL[d]) for d in range(1, 10)) / 9.0
    # Distancia euclidiana como medida de separacion global entre ambas distribuciones
    dist_euclidiana = math.sqrt(sum((pct_observado[d] - BENFORD_THEORETICAL[d]) ** 2 for d in range(1, 10)))

    # Criterio: p >= 0.05 o MAD <= 1.8% -> distribucion aceptable (organica)
    # De lo contrario -> anomalia estadistica que puede indicar cuentas no reales
    if p_val >= 0.05 or mad <= 1.8:
        es_organico = True
        veredicto = "COMPORTAMIENTO ORGÁNICO (Sigue Ley de Benford)"
        explicacion = (
            f"La distribución de los seguidores de la cuenta evaluada se ajusta de forma natural "
            f"a la Ley de Benford (χ² = {chi2_total:.2f}, p-valor = {p_val:.4f}, MAD = {mad:.2f}%). "
            f"No existe evidencia estadística de automatización centralizada o granjas de bots."
        )
    else:
        es_organico = False
        veredicto = "ANOMALÍA DETECTADA (Sospecha de Cuentas Automatizadas / Bots)"
        explicacion = (
            f"La distribución presenta una discrepancia estadísticamente significativa con la Ley de Benford "
            f"(χ² = {chi2_total:.2f} > valor crítico {valor_critico_95}, p-valor = {p_val:.4e}, MAD = {mad:.2f}%). "
            f"Esta desviación suele reflejar manipulación artificial de métricas, cuentas clonadas o bots."
        )

    return {
        "total_analizados": len(usuarios_stats),
        "total_validos": total_validos,
        "total_ceros": total_ceros,
        "total_sin_datos": total_sin_datos,
        "conteo_digitos": conteo_digitos,
        "porcentaje_observado": pct_observado,
        "porcentaje_benford": BENFORD_THEORETICAL,
        "esperado_conteo": conteo_esperado,
        "chi2_por_digito": chi2_por_digito,
        "chi2_total": chi2_total,
        "grados_libertad": df,
        "valor_critico_95": valor_critico_95,
        "p_valor": p_val,
        "distancia_mad": mad,
        "distancia_euclidiana": dist_euclidiana,
        "es_organico": es_organico,
        "veredicto": veredicto,
        "explicacion": explicacion,
    }


# ============================================================
# Generación de Gráfico Comparativo Superpuesto (Matplotlib)
# ============================================================
def generar_grafico(
    stats: dict,
    usuario_objetivo: str,
    tipo_lista: str,
    ruta_guardado_png: Path,
) -> Path:
    """
    Genera y guarda el gráfico PNG comparativo con:
    - Barras de frecuencia real (Azul) y barras de expectativa teórica (Rojo/Naranja).
    - Línea de tendencia real (Azul) y línea de Ley de Benford (Roja).
    """
    digitos = list(range(1, 10))
    pct_real = [
        stats["porcentaje_observado"].get(d, stats["porcentaje_observado"].get(str(d), 0.0))
        for d in digitos
    ]
    pct_benford = [
        stats["porcentaje_benford"].get(d, stats["porcentaje_benford"].get(str(d), BENFORD_THEORETICAL.get(d, 0.0)))
        for d in digitos
    ]

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(10.5, 6.5), dpi=300)

    ancho_barra = 0.36
    x = np.array(digitos)

    # 1. Barras de Frecuencia Real (Azul) y Barras de Expectativa Teórica Benford (Rojo suave)
    barras_real = ax.bar(
        x - ancho_barra / 2,
        pct_real,
        width=ancho_barra,
        color="#2563EB",
        alpha=0.85,
        edgecolor="#1D4ED8",
        linewidth=1.2,
        label=f"Frecuencia Real (Barras - {tipo_lista.capitalize()})",
        zorder=3,
    )

    barras_benford = ax.bar(
        x + ancho_barra / 2,
        pct_benford,
        width=ancho_barra,
        color="#F87171",
        alpha=0.60,
        edgecolor="#DC2626",
        linewidth=1.2,
        label="Expectativa Teórica Benford (Barras)",
        zorder=3,
    )

    # 2. Línea Real (Azul) y Línea Teórica Benford (Roja)
    linea_real = ax.plot(
        x - ancho_barra / 2,
        pct_real,
        color="#1E3A8A",
        marker="s",
        markersize=6,
        linewidth=2.2,
        linestyle="-",
        label="Tendencia Real (Línea)",
        zorder=5,
    )

    linea_benford = ax.plot(
        x + ancho_barra / 2,
        pct_benford,
        color="#B91C1C",
        marker="o",
        markersize=7,
        linewidth=2.4,
        linestyle="-",
        label="Ley de Benford Teórica (Línea)",
        zorder=5,
    )

    # Porcentaje encima de cada barra real
    for rect in barras_real:
        h = rect.get_height()
        if h > 0:
            ax.annotate(
                f"{h:.1f}%",
                xy=(rect.get_x() + rect.get_width() / 2, h),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8.0,
                fontweight="bold",
                color="#1E3A8A",
            )

    # Porcentaje encima de cada barra teórica
    for rect in barras_benford:
        h = rect.get_height()
        if h > 0:
            ax.annotate(
                f"{h:.1f}%",
                xy=(rect.get_x() + rect.get_width() / 2, h),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7.8,
                fontweight="bold",
                color="#991B1B",
            )

    # Ejes y límites
    ax.set_xticks(x)
    ax.set_xticklabels([f"Dígito {d}" for d in digitos], fontsize=10, fontweight="bold")
    ax.set_xlabel("Primer Dígito Significativo (d)", fontsize=11, fontweight="bold", labelpad=8)
    ax.set_ylabel("Frecuencia Relativa (%)", fontsize=11, fontweight="bold", labelpad=8)
    
    max_y = max(max(pct_real or [0]), max(pct_benford or [0])) + 7
    ax.set_ylim(0, max_y)

    # Título del gráfico
    tipo_str = "Seguidores (Followers)" if tipo_lista == "seguidores" else "Seguidos (Following)"
    plt.title(
        f"Detección de Bots y Cuentas Falsas: Ley de Benford en @{usuario_objetivo}\n"
        f"Comparativa de Métricas de {tipo_str} — N = {stats['total_validos']} perfiles",
        fontsize=13,
        fontweight="bold",
        pad=14,
        color="#0F172A",
    )

    # Recuadro con el resumen estadístico dentro del gráfico
    color_caja = "#DCFCE7" if stats["es_organico"] else "#FEE2E2"
    borde_caja = "#16A34A" if stats["es_organico"] else "#DC2626"
    color_texto = "#166534" if stats["es_organico"] else "#991B1B"
    icono = "[OK]" if stats["es_organico"] else "[ALERTA]"

    texto_caja = (
        f"TEST CHI-CUADRADO (bondad de ajuste)\n"
        f"  chi2: {stats['chi2_total']:.2f}  (crítico α=0.05: {stats['valor_critico_95']})\n"
        f"  df: {stats['grados_libertad']} | p-valor: {stats['p_valor']:.4f}\n"
        f"  MAD: {stats['distancia_mad']:.2f}%\n"
        f"  {icono} {stats['veredicto']}"
    )

    ax.text(
        0.98,
        0.96,
        texto_caja,
        transform=ax.transAxes,
        fontsize=9,
        fontfamily="monospace",
        verticalalignment="top",
        horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.6", facecolor=color_caja, edgecolor=borde_caja, alpha=0.95, linewidth=1.2),
        color=color_texto,
        zorder=6,
    )

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4, frameon=True, fontsize=9)
    plt.tight_layout()

    ruta_guardado_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(ruta_guardado_png, dpi=300, bbox_inches="tight")
    plt.close()

    return ruta_guardado_png


# ============================================================
# Generación de Hoja de Cálculo Excel (.xlsx) con Openpyxl
# ============================================================
def generar_excel(
    usuarios_data: list[dict],
    stats: dict,
    usuario_objetivo: str,
    tipo_lista: str,
    ruta_guardado_xlsx: Path,
    ruta_grafico_png: Path | None = None,
) -> Path:
    """
    Genera un libro Excel con una sola hoja que contiene:
    - Columnas A-E: tabla de usuarios con followers, following y primer digito.
    - Columnas G-L: tabla de frecuencias Benford y estadisticos Chi-cuadrado.
    - Grafico PNG incrustado debajo de las tablas.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Detección de Bots"
    ws.views.sheetView[0].showGridLines = True

    # Estilos de celdas
    azul_header = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    azul_claro = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    gris_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    verde_exito = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    rojo_alerta = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    font_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=10, bold=True, color="000000")
    font_regular = Font(name="Calibri", size=10, color="000000")
    font_title = Font(name="Calibri", size=13, bold=True, color="1F4E79")
    font_subtitle = Font(name="Calibri", size=10, italic=True, color="555555")

    thin_border = Border(
        left=Side(style="thin", color="D0D5DD"),
        right=Side(style="thin", color="D0D5DD"),
        top=Side(style="thin", color="D0D5DD"),
        bottom=Side(style="thin", color="D0D5DD"),
    )
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    # Cabecera del documento
    ws.cell(row=1, column=1, value=f"LEY DE BENFORD Y DETECCIÓN DE BOTS — @{usuario_objetivo}").font = font_title
    ws.cell(row=2, column=1, value=f"Lista evaluada: {tipo_lista.upper()} | Muestra analizada: {stats['total_validos']} perfiles | Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}").font = font_subtitle

    # Tabla de usuarios (columnas A-E)
    headers_users = [
        "N°",
        "Usuario",
        "Followers (Seguidores)",
        "Following (Seguidos)",
        "Primer Dígito (Followers)",
    ]

    for col_idx, h in enumerate(headers_users, start=1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = azul_header
        cell.alignment = align_center
        cell.border = thin_border

    for r_idx, u in enumerate(usuarios_data, start=5):
        bg = gris_zebra if r_idx % 2 == 1 else PatternFill(fill_type=None)

        c1 = ws.cell(row=r_idx, column=1, value=r_idx - 4)
        c2 = ws.cell(row=r_idx, column=2, value=f"@{u.get('usuario', '')}")
        c3 = ws.cell(row=r_idx, column=3, value=u.get("followers"))
        c4 = ws.cell(row=r_idx, column=4, value=u.get("following"))
        c5 = ws.cell(row=r_idx, column=5, value=u.get("primer_digito"))

        c1.alignment = align_center
        c2.alignment = align_left
        c3.alignment = align_right
        c4.alignment = align_right
        c5.alignment = align_center

        if u.get("primer_digito"):
            c5.font = Font(name="Calibri", size=10, bold=True, color="1F4E79")
        else:
            c5.font = font_regular

        for c in (c1, c2, c3, c4, c5):
            c.border = thin_border
            if bg.fill_type:
                c.fill = bg
            if c != c5:
                c.font = font_regular

    # Tabla de frecuencias Benford y chi-cuadrado (columnas G-L)
    headers_benford = [
        "Primer Dígito (d)",
        "Conteo Observado (O)",
        "Frecuencia Real (%)",
        "Esperado Benford (%)",
        "Conteo Esperado (E)",
        "Chi-Cuadrado Parcial (O - E)² / E",
    ]

    col_b_start = 7  # columna G
    for i, h in enumerate(headers_benford):
        cell = ws.cell(row=4, column=col_b_start + i, value=h)
        cell.font = font_header
        cell.fill = azul_header
        cell.alignment = align_center
        cell.border = thin_border

    digitos = list(range(1, 10))
    for idx, d in enumerate(digitos, start=5):
        bg = gris_zebra if idx % 2 == 1 else PatternFill(fill_type=None)
        obs = stats["conteo_digitos"].get(d, stats["conteo_digitos"].get(str(d), 0))
        pct_obs = stats["porcentaje_observado"].get(d, stats["porcentaje_observado"].get(str(d), 0.0))
        pct_ben = stats["porcentaje_benford"].get(d, stats["porcentaje_benford"].get(str(d), BENFORD_THEORETICAL.get(d, 0.0)))
        esp = stats["esperado_conteo"].get(d, stats["esperado_conteo"].get(str(d), 0.0))
        chi_part = stats["chi2_por_digito"].get(d, stats["chi2_por_digito"].get(str(d), 0.0))

        c1 = ws.cell(row=idx, column=col_b_start + 0, value=d)
        c2 = ws.cell(row=idx, column=col_b_start + 1, value=obs)
        c3 = ws.cell(row=idx, column=col_b_start + 2, value=round(pct_obs, 2))
        c4 = ws.cell(row=idx, column=col_b_start + 3, value=round(pct_ben, 2))
        c5 = ws.cell(row=idx, column=col_b_start + 4, value=round(esp, 2))
        c6 = ws.cell(row=idx, column=col_b_start + 5, value=round(chi_part, 4))

        c1.alignment = align_center
        c2.alignment = align_right
        c3.alignment = align_right
        c4.alignment = align_right
        c5.alignment = align_right
        c6.alignment = align_right

        for c in (c1, c2, c3, c4, c5, c6):
            c.border = thin_border
            c.font = font_regular
            if bg.fill_type:
                c.fill = bg

    # Fila de Totales Benford
    total_row = 14
    c_tot_label = ws.cell(row=total_row, column=col_b_start + 0, value="TOTAL")
    c_tot_obs = ws.cell(row=total_row, column=col_b_start + 1, value=stats["total_validos"])
    c_tot_pct_obs = ws.cell(row=total_row, column=col_b_start + 2, value=round(sum(stats["porcentaje_observado"].values()), 1))
    c_tot_pct_ben = ws.cell(row=total_row, column=col_b_start + 3, value=100.0)
    c_tot_esp = ws.cell(row=total_row, column=col_b_start + 4, value=round(sum(stats["esperado_conteo"].values()), 1))
    c_tot_chi = ws.cell(row=total_row, column=col_b_start + 5, value=round(stats["chi2_total"], 4))

    for c in (c_tot_label, c_tot_obs, c_tot_pct_obs, c_tot_pct_ben, c_tot_esp, c_tot_chi):
        c.font = font_bold
        c.fill = azul_claro
        c.border = thin_border
        if c == c_tot_label:
            c.alignment = align_center
        else:
            c.alignment = align_right

    # Tabla de parametros estadisticos (filas 16-23)
    metric_start = 16
    ws.merge_cells(start_row=metric_start, start_column=col_b_start, end_row=metric_start, end_column=col_b_start + 1)
    c_m_h1 = ws.cell(row=metric_start, column=col_b_start, value="PARÁMETRO ESTADÍSTICO")
    c_m_h1.font = font_header
    c_m_h1.fill = azul_header
    c_m_h1.alignment = align_center
    c_m_h1.border = thin_border

    ws.merge_cells(start_row=metric_start, start_column=col_b_start + 2, end_row=metric_start, end_column=col_b_start + 3)
    c_m_h2 = ws.cell(row=metric_start, column=col_b_start + 2, value="VALOR OBTENIDO")
    c_m_h2.font = font_header
    c_m_h2.fill = azul_header
    c_m_h2.alignment = align_center
    c_m_h2.border = thin_border

    ws.merge_cells(start_row=metric_start, start_column=col_b_start + 4, end_row=metric_start, end_column=col_b_start + 5)
    c_m_h3 = ws.cell(row=metric_start, column=col_b_start + 4, value="INTERPRETACIÓN / CRITERIO")
    c_m_h3.font = font_header
    c_m_h3.fill = azul_header
    c_m_h3.alignment = align_center
    c_m_h3.border = thin_border

    # Bordes en celdas combinadas
    for col_m in range(col_b_start, col_b_start + 6):
        ws.cell(row=metric_start, column=col_m).border = thin_border

    metrics_data = [
        ("Estadístico Chi-Cuadrado (χ²)", f"{stats['chi2_total']:.4f}", f"Valor Crítico α=0.05: {stats['valor_critico_95']}"),
        ("Grados de Libertad (df)", f"{stats['grados_libertad']}", "k - 1 (9 dígitos - 1 = 8)"),
        ("Valor p (p-value)", f"{stats['p_valor']:.4e}", "p >= 0.05 indica conformidad con Benford"),
        ("Distancia Media Absoluta (MAD)", f"{stats['distancia_mad']:.2f}%", "< 1.2% estricto | > 1.8% sospechoso"),
        ("Distancia Euclidiana", f"{stats['distancia_euclidiana']:.2f}%", "Magnitud de separación vectorial"),
        ("Veredicto de Detección de Bots", stats["veredicto"], "Evaluación conforme a hipótesis nula"),
    ]

    for m_idx, (p_name, p_val, p_desc) in enumerate(metrics_data, start=metric_start + 1):
        ws.merge_cells(start_row=m_idx, start_column=col_b_start, end_row=m_idx, end_column=col_b_start + 1)
        ws.merge_cells(start_row=m_idx, start_column=col_b_start + 2, end_row=m_idx, end_column=col_b_start + 3)
        ws.merge_cells(start_row=m_idx, start_column=col_b_start + 4, end_row=m_idx, end_column=col_b_start + 5)

        c_m1 = ws.cell(row=m_idx, column=col_b_start, value=p_name)
        c_m2 = ws.cell(row=m_idx, column=col_b_start + 2, value=p_val)
        c_m3 = ws.cell(row=m_idx, column=col_b_start + 4, value=p_desc)

        for col_m in range(col_b_start, col_b_start + 6):
            ws.cell(row=m_idx, column=col_m).border = thin_border

        c_m1.font = font_bold
        c_m1.alignment = align_left
        c_m2.font = font_regular
        c_m2.alignment = align_center
        c_m3.font = font_regular
        c_m3.alignment = align_left

        if "Veredicto" in p_name:
            fill_v = verde_exito if stats["es_organico"] else rojo_alerta
            color_txt = "166534" if stats["es_organico"] else "991B1B"
            for col_v in range(col_b_start + 2, col_b_start + 4):
                ws.cell(row=m_idx, column=col_v).fill = fill_v
            c_m2.font = Font(name="Calibri", size=9, bold=True, color=color_txt)

    # Anchos de columna
    col_widths = {
        "A": 7,   # N°
        "B": 22,  # Usuario
        "C": 22,  # Followers
        "D": 22,  # Following
        "E": 24,  # Primer Dígito
        "F": 4,   # Separador
        "G": 18,  # Dígito (d)
        "H": 22,  # Conteo Observado
        "I": 20,  # Frecuencia Real %
        "J": 20,  # Esperado Benford %
        "K": 20,  # Conteo Esperado
        "L": 28,  # Chi-Cuadrado Parcial
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    # Insertar grafico PNG bajo las tablas
    if ruta_grafico_png and Path(ruta_grafico_png).exists():
        try:
            img = OpenpyxlImage(str(ruta_grafico_png))
            img.width = 680
            img.height = 420
            ws.add_image(img, f"G{metric_start + len(metrics_data) + 2}")
        except Exception as e:
            print(f"[!] No se pudo incrustar la imagen en el Excel: {e}")

    ruta_guardado_xlsx.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta_guardado_xlsx)
    return ruta_guardado_xlsx


# -- Obtencion de followers/following reales visitando cada perfil con Playwright --
def obtener_metricas_en_vivo(
    usuarios: list[dict],
    headless: bool = True,
    log_fn=print,
) -> list[dict]:
    """
    Visita cada perfil en paralelo (max 5 simultáneos) para leer followers y following
    directamente del encabezado. Actualiza cada elemento de la lista en su lugar.
    """
    import asyncio
    from playwright.async_api import async_playwright

    pendientes = [u for u in usuarios if u.get("followers") is None]
    if not pendientes:
        return usuarios

    log_fn(f"[*] Obteniendo métricas reales desde encabezados para {len(pendientes)} perfiles...")

    async def _enriquecer_async():
        sem = asyncio.Semaphore(5)
        progreso = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            )
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800} if headless else None,
            )

            cookies = []
            if SESSIONID:
                cookies.append({"name": "sessionid", "value": SESSIONID, "domain": ".instagram.com", "path": "/"})
            if DS_USER_ID:
                cookies.append({"name": "ds_user_id", "value": DS_USER_ID, "domain": ".instagram.com", "path": "/"})
            if CSRFTOKEN:
                cookies.append({"name": "csrftoken", "value": CSRFTOKEN, "domain": ".instagram.com", "path": "/"})

            if cookies:
                await context.add_cookies(cookies)

            async def _procesar_perfil(item):
                nonlocal progreso
                u = item.get("usuario")
                if not u or item.get("followers") is not None:
                    return

                async with sem:
                    url_u = f"https://www.instagram.com/{u}/"
                    foll_count = None
                    follg_count = None
                    page = await context.new_page()

                    try:
                        await page.goto(url_u, wait_until="domcontentloaded", timeout=16000)
                        await page.wait_for_selector("header ul, header section, header", timeout=6000)
                        header_text = await page.locator("header").first.inner_text()

                        m_foll = re.search(r"([\d.,]+[KkMm]?)\s*\n?\s*(?:followers|seguidores)", header_text, re.IGNORECASE)
                        m_follg = re.search(r"([\d.,]+[KkMm]?)\s*\n?\s*(?:following|seguidos|siguiendo)", header_text, re.IGNORECASE)

                        foll_count = texto_a_entero(m_foll.group(1)) if m_foll else None
                        follg_count = texto_a_entero(m_follg.group(1)) if m_follg else None
                    except Exception:
                        foll_count = None
                        follg_count = None
                    finally:
                        await page.close()

                    digito = primer_digito_de(foll_count)
                    item["followers"] = foll_count
                    item["following"] = follg_count
                    item["primer_digito"] = digito
                    progreso += 1

                    dig_txt = f"Dígito: {digito}" if digito else "Dígito: -"
                    log_fn(
                        f"  [{progreso:02d}/{len(pendientes)}] @{u:18} | "
                        f"Followers: {str(foll_count):6} | Following: {str(follg_count):6} | {dig_txt}"
                    )

            tasks = [_procesar_perfil(item) for item in usuarios if item.get("followers") is None]
            await asyncio.gather(*tasks)
            await browser.close()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_enriquecer_async())
    finally:
        loop.close()

    return usuarios


def guardar_metricas_en_json(target_user: str, tipo: str, usuarios: list[dict]):
    """Actualiza el JSON local con los followers/following recién obtenidos para no repetir visitas."""
    ruta_json = DIR_DATOS / f"datos_{target_user}.json"
    if not ruta_json.exists():
        ruta_json = BASE_DIR / f"datos_{target_user}.json"

    if not ruta_json.exists():
        return

    try:
        with open(ruta_json, "r", encoding="utf-8") as f:
            d = json.load(f)

        clave_lista = "seguidores_lista" if tipo == "seguidores" else "seguidos_lista"
        lista_existente = d.get(clave_lista, [])
        mapa_actualizado = {u["usuario"]: u for u in usuarios if "usuario" in u}

        for item in lista_existente:
            nom = item.get("usuario")
            if nom in mapa_actualizado:
                act = mapa_actualizado[nom]
                if act.get("followers") is not None:
                    item["followers"] = act["followers"]
                if act.get("following") is not None:
                    item["following"] = act["following"]
                if act.get("primer_digito") is not None:
                    item["primer_digito"] = act["primer_digito"]

        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def cargar_lista_usuarios(
    target_user: str,
    tipo: str = "seguidores",
    headless: bool = True,
    log_fn=print,
) -> list[dict]:
    """
    Carga la lista de usuarios desde el JSON local si existe.
    Si no hay datos previos, abre el modal de Instagram y hace scroll para extraerlos.
    """
    ruta_json = DIR_DATOS / f"datos_{target_user}.json"
    if not ruta_json.exists():
        ruta_json = BASE_DIR / f"datos_{target_user}.json"

    if ruta_json.exists():
        try:
            with open(ruta_json, "r", encoding="utf-8") as f:
                d = json.load(f)
            clave_lista = "seguidores_lista" if tipo == "seguidores" else "seguidos_lista"
            lista = d.get(clave_lista, [])
            if lista:
                candidatos = []
                for item in lista:
                    u = item.get("usuario")
                    foll = texto_a_entero(item.get("followers"))
                    follg = texto_a_entero(item.get("following"))
                    digito = primer_digito_de(foll)
                    candidatos.append({
                        "usuario": u,
                        "followers": foll,
                        "following": follg,
                        "primer_digito": digito,
                        "url": item.get("url", f"https://www.instagram.com/{u}/"),
                    })
                log_fn(f"[+] Se cargaron {len(candidatos)} {tipo} desde la base de datos local.")
                return candidatos
        except Exception:
            pass

    # No hay datos locales: abrir Instagram y hacer scroll en el modal
    from playwright.sync_api import sync_playwright

    log_fn(f"[*] No se encontró lista previa local. Extrayendo lista de {tipo} desde Instagram...")
    resultados = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        )
        context = browser.new_context(user_agent=USER_AGENT)

        cookies = []
        if SESSIONID:
            cookies.append({"name": "sessionid", "value": SESSIONID, "domain": ".instagram.com", "path": "/"})
        if DS_USER_ID:
            cookies.append({"name": "ds_user_id", "value": DS_USER_ID, "domain": ".instagram.com", "path": "/"})
        if CSRFTOKEN:
            cookies.append({"name": "csrftoken", "value": CSRFTOKEN, "domain": ".instagram.com", "path": "/"})
        if cookies:
            context.add_cookies(cookies)

        page = context.new_page()
        try:
            url_perfil = f"https://www.instagram.com/{target_user}/"
            page.goto(url_perfil, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3500)

            palabra_clave = "seguidores" if tipo == "seguidores" else "seguidos"
            regex_boton = re.compile(rf"\d+\s*(?:{palabra_clave}|followers|following|siguiendo)", re.IGNORECASE)
            btn = page.locator("header a, header button, header span").filter(has_text=regex_boton)

            if btn.count() == 0:
                btn = page.locator(f'a[href*="/{tipo}/"]')
                if btn.count() == 0:
                    raise RuntimeError(f"No se encontró el botón de '{tipo}' en el perfil de @{target_user}.")

            btn.first.click()
            page.wait_for_timeout(3000)

            dialog = page.locator('div[role="dialog"]').first
            if dialog.count() == 0 or not dialog.is_visible():
                raise RuntimeError("El diálogo modal de usuarios no se abrió correctamente.")

            JS_SCROLL = """() => {
                const dialog = document.querySelector('div[role="dialog"]');
                if (!dialog) return false;
                const scrollable = dialog.querySelector('div[style*="overflow-y"], div[class*="overflow"]');
                if (scrollable) { scrollable.scrollTop += 650; return true; }
                return false;
            }"""

            usuarios_procesados = set()
            sin_nuevos = 0

            for ronda in range(80):
                links = dialog.locator('a[href^="/"]')
                c_links = links.count()
                encontrados = 0

                for i in range(c_links):
                    href = links.nth(i).get_attribute("href") or ""
                    m = re.match(r"^/([a-zA-Z0-9_.]+)/?$", href)
                    if not m:
                        continue
                    u = m.group(1).lower()
                    if u == target_user.lower() or u in usuarios_procesados:
                        continue

                    usuarios_procesados.add(u)
                    resultados.append({
                        "usuario": u,
                        "followers": None,
                        "following": None,
                        "primer_digito": None,
                        "url": f"https://www.instagram.com/{u}/",
                    })
                    encontrados += 1

                if encontrados == 0:
                    sin_nuevos += 1
                    if sin_nuevos >= 4:
                        break
                else:
                    sin_nuevos = 0

                page.evaluate(JS_SCROLL)
                page.wait_for_timeout(random.randint(1800, 2500))

        finally:
            browser.close()

    return resultados


# -- Funcion principal: carga datos, obtiene metricas, calcula Benford y exporta --
def ejecutar_analisis_benford(
    target_user: str,
    tipo: str = "seguidores",
    limite: int | None = None,
    usar_json_existente: bool = True,
    headless: bool = True,
    log_fn=print,
) -> dict:
    """
    Ejecuta el analisis completo:
    - Carga o extrae la lista de usuarios.
    - Ajusta el limite si supera los disponibles.
    - Obtiene followers/following de los que falten.
    - Calcula chi-cuadrado y genera Excel + PNG.
    """
    log_fn("\n" + "=" * 65)
    log_fn(f"ANALISIS BENFORD -- @{target_user}")
    log_fn(f"Lista:          {tipo.upper()}")
    log_fn(f"Navegador:      {'Segundo plano' if headless else 'Visible'}")
    log_fn("=" * 65)

    # Cargar lista de usuarios del JSON local (o extraer si no existe)
    usuarios_disponibles = cargar_lista_usuarios(
        target_user=target_user,
        tipo=tipo,
        headless=headless,
        log_fn=log_fn,
    )

    total_disponibles = len(usuarios_disponibles)
    if total_disponibles == 0:
        raise RuntimeError(f"No se encontraron cuentas en la lista de {tipo} para @{target_user}.")

    # Ajustar limite si supera el total disponible
    if limite is not None and int(limite) > 0:
        limite_int = int(limite)
        if limite_int > total_disponibles:
            log_fn(
                f"[!] AVISO: Solicitaste una muestra de {limite_int} perfiles, pero @{target_user} "
                f"solo cuenta con {total_disponibles} {tipo} en su lista. "
                f"Se ajusta automáticamente la muestra a {total_disponibles} perfiles."
            )
            limite_efectivo = total_disponibles
        else:
            limite_efectivo = limite_int
            log_fn(f"[*] Tamaño de muestra solicitado: {limite_efectivo} perfiles (de {total_disponibles} disponibles)")
    else:
        limite_efectivo = total_disponibles
        log_fn(f"[*] Tamaño de muestra: TODOS los perfiles disponibles ({total_disponibles} perfiles)")

    muestra = usuarios_disponibles[:limite_efectivo]

    # Obtener followers/following de los perfiles que aun no tienen datos
    pendientes = [u for u in muestra if u.get("followers") is None]
    if pendientes:
        log_fn(f"[*] Enriqueciendo métricas reales de {len(pendientes)} perfiles...")
        muestra = obtener_metricas_en_vivo(muestra, headless=headless, log_fn=log_fn)
        guardar_metricas_en_json(target_user, tipo, muestra)
    else:
        log_fn(f"[+] Todas las métricas de seguidores y seguidos están cargadas.")

    # Calcular distribución de Benford y estadisticos
    stats = calcular_benford(muestra, campo="followers")

    if stats["total_validos"] == 0:
        raise RuntimeError(
            f"No se encontraron perfiles con seguidores numéricos mayores a 0 en la lista de {tipo} "
            f"de @{target_user}. Verifique que la cuenta sea accesible y que los datos se hayan extraído correctamente."
        )

    # Rutas de salida
    nombre_base = f"benford_{tipo}_{target_user}"
    ruta_png = DIR_BENFORD / f"grafico_{nombre_base}.png"
    ruta_xlsx = DIR_BENFORD / f"{nombre_base}.xlsx"
    ruta_json = DIR_BENFORD / f"analisis_{nombre_base}.json"

    # Generar grafico PNG
    log_fn("[*] Generando gráfico comparativo superpuesto (Azul = Real, Rojo = Benford)...")
    generar_grafico(stats, target_user, tipo, ruta_png)

    # Generar Excel
    log_fn(f"[*] Creando libro Excel con fórmulas y gráfico: {ruta_xlsx.name}...")
    generar_excel(muestra, stats, target_user, tipo, ruta_xlsx, ruta_grafico_png=ruta_png)

    # Guardar reporte JSON
    resultado_completo = {
        "usuario_objetivo": target_user,
        "tipo_lista": tipo,
        "fecha_analisis": datetime.now(timezone.utc).isoformat(),
        "estadisticas": stats,
        "total_usuarios_procesados": len(muestra),
        "archivo_excel": str(ruta_xlsx.resolve()),
        "archivo_grafico": str(ruta_png.resolve()),
        "usuarios": muestra,
    }

    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(resultado_completo, f, ensure_ascii=False, indent=2)

    log_fn("\n" + "=" * 65)
    log_fn(f"ANALISIS BENFORD FINALIZADO: {stats['veredicto']}")
    log_fn(f"  Perfiles evaluados: {stats['total_validos']} con followers > 0")
    log_fn(f"  Chi-cuadrado (chi2): {stats['chi2_total']:.4f} (Critico: {stats['valor_critico_95']})")
    log_fn(f"  p-valor: {stats['p_valor']:.4e} | Grados de libertad: {stats['grados_libertad']}")
    log_fn(f"  MAD: {stats['distancia_mad']:.2f}% | Euclidiana: {stats['distancia_euclidiana']:.2f}%")
    log_fn(f"  Excel:   {ruta_xlsx.name}")
    log_fn(f"  Grafico: {ruta_png.name}")
    log_fn("=" * 65)

    return resultado_completo


# -- Interfaz de linea de comandos --
def main():
    parser = argparse.ArgumentParser(
        description="Detección de bots y cuentas falsas con Ley de Benford en Instagram."
    )
    parser.add_argument(
        "--usuario",
        type=str,
        default=None,
        help="Nombre de usuario objetivo (ej: sausage_player).",
    )
    parser.add_argument(
        "--tipo",
        type=str,
        choices=["seguidores", "seguidos"],
        default=None,
        help="Tipo de red a auditar: 'seguidores' (followers) o 'seguidos' (following).",
    )
    parser.add_argument(
        "--limite",
        type=str,
        default=None,
        help="Cantidad de perfiles a inspeccionar (ej: 50, 100, o 'todos'/0 para TODOS).",
    )
    parser.add_argument(
        "--from-json",
        action="store_true",
        help="Usar lista previa de 'datos_<usuario>.json' sin re-extraer desde cero.",
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Abrir navegador visible en vez de headless.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Generar análisis con perfiles de prueba rápidos.",
    )

    args = parser.parse_args()

    # Si se ejecuta sin parámetros en la terminal, solicitar interactivamente al usuario
    es_interactivo = len(sys.argv) <= 1 or (args.usuario is None and args.limite is None)

    if es_interactivo:
        print("\n" + "=" * 65)
        print("CONFIGURACIÓN DE ANÁLISIS DE BENFORD")
        print("=" * 65)
        u_input = input(f"Usuario a analizar [ENTER para @{TARGET_DEFAULT}]: ").strip()
        target_user = u_input.lstrip("@") if u_input else TARGET_DEFAULT

        t_input = input("Tipo de lista (1: seguidores, 2: seguidos) [ENTER para seguidores]: ").strip()
        tipo = "seguidos" if t_input == "2" else "seguidores"

        l_input = input("¿Cuántos perfiles deseas sacar? (Escribe un número o ENTER para TODOS): ").strip()
        if not l_input or l_input.lower() in ("todos", "all", "0"):
            limite = None
        else:
            try:
                limite = int(l_input)
            except ValueError:
                limite = None
        usar_json = True
    else:
        target_user = (args.usuario or TARGET_DEFAULT).strip().lstrip("@")
        tipo = args.tipo or "seguidores"
        if args.limite is not None:
            if str(args.limite).lower() in ("todos", "all", "0"):
                limite = None
            else:
                try:
                    limite = int(args.limite)
                except ValueError:
                    limite = None
        else:
            limite = None
        usar_json = args.from_json or args.demo

    headless = not args.visible

    ejecutar_analisis_benford(
        target_user=target_user,
        tipo=tipo,
        limite=limite,
        usar_json_existente=usar_json,
        headless=headless,
        log_fn=print,
    )


if __name__ == "__main__":
    main()

