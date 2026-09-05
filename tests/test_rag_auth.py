"""Tests para el middleware de autenticación IAP."""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from rag_agent.middleware.auth import ALLOWED_EMAILS, authenticate


def test_authenticate_missing_assertion_raises_401():
    request = MagicMock()
    request.headers = {}
    with pytest.raises(HTTPException) as exc_info:
        authenticate(request)
    assert exc_info.value.status_code == 401
    assert "Falta la aserción" in exc_info.value.detail


def test_authenticate_invalid_jwt_raises_401():
    request = MagicMock()
    request.headers = {"x-goog-iap-jwt-assertion": "invalid-token"}
    with pytest.raises(HTTPException) as exc_info:
        authenticate(request)
    assert exc_info.value.status_code == 401


def test_allowed_emails_contains_all_three():
    assert "diego@talamantes.com.mx" in ALLOWED_EMAILS
    assert "medallon.rag.test01@talamantes.com.mx" in ALLOWED_EMAILS
    assert "medallon.rag.test02@talamantes.com.mx" in ALLOWED_EMAILS
    # SA de evaluación (rag-evaluation-suite) — aprobado 2026-09-05
    assert "rag-backend-sa@medallon-youtube.iam.gserviceaccount.com" in ALLOWED_EMAILS
    assert len(ALLOWED_EMAILS) == 4
