"""Rate limit y cuota diaria sobre Firestore.

Ver .claude/skills/rag-quota-limits/SKILL.md.
- Rate limit: 5 consultas/min por usuario (configurable)
- Cuota diaria: 30 consultas por usuario
- Contadores atómicos con firestore.Increment
- Zona horaria fija: America/Mexico_City
- Un hit de caché igual cuenta para la cuota
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

logger = logging.getLogger("rag_agent.quota")

RATE_LIMIT_PER_MINUTE = 5
DAILY_QUOTA = 30
TZ_NAME = "America/Mexico_City"

# ── Excepciones por usuario ───────────────────────────────────────────────
#
# Se configuran en `infra/fase2/cloud_run.tf` como variable de entorno, no en
# Firestore: así el cambio aparece en `terraform plan`, pasa por approval-gate y
# queda en la bitácora. Un override guardado en Firestore sería mutable sin
# dejar rastro, que es justo lo que un guardrail de presupuesto no debe ser.
#
# Formato: "correo=limite,correo=limite". Un límite de 0 significa SIN TOPE.
# Ejemplo: QUOTA_OVERRIDES="diego@talamantes.com.mx=0"
QUOTA_OVERRIDES_ENV = "QUOTA_OVERRIDES"

# ── Circuito de protección agregado ───────────────────────────────────────
#
# rag-quota-limits lo especifica y no estaba implementado. Con un usuario sin
# tope, este es el ÚNICO límite que queda entre un bug en bucle y la factura.
#
# Cubre el escenario que las cuotas por usuario no cubren: el servicio
# reintentando con identidad válida. Los usuarios son de confianza; el código
# no necesariamente.
GLOBAL_DAILY_LIMIT = int(os.environ.get("GLOBAL_DAILY_LIMIT", "300"))
GLOBAL_COUNTER_ID = "_global"


# Zona horaria fija y declarada del proyecto. El día de la cuota se calcula
# aquí, no en UTC ni en la del servidor: si no, la cuota se reinicia a las 6 de
# la tarde y nadie entiende por qué.
PROJECT_TZ = timezone(timedelta(hours=-6))  # America/Mexico_City


def _get_user_tz() -> timezone:
    """Retorna la zona horaria fija del proyecto (America/Mexico_City = UTC-6)."""
    return PROJECT_TZ


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


def quota_limit_for(email: str | None) -> int | None:
    """Límite diario de esta identidad. `None` significa sin tope.

    Se lee del entorno en cada llamada y no se memoiza: el valor cambia solo
    con un despliegue, y releerlo cuesta nada frente a que un override quede
    pegado en memoria tras un cambio de configuración.
    """
    if not email:
        return DAILY_QUOTA

    crudo = os.environ.get(QUOTA_OVERRIDES_ENV, "")
    for par in crudo.split(","):
        par = par.strip()
        if not par or "=" not in par:
            continue
        correo, _, valor = par.partition("=")
        if correo.strip().lower() != email.strip().lower():
            continue
        try:
            limite = int(valor.strip())
        except ValueError:
            logger.warning("QUOTA_OVERRIDES con valor no numérico: %r", par)
            return DAILY_QUOTA
        return None if limite <= 0 else limite

    return DAILY_QUOTA


def check_global_circuit(db: firestore.Client) -> bool:
    """Circuito de protección agregado. True si se puede seguir atendiendo.

    Cuenta TODAS las consultas del día, de todos los usuarios, incluidas las de
    quienes no tienen tope. Es el último límite antes de la factura.
    """
    doc_ref = db.collection("daily_quotas").document(
        f"{GLOBAL_COUNTER_ID}:{datetime.now(_get_user_tz()):%Y-%m-%d}"
    )
    doc = doc_ref.get()
    total = doc.to_dict().get("count", 0) if doc.exists else 0
    if total >= GLOBAL_DAILY_LIMIT:
        logger.error(
            "Circuito agregado abierto: %d consultas hoy (tope %d)",
            total, GLOBAL_DAILY_LIMIT,
        )
        return False
    doc_ref.set(
        {
            "count": firestore.Increment(1),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=2),
        },
        merge=True,
    )
    return True


def check_daily_quota(
    db: firestore.Client, user_id: str, limit: int | None = DAILY_QUOTA
) -> tuple[bool, int]:
    """Verifica la cuota diaria. Retorna (permitido, restante).

    `limit=None` = sin tope. El contador se incrementa igual: sin tope no
    significa sin medición — es la única forma de ver cuánto se está gastando.
    En ese caso `restante` viene como -1, que la UI muestra como ilimitado.
    """
    doc_ref = db.collection("daily_quotas").document(_day_key(user_id))
    doc = doc_ref.get()
    current = 0
    if doc.exists:
        current = doc.to_dict().get("count", 0)

    if limit is not None and current >= limit:
        return False, 0

    doc_ref.set(
        {
            "count": firestore.Increment(1),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=2),
        },
        merge=True,
    )
    if limit is None:
        return True, -1
    return True, limit - current - 1


def get_quota_remaining(
    db: firestore.Client, user_id: str, limit: int | None = DAILY_QUOTA
) -> int:
    """Consultas restantes del día, sin incrementar. -1 si no hay tope."""
    if limit is None:
        return -1
    doc_ref = db.collection("daily_quotas").document(_day_key(user_id))
    doc = doc_ref.get()
    if not doc.exists:
        return limit
    return max(0, limit - doc.to_dict().get("count", 0))
