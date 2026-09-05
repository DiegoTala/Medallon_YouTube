"""Verificación del JWT de IAP (Identity-Aware Proxy).

Ver .claude/skills/rag-iap-auth/SKILL.md.
IAP inyecta x-goog-iap-jwt-assertion — un JWT firmado que el backend verifica.
Los headers x-goog-authenticated-user-* NO se usan (sin firma, falsificables).
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from google.auth.transport import requests as ga_requests
from google.oauth2 import id_token

PROJECT_NUMBER = "180406516352"
REGION = "us-central1"
SERVICE_NAME = "rag-chat-service"

IAP_AUDIENCE = f"/projects/{PROJECT_NUMBER}/locations/{REGION}/services/{SERVICE_NAME}"
IAP_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"

ALLOWED_EMAILS = frozenset({
    "diego@talamantes.com.mx",
    "medallon.rag.test01@talamantes.com.mx",
    "medallon.rag.test02@talamantes.com.mx",
})


def authenticate(request: Request) -> str:
    """Verifica el JWT de IAP y devuelve el sub del usuario.

    Returns:
        str: El identificador estable del usuario (claims.sub).

    Raises:
        HTTPException 401: Si falta la aserción o es inválida.
        HTTPException 403: Si la identidad no está en la allowlist.
    """
    assertion = request.headers.get("x-goog-iap-jwt-assertion")
    if not assertion:
        raise HTTPException(status_code=401, detail="Falta la aserción de IAP")

    try:
        claims = id_token.verify_token(
            assertion,
            ga_requests.Request(),
            audience=IAP_AUDIENCE,
            certs_url=IAP_CERTS_URL,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Aserción de IAP inválida") from exc

    email = claims.get("email")
    if email not in ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="Identidad no autorizada")

    return claims["sub"]
