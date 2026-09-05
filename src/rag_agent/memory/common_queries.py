"""Registro de consultas frecuentes — TTL 180 días.

Ver .claude/skills/rag-memory-common-queries/SKILL.md.
Estructura: users/{user_id}/common_queries/{query_hash}
No almacena respuestas completas — solo consulta, filtros y contador.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from rag_agent.utils.normalize import normalize_query, query_hash

QUERIES_TTL_DAYS = 180


def record_query(
    db: firestore.Client,
    user_id: str,
    raw_query: str,
    filters: dict,
    language: str,
) -> None:
    """Registra o incrementa una consulta frecuente.

    Se llama al ATENDER la consulta (incluyendo hits de caché).
    No se registran consultas rechazadas por security guardrails.
    """
    normalized = normalize_query(raw_query)
    qh = query_hash(normalized, filters, language)
    now = datetime.now(timezone.utc)

    doc_ref = (
        db.collection("users").document(user_id)
        .collection("common_queries").document(qh)
    )
    doc_ref.set({
        "normalized_query": normalized,
        "query_hash": qh,
        "count": firestore.Increment(1),
        "last_used_at": now,
        "expires_at": now + timedelta(days=QUERIES_TTL_DAYS),
        "filters": filters,
        "language": language,
    }, merge=True)


def get_common_queries(
    db: firestore.Client, user_id: str, limit: int = 10
) -> list[dict]:
    """Retorna las consultas más frecuentes del usuario."""
    now = datetime.now(timezone.utc)
    queries_ref = (
        db.collection("users").document(user_id)
        .collection("common_queries")
        .where("expires_at", ">", now)
        .order_by("count", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [doc.to_dict() for doc in queries_ref.stream()]
