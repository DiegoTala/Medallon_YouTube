"""Memoria de sesión en Firestore — TTL 7 días.

Ver .claude/skills/rag-memory-session/SKILL.md.
Estructura: users/{user_id}/sessions/{session_id}/messages/{message_id}
Subcolección para evitar el límite de 1 MiB por documento.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

SESSION_TTL_DAYS = 7


def create_session(db: firestore.Client, user_id: str) -> str:
    """Crea una nueva sesión y retorna su ID."""
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.collection("users").document(user_id).collection("sessions").document(session_id).set({
        "created_at": now,
        "expires_at": now + timedelta(days=SESSION_TTL_DAYS),
    })
    return session_id


def save_message(
    db: firestore.Client,
    user_id: str,
    session_id: str,
    role: str,
    content: str,
    tools_used: list[str] | None = None,
    citations: list | None = None,
    gold_snapshot_id: str | None = None,
) -> str:
    """Guarda un mensaje en la subcolección de la sesión. Retorna message_id."""
    message_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.collection("users").document(user_id)\
      .collection("sessions").document(session_id)\
      .collection("messages").document(message_id).set({
        "role": role,
        "content": content,
        "timestamp": now,
        "tools_used": tools_used or [],
        "citations": citations or [],
        "gold_snapshot_id": gold_snapshot_id,
        "expires_at": now + timedelta(days=SESSION_TTL_DAYS),
    })
    return message_id


def load_session_messages(
    db: firestore.Client, user_id: str, session_id: str
) -> list[dict]:
    """Carga los mensajes de una sesión, filtrando por TTL.

    Retorna lista ordenada por timestamp (más viejo primero).
    """
    now = datetime.now(timezone.utc)
    messages_ref = (
        db.collection("users").document(user_id)
        .collection("sessions").document(session_id)
        .collection("messages")
        .where("expires_at", ">", now)
        .order_by("timestamp")
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in messages_ref.stream()]


def get_recent_sessions(
    db: firestore.Client, user_id: str, limit: int = 5
) -> list[dict]:
    """Retorna las sesiones más recientes del usuario (no expiradas)."""
    now = datetime.now(timezone.utc)
    sessions_ref = (
        db.collection("users").document(user_id)
        .collection("sessions")
        .where("expires_at", ">", now)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in sessions_ref.stream()]
