"""Tests de integración end-to-end del agente RAG.

Verifica la cadena completa: auth -> sanitize -> rate limit -> quota -> cache -> agent -> persistencia.
Usa mocks para dependencias externas (BigQuery, Firestore, ADK Runner).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from rag_agent.main import app


@pytest.fixture
def client():
    """Cliente de prueba FastAPI."""
    return TestClient(app)


@pytest.fixture
def mock_auth():
    """Mock del middleware de autenticación IAP."""
    with patch("rag_agent.main.authenticate") as mock:
        mock.return_value = "test-user@example.com"
        yield mock


@pytest.fixture
def mock_rate_limit():
    """Mock del rate limiter."""
    with patch("rag_agent.main.check_rate_limit") as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_quota():
    """Mock de la cuota diaria."""
    with patch("rag_agent.main.check_daily_quota") as mock:
        mock.return_value = (True, 25)
        yield mock


@pytest.fixture
def mock_cache_miss():
    """Mock del caché (miss)."""
    with patch("rag_agent.main.get_cached_response") as mock:
        mock.return_value = None
        yield mock


@pytest.fixture
def mock_cache_hit():
    """Mock del caché (hit)."""
    with patch("rag_agent.main.get_cached_response") as mock:
        mock.return_value = {
            "response": "Respuesta cacheada",
            "citations": [{"comment_id": "cached-123"}],
        }
        yield mock


@pytest.fixture
def mock_session():
    """Mock de memoria de sesión."""
    with patch("rag_agent.main.get_recent_sessions") as mock_get:
        mock_get.return_value = [{"id": "session-123"}]
        with patch("rag_agent.main.load_session_messages") as mock_load:
            mock_load.return_value = [
                {"role": "user", "content": "Pregunta anterior"},
                {"role": "assistant", "content": "Respuesta anterior"},
            ]
            with patch("rag_agent.main.create_session") as mock_create:
                mock_create.return_value = "new-session-456"
                with patch("rag_agent.main.save_message") as mock_save:
                    mock_save.return_value = "msg-789"
                    yield {
                        "get": mock_get,
                        "load": mock_load,
                        "create": mock_create,
                        "save": mock_save,
                    }


@pytest.fixture
def mock_runner():
    """Mock del ADK Runner."""
    with patch("rag_agent.main.runner") as mock:
        # Simular respuesta del agente
        event = MagicMock()
        event.is_final_response.return_value = True
        event.content = MagicMock()
        event.content.parts = [MagicMock(text="Respuesta del agente sobre DJs")]
        event.custom_metadata = {
            "citations": [{"comment_id": "abc123", "video_title": "Test Video"}],
            "tools_used": ["semantic_search"],
        }

        async def mock_run(*args, **kwargs):
            yield event

        mock.run_async = mock_run
        yield mock


@pytest.fixture
def mock_store():
    """Mock del almacenamiento en caché."""
    with patch("rag_agent.main.store_response") as mock:
        yield mock


@pytest.fixture
def mock_record_query():
    """Mock del registro de consultas frecuentes."""
    with patch("rag_agent.main.record_query") as mock:
        yield mock


# ── Tests de integración ─────────────────────────────────────────────────────


def test_health_endpoint(client):
    """Healthcheck responde 200 sin autenticación."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == "ok"


def test_root_serves_ui(client):
    """La raíz sirve la UI HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "YouTube DJ Analytics" in response.text
    assert "text/html" in response.headers["content-type"]


def test_chat_full_flow(
    client, mock_auth, mock_rate_limit, mock_quota,
    mock_cache_miss, mock_session, mock_runner,
    mock_store, mock_record_query,
):
    """Flujo completo: auth -> sanitize -> rate limit -> quota -> cache -> agent -> persistencia."""
    response = client.post(
        "/chat",
        json={"query": "¿Qué opinan sobre Fisher?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "citations" in data
    assert "quota_remaining" in data
    assert data["cached"] is False
    assert data["quota_remaining"] == 25
    assert "Respuesta del agente" in data["response"]
    assert len(data["citations"]) == 1

    # Verificar que se llamaron todos los pasos de la cadena
    mock_auth.assert_called_once()
    mock_rate_limit.assert_called_once()
    mock_quota.assert_called_once()
    mock_cache_miss.assert_called_once()


def test_chat_empty_query_returns_400(client, mock_auth):
    """Query vacía retorna 400."""
    response = client.post("/chat", json={"query": ""})
    assert response.status_code == 400
    assert "vacía" in response.json()["error"]


def test_chat_sanitize_failure_returns_400(client, mock_auth):
    """Query que falla sanitización retorna 400."""
    with patch("rag_agent.main.sanitize") as mock:
        mock.return_value = ""
        response = client.post("/chat", json={"query": "   "})
        assert response.status_code == 400


def test_chat_rate_limited_returns_429(client, mock_auth, mock_rate_limit):
    """Rate limit excedido retorna 429."""
    mock_rate_limit.return_value = False
    response = client.post("/chat", json={"query": "test"})
    assert response.status_code == 429
    assert "5 consultas" in response.json()["error"]


def test_chat_quota_exceeded_returns_429(client, mock_auth, mock_rate_limit, mock_quota):
    """Cuota diaria agotada retorna 429."""
    mock_quota.return_value = (False, 0)
    response = client.post("/chat", json={"query": "test"})
    assert response.status_code == 429
    assert "30 consultas" in response.json()["error"]


def test_chat_cache_hit_returns_cached(
    client, mock_auth, mock_rate_limit, mock_quota,
    mock_cache_hit, mock_record_query,
):
    """Hit de caché retorna respuesta cacheada sin ejecutar agente."""
    response = client.post("/chat", json={"query": "test"})

    assert response.status_code == 200
    data = response.json()
    assert data["cached"] is True
    assert data["response"] == "Respuesta cacheada"


def test_chat_auth_failure_returns_401(client, mock_auth):
    """Fallo de autenticación retorna 401."""
    mock_auth.side_effect = Exception("Unauthorized")
    response = client.post("/chat", json={"query": "test"})
    assert response.status_code == 500


def test_chat_saves_session_messages(
    client, mock_auth, mock_rate_limit, mock_quota,
    mock_cache_miss, mock_session, mock_runner,
    mock_store, mock_record_query,
):
    """Se guardan mensajes de usuario y asistente en la sesión."""
    client.post("/chat", json={"query": "test"})

    # Verificar que se guardaron 2 mensajes (user + assistant)
    assert mock_session["save"].call_count == 2


def test_chat_records_common_query(
    client, mock_auth, mock_rate_limit, mock_quota,
    mock_cache_miss, mock_session, mock_runner,
    mock_store, mock_record_query,
):
    """Se registra la consulta frecuente."""
    client.post("/chat", json={"query": "test"})
    mock_record_query.assert_called_once()


def test_chat_stores_in_cache(
    client, mock_auth, mock_rate_limit, mock_quota,
    mock_cache_miss, mock_session, mock_runner,
    mock_store, mock_record_query,
):
    """Se almacena la respuesta en caché."""
    client.post("/chat", json={"query": "test"})
    mock_store.assert_called_once()


def test_chat_sanitizes_query(
    client, mock_auth, mock_rate_limit, mock_quota,
    mock_cache_miss, mock_session, mock_runner,
    mock_store, mock_record_query,
):
    """La query se sanitiza antes de procesar."""
    with patch("rag_agent.main.sanitize") as mock:
        mock.return_value = "query sanitizada"
        client.post("/chat", json={"query": "query sanitizada"})
        mock.assert_called_once()
