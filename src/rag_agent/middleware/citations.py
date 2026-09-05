"""Validación de citas — en código, contra los resultados reales de las tools.

Ver .claude/skills/rag-synthesis-citations/SKILL.md.

El invariante del PRD Fase 2 §13 ("ninguna respuesta con datos sin cita, y
ninguna cita sin evidencia") no lo puede sostener un prompt. El synthesis_agent
puede inventar un comment_id con total confianza y no hay nada en su salida que
distinga uno inventado de uno real. La única verificación posible es comparar
contra lo que las herramientas devolvieron de verdad.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

logger = logging.getLogger("rag_agent.citations")

# Formato de cita de rag-synthesis-citations:
#   [comment_id · "título del video" · canal · fecha · URL]
# Los comment_id de YouTube son opacos (base64 URL-safe, típicamente >20 chars).
# El separador puede venir como '·' o, si el modelo lo degrada, como '|' o '-'.
CITATION_RE = re.compile(r"\[\s*([A-Za-z0-9_.\-]{8,})\s*(?:·|\||—|–)")

MENSAJE_DEGRADADO = (
    "No puedo entregar esta respuesta: incluía citas que no corresponden a "
    "ningún comentario de los datos consultados. Reformula la pregunta o "
    "pídeme que busque de nuevo."
)


def collect_tool_payloads(event: Any) -> list[tuple[str, dict]]:
    """Extrae los (nombre, respuesta) de las tools de un evento de ADK.

    Defensivo a propósito: la forma de los eventos de ADK cambia entre
    versiones, y una respuesta sin validar es peor que una excepción aquí.
    """
    payloads: list[tuple[str, dict]] = []
    content = getattr(event, "content", None)
    for part in getattr(content, "parts", None) or []:
        fr = getattr(part, "function_response", None)
        if fr is None:
            continue
        response = getattr(fr, "response", None)
        if isinstance(response, dict):
            payloads.append((getattr(fr, "name", "") or "", response))
    return payloads


# Campos que viajan a la UI y al historial por cada cita. Son los que
# rag-synthesis-citations exige para el formato
# [comment_id · "título del video" · canal · fecha · URL].
CAMPOS_CITA = (
    "comment_id",
    "video_title",
    "channel_name",
    "video_url",
    "comment_published_at",
)


def evidence_index(tool_payloads: Iterable[tuple[str, dict]]) -> dict[str, dict]:
    """Indexa por comment_id los resultados REALES de las herramientas.

    Es a la vez la evidencia contra la que se validan las citas y la fuente de
    su metadata: la cita que se le entrega a la UI se arma con esta fila, nunca
    con lo que el modelo escribió. El modelo elige QUÉ citar; de CÓMO se ve esa
    cita se encarga el código.
    """
    index: dict[str, dict] = {}
    for _name, payload in tool_payloads:
        if payload.get("status") != "success":
            continue
        for row in payload.get("results") or []:
            if not isinstance(row, dict) or not row.get("comment_id"):
                continue
            cid = str(row["comment_id"])
            index.setdefault(cid, {
                campo: ("" if row.get(campo) is None else str(row[campo]))
                for campo in CAMPOS_CITA
            })
    return index


def valid_comment_ids(tool_payloads: Iterable[tuple[str, dict]]) -> set[str]:
    """Reúne los comment_id que las herramientas devolvieron realmente."""
    return set(evidence_index(tool_payloads))


def extract_cited_ids(response_text: str) -> set[str]:
    """Extrae los identificadores citados en el texto de la respuesta."""
    return {m.group(1) for m in CITATION_RE.finditer(response_text)}


def validate_citations(
    response_text: str,
    tool_payloads: Iterable[tuple[str, dict]],
) -> tuple[bool, list[dict], list[str]]:
    """Verifica que toda cita corresponda a un resultado real de herramienta.

    Returns:
        (ok, citas, citas_inventadas), donde `citas` son objetos con la
        metadata real de cada comentario citado — listos para la UI y para el
        historial — y `citas_inventadas` son los identificadores citados que no
        existen en ningún resultado.

        `ok` es False solo cuando hay al menos una cita inventada. Una
        respuesta sin citas (p. ej. "no hay datos sobre eso") es válida:
        admitir ausencia de evidencia es la conducta correcta. Que falten citas
        donde debería haberlas es calidad, y eso lo mide rag-evaluation-suite.
    """
    payloads = list(tool_payloads)
    index = evidence_index(payloads)
    citadas = extract_cited_ids(response_text)

    citas = [index[cid] for cid in sorted(citadas & set(index))]
    inventadas = sorted(citadas - set(index))

    if inventadas:
        logger.error(
            "Citas sin evidencia: %s (reales disponibles: %d)",
            inventadas,
            len(index),
        )

    return (not inventadas), citas, inventadas


def tools_used(tool_payloads: Iterable[tuple[str, dict]]) -> list[str]:
    """Nombres de las herramientas que efectivamente corrieron."""
    return sorted({name for name, _ in tool_payloads if name})


# ── Qué NO se cachea ──────────────────────────────────────────────────────

EVIDENCIA_NO_CACHEABLE = frozenset({"insufficient", "weak"})


def es_cacheable(tool_payloads: Iterable[tuple[str, dict]]) -> bool:
    """False si alguna herramienta reportó evidencia insuficiente o débil.

    Una conclusión sostenida por 6 comentarios puede cambiar por completo con
    la corrida del pipeline del lunes. Congelarla 7 días en el caché la vuelve
    la respuesta permanente a esa pregunta, y la versión del corpus no alcanza:
    invalida cuando el corpus cambia, pero aquí el punto es que la respuesta era
    frágil desde el principio.

    Ver rag-response-cache, "Qué no se cachea".
    """
    for _name, payload in tool_payloads:
        if payload.get("status") != "success":
            return False
        if payload.get("evidence_level") in EVIDENCIA_NO_CACHEABLE:
            return False
    return True


# ── Validación numérica ───────────────────────────────────────────────────
#
# Las citas de comentario se validan por comment_id. Las de analítica se
# validan por su `n`, y hacía falta: el modelo reportó "ILLENIUM (n=1869)"
# cuando ILLENIUM tiene 292 comentarios — copió el número del EJEMPLO que
# traía el prompt de síntesis. La respuesta salió convincente, con su
# advertencia sobre tamaños de muestra y todo, y las cifras eran falsas.
#
# Una respuesta persuasiva y equivocada es peor que una evasiva, y ningún
# prompt lo impide de forma confiable: el ejemplo mismo era la fuente del
# error. Esto sí lo impide.

# Solo se valida el `n=` del formato de cita que el prompt exige. Es
# deliberadamente estrecho: alto valor y casi sin falsos positivos. Otras
# cifras (porcentajes redondeados, cambios derivados, fechas) darían falsas
# alarmas y acabarían degradando respuestas correctas — que es la forma de
# que un control termine apagado.
N_CITADO_RE = re.compile(r"\bn\s*=\s*([\d.,]+)", re.IGNORECASE)

MENSAJE_NUMEROS = (
    "No puedo entregar esta respuesta: incluía cifras que no corresponden a "
    "los datos consultados. Vuelve a preguntar, por favor."
)


def _a_entero(texto: str) -> int | None:
    """'1,869' y '1.869' son el mismo número escrito por locales distintos."""
    limpio = texto.replace(",", "").replace(".", "").strip()
    return int(limpio) if limpio.isdigit() else None


def sample_sizes_reales(tool_payloads: Iterable[tuple[str, dict]]) -> set[int]:
    """Todos los tamaños de muestra que las herramientas reportaron de verdad."""
    reales: set[int] = set()
    for _name, payload in tool_payloads:
        if payload.get("status") != "success":
            continue

        for valor in (payload.get("sample_sizes") or {}).values():
            if isinstance(valor, int):
                reales.add(valor)

        # trend_detection reporta sus dos periodos por separado.
        for clave in ("n_current", "n_baseline"):
            if isinstance(payload.get(clave), int):
                reales.add(payload[clave])

        # El `n` de cada fila de una distribución, y el conteo de resultados.
        for fila in payload.get("results") or []:
            if isinstance(fila, dict) and isinstance(fila.get("n"), int):
                reales.add(fila["n"])
        if isinstance(payload.get("count"), int):
            reales.add(payload["count"])

    return reales


def validate_numeric_claims(
    response_text: str,
    tool_payloads: Iterable[tuple[str, dict]],
) -> tuple[bool, list[int]]:
    """Verifica que todo `n=` citado exista en los resultados reales.

    Returns:
        (ok, inventados). Una respuesta sin ningún `n=` pasa: no todas las
        respuestas son numéricas, y exigir citas donde no aplica sería
        degradar respuestas correctas.
    """
    payloads = list(tool_payloads)
    reales = sample_sizes_reales(payloads)

    citados = {
        n for m in N_CITADO_RE.finditer(response_text)
        if (n := _a_entero(m.group(1))) is not None
    }
    inventados = sorted(citados - reales)

    if inventados:
        logger.error(
            "Cifras sin respaldo: n=%s (reales: %s)",
            inventados, sorted(reales),
        )

    return (not inventados), inventados
