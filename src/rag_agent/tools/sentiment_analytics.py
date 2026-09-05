"""Analítica de sentimiento — catálogo cerrado de 5 plantillas SQL.

Ver .claude/skills/rag-tool-sentiment-analytics/SKILL.md.
- Cero SQL libre: el texto del usuario nunca forma parte de una consulta
- Solo plantillas parametrizadas
- maximum_bytes_billed = 10 MB
- Lee exclusivamente de gold_rag_corpus
"""

from __future__ import annotations

from typing import Final

from google.cloud import bigquery

MAX_BYTES_BILLED = 10 * 1024 * 1024  # 10 MB

TEMPLATES: Final[dict[str, str]] = {
    "distribution_by_channel": """
        SELECT sentiment_label, COUNT(*) AS n,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM `{project}.{dataset}.gold_rag_corpus`
        WHERE channel_name = @channel_name
        GROUP BY sentiment_label
        ORDER BY n DESC
    """,
    "distribution_by_period": """
        SELECT sentiment_label, COUNT(*) AS n,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM `{project}.{dataset}.gold_rag_corpus`
        WHERE comment_published_at BETWEEN @date_from AND @date_to
          AND (@channel_name IS NULL OR channel_name = @channel_name)
        GROUP BY sentiment_label
        ORDER BY n DESC
    """,
    "compare_channels": """
        SELECT channel_name, sentiment_label, COUNT(*) AS n,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY channel_name), 1) AS pct
        FROM `{project}.{dataset}.gold_rag_corpus`
        WHERE channel_name IN UNNEST(@channels)
        GROUP BY channel_name, sentiment_label
        ORDER BY channel_name, n DESC
    """,
    "evolution_over_time": """
        SELECT
          FORMAT_TIMESTAMP('%Y-%m', comment_published_at) AS month,
          sentiment_label,
          COUNT(*) AS n
        FROM `{project}.{dataset}.gold_rag_corpus`
        WHERE (@channel_name IS NULL OR channel_name = @channel_name)
          AND (@date_from IS NULL OR comment_published_at >= @date_from)
          AND (@date_to IS NULL OR comment_published_at <= @date_to)
        GROUP BY month, sentiment_label
        ORDER BY month, n DESC
    """,
    "summary_by_video": """
        SELECT sentiment_label, COUNT(*) AS n,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM `{project}.{dataset}.gold_rag_corpus`
        WHERE video_id = @video_id
        GROUP BY sentiment_label
        ORDER BY n DESC
    """,
}


def sentiment_analytics(
    client: bigquery.Client,
    project: str,
    dataset: str,
    query_type: str,
    channel_name: str | None = None,
    video_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    channels: list[str] | None = None,
) -> dict:
    """Calcula métricas agregadas de sentimiento sobre gold_rag_corpus.

    Args:
        client: BigQuery client autenticado.
        project: ID del proyecto GCP.
        dataset: Nombre del dataset Gold.
        query_type: Una de las 5 plantillas permitidas.
        channel_name: Nombre exacto del canal de DJ.
        video_id: ID del video (solo para summary_by_video).
        date_from: Fecha inicial ISO 8601.
        date_to: Fecha final ISO 8601.
        channels: Lista de canales (solo para compare_channels).

    Returns:
        dict con status y resultados.
    """
    if query_type not in TEMPLATES:
        return {
            "status": "error",
            "error": f"query_type no soportado: {query_type}",
            "supported": sorted(TEMPLATES),
        }

    sql = TEMPLATES[query_type].format(project=project, dataset=dataset)

    params = [
        bigquery.ScalarQueryParameter("channel_name", "STRING", channel_name),
        bigquery.ScalarQueryParameter("video_id", "STRING", video_id),
        bigquery.ScalarQueryParameter("date_from", "TIMESTAMP", date_from),
        bigquery.ScalarQueryParameter("date_to", "TIMESTAMP", date_to),
        bigquery.ArrayQueryParameter("channels", "STRING", channels or []),
    ]

    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=MAX_BYTES_BILLED,
        query_parameters=params,
    )

    try:
        results = client.query(sql, job_config=job_config).result()
        rows = [dict(row) for row in results]
        return {"status": "success", "query_type": query_type, "results": rows, "count": len(rows)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
