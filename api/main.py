# api/main.py
import sys
import os
import json
import uuid
import queue
import threading
import asyncio
from pathlib import Path

# Set working directory to project root so agents find data/ outputs/ etc.
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from anthropic import Anthropic
from agents import (
    ingesta, competencia, resenas, gap_analysis,
    precio_valor, keywords, concepto, listado_optimizado
)
from agents.memoria import limpiar_memoria, leer_memoria
from agents.validador import ejecutar as ejecutar_validador

app = FastAPI(title="Market Research Validator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job storage (resets on restart — OK for MVP)
jobs: dict = {}

# Semaphore: one pipeline at a time per instance
_pipeline_lock = threading.Semaphore(1)


class ValidarRequest(BaseModel):
    producto: str
    precio_compra: float
    unidades: int = 1


def detectar_mercado(producto: str) -> str:
    client = Anthropic()
    respuesta = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=50,
        system=(
            "Responde SOLO con el nombre del nicho de mercado en 1-3 palabras en espanol. "
            "Ejemplos: suplementos, electrodomesticos, ropa deportiva, miel y mermeladas, "
            "snacks saludables, productos de limpieza. Sin puntuacion ni explicacion."
        ),
        messages=[{"role": "user", "content": f"Nicho de Amazon para: {producto}"}]
    )
    return respuesta.content[0].text.strip()


def ejecutar_pipeline(
    job_id: str,
    producto: str,
    precio_compra: float,
    unidades: int,
    q: queue.Queue,
):
    def prog(step: int, agente: str, mensaje: str, status: str = "running"):
        q.put({
            "type": "progress",
            "step": step,
            "total": 9,
            "agent": agente,
            "message": mensaje,
            "status": status,
        })

    acquired = _pipeline_lock.acquire(timeout=5)
    if not acquired:
        q.put({"type": "error", "message": "Servidor ocupado. Intenta en 30 segundos."})
        return

    try:
        # Step 0 — detect market
        prog(0, "Detector de nicho", "Identificando nicho de mercado...", "running")
        mercado = detectar_mercado(producto)
        prog(0, "Detector de nicho", f"Nicho: {mercado}", "done")

        limpiar_memoria()

        pasos = [
            (1, "Ingesta de datos",            lambda: ingesta.ejecutar(mercado)),
            (2, "Analisis de competencia",     lambda: competencia.ejecutar(mercado)),
            (3, "Analisis de resenas",         lambda: resenas.ejecutar(mercado)),
            (4, "GAP Analysis",                lambda: gap_analysis.ejecutar(mercado)),
            (5, "Precio vs Valor",             lambda: precio_valor.ejecutar(mercado)),
            (6, "Keywords y SEO",              lambda: keywords.ejecutar(mercado)),
            (7, "Concepto de diferenciacion",  lambda: concepto.ejecutar(mercado)),
            (8, "Listado optimizado",          lambda: listado_optimizado.ejecutar(mercado)),
            (9, "Validacion de arbitraje",     lambda: ejecutar_validador(producto, precio_compra, unidades, mercado)),
        ]

        resultados = {}
        for step, nombre, funcion in pasos:
            prog(step, nombre, f"Analizando {nombre.lower()}...", "running")
            try:
                resultados[nombre] = funcion()
                prog(step, nombre, nombre, "done")
            except Exception as e:
                prog(step, nombre, f"Error: {str(e)[:60]}", "error")
                resultados[nombre] = None

        # Build final result from memory
        mem = leer_memoria()
        validador_mem  = mem.get("validador",          {}).get("hallazgos", {})
        listado_mem    = mem.get("listado_optimizado", {}).get("hallazgos", {})
        concepto_mem   = mem.get("concepto",           {}).get("hallazgos", {})
        keywords_mem   = mem.get("keywords",           {}).get("hallazgos", {})

        validador_full = resultados.get("Validacion de arbitraje") or {}

        final = {
            "mercado":           mercado,
            "producto":          producto,
            "precio_compra_mx":  precio_compra,
            "unidades":          unidades,
            "veredicto":         validador_mem.get("veredicto", ""),
            "score_oportunidad": validador_mem.get("score_oportunidad", 0),
            "roi_estimado_pct":  validador_mem.get("roi_estimado_pct", 0),
            "precio_venta_recomendado_mx": validador_mem.get("precio_venta_recomendado_mx", 0),
            "ganancia_por_unidad_mx":      validador_full.get("ganancia_por_unidad_mx", 0),
            "ganancia_total_estimada_mx":  validador_full.get("ganancia_total_estimada_mx", 0),
            "referral_fee_mx":             validador_full.get("referral_fee_mx", 0),
            "fba_fee_estimado_mx":         validador_full.get("fba_fee_estimado_mx", 0),
            "tiempo_recuperacion":         validador_full.get("tiempo_recuperacion_estimado", ""),
            "razon_principal":             validador_full.get("razon_principal", ""),
            "resumen_ejecutivo":           validador_full.get("resumen_ejecutivo", ""),
            "riesgos":                     validador_full.get("riesgos", []),
            "acciones_inmediatas":         validador_full.get("acciones_inmediatas", []),
            "listing": {
                "titulo":              listado_mem.get("titulo", ""),
                "precio_lanzamiento":  listado_mem.get("precio_lanzamiento_mx", 0),
                "precio_objetivo":     listado_mem.get("precio_objetivo_mx", 0),
                "terminos_backend":    listado_mem.get("terminos_backend", []),
                "top_bullets":         listado_mem.get("top_3_bullets", []),
            },
            "concepto": {
                "nombre":          concepto_mem.get("nombre_concepto", ""),
                "tagline":         concepto_mem.get("tagline", ""),
                "mensaje_central": concepto_mem.get("mensaje_central", ""),
            },
            "keyword_principal": keywords_mem.get("keyword_principal", ""),
        }

        jobs[job_id]["result"] = final
        jobs[job_id]["status"] = "done"
        q.put({"type": "done", "result": final})

    except Exception as e:
        jobs[job_id]["status"] = "error"
        q.put({"type": "error", "message": str(e)})
    finally:
        _pipeline_lock.release()


@app.post("/validar")
async def iniciar_validacion(request: ValidarRequest):
    if not request.producto.strip():
        raise HTTPException(400, "El nombre del producto es requerido")
    if request.precio_compra <= 0:
        raise HTTPException(400, "El precio de compra debe ser mayor a 0")

    job_id = str(uuid.uuid4())
    q: queue.Queue = queue.Queue()
    jobs[job_id] = {"queue": q, "result": None, "status": "pending"}

    threading.Thread(
        target=ejecutar_pipeline,
        args=(job_id, request.producto.strip(), request.precio_compra, request.unidades, q),
        daemon=True,
    ).start()

    return {"job_id": job_id}


@app.get("/stream/{job_id}")
async def stream_progreso(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")

    q = jobs[job_id]["queue"]

    async def generate():
        while True:
            try:
                msg = q.get(timeout=0.3)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("type") in ("done", "error"):
                    break
            except queue.Empty:
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.2)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/resultado/{job_id}")
async def obtener_resultado(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job no encontrado")
    job = jobs[job_id]
    return {"status": job["status"], "result": job.get("result")}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
