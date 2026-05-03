# agents/estacionalidad.py
import json
import time
from datetime import date
from anthropic import Anthropic
from dotenv import load_dotenv
from agents.memoria import escribir_memoria, parsear_json_claude

load_dotenv()

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

# Penalización al score de arbitraje por riesgo estacional
PENALIZACION_POR_RIESGO = {"ALTO": 15, "MEDIO": 8, "BAJO": 0}


# ─────────────────────────────────────────────
# BLOQUE 1 — Google Trends
# ─────────────────────────────────────────────

def obtener_datos_trends(termino: str, geo: str = "MX") -> dict:
    """
    Consulta Google Trends para el último año en México.
    Retorna dict {YYYY-MM: valor_promedio} o {} si falla.
    """
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="es-MX", tz=360, timeout=(10, 25), retries=2)
        pytrends.build_payload([termino], cat=0, timeframe="today 12-m", geo=geo)
        time.sleep(1.5)  # respetar rate limit de Google

        df = pytrends.interest_over_time()
        if df is None or df.empty or termino not in df.columns:
            return {}

        # Resamplear datos semanales → promedio mensual
        import pandas as pd
        serie = df[termino].resample("ME").mean().round(1)
        return {
            str(idx.strftime("%Y-%m")): float(val)
            for idx, val in serie.items()
            if not pd.isna(val)
        }
    except Exception as e:
        print(f"  [estacionalidad] pytrends: {type(e).__name__}: {e}")
        return {}


# ─────────────────────────────────────────────
# BLOQUE 2 — Análisis con Claude Haiku
# ─────────────────────────────────────────────

def analizar_con_claude_haiku(termino: str, datos_trends: dict, mes_actual: int) -> dict:
    client = Anthropic()
    mes_nombre = MESES_ES[mes_actual]

    if datos_trends:
        datos_str = json.dumps(datos_trends, ensure_ascii=False)
        contexto_datos = (
            f"Datos de Google Trends México — interés de búsqueda (escala 0-100), "
            f"últimos 12 meses:\n{datos_str}"
        )
    else:
        contexto_datos = (
            "No hay datos de Google Trends disponibles para este término. "
            "Usa tu conocimiento general sobre estacionalidad en el mercado mexicano."
        )

    prompt = f"""Analiza la estacionalidad del siguiente producto o mercado en México.
Producto/mercado: {termino}
Mes actual de análisis: {mes_nombre}

{contexto_datos}

Determina si la demanda varía significativamente según la época del año en México,
considerando temporadas, fechas comerciales (Buen Fin, Navidad, Día de Madres, etc.)
y patrones de consumo locales.

Responde ÚNICAMENTE con este JSON válido (sin backticks):

{{
  "tiene_estacionalidad": true,
  "tipo": "anual | trimestral | none",
  "pico_meses": ["Diciembre", "Enero"],
  "valle_meses": ["Junio", "Julio"],
  "riesgo_actual": "ALTO | MEDIO | BAJO",
  "advertencia": "texto específico si el mes actual está en temporada baja, vacío si no aplica",
  "confianza": "alta | media | baja"
}}

Reglas estrictas para riesgo_actual:
- ALTO: el mes actual ({mes_nombre}) es uno de los 2 peores meses para este producto
- MEDIO: el mes actual está en temporada baja pero no en el peor momento
- BAJO: el mes actual es temporada normal o alta
- Si no hay estacionalidad clara: tipo="none", riesgo_actual="BAJO", listas vacías"""

    respuesta = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system="Eres experto en estacionalidad de mercados en México. Respondes solo con JSON válido.",
        messages=[{"role": "user", "content": prompt}]
    )

    resultado = parsear_json_claude(respuesta.content[0].text, "estacionalidad")
    resultado["_tokens"] = {
        "entrada": respuesta.usage.input_tokens,
        "salida":  respuesta.usage.output_tokens,
    }
    return resultado


# ─────────────────────────────────────────────
# BLOQUE 3 — Punto de entrada (pipeline)
# ─────────────────────────────────────────────

def ejecutar(mercado: str) -> dict:
    print(f"\n{'='*50}")
    print("AGENTE — ESTACIONALIDAD")
    print(f"{'='*50}")

    mes_actual = date.today().month
    mes_nombre = MESES_ES[mes_actual]
    print(f"\n  Mercado: {mercado!r} | Mes actual: {mes_nombre}")
    print("  Consultando Google Trends (México)...")

    datos_trends = obtener_datos_trends(mercado)
    if datos_trends:
        vals = list(datos_trends.values())
        print(f"  {len(datos_trends)} meses obtenidos — rango: {min(vals):.0f}–{max(vals):.0f}")
    else:
        print("  Sin datos de Trends — Claude usará conocimiento general")

    print("  Claude Haiku analizando patrón estacional...")
    analisis = analizar_con_claude_haiku(mercado, datos_trends, mes_actual)

    hallazgos = {
        "tiene_estacionalidad": analisis.get("tiene_estacionalidad", False),
        "tipo":                 analisis.get("tipo", "none"),
        "pico_meses":           analisis.get("pico_meses", []),
        "valle_meses":          analisis.get("valle_meses", []),
        "riesgo_actual":        analisis.get("riesgo_actual", "BAJO"),
        "advertencia":          analisis.get("advertencia", ""),
        "confianza":            analisis.get("confianza", "baja"),
        "datos_disponibles":    bool(datos_trends),
    }

    escribir_memoria("estacionalidad", hallazgos)

    riesgo = hallazgos["riesgo_actual"]
    if riesgo == "ALTO":
        print(f"\n  RIESGO ESTACIONAL ALTO en {mes_nombre}:")
        print(f"  {hallazgos['advertencia']}")
    elif riesgo == "MEDIO":
        print(f"\n  Riesgo estacional MEDIO en {mes_nombre}")
        if hallazgos["advertencia"]:
            print(f"  {hallazgos['advertencia']}")
    else:
        print(f"\n  Riesgo estacional: BAJO (temporada favorable en {mes_nombre})")

    if hallazgos["pico_meses"]:
        print(f"  Picos: {', '.join(hallazgos['pico_meses'])}")
    if hallazgos["valle_meses"]:
        print(f"  Valles: {', '.join(hallazgos['valle_meses'])}")

    tokens = analisis.get("_tokens", {})
    print(f"  Tokens Haiku: {tokens.get('entrada', 0)} entrada / {tokens.get('salida', 0)} salida")

    return hallazgos


# ─────────────────────────────────────────────
# BLOQUE 4 — Función rápida para batch
# ─────────────────────────────────────────────

def obtener_penalizacion_batch(termino: str) -> tuple[int, str]:
    """
    Versión ligera para batch_arbitraje: una sola llamada Haiku.
    No requiere datos de Trends (usa conocimiento general).
    Retorna (puntos_penalizacion, advertencia).
    """
    mes_actual = date.today().month
    analisis = analizar_con_claude_haiku(termino, {}, mes_actual)
    riesgo = analisis.get("riesgo_actual", "BAJO")
    puntos = PENALIZACION_POR_RIESGO.get(riesgo, 0)
    advertencia = analisis.get("advertencia", "")
    return puntos, advertencia
