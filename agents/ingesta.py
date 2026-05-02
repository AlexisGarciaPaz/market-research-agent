# agents/ingesta.py
import os
import re
import pandas as pd
from pathlib import Path
from datetime import date, datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

RAW_DIR     = Path("data/raw")
REPORTS_DIR = Path("reports")

# Columnas clave para identificar el tipo de CSV por su contenido
DETECTORES = {
    "xray":         ["ASIN Sales", "Parent Level Sales", "Fees $", "Active Sellers"],
    "xray_keyword": ["Cerebro IQ Score", "Search Volume", "Title Density"],
    "asin_grabber": ["Price MX$", "Ratings", "Review Count", "Origin"],
}


# ─────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────

def get_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL no está definida en .env")
    return create_engine(url)


def normalizar_columnas(df):
    """Limpia nombres de columnas: strip y colapsa espacios múltiples."""
    df.columns = [re.sub(r"\s+", " ", c).strip() for c in df.columns]
    return df


def limpiar_numero(val):
    """Convierte '1,435', 'MX$181.22', 'N/A', '-' a float o None."""
    if pd.isna(val):
        return None
    s = re.sub(r"[^\d.]", "", str(val))
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def limpiar_bool(val):
    """Convierte 'Sponsored', 'Yes', 'No', vacío a bool."""
    if pd.isna(val):
        return False
    v = str(val).strip().upper()
    return v not in ("NO", "FALSE", "0", "", "N/A", "-")


def parsear_fecha(val):
    """Convierte 'May 13, 2015' a date o None."""
    if pd.isna(val) or str(val).strip() in ("N/A", "-", ""):
        return None
    try:
        return datetime.strptime(str(val).strip(), "%b %d, %Y").date()
    except ValueError:
        return None


def detectar_tipo(df):
    cols = set(df.columns)
    for tipo, columnas_clave in DETECTORES.items():
        if all(c in cols for c in columnas_clave):
            return tipo
    return "desconocido"


# ─────────────────────────────────────────────
# PARSERS POR TIPO DE ARCHIVO
# ─────────────────────────────────────────────

def parsear_xray(df, mercado):
    """Parsea Helium 10 Xray export → tabla productos."""
    registros = []
    for _, row in df.iterrows():
        asin = str(row.get("ASIN", "")).strip()
        if not asin or asin in ("nan", "N/A"):
            continue
        registros.append({
            "asin":                     asin,
            "titulo":                   str(row.get("Product Details", ""))[:500],
            "marca":                    str(row.get("Brand", ""))[:255],
            "categoria":                str(row.get("Category", ""))[:255]   if not pd.isna(row.get("Category", ""))   else None,
            "size_tier":                str(row.get("Size Tier", ""))[:50]   if not pd.isna(row.get("Size Tier", ""))   else None,
            "precio":                   limpiar_numero(row.get("Price $")),
            "bsr":                      int(limpiar_numero(row.get("BSR")) or 0) or None,
            "reviews_count":            int(limpiar_numero(row.get("Review Count")) or 0) or None,
            "rating":                   limpiar_numero(row.get("Ratings")),
            "ventas_mensuales_asin":    int(limpiar_numero(row.get("ASIN Sales")) or 0) or None,
            "ventas_mensuales_parent":  int(limpiar_numero(row.get("Parent Level Sales")) or 0) or None,
            "revenue_mensual_asin":     limpiar_numero(row.get("ASIN Revenue")),
            "revenue_mensual_parent":   limpiar_numero(row.get("Parent Level Revenue")),
            "fees":                     limpiar_numero(row.get("Fees $")),
            "active_sellers":           int(limpiar_numero(row.get("Active Sellers")) or 0) or None,
            "review_velocity":          int(limpiar_numero(row.get("Review velocity")) or 0) or None,
            "fba":                      str(row.get("Fulfillment", "")).upper() in ("FBA", "AMZ"),
            "dimensiones":              str(row.get("Dimensions", ""))[:100] if not pd.isna(row.get("Dimensions", "")) else None,
            "peso_kg":                  limpiar_numero(row.get("Weight")),
            "seller_nombre":            str(row.get("Seller", ""))[:255]     if not pd.isna(row.get("Seller", ""))     else None,
            "seller_age_months":        int(limpiar_numero(row.get("Seller Age (mo)")) or 0) or None,
            "buy_box":                  str(row.get("Buy Box", ""))[:255]    if not pd.isna(row.get("Buy Box", ""))    else None,
            "best_seller":              limpiar_bool(row.get("Best Seller")),
            "pais_vendedor":            str(row.get("Seller Country/Region", ""))[:10] if not pd.isna(row.get("Seller Country/Region", "")) else None,
            "imagen_url":               str(row.get("Image URL", ""))        if not pd.isna(row.get("Image URL", ""))  else None,
            "fecha_creacion_listing":   parsear_fecha(row.get("Creation Date")),
            "fuente":                   "xray",
            "mercado":                  mercado,
            "fecha_captura":            date.today(),
        })
    return registros


def parsear_asin_grabber(df, mercado):
    """Parsea ASIN Grabber export → tabla productos."""
    registros = []
    for _, row in df.iterrows():
        asin = str(row.get("ASIN", "")).strip()
        if not asin or asin in ("nan", "N/A"):
            continue
        registros.append({
            "asin":          asin,
            "titulo":        str(row.get("Product Details", ""))[:500],
            "marca":         str(row.get("Brand", ""))[:255],
            "precio":        limpiar_numero(row.get("Price MX$")),
            "bsr":           int(limpiar_numero(row.get("BSR")) or 0) or None,
            "reviews_count": int(limpiar_numero(row.get("Review Count")) or 0) or None,
            "rating":        limpiar_numero(row.get("Ratings")),
            "imagen_url":    str(row.get("Image URL", "")) if not pd.isna(row.get("Image URL", "")) else None,
            "fuente":        "asin_grabber",
            "mercado":       mercado,
            "fecha_captura": date.today(),
        })
    return registros


def parsear_xray_keyword(df, mercado):
    """Parsea Helium 10 Xray Keyword / Cerebro export → tabla keywords."""
    registros = []
    for _, row in df.iterrows():
        keyword = str(row.get("Keyword Phrase", "")).strip()
        if not keyword or keyword == "nan":
            continue
        registros.append({
            "keyword":             keyword,
            "volumen_busqueda":    int(limpiar_numero(row.get("Search Volume")) or 0) or None,
            "tendencia_30d":       limpiar_numero(row.get("Search Volume Trend")),
            "productos_competidores": int(limpiar_numero(row.get("Competing Products")) or 0) or None,
            "cerebro_iq_score":    int(limpiar_numero(row.get("Cerebro IQ Score")) or 0) or None,
            "keyword_sales":       int(limpiar_numero(row.get("Keyword Sales")) or 0) or None,
            "title_density":       int(limpiar_numero(row.get("Title Density")) or 0) or None,
            "competitor_rank_avg": limpiar_numero(row.get("Competitor Rank (avg)")),
            "sugerido_ppc_bid":    limpiar_numero(row.get("Suggested PPC Bid")),
            "fuente":              "xray_keyword",
            "asin_origen":         "",
            "mercado":             mercado,
            "fecha_captura":       date.today(),
        })
    return registros


# ─────────────────────────────────────────────
# CARGA A POSTGRESQL
# ─────────────────────────────────────────────

def insertar_productos(registros, engine):
    if not registros:
        return 0

    cols = list(registros[0].keys())
    col_names   = ", ".join(cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in cols
        if c not in ("asin", "fuente", "fecha_captura")
    )

    sql = text(f"""
        INSERT INTO productos ({col_names})
        VALUES ({placeholders})
        ON CONFLICT (asin, fuente, fecha_captura) DO UPDATE SET {updates}
    """)

    insertados = 0
    with engine.begin() as conn:
        for r in registros:
            conn.execute(sql, r)
            insertados += 1

    return insertados


def insertar_keywords(registros, engine):
    if not registros:
        return 0

    cols = list(registros[0].keys())
    col_names    = ", ".join(cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in cols
        if c not in ("keyword", "fuente", "asin_origen", "fecha_captura")
    )

    sql = text(f"""
        INSERT INTO keywords ({col_names})
        VALUES ({placeholders})
        ON CONFLICT (keyword, fuente, asin_origen, fecha_captura) DO UPDATE SET {updates}
    """)

    insertados = 0
    with engine.begin() as conn:
        for r in registros:
            conn.execute(sql, r)
            insertados += 1

    return insertados


# ─────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────

def ejecutar(mercado="suplementos"):
    print("\n" + "="*50)
    print("AGENTE 1: INGESTA DE DATOS")
    print("="*50)

    REPORTS_DIR.mkdir(exist_ok=True)

    archivos_csv = sorted(RAW_DIR.glob("*.csv"))
    if not archivos_csv:
        print("\n  Sin archivos CSV en data/raw/")
        return None

    print(f"\n  Archivos CSV detectados: {len(archivos_csv)}")

    engine = get_engine()
    resumen = {"productos": 0, "keywords": 0, "omitidos": [], "errores": []}
    procesados = []

    asins_vistos = set()  # para deduplicar asinGrabber duplicados entre archivos

    for path in archivos_csv:
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            df = normalizar_columnas(df)
        except Exception as e:
            print(f"\n  Error leyendo {path.name}: {e}")
            resumen["errores"].append(path.name)
            continue

        tipo = detectar_tipo(df)
        print(f"\n  {path.name}")
        print(f"    Tipo: {tipo} | Filas: {len(df)}")

        if tipo == "xray":
            registros = parsear_xray(df, mercado)
            n = insertar_productos(registros, engine)
            resumen["productos"] += n
            print(f"    Insertados en productos: {n}")
            procesados.append({"archivo": path.name, "tipo": tipo, "registros": n})

        elif tipo == "asin_grabber":
            registros = parsear_asin_grabber(df, mercado)
            # Deduplicar contra lo ya procesado en esta sesión
            nuevos = [r for r in registros if r["asin"] not in asins_vistos]
            asins_vistos.update(r["asin"] for r in nuevos)
            n = insertar_productos(nuevos, engine)
            omitidos = len(registros) - len(nuevos)
            resumen["productos"] += n
            print(f"    Insertados en productos: {n} ({omitidos} duplicados omitidos)")
            procesados.append({"archivo": path.name, "tipo": tipo, "registros": n})

        elif tipo == "xray_keyword":
            registros = parsear_xray_keyword(df, mercado)
            n = insertar_keywords(registros, engine)
            resumen["keywords"] += n
            print(f"    Insertados en keywords: {n}")
            procesados.append({"archivo": path.name, "tipo": tipo, "registros": n})

        else:
            print(f"    Tipo no reconocido — omitido")
            resumen["omitidos"].append(path.name)

    # Guardar reporte
    lineas = [
        "# Reporte de Ingesta\n",
        f"- Mercado: **{mercado}**",
        f"- Fecha: {date.today()}",
        f"- Registros en `productos`: {resumen['productos']}",
        f"- Registros en `keywords`: {resumen['keywords']}",
    ]
    if resumen["omitidos"]:
        lineas.append(f"- Archivos omitidos (tipo desconocido): {', '.join(resumen['omitidos'])}")
    if resumen["errores"]:
        lineas.append(f"- Archivos con error: {', '.join(resumen['errores'])}")
    lineas.append("\n## Detalle por archivo")
    for p in procesados:
        lineas.append(f"- `{p['archivo']}` → tipo `{p['tipo']}`, {p['registros']} registros")

    reporte_path = REPORTS_DIR / "ingesta.md"
    reporte_path.write_text("\n".join(lineas), encoding="utf-8")

    print(f"\n  Reporte guardado en: {reporte_path}")
    print(f"\n  Productos: {resumen['productos']} | Keywords: {resumen['keywords']}")
    print("\n  Agente de ingesta completado.")
    return resumen


if __name__ == "__main__":
    ejecutar()
