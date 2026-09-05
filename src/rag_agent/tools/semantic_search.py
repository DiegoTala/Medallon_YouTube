"""Búsqueda semántica sobre gold_rag_corpus con VECTOR_SEARCH.

Ver .claude/skills/rag-tool-semantic-search/SKILL.md.
- top_k ≤ 20 (tope duro en código, no solo documentado)
- maximum_bytes_billed = 50 MB (excepción documentada en rag-quota-limits)
- Mismo modelo de embedding que el corpus (text-embedding-004)
- Cero interpolación de strings en SQL
"""

from __future__ import annotations

import logging
import os

from google.cloud import bigquery

logger = logging.getLogger("rag_agent.semantic_search")

MAX_TOP_K = 20

# ── Umbral de relevancia ──────────────────────────────────────────────────
#
# VECTOR_SEARCH SIEMPRE devuelve top_k filas, tengan o no que ver con la
# consulta. Con un corpus de 3,261 comentarios eso es la principal fuente de
# malas respuestas: preguntar por un DJ que no está devuelve los 5 comentarios
# "menos lejanos", y el modelo tiene que rescatar una recuperación mala —
# de ahí salen las respuestas evasivas del tipo "hay admiración general, pero
# no menciones específicas".
#
# Calibrado el 2026-09-05 con seis consultas reales contra el corpus:
#
#   drops de Martin Garrix      (en corpus)     0.224 – 0.280
#   el mejor set en vivo        (en corpus)     0.178 – 0.307
#   los sets de Tiesto          (DJ ausente)    0.379 – 0.411
#   recetas de cocina italiana  (fuera dominio) 0.422 – 0.553
#   drops de Fisher             (DJ ausente)    0.496 – 0.526
#   declarar impuestos          (fuera dominio) 0.509 – 0.575
#
# Hueco limpio entre 0.31 y 0.38. El corte va en 0.35: deja pasar todo lo
# relevante medido y descarta todo lo irrelevante medido.
#
# Es una calibración con seis consultas, no una validación: el número es
# configurable y cuando el filtro descarta TODO se registra en el log, para
# poder ajustarlo con casos reales en vez de con intuición. Al regenerar el
# corpus con otro modelo de embedding, recalibrar — las distancias no son
# comparables entre modelos.
MAX_DISTANCE = float(os.environ.get("SEARCH_MAX_DISTANCE", "0.35"))
# Excepción al tope general de 10 MB de rag-quota-limits.
#
# VECTOR_SEARCH en modo exhaustivo (el corpus está por debajo de las 5,000 filas
# que BigQuery exige para un índice vectorial) debe leer la columna
# `text_embedding` completa: 3,261 filas x 768 floats = ~20 MB. Medido con
# `bq query --dry_run` el 2026-09-05: 20,856,549 bytes.
#
# No es "le falta un filtro": ningún WHERE reduce el escaneo de una búsqueda
# vectorial exhaustiva. Con el tope de 10 MB BigQuery rechazaba TODA consulta
# semántica ("Query exceeded limit for bytes billed"), que es como estaba el
# servicio en producción.
#
# 50 MB = ~2.4x el corpus actual, margen de ~9 meses al ritmo de +125
# comentarios/semana. Sigue siendo un guardrail real: acota el peor caso a
# 2,700 consultas/mes x 50 MB = 132 GB = ~$0.83 USD/mes.
# Revisar este valor cuando el corpus pase de 5,000 filas y el índice vectorial
# sea creable — ahí el escaneo baja y el tope puede volver a bajar.
MAX_BYTES_BILLED = 50 * 1024 * 1024  # 50 MB

SEARCH_SQL = """
WITH query_embedding AS (
  SELECT ml_generate_embedding_result AS embedding
  FROM ML.GENERATE_EMBEDDING(
    MODEL `{project}.{dataset}.embedding_model`,
    (SELECT @query AS content)
  )
)
SELECT
  base.comment_id,
  base.comment_text,
  base.video_id,
  base.video_title,
  base.channel_name,
  base.comment_published_at,
  base.sentiment_label,
  base.like_count,
  base.video_url,
  distance
FROM VECTOR_SEARCH(
  TABLE `{project}.{dataset}.gold_rag_corpus`,
  'text_embedding',
  (SELECT embedding FROM query_embedding),
  top_k => @top_k,
  distance_type => 'COSINE'
)
WHERE (@channel_name    IS NULL OR base.channel_name    = @channel_name)
  AND (@sentiment_label IS NULL OR base.sentiment_label  = @sentiment_label)
  AND (@date_from       IS NULL OR base.comment_published_at >= @date_from)
  AND (@date_to         IS NULL OR base.comment_published_at <= @date_to)
ORDER BY distance;
"""


def semantic_search(
    client: bigquery.Client,
    project: str,
    dataset: str,
    query: str,
    top_k: int = 10,
    channel_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sentiment_label: str | None = None,
) -> dict:
    """Busca comentarios semánticamente similares a una consulta.

    Args:
        client: BigQuery client autenticado.
        project: ID del proyecto GCP.
        dataset: Nombre del dataset Gold.
        query: Texto de búsqueda en lenguaje natural.
        top_k: Cuántos comentarios devolver (máximo 20).
        channel_name: Limita la búsqueda a un canal de DJ.
        date_from: Fecha inicial ISO 8601 del comentario.
        date_to: Fecha final ISO 8601 del comentario.
        sentiment_label: Filtra por etiqueta de sentimiento.

    Returns:
        dict con status y lista de resultados.
    """
    top_k = min(max(top_k, 1), MAX_TOP_K)

    sql = SEARCH_SQL.format(project=project, dataset=dataset)
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=MAX_BYTES_BILLED,
        query_parameters=[
            bigquery.ScalarQueryParameter("query", "STRING", query),
            bigquery.ScalarQueryParameter("top_k", "INT64", top_k),
            bigquery.ScalarQueryParameter("channel_name", "STRING", channel_name),
            bigquery.ScalarQueryParameter("date_from", "TIMESTAMP", date_from),
            bigquery.ScalarQueryParameter("date_to", "TIMESTAMP", date_to),
            bigquery.ScalarQueryParameter("sentiment_label", "STRING", sentiment_label),
        ],
    )

    try:
        results = client.query(sql, job_config=job_config).result()
        rows = [dict(row) for row in results]
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    # Filtro de relevancia: convierte "cinco coincidencias flojas" en "no hay
    # datos", que es la respuesta honesta y la que el agente sabe dar bien.
    relevantes = [r for r in rows if r.get("distance") is not None
                  and r["distance"] <= MAX_DISTANCE]

    if rows and not relevantes:
        logger.info(
            "Todos los resultados sobre el umbral %.2f (mejor: %.4f) para: %r",
            MAX_DISTANCE, min(r["distance"] for r in rows), query[:80],
        )

    return {
        "status": "success",
        "results": relevantes,
        "count": len(relevantes),
        # Para que la síntesis pueda decir "no hay nada suficientemente
        # cercano" en vez de "no hay nada": son cosas distintas.
        "descartados_por_relevancia": len(rows) - len(relevantes),
    }
