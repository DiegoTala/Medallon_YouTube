"""Analítica de sentimiento — catálogo cerrado de 5 plantillas SQL.

Ver .claude/skills/rag-tool-sentiment-analytics/SKILL.md.
- Cero SQL libre: el texto del usuario nunca forma parte de una consulta
- Solo plantillas parametrizadas
- maximum_bytes_billed = 10 MB
- Todo resultado lleva evidence_level y sample_sizes
- Lee exclusivamente de gold_rag_corpus
"""

from __future__ import annotations

from typing import Final

from google.cloud import bigquery

from rag_agent.tools.evidence import evidence_level

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
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    return {
        "status": "success",
        "query_type": query_type,
        "results": rows,
        "count": len(rows),
        **_evidencia(query_type, rows),
    }


def _evidencia(query_type: str, rows: list[dict]) -> dict:
    """Tamaños de muestra y nivel de evidencia de un resultado agregado.

    Un porcentaje sin su n es una cifra sin significado: "84.4% positivo" sobre
    90 comentarios y sobre 6 se leen igual y no valen lo mismo. Ver
    rag_agent.tools.evidence.
    """
    if not rows:
        return {"evidence_level": "insufficient", "sample_sizes": {}}

    if query_type == "compare_channels":
        # El nivel lo marca el canal con menos datos: una comparación vale lo
        # que vale su lado más flaco.
        por_canal: dict[str, int] = {}
        for r in rows:
            canal = r.get("channel_name")
            if canal is not None:
                por_canal[canal] = por_canal.get(canal, 0) + int(r.get("n") or 0)
        return {
            "evidence_level": evidence_level(*por_canal.values()),
            "sample_sizes": por_canal,
        }

    if query_type == "evolution_over_time":
        # Cada mes es una observación independiente; el mes más flaco manda.
        por_mes: dict[str, int] = {}
        for r in rows:
            mes = r.get("month")
            if mes is not None:
                por_mes[mes] = por_mes.get(mes, 0) + int(r.get("n") or 0)
        return {
            "evidence_level": evidence_level(*por_mes.values()),
            "sample_sizes": por_mes,
        }

    total = sum(int(r.get("n") or 0) for r in rows)
    return {"evidence_level": evidence_level(total), "sample_sizes": {"total": total}}
