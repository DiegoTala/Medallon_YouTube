"""Catálogo de lo que el agente puede responder — para la bienvenida.

Ver .claude/skills/rag-fastapi-service/SKILL.md.

La lista de DJs se LEE del corpus, no se escribe a mano. Dos razones, ambas de
corrección:

- `infra/terraform.tfvars` configura 10 canales, pero solo los que tienen
  comentarios en `gold_rag_corpus` se pueden responder. Anunciar un DJ del que
  no hay datos es prometer lo que no existe, y el agente tendría que contestar
  "no hay comentarios" a algo que él mismo ofreció.
- Cuando el pipeline alcance a los canales que faltan, la bienvenida se entera
  sola. Una lista hardcodeada envejece en silencio.
"""

from __future__ import annotations

import logging
import time

from google.cloud import bigquery

logger = logging.getLogger("rag_agent.catalog")

CHANNELS_SQL = """
SELECT
  channel_name,
  COUNT(*) AS n_comments,
  DATE(MIN(comment_published_at)) AS desde,
  DATE(MAX(comment_published_at)) AS hasta
FROM `{project}.{dataset}.gold_rag_corpus`
WHERE channel_name IS NOT NULL
GROUP BY channel_name
ORDER BY n_comments DESC
"""

# Escaneo real medido: ~79 KB (solo channel_name y comment_published_at).
MAX_BYTES_BILLED = 10 * 1024 * 1024

# El corpus se materializa una vez por semana; una hora de memoización hace que
# el catálogo cueste una consulta por instancia por hora, no una por refresh de
# navegador.
CACHE_TTL_SECONDS = 3600

_cached: tuple[float, list[dict]] | None = None


def get_available_channels(
    client: bigquery.Client,
    project: str,
    dataset: str,
) -> list[dict]:
    """Canales con comentarios en el corpus, de mayor a menor volumen.

    Returns:
        Lista de dicts con channel_name, n_comments, desde y hasta. Lista vacía
        si la consulta falla: la bienvenida se degrada a no listar DJs, que es
        preferible a no cargar.
    """
    global _cached

    now = time.monotonic()
    if _cached is not None and now - _cached[0] < CACHE_TTL_SECONDS:
        return _cached[1]

    sql = CHANNELS_SQL.format(project=project, dataset=dataset)
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)
    try:
        rows = list(client.query(sql, job_config=job_config).result())
    except Exception:
        logger.exception("No se pudo leer el catálogo de canales")
        return []

    canales = [
        {
            "channel_name": r["channel_name"],
            "n_comments": int(r["n_comments"]),
            "desde": str(r["desde"]),
            "hasta": str(r["hasta"]),
        }
        for r in rows
    ]
    _cached = (now, canales)
    return canales


def reset_cache() -> None:
    """Olvida el catálogo memoizado. Para tests."""
    global _cached
    _cached = None
