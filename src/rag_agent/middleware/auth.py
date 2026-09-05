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

# Nombre visible para el saludo de /welcome. Mapa explícito y no heurística:
# son tres identidades conocidas, y derivar el nombre de la parte local del
# correo produce "Medallon Rag Test01". El fallback existe para no romper si se
# agrega una identidad y se olvida el nombre.
DISPLAY_NAMES = {
    "diego@talamantes.com.mx": "Diego",
    "medallon.rag.test01@talamantes.com.mx": "Usuario de prueba 1",
    "medallon.rag.test02@talamantes.com.mx": "Usuario de prueba 2",
    "rag-backend-sa@medallon-youtube.iam.gserviceaccount.com": "Evaluación automatizada",
}

ALLOWED_EMAILS = frozenset({
    "diego@talamantes.com.mx",
    "medallon.rag.test01@talamantes.com.mx",
    "medallon.rag.test02@talamantes.com.mx",
    # SA de evaluación (rag-evaluation-suite): invoca vía JWT self-signed
    # con binding IAP; la cuota la consume esta identidad, no la de Diego.
    "rag-backend-sa@medallon-youtube.iam.gserviceaccount.com",
})


def authenticate_identity(request: Request) -> tuple[str, str]:
    """Verifica el JWT de IAP y devuelve (sub, email).

    El `sub` es lo que identifica al usuario en todo el sistema: cuota diaria,
    historial y caché van indexados por él. El email se usa SOLO para mostrar
    (el saludo de /welcome) — nunca como clave, porque un cambio de correo
    huerfanaría la memoria y reiniciaría los contadores.

    Returns:
        tuple[str, str]: (claims.sub, claims.email)

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

    return claims["sub"], email


def authenticate(request: Request) -> str:
    """Verifica el JWT de IAP y devuelve el sub del usuario.

    Envoltura de authenticate_identity para el resto de la cadena, que solo
    necesita el identificador.
    """
    sub, _email = authenticate_identity(request)
    return sub


def display_name(email: str) -> str:
    """Nombre visible para el saludo. Nunca es la clave de nada."""
    return DISPLAY_NAMES.get(email) or (email.split("@")[0] if email else "")
