---
name: rag-tool-sentiment-analytics
description: Contrato de la herramienta sentiment_analytics — catálogo cerrado de cinco plantillas SQL parametrizadas sobre gold_rag_corpus, sin generación de SQL libre. Úsalo al escribir o modificar esta herramienta, o al agregar una plantilla nueva.
---

# rag-tool-sentiment-analytics

## Alcance

Responder preguntas cuantitativas de sentimiento (PRD Fase 2 §7) mediante un **catálogo cerrado de plantillas**. Esta herramienta nunca construye SQL a partir de texto del usuario ni de salida del modelo.

## El catálogo (cinco plantillas, PRD §7)

| `query_type` | Pregunta que responde | Parámetros |
| :--- | :--- | :--- |
| `distribution_by_channel` | Distribución de sentimiento de un canal | `channel_name` |
| `distribution_by_period` | Distribución en un rango de fechas | `date_from`, `date_to`, `channel_name?` |
| `compare_channels` | Comparación entre dos o más canales | `channels[]` |
| `evolution_over_time` | Evolución temporal por mes | `channel_name?`, `date_from?`, `date_to?` |
| `summary_by_video` | Resumen de un video | `video_id` |

Cualquier pregunta que no encaje en una de estas cinco **no se responde improvisando SQL**: se responde diciendo que esa analítica no está disponible. Ver [[rag-synthesis-citations]] para la forma de esa respuesta.

## Por qué el catálogo es cerrado

El PRD pone Text-to-SQL libre explícitamente fuera de alcance (§4), y por buenas razones acumuladas: la service account tiene lectura sobre Gold, así que un SQL generado por el modelo es un SQL escrito por texto que vino del usuario. Además, `maximum_bytes_billed` protege el costo pero no la corrección — una consulta generada puede ser barata y aun así estar mal, y el usuario recibiría un número inventado con apariencia de dato.

Con plantillas, el modelo solo elige **cuál** y **con qué parámetros**; la forma del SQL es código revisado.

## Implementación

```python
from typing import Final
from google.cloud import bigquery

_TEMPLATES: Final[dict[str, str]] = {
    "distribution_by_channel": """
        SELECT sentiment_label, COUNT(*) AS n,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM `{corpus}`
        WHERE channel_name = @channel_name
        GROUP BY sentiment_label
        ORDER BY n DESC
    """,
    # ... las otras cuatro
}

def sentiment_analytics(
    query_type: str,
    channel_name: str | None = None,
    video_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Calcula métricas agregadas de sentimiento sobre los comentarios en Gold.

    Args:
        query_type (str): Una de: distribution_by_channel, distribution_by_period,
            compare_channels, evolution_over_time, summary_by_video.
        channel_name (str | None): Nombre exacto del canal de DJ.
        video_id (str | None): ID del video, solo para summary_by_video.
        date_from (str | None): Fecha inicial ISO 8601.
        date_to (str | None): Fecha final ISO 8601.
    """
    if query_type not in _TEMPLATES:
        return {"status": "error",
                "error": f"query_type no soportado: {query_type}",
                "supported": sorted(_TEMPLATES)}
    ...
```

El rechazo de un `query_type` desconocido devuelve `status: "error"` con la lista de los soportados — no lanza excepción ni intenta el más parecido. Adivinar la intención aquí produce el número correcto para la pregunta equivocada.

## Validación estricta de parámetros

Antes de ejecutar, cada plantilla valida **sus** parámetros:

- `channel_name` debe existir en el corpus (lista cacheada de los canales conocidos; no se acepta un canal arbitrario).
- `date_from` / `date_to` deben parsear como fecha ISO 8601 y cumplir `date_from <= date_to`.
- `video_id` debe cumplir la forma de un ID de YouTube antes de tocar BigQuery.
- Todo parámetro faltante que la plantilla requiere → `status: "error"`, nunca un `NULL` que silenciosamente devuelva el agregado global.

Ese último punto es el que más fácil se rompe: una plantilla de canal con `channel_name = NULL` y un `WHERE` mal escrito devuelve la distribución de **los diez canales** presentada como si fuera la de uno.

## Invariantes

- **Cero SQL libre.** El texto del usuario nunca llega a formar parte de una consulta, ni siquiera "sanitizado".
- **Catálogo cerrado.** Agregar una plantilla es un cambio de código revisado, con su prueba en [[rag-evaluation-suite]] — no algo que el agente pueda hacer en tiempo de ejecución.
- **Parámetros por `ScalarQueryParameter`**, jamás por interpolación. El único `{corpus}` interpolado es una constante de configuración, nunca entrada del usuario.
- **`maximum_bytes_billed` en todas las plantillas** — ver [[rag-quota-limits]].
- **Solo lee [[gold-rag-corpus]].** Ninguna plantilla referencia Bronze, Silver ni la DLQ, ni siquiera para "enriquecer" un resultado.
- **Exactitud verificable:** cada plantilla tiene al menos una pregunta dorada con resultado numérico esperado en [[rag-evaluation-suite]] (meta del PRD §13: ≥90% de exactitud numérica).

## Relación con otros skills

- Lee exclusivamente de [[gold-rag-corpus]].
- La invoca `analytics_agent`, junto con [[rag-tool-trend-detection]] — ver [[rag-agent-topology]].
- Las etiquetas válidas de sentimiento vienen del catálogo de [[gold-sentiment-analysis]].
- La prohibición de SQL libre es un invariante compartido con [[rag-security-guardrails]].
