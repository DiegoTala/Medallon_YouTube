"""Normalización de consultas y generación de hashes.

Compartida entre rag-response-cache y rag-memory-common-queries.
Ver .claude/skills/rag-memory-common-queries/SKILL.md.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata


def normalize_query(text: str) -> str:
    """Normaliza una consulta: NFKC, strip, lowercase, colapsa espacios."""
    text = unicodedata.normalize("NFKC", text).strip().lower()
    return " ".join(text.split())


def query_hash(normalized: str, filters: dict, language: str) -> str:
    """Genera un hash determinístico para una consulta + filtros + idioma.

    Usado por common_queries (no incluye versiones de corpus/prompt/modelo).
    """
    payload = json.dumps(
        {"q": normalized, "f": filters, "l": language},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_key(
    normalized_query: str,
    filters: dict,
    language: str,
    corpus_version: str,
    prompt_version: str,
    model: str,
    user_id: str | None = None,
) -> str:
    """Genera la clave de caché exacto (6 componentes + user_id opcional).

    Ver .claude/skills/rag-response-cache/SKILL.md.
    """
    payload = json.dumps(
        {
            "q": normalized_query,
            "f": filters,
            "l": language,
            "corpus": corpus_version,
            "prompt": prompt_version,
            "model": model,
            "u": user_id,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
