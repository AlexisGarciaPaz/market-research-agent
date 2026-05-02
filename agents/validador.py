# agents/validador.py
import json
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv
from agents.memoria import obtener_contexto_para_claude, escribir_memoria, leer_memoria

load_dotenv()
REPORTS_DIR = Path("reports")


def analizar_arbitraje(producto, precio_compra, unidades=1):
    client = Anthropic()
    contexto = obtener_contexto_para_claude()
    mem = leer_memoria()

    listing_mem   = mem.get("listado_optimizado", {}).get("hallazgos", {})
    precio_venta  = listing_mem.get("precio_objetivo_mx", 0)
    precio_launch = listing_mem.get("precio_lanzamiento_mx", 0)

    precio_valor_mem = mem.get("precio_valor", {}).get("hallazgos", {})
    margen_pct = precio_valor_mem.get("margen_estimado_pct", 30)

    inversion_total = precio_compra * unidades

    prompt = f"""Eres un experto en arbitraje de productos para Amazon México.
El vendedor evalúa si conviene comprar este producto para revenderlo en Amazon MX.

PRODUCTO: {producto}
PRECIO DE COMPRA (por unidad): MX${precio_compra:,.2f}
UNIDADES A COMPRAR: {unidades}
INVERSIÓN TOTAL: MX${inversion_total:,.2f}

{contexto}

El análisis del mercado sugiere:
- Precio de venta objetivo: MX${precio_venta:,.0f}
- Precio de lanzamiento: MX${precio_launch:,.0f}
- Margen estimado del mercado: {margen_pct}%

Calcula con precisión:
- Referral fee Amazon MX: 15% del precio de venta
- FBA fee estimado: MX$45-80 según tamaño/peso típico del producto
- Ganancia neta por unidad = precio_venta - precio_compra - referral_fee - fba_fee
- ROI = (ganancia_neta_total / inversión_total) * 100

Responde ÚNICAMENTE con JSON válido, sin backticks:

{{
  "veredicto": "COMPRA",
  "score_oportunidad": 0,
  "precio_venta_recomendado_mx": 0.0,
  "precio_lanzamiento_mx": 0.0,
  "referral_fee_mx": 0.0,
  "fba_fee_estimado_mx": 0.0,
  "ganancia_por_unidad_mx": 0.0,
  "ganancia_total_estimada_mx": 0.0,
  "roi_estimado_pct": 0.0,
  "tiempo_recuperacion_estimado": "X semanas",
  "razon_principal": "razón del veredicto en 1-2 oraciones",
  "resumen_ejecutivo": "párrafo de 3-4 oraciones para el vendedor",
  "riesgos": ["riesgo 1", "riesgo 2", "riesgo 3"],
  "acciones_inmediatas": ["acción 1", "acción 2", "acción 3"]
}}

veredicto debe ser exactamente: "COMPRA", "NO COMPRA" o "RIESGO MEDIO"
score_oportunidad: entero de 0 a 100"""

    print("  Claude evaluando arbitraje...")
    respuesta = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system="Eres experto en arbitraje Amazon Mexico. Respondes siempre con JSON valido.",
        messages=[{"role": "user", "content": prompt}]
    )

    texto = respuesta.content[0].text
    if "```json" in texto:
        texto = texto.split("```json")[1].split("```")[0].strip()
    elif "```" in texto:
        texto = texto.split("```")[1].split("```")[0].strip()

    try:
        resultado = json.loads(texto)
    except json.JSONDecodeError:
        inicio = texto.find("{")
        fin    = texto.rfind("}") + 1
        resultado = json.loads(texto[inicio:fin]) if inicio != -1 else {}

    resultado["_tokens"] = {
        "entrada": respuesta.usage.input_tokens,
        "salida":  respuesta.usage.output_tokens,
    }

    escribir_memoria("validador", {
        "producto":                    producto,
        "precio_compra_mx":            precio_compra,
        "veredicto":                   resultado.get("veredicto", ""),
        "roi_estimado_pct":            resultado.get("roi_estimado_pct", 0),
        "precio_venta_recomendado_mx": resultado.get("precio_venta_recomendado_mx", 0),
        "ganancia_por_unidad_mx":      resultado.get("ganancia_por_unidad_mx", 0),
        "score_oportunidad":           resultado.get("score_oportunidad", 0),
    })
    return resultado


def ejecutar(producto, precio_compra, unidades=1, mercado=None):
    print("\n" + "="*50)
    print("AGENTE 9: VALIDADOR DE ARBITRAJE")
    print("="*50)

    REPORTS_DIR.mkdir(exist_ok=True)

    resultado = analizar_arbitraje(producto, precio_compra, unidades)
    if not resultado:
        print("  No se pudo generar el analisis")
        return None

    veredicto   = resultado.get("veredicto", "?")
    roi         = resultado.get("roi_estimado_pct", 0)
    precio_venta = resultado.get("precio_venta_recomendado_mx", 0)
    score        = resultado.get("score_oportunidad", 0)

    print(f"\n  Producto: {producto}")
    print(f"  Precio compra: MX${precio_compra:,.2f} x {unidades} uds")
    print(f"\n  VEREDICTO: {veredicto}")
    print(f"  Score: {score}/100")
    print(f"  ROI estimado: {roi}%")
    print(f"  Precio venta: MX${precio_venta:,.0f}")
    print(f"\n  {resultado.get('razon_principal', '')[:120]}")

    reporte = generar_reporte(producto, precio_compra, unidades, resultado)
    path = REPORTS_DIR / "fase6_arbitraje.md"
    path.write_text(reporte, encoding="utf-8")
    print(f"\n  Reporte guardado en: {path}")

    return resultado


def generar_reporte(producto, precio_compra, unidades, resultado):
    r = []
    veredicto = resultado.get("veredicto", "?")

    r.append(f"# Analisis de Arbitraje — {producto}\n")
    r.append(f"## Veredicto: **{veredicto}**")
    r.append(f"**Score de oportunidad:** {resultado.get('score_oportunidad', 0)}/100\n")

    r.append("## Numeros clave")
    r.append("| | |")
    r.append("|---|---|")
    r.append(f"| Precio de compra | MX${precio_compra:,.2f} |")
    r.append(f"| Unidades | {unidades} |")
    r.append(f"| Inversion total | MX${precio_compra * unidades:,.2f} |")
    r.append(f"| Precio venta recomendado | MX${resultado.get('precio_venta_recomendado_mx', 0):,.0f} |")
    r.append(f"| Referral fee (15%) | MX${resultado.get('referral_fee_mx', 0):,.0f} |")
    r.append(f"| FBA fee estimado | MX${resultado.get('fba_fee_estimado_mx', 0):,.0f} |")
    r.append(f"| Ganancia por unidad | MX${resultado.get('ganancia_por_unidad_mx', 0):,.0f} |")
    r.append(f"| Ganancia total estimada | MX${resultado.get('ganancia_total_estimada_mx', 0):,.0f} |")
    r.append(f"| ROI estimado | {resultado.get('roi_estimado_pct', 0)}% |")
    r.append(f"| Tiempo recuperacion | {resultado.get('tiempo_recuperacion_estimado', '?')} |\n")

    r.append("## Resumen ejecutivo")
    r.append(resultado.get("resumen_ejecutivo", "") + "\n")

    r.append("## Razon del veredicto")
    r.append(resultado.get("razon_principal", "") + "\n")

    r.append("## Riesgos")
    for riesgo in resultado.get("riesgos", []):
        r.append(f"- {riesgo}")

    r.append("\n## Acciones inmediatas")
    for i, accion in enumerate(resultado.get("acciones_inmediatas", []), 1):
        r.append(f"{i}. {accion}")

    tokens = resultado.get("_tokens", {})
    r.append(f"\n*Tokens: {tokens.get('entrada', 0)} entrada / {tokens.get('salida', 0)} salida*")
    return "\n".join(r)


if __name__ == "__main__":
    ejecutar("Miel maple Members Mark 600ml", 189.0, 12)
