"""Versiones que componen la clave del caché de respuestas.

Ver .claude/skills/rag-response-cache/SKILL.md.

Tres de los seis componentes de la clave viven aquí: la versión del corpus, la
del prompt y el modelo. Sin ellos la clave colisiona entre datos viejos y
nuevos, entre reglas de citación derogadas y vigentes, y entre modelos
distintos — y no hay ningún error que lo delate.
"""

from __future__ import annotations

import logging
import time

from google.cloud import bigquery

logger = logging.getLogger("rag_agent.versions")

# ── Versión del prompt ────────────────────────────────────────────────────
#
# Se sube A MANO, en el mismo commit que toque cualquier instrucción de agente
# (router, search, analytics, synthesis). Es el punto frágil del mecanismo: si
# se edita un prompt y esto no sube, el servicio sirve respuestas redactadas
# con las reglas viejas y nada falla visiblemente.
#
# 2026-09-05.1 — versión inicial con validación de citas en código.
# 2026-09-05.2 — topología real (ParallelAgent + SequentialAgent), reglas de
#   delegación explícitas en el router, memory_agent nuevo y descripciones en
#   los cuatro agentes. Cambió el prompt de TODOS: las respuestas cacheadas con
#   la versión anterior se redactaron sin pasar por síntesis.
# 2026-09-05.3 — contexto situacional (fecha de hoy, periodos resueltos y
#   catálogo de canales) inyectado en router, search y analytics; reglas de
#   aclaración reescritas para dejar de pedir fechas en AAAA-MM-DD.
# 2026-09-05.4 — la síntesis por fin RECIBE los resultados: {search_result?} y
#   {analytics_result?} como variables de estado, no como palabras sueltas.
#   Prohibido nombrar agentes, ejemplo de cita con valores reales, y el
#   search_agent distingue "no hay datos" de "nada suficientemente cercano".
# 2026-09-05.5 — sin cifras concretas en el prompt de síntesis (el ejemplo
#   "n=1869" se filtró a una respuesta real), campos numéricos declarados,
#   search_agent manda la pregunta completa en vez de keywords, y
#   trend_detection solo corre bajo petición explícita.
# 2026-09-05.6 — citas visibles y correctas: search_result/analytics_result
#   son los payloads CRUDOS de las herramientas (after_tool_callback), no el
#   texto del modelo que perdía comment_id/channel_name; la síntesis cita solo
#   [comment_id] y el código arma el formato completo con la metadata real.
#   Invalida el caché: las respuestas viejas traían el molde literal.
# 2026-09-05.7 — la forma abstracta "[id]" hizo que la síntesis omitiera las
#   citas por completo (medido post-deploy). Se revierte a la plantilla
#   concreta [comment_id · "video_title" · channel_name · fecha], que sí
#   elicita los corchetes — y ahora el payload crudo trae todos los valores.
#   render_inline_citations queda como red de seguridad para la forma [id].
PROMPT_VERSION = "2026-09-05.7"

# ── Versión del corpus ────────────────────────────────────────────────────
#
# Se LEE del corpus (MAX(updated_at)), nunca se hardcodea: es lo que hace que
# un nuevo run del pipeline de Fase 1 invalide el caché por sí solo.
CORPUS_VERSION_SQL = """
SELECT FORMAT_TIMESTAMP('%Y%m%dT%H%M%SZ', MAX(updated_at)) AS version
FROM `{project}.{dataset}.gold_rag_corpus`
"""

# Escaneo real de una sola columna TIMESTAMP: ~26 KB. El tope general de
# rag-quota-limits sobra.
MAX_BYTES_BILLED = 10 * 1024 * 1024

# El corpus se materializa una vez por semana; releerlo en cada request sería
# una consulta a BigQuery por consulta de usuario, para un valor que casi nunca
# cambia. 5 minutos acota el riesgo de servir caché contra un corpus recién
# actualizado a una ventana irrelevante frente al TTL de 7 días.
CACHE_TTL_SECONDS = 300

_cached: tuple[float, str] | None = None


def get_corpus_version(
    client: bigquery.Client,
    project: str,
    dataset: str,
) -> str | None:
    """Lee MAX(updated_at) de gold_rag_corpus, memoizado 5 minutos.

    Returns:
        La versión como string, o None si no se pudo leer. `None` significa
        "no sé contra qué datos estoy" — quien llama debe SALTARSE el caché,
        no sustituir un valor por defecto: un valor fijo agruparía todas las
        lecturas fallidas en la misma clave y serviría respuestas viejas sobre
        datos nuevos, que es exactamente lo que la versión existe para evitar.
    """
    global _cached

    now = time.monotonic()
    if _cached is not None and now - _cached[0] < CACHE_TTL_SECONDS:
        return _cached[1]

    sql = CORPUS_VERSION_SQL.format(project=project, dataset=dataset)
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)
    try:
        rows = list(client.query(sql, job_config=job_config).result())
    except Exception:
        logger.exception("No se pudo leer la versión del corpus")
        return None

    if not rows or rows[0]["version"] is None:
        logger.warning("gold_rag_corpus sin updated_at — corpus vacío?")
        return None

    version = str(rows[0]["version"])
    _cached = (now, version)
    return version


def reset_cache() -> None:
    """Olvida la versión memoizada. Para tests."""
    global _cached
    _cached = None
