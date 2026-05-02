# Market Research Multi-Agent System

## Objetivo
Sistema multiagente para análisis de mercado y diferenciación de productos en ecommerce.

## Stack
- Python 3.11+
- pandas, openpyxl, anthropic

## Estructura de datos
- data/raw/       → archivos fuente (Excel, CSV, reseñas Amazon)
- data/processed/ → datasets limpios generados por los agentes
- reports/        → reportes Markdown por fase
- outputs/        → CSV/JSON de salida estructurada

## Agentes
1. Agente_Ingesta_Datos
2. Agente_Analisis_Competencia
3. Agente_Analisis_Resenas
4. Agente_GAP_Analysis
5. Agente_Precio_Valor
6. Agente_Imagenes_Presentacion
7. Agente_Keywords_SEO
8. Agente_Concepto_Diferenciacion
9. Agente_Listado_Optimizado

## Cómo ejecutar
python orchestrator.py --market "nombre del mercado"