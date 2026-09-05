"""Preferencias de usuario en Firestore — sin TTL.

Ver .claude/skills/rag-memory-preferences/SKILL.md.
Solo se guardan por instrucción explícita + confirmación previa.
Documento: users/{user_id}
"""

from __future__ import annotations

from datetime import datetime, timezone

from google.cloud import firestore


def load_preferences(db: firestore.Client, user_id: str) -> dict:
    """Carga las preferencias del usuario. Retorna {} si no existen."""
    doc = db.collection("users").document(user_id).get()
    if not doc.exists:
        return {}
    return doc.to_dict() or {}


def save_preferences(
    db: firestore.Client,
    user_id: str,
    preferences: dict,
) -> None:
    """Guarda preferencias (merge). Solo llamar después de confirmación explícita.

    preferences puede contener:
      - preferred_language: str
      - favorite_channels: list[str]
      - topics_of_interest: list[str]
      - format_preferences: dict
    """
    preferences["updated_at"] = datetime.now(timezone.utc)
    db.collection("users").document(user_id).set(preferences, merge=True)


def delete_preference(db: firestore.Client, user_id: str, key: str) -> bool:
    """Elimina una preferencia específica. Retorna True si existía."""
    doc = db.collection("users").document(user_id).get()
    if not doc.exists or key not in (doc.to_dict() or {}):
        return False
    db.collection("users").document(user_id).update({
        key: firestore.DELETE_FIELD,
    })
    return True
