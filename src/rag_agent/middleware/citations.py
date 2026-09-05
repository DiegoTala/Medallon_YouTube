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


def valid_comment_ids(tool_payloads: Iterable[tuple[str, dict]]) -> set[str]:
    """Reúne los comment_id que las herramientas devolvieron realmente."""
    ids: set[str] = set()
    for _name, payload in tool_payloads:
        if payload.get("status") != "success":
            continue
        for row in payload.get("results") or []:
            if isinstance(row, dict) and row.get("comment_id"):
                ids.add(str(row["comment_id"]))
    return ids


def extract_cited_ids(response_text: str) -> set[str]:
    """Extrae los identificadores citados en el texto de la respuesta."""
    return {m.group(1) for m in CITATION_RE.finditer(response_text)}


def validate_citations(
    response_text: str,
    tool_payloads: Iterable[tuple[str, dict]],
) -> tuple[bool, list[str], list[str]]:
    """Verifica que toda cita corresponda a un resultado real de herramienta.

    Returns:
        (ok, citas_validas, citas_inventadas). `ok` es False solo cuando hay al
        menos una cita que no existe en los resultados: una respuesta sin citas
        (p. ej. "no hay datos sobre eso") es válida — que falten citas donde
        debería haberlas es un problema de calidad que mide rag-evaluation-suite,
        no una alucinación que debamos bloquear aquí.
    """
    payloads = list(tool_payloads)
    reales = valid_comment_ids(payloads)
    citadas = extract_cited_ids(response_text)

    validas = sorted(citadas & reales)
    inventadas = sorted(citadas - reales)

    if inventadas:
        logger.error(
            "Citas sin evidencia: %s (reales disponibles: %d)",
            inventadas,
            len(reales),
        )

    return (not inventadas), validas, inventadas


def tools_used(tool_payloads: Iterable[tuple[str, dict]]) -> list[str]:
    """Nombres de las herramientas que efectivamente corrieron."""
    return sorted({name for name, _ in tool_payloads if name})
