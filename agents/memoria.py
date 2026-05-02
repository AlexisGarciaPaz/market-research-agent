# agents/memoria.py
import json
from pathlib import Path
from datetime import datetime

MEMORIA_PATH = Path("outputs/memoria_pipeline.json")

def leer_memoria() -> dict:
    """
    Lee la memoria compartida del pipeline.
    Si no existe todavía, devuelve un dict vacío.
    """
    if not MEMORIA_PATH.exists():
        return {}
    with open(MEMORIA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def escribir_memoria(agente: str, hallazgos: dict):
    """
    Agrega los hallazgos clave de un agente a la memoria compartida.

    Flujo:
    1. Lee lo que escribieron agentes anteriores
    2. Agrega la sección del agente actual
    3. Guarda el archivo actualizado en disco

    Args:
        agente:    Nombre corto del agente (ej: "resenas", "gap_analysis")
        hallazgos: Dict con los datos clave a compartir con agentes posteriores
    """
    memoria = leer_memoria()

    memoria[agente] = {
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "hallazgos": hallazgos
    }

    MEMORIA_PATH.parent.mkdir(exist_ok=True)
    with open(MEMORIA_PATH, "w", encoding="utf-8") as f:
        json.dump(memoria, f, ensure_ascii=False, indent=2)

def obtener_contexto_para_claude() -> str:
    """
    Genera un resumen legible de toda la memoria acumulada hasta ese momento.

    Este string se inyecta al inicio del prompt de Claude en cada agente,
    dándole contexto de lo que decidieron y encontraron los agentes anteriores.

    Ejemplo de lo que Claude verá en gap_analysis:
        [RESENAS] — sentimiento_general: mixto
                  — pain_points_criticos: durabilidad, bateria, microfono
                  — insight_principal: Los clientes valoran...

    Returns:
        String formateado listo para incluir en un prompt de Claude
    """
    memoria = leer_memoria()

    if not memoria:
        return ""  # Primer agente — no hay contexto previo todavía

    secciones = []
    secciones.append("=== CONTEXTO ACUMULADO DE AGENTES ANTERIORES ===")
    secciones.append("Usa este contexto para mantener coherencia con decisiones previas.\n")

    # Orden lógico del pipeline para presentar el contexto en secuencia
    orden = ["resenas", "gap_analysis", "keywords", "concepto", "listado_optimizado"]
    agentes_ordenados = [a for a in orden if a in memoria] + \
                        [a for a in memoria if a not in orden]

    for agente in agentes_ordenados:
        datos = memoria[agente]
        secciones.append(f"[{agente.upper()}] — {datos.get('timestamp', '')}")
        hallazgos = datos.get("hallazgos", {})

        for clave, valor in hallazgos.items():
            if isinstance(valor, list):
                items = valor[:5]  # máximo 5 para no saturar el prompt
                secciones.append(f"  {clave}:")
                for item in items:
                    secciones.append(f"    - {item}")
            elif isinstance(valor, dict):
                secciones.append(f"  {clave}: {json.dumps(valor, ensure_ascii=False)[:200]}")
            else:
                secciones.append(f"  {clave}: {str(valor)[:200]}")

        secciones.append("")  # línea en blanco entre agentes

    secciones.append("=== FIN CONTEXTO ===\n")
    return "\n".join(secciones)

def limpiar_memoria():
    """
    Borra la memoria del pipeline anterior.
    El orchestrator llama esto al inicio de cada ejecución nueva
    para que no se mezclen datos de runs anteriores.
    """
    if MEMORIA_PATH.exists():
        MEMORIA_PATH.unlink()
        print("  OK Memoria del pipeline anterior limpiada")