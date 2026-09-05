"""Sanitización de entrada del usuario.

Ver .claude/skills/rag-security-guardrails/SKILL.md.
Antes de que la consulta llegue a ningún prompt: normaliza Unicode NFKC,
elimina caracteres de control (incluidos invisibles usados para ocultar
instrucciones), colapsa espacios y trunca.
"""

from __future__ import annotations

import unicodedata

MAX_QUERY_LENGTH = 500


def sanitize(raw: str) -> str:
    """Normaliza y trunca la entrada del usuario.

    Sanitizar NO convierte la entrada en confiable — solo acota su forma.
    """
    text = unicodedata.normalize("NFKC", raw)
    # Eliminar caracteres de control (category empieza con 'C'), excepto newline
    text = "".join(ch for ch in text if ch == "\n" or not unicodedata.category(ch).startswith("C"))
    # Colapsar espacios por línea (preservando newlines)
    lines = text.split("\n")
    text = "\n".join(" ".join(line.split()) for line in lines)
    return text[:MAX_QUERY_LENGTH]
