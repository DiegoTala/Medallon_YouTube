"""Caché exacto de respuestas en Firestore.

Ver .claude/skills/rag-response-cache/SKILL.md.
Clave compuesta con 6 componentes + user_id opcional (para respuestas
personalizadas por preferencias). TTL de 7 días.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from rag_agent.utils.normalize import cache_key

CACHE_TTL_DAYS = 7
COLLECTION = "response_cache"


def get_cached_response(
    db: firestore.Client,
    normalized_query: str,
    filters: dict,
    language: str,
    corpus_version: str,
    prompt_version: str,
    model: str,
    user_id: str | None = None,
) -> dict | None:
    """Busca una respuesta en caché. Retorna None si no hay hit."""
    key = cache_key(
        normalized_query, filters, language,
        corpus_version, prompt_version, model, user_id,
    )
    doc_ref = db.collection(COLLECTION).document(key)
    doc = doc_ref.get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    # Verificar TTL manualmente (Firestore TTL puede tardar hasta 24h)
    if data.get("expires_at") and data["expires_at"] < datetime.now(timezone.utc):
        return None
    # Incrementar hit count
    doc_ref.update({"hit_count": firestore.Increment(1)})
    return data


def store_response(
    db: firestore.Client,
    normalized_query: str,
    filters: dict,
    language: str,
    corpus_version: str,
    prompt_version: str,
    model: str,
    response: str,
    citations: list,
    user_id: str | None = None,
) -> None:
    """Almacena una respuesta en caché con TTL de 7 días."""
    key = cache_key(
        normalized_query, filters, language,
        corpus_version, prompt_version, model, user_id,
    )
    now = datetime.now(timezone.utc)
    db.collection(COLLECTION).document(key).set({
        "response": response,
        "citations": citations,
        "created_at": now,
        "expires_at": now + timedelta(days=CACHE_TTL_DAYS),
        "hit_count": 0,
    })
