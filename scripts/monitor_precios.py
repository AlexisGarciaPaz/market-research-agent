# scripts/monitor_precios.py
"""
Monitor de precios diario para arbitraje Amazon México.
Detecta cambios de precio > 10% en ASINs del historial y envía
alertas Telegram cuando el semáforo cambia de categoría.

Configurar en Railway como servicio Cron independiente:
  schedule: "0 9 * * *"
  command:  "python scripts/monitor_precios.py"

Variables .env requeridas:
  DATABASE_URL        (ya existe)
  TELEGRAM_BOT_TOKEN  (nuevo)
  TELEGRAM_CHAT_ID    (nuevo)
"""
import os
import re
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from agents.batch_arbitraje import calcular_financiero, asignar_semaforo

HISTORIAL_DIR     = Path("historial")
UMBRAL_CAMBIO_PCT = 10.0
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT     = os.getenv("TELEGRAM_CHAT_ID", "")


# ─────────────────────────────────────────────
# BLOQUE 1 — Lectura de historial
# ─────────────────────────────────────────────

def leer_asins_historial() -> list[str]:
    """
    Extrae ASINs únicos del index.md.
    Busca el patrón `B0XXXXXXXXX` en las tablas markdown.
    """
    path = HISTORIAL_DIR / "index.md"
    if not path.exists():
        return []
    texto = path.read_text(encoding="utf-8")
    asins = re.findall(r"`([A-Z0-9]{10})`", texto)
    return list(dict.fromkeys(asins))  # deduplicar, mantener orden


def leer_ultimo_analisis(asin: str) -> dict | None:
    """
    Extrae precio_compra, precio_amazon, roi, score y semaforo
    del análisis más reciente en historial/productos/{ASIN}.md.
    """
    path = HISTORIAL_DIR / "productos" / f"{asin}.md"
    if not path.exists():
        return None

    texto = path.read_text(encoding="utf-8")
    lineas = texto.split("\n")

    # La primera fila de datos está inmediatamente después del separador |------|
    sep_encontrado = False
    for linea in lineas:
        if "|----" in linea:
            sep_encontrado = True
            continue
        if not sep_encontrado or "|" not in linea:
            continue

        # Formato: | YYYY-MM-DD | MX$NNN | MX$NNN | NN.N% | NN | SEMAFORO | ...
        partes = [c.strip() for c in linea.split("|") if c.strip()]
        if len(partes) < 6:
            continue
        try:
            return {
                "fecha":         partes[0],
                "precio_compra": float(partes[1].replace("MX$", "").replace(",", "")),
                "precio_amazon": float(partes[2].replace("MX$", "").replace(",", "")),
                "roi":           float(partes[3].replace("%", "")),
                "score":         int(partes[4]),
                "semaforo":      partes[5],
            }
        except (ValueError, IndexError):
            continue

    return None


def leer_titulo(asin: str) -> str:
    """Lee la primera línea del archivo del ASIN como título."""
    path = HISTORIAL_DIR / "productos" / f"{asin}.md"
    if not path.exists():
        return asin
    try:
        primera = path.read_text(encoding="utf-8").split("\n")[0]
        return primera.lstrip("# ").strip() or asin
    except Exception:
        return asin


# ─────────────────────────────────────────────
# BLOQUE 2 — Consulta PostgreSQL
# ─────────────────────────────────────────────

def obtener_precio_actual(asin: str, engine) -> tuple[float | None, str | None]:
    """
    Retorna (precio_actual, fecha_captura) del registro más reciente
    en la tabla productos de PostgreSQL.
    """
    try:
        sql = text("""
            SELECT precio, fecha_captura
            FROM productos
            WHERE asin = :asin
            ORDER BY fecha_captura DESC
            LIMIT 1
        """)
        with engine.connect() as conn:
            row = conn.execute(sql, {"asin": asin}).fetchone()
        if row and row[0]:
            return float(row[0]), str(row[1])
        return None, None
    except Exception as e:
        print(f"  [bd] {asin}: {type(e).__name__}: {e}")
        return None, None


# ─────────────────────────────────────────────
# BLOQUE 3 — Telegram
# ─────────────────────────────────────────────

def enviar_telegram(mensaje: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("  [telegram] Sin credenciales — alerta solo en consola:")
        print(f"  {mensaje[:300]}")
        return False

    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":    TELEGRAM_CHAT,
        "text":       mensaje,
        "parse_mode": "HTML",
    }).encode()

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
            if ok:
                print("  [telegram] Mensaje enviado OK")
            return ok
    except Exception as e:
        print(f"  [telegram] Error: {e}")
        return False


def formatear_mensaje(asin: str, titulo: str, prev: dict, fin_nuevo: dict,
                       semaforo_nuevo: str, precio_actual: float) -> str:
    precio_prev  = prev["precio_amazon"]
    roi_prev     = prev["roi"]
    roi_nuevo    = fin_nuevo["roi"]
    semaforo_prev = prev["semaforo"]
    cambio_pct   = (precio_actual - precio_prev) / precio_prev * 100

    if semaforo_nuevo == "INVERTIR" and semaforo_prev != "INVERTIR":
        cabecera = "🟢 <b>NUEVA OPORTUNIDAD</b>"
    elif semaforo_nuevo == "DESCARTAR" and semaforo_prev != "DESCARTAR":
        cabecera = "🔴 <b>ALERTA DE RIESGO</b>"
    else:
        cabecera = "🟡 <b>CAMBIO DE SEMÁFORO</b>"

    signo = "↑" if cambio_pct > 0 else "↓"

    return (
        f"{cabecera}\n"
        f"Producto: {titulo[:60]}\n"
        f"ASIN: <code>{asin}</code>\n\n"
        f"Precio {signo}: MX${precio_prev:,.0f} → MX${precio_actual:,.0f} "
        f"({cambio_pct:+.1f}%)\n"
        f"ROI: {roi_prev:.1f}% → {roi_nuevo:.1f}%\n"
        f"Semáforo: {semaforo_prev} → {semaforo_nuevo}\n\n"
        f"📅 {date.today().strftime('%d/%m/%Y')}"
    )


# ─────────────────────────────────────────────
# BLOQUE 4 — Ejecución principal
# ─────────────────────────────────────────────

def ejecutar():
    print(f"\n{'='*50}")
    print("MONITOR DE PRECIOS DIARIO")
    print(f"{'='*50}")
    print(f"  Fecha: {date.today().isoformat()}")

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("  ERROR: DATABASE_URL no configurada")
        return

    engine = create_engine(db_url)

    asins = leer_asins_historial()
    if not asins:
        print("  historial/index.md vacío o no existe — nada que monitorear")
        return
    print(f"  {len(asins)} ASINs en historial\n")

    revisados      = 0
    cambios        = 0
    alertas        = 0

    for asin in asins:
        prev = leer_ultimo_analisis(asin)
        if not prev:
            print(f"  {asin}: sin historial parseado — omitiendo")
            continue

        precio_actual, fecha_bd = obtener_precio_actual(asin, engine)
        if not precio_actual:
            print(f"  {asin}: sin precio en BD — omitiendo")
            continue

        revisados += 1
        precio_prev = prev["precio_amazon"]
        cambio_pct  = abs((precio_actual - precio_prev) / precio_prev * 100)

        if cambio_pct < UMBRAL_CAMBIO_PCT:
            print(f"  {asin}: cambio {cambio_pct:.1f}% < {UMBRAL_CAMBIO_PCT}% — sin alerta")
            continue

        # Recalcular financiero con precio nuevo pero mismo precio_compra
        fin_nuevo = calcular_financiero({
            "precio_amazon": precio_actual,
            "precio_compra": prev["precio_compra"],
            "fees": None,
        })
        if not fin_nuevo:
            continue

        # Usar el score histórico — no tenemos BSR/reviews actualizados
        semaforo_nuevo = asignar_semaforo(fin_nuevo["roi"], prev["score"])
        semaforo_prev  = prev["semaforo"]
        cambios += 1

        print(
            f"  {asin}: precio {precio_prev:.0f}→{precio_actual:.0f} "
            f"({cambio_pct:+.1f}%) | ROI {prev['roi']:.1f}%→{fin_nuevo['roi']:.1f}% "
            f"| {semaforo_prev}→{semaforo_nuevo}"
        )

        # Solo alerta si cambió el semáforo de categoría
        if semaforo_nuevo != semaforo_prev:
            titulo  = leer_titulo(asin)
            mensaje = formatear_mensaje(asin, titulo, prev, fin_nuevo, semaforo_nuevo, precio_actual)
            ok = enviar_telegram(mensaje)
            if ok:
                alertas += 1

    print(f"\n  Revisados: {revisados} | Con cambio >10%: {cambios} | Alertas enviadas: {alertas}")
    print("  Monitor completado.")


if __name__ == "__main__":
    ejecutar()
