"""Rate limit y cuota diaria sobre Firestore.

Ver .claude/skills/rag-quota-limits/SKILL.md.
- Rate limit: 5 consultas/min por usuario (configurable)
- Cuota diaria: 30 consultas por usuario
- Contadores atómicos con firestore.Increment
- Zona horaria fija: America/Mexico_City
- Un hit de caché igual cuenta para la cuota
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from google.cloud import firestore

RATE_LIMIT_PER_MINUTE = 5
DAILY_QUOTA = 30
TZ_NAME = "America/Mexico_City"


def _get_user_tz() -> timezone:
    """Retorna la zona horaria fija del proyecto (America/Mexico_City = UTC-6)."""
    return timezone(timedelta(hours=-6))


def _day_key(user_id: str) -> str:
    """Genera la clave del día para la cuota (YYYY-MM-DD en hora de CDMX)."""
    now = datetime.now(_get_user_tz())
    return f"{user_id}:{now:%Y-%m-%d}"


def _minute_key(user_id: str) -> str:
    """Genera clave de minuto para rate limit (YYYY-MM-DDTHH:MM)."""
    now = datetime.now(_get_user_tz())
    return f"{user_id}:{now:%Y-%m-%dT%H:%M}"


def check_rate_limit(db: firestore.Client, user_id: str) -> bool:
    """Verifica rate limit (5/min). Retorna True si está dentro del límite."""
    doc_ref = db.collection("rate_limits").document(_minute_key(user_id))
    doc = doc_ref.get()
    if doc.exists:
        count = doc.to_dict().get("count", 0)
        if count >= RATE_LIMIT_PER_MINUTE:
            return False
    doc_ref.set(
        {
            "count": firestore.Increment(1),
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        merge=True,
    )
    return True


def check_daily_quota(db: firestore.Client, user_id: str) -> tuple[bool, int]:
    """Verifica cuota diaria (30/día). Retorna (permitido, restante)."""
    doc_ref = db.collection("daily_quotas").document(_day_key(user_id))
    doc = doc_ref.get()
    current = 0
    if doc.exists:
        current = doc.to_dict().get("count", 0)
    if current >= DAILY_QUOTA:
        return False, 0
    doc_ref.set(
        {
            "count": firestore.Increment(1),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=2),
        },
        merge=True,
    )
    return True, DAILY_QUOTA - current - 1


def get_quota_remaining(db: firestore.Client, user_id: str) -> int:
    """Retorna las consultas restantes del día sin incrementar."""
    doc_ref = db.collection("daily_quotas").document(_day_key(user_id))
    doc = doc_ref.get()
    if not doc.exists:
        return DAILY_QUOTA
    return max(0, DAILY_QUOTA - doc.to_dict().get("count", 0))
