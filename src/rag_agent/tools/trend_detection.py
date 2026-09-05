"""Detección de tendencias — comparación entre dos periodos.

Ver .claude/skills/rag-tool-trend-detection/SKILL.md.
- Solo bajo demanda explícita (nunca proactiva)
- evidence_level: insufficient (<30), weak (30-99), solid (≥100)
- Catálogo cerrado de métricas
- maximum_bytes_billed = 10 MB
"""

from __future__ import annotations

from google.cloud import bigquery

MAX_BYTES_BILLED = 10 * 1024 * 1024  # 10 MB

VALID_METRICS = {"positive_ratio", "negative_ratio", "comment_volume", "avg_likes"}

TREND_SQL = """
SELECT
  COUNTIF(comment_published_at BETWEEN @current_from  AND @current_to)  AS n_current,
  COUNTIF(comment_published_at BETWEEN @baseline_from AND @baseline_to) AS n_baseline,
  AVG(IF(comment_published_at BETWEEN @current_from AND @current_to,
         IF(sentiment_label = 'positivo', 1.0, 0.0), NULL))            AS current_positive,
  AVG(IF(comment_published_at BETWEEN @baseline_from AND @baseline_to,
         IF(sentiment_label = 'positivo', 1.0, 0.0), NULL))            AS baseline_positive,
  AVG(IF(comment_published_at BETWEEN @current_from AND @current_to,
         IF(sentiment_label = 'negativo', 1.0, 0.0), NULL))            AS current_negative,
  AVG(IF(comment_published_at BETWEEN @baseline_from AND @baseline_to,
         IF(sentiment_label = 'negativo', 1.0, 0.0), NULL))            AS baseline_negative,
  AVG(IF(comment_published_at BETWEEN @current_from AND @current_to,
         CAST(like_count AS FLOAT64), NULL))                            AS current_avg_likes,
  AVG(IF(comment_published_at BETWEEN @baseline_from AND @baseline_to,
         CAST(like_count AS FLOAT64), NULL))                            AS baseline_avg_likes,
  COUNTIF(comment_published_at BETWEEN @current_from AND @current_to)  AS current_volume,
  COUNTIF(comment_published_at BETWEEN @baseline_from AND @baseline_to) AS baseline_volume
FROM `{project}.{dataset}.gold_rag_corpus`
WHERE (@channel_name IS NULL OR channel_name = @channel_name)
  AND comment_published_at BETWEEN @baseline_from AND @current_to;
"""


def _evidence_level(n_current: int, n_baseline: int) -> str:
    """Clasifica el nivel de evidencia según los tamaños de muestra."""
    if n_current < 30 or n_baseline < 30:
        return "insufficient"
    if n_current < 100 or n_baseline < 100:
        return "weak"
    return "solid"


def _get_metric_values(row: dict, metric: str) -> tuple[float | None, float | None]:
    """Extrae los valores current y baseline para la métrica dada."""
    mapping = {
        "positive_ratio": ("current_positive", "baseline_positive"),
        "negative_ratio": ("current_negative", "baseline_negative"),
        "comment_volume": ("current_volume", "baseline_volume"),
        "avg_likes": ("current_avg_likes", "baseline_avg_likes"),
    }
    curr_key, base_key = mapping[metric]
    return row.get(curr_key), row.get(base_key)


def trend_detection(
    client: bigquery.Client,
    project: str,
    dataset: str,
    current_from: str,
    current_to: str,
    baseline_from: str,
    baseline_to: str,
    metric: str,
    channel_name: str | None = None,
) -> dict:
    """Compara una métrica entre dos periodos sobre gold_rag_corpus.

    Args:
        client: BigQuery client autenticado.
        project: ID del proyecto GCP.
        dataset: Nombre del dataset Gold.
        current_from/current_to: Periodo actual ISO 8601.
        baseline_from/baseline_to: Periodo base ISO 8601.
        metric: Una de: positive_ratio, negative_ratio, comment_volume, avg_likes.
        channel_name: Limita a un canal específico.

    Returns:
        dict con status, cambio absoluto, porcentual, dirección, evidence_level.
    """
    if metric not in VALID_METRICS:
        return {
            "status": "error",
            "error": f"Métrica no soportada: {metric}",
            "supported": sorted(VALID_METRICS),
        }

    sql = TREND_SQL.format(project=project, dataset=dataset)
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=MAX_BYTES_BILLED,
        query_parameters=[
            bigquery.ScalarQueryParameter("current_from", "TIMESTAMP", current_from),
            bigquery.ScalarQueryParameter("current_to", "TIMESTAMP", current_to),
            bigquery.ScalarQueryParameter("baseline_from", "TIMESTAMP", baseline_from),
            bigquery.ScalarQueryParameter("baseline_to", "TIMESTAMP", baseline_to),
            bigquery.ScalarQueryParameter("channel_name", "STRING", channel_name),
        ],
    )

    try:
        results = list(client.query(sql, job_config=job_config).result())
        if not results:
            return {"status": "error", "error": "Sin datos para los periodos indicados."}

        row = dict(results[0])
        n_current = row.get("current_volume", 0)
        n_baseline = row.get("baseline_volume", 0)
        evidence = _evidence_level(n_current, n_baseline)

        current_val, baseline_val = _get_metric_values(row, metric)

        if current_val is None:
            return {"status": "error", "error": "No se pudieron calcular los valores para la métrica."}

        if baseline_val is None or baseline_val == 0:
            absolute_change = round(current_val, 4) if baseline_val is None else 0.0
            percent_change = None
            direction = "flat"
        else:
            absolute_change = round(current_val - baseline_val, 4)
            percent_change = round(((current_val - baseline_val) / baseline_val) * 100, 2)
            direction = "up" if absolute_change > 0 else ("down" if absolute_change < 0 else "flat")

        return {
            "status": "success",
            "metric": metric,
            "absolute_change": absolute_change,
            "percent_change": percent_change,
            "direction": direction,
            "evidence_level": evidence,
            "n_current": n_current,
            "n_baseline": n_baseline,
            "periods": {
                "current_from": current_from,
                "current_to": current_to,
                "baseline_from": baseline_from,
                "baseline_to": baseline_to,
            },
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
