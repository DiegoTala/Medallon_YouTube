"""Tests para las herramientas de datos (semantic_search, sentiment_analytics, trend_detection)."""
from unittest.mock import MagicMock

import pytest

# Cada herramienta declara su propio tope de bytes: semantic_search usa 50 MB por el
# escaneo exhaustivo de VECTOR_SEARCH, las otras dos 10 MB. Ver rag-quota-limits.
from rag_agent.tools.semantic_search import (
    MAX_BYTES_BILLED as SEARCH_MAX_BYTES,
    MAX_TOP_K,
    semantic_search,
)
from rag_agent.tools.sentiment_analytics import (
    MAX_BYTES_BILLED as ANALYTICS_MAX_BYTES,
    TEMPLATES,
    sentiment_analytics,
)
from rag_agent.tools.trend_detection import (
    MAX_BYTES_BILLED as TREND_MAX_BYTES,
    VALID_METRICS,
    _evidence_level,
    trend_detection,
)


# ── semantic_search ──────────────────────────────────────────────────────

def test_semantic_search_clamps_top_k():
    client = MagicMock()
    client.query.return_value.result.return_value = []
    result = semantic_search(client, "proj", "gold", "test", top_k=100)
    sql = client.query.call_args.args[0]
    job_config = client.query.call_args.kwargs["job_config"]
    assert job_config.maximum_bytes_billed == SEARCH_MAX_BYTES
    # top_k debe estar clampeado a MAX_TOP_K
    params = {p.name: p.value for p in job_config.query_parameters}
    assert params["top_k"] == MAX_TOP_K


def test_semantic_search_uses_parameterized_query():
    client = MagicMock()
    client.query.return_value.result.return_value = []
    semantic_search(client, "proj", "gold", "test query", channel_name="Fisher")
    _, kwargs = client.query.call_args
    params = {p.name: p.value for p in kwargs["job_config"].query_parameters}
    assert params["query"] == "test query"
    assert params["channel_name"] == "Fisher"
    assert params["top_k"] == 10


def test_semantic_search_returns_success():
    client = MagicMock()
    client.query.return_value.result.return_value = [
        {"comment_id": "c1", "comment_text": "great", "distance": 0.1}
    ]
    result = semantic_search(client, "proj", "gold", "test")
    assert result["status"] == "success"
    assert result["count"] == 1


def test_semantic_search_handles_error():
    client = MagicMock()
    client.query.side_effect = Exception("BQ error")
    result = semantic_search(client, "proj", "gold", "test")
    assert result["status"] == "error"
    assert "BQ error" in result["error"]


# ── sentiment_analytics ─────────────────────────────────────────────────

def test_sentiment_analytics_rejects_unknown_query_type():
    client = MagicMock()
    result = sentiment_analytics(client, "proj", "gold", "unknown_type")
    assert result["status"] == "error"
    assert "no soportado" in result["error"]
    assert "supported" in result


def test_sentiment_analytics_accepts_all_five_types():
    for qt in TEMPLATES:
        client = MagicMock()
        client.query.return_value.result.return_value = []
        result = sentiment_analytics(client, "proj", "gold", qt)
        assert result["status"] == "success"
        assert result["query_type"] == qt


def test_sentiment_analytics_uses_parameterized_query():
    client = MagicMock()
    client.query.return_value.result.return_value = []
    sentiment_analytics(
        client, "proj", "gold", "distribution_by_channel",
        channel_name="Fisher",
    )
    _, kwargs = client.query.call_args
    job_config = kwargs["job_config"]
    assert job_config.maximum_bytes_billed == ANALYTICS_MAX_BYTES
    # Verificar que channel_name está parametrizado
    scalar_params = {p.name: p.value for p in job_config.query_parameters if hasattr(p, 'value')}
    assert scalar_params.get("channel_name") == "Fisher"


# ── trend_detection ─────────────────────────────────────────────────────

def test_trend_detection_rejects_unknown_metric():
    client = MagicMock()
    result = trend_detection(
        client, "proj", "gold",
        "2026-01-01", "2026-01-31", "2025-12-01", "2025-12-31",
        "invalid_metric",
    )
    assert result["status"] == "error"
    assert "no soportada" in result["error"]


def test_trend_detection_accepts_all_valid_metrics():
    for metric in VALID_METRICS:
        client = MagicMock()
        mock_row = {
            "current_volume": 50, "baseline_volume": 40,
            "current_positive": 0.6, "baseline_positive": 0.4,
            "current_negative": 0.2, "baseline_negative": 0.3,
            "current_avg_likes": 10.0, "baseline_avg_likes": 8.0,
        }
        client.query.return_value.result.return_value = [mock_row]
        result = trend_detection(
            client, "proj", "gold",
            "2026-01-01", "2026-01-31", "2025-12-01", "2025-12-31",
            metric,
        )
        assert result["status"] == "success", f"Failed for {metric}: {result}"
        assert result["metric"] == metric


def test_evidence_level_insufficient():
    assert _evidence_level(10, 50) == "insufficient"
    assert _evidence_level(50, 10) == "insufficient"


def test_evidence_level_weak():
    assert _evidence_level(50, 50) == "weak"


def test_evidence_level_solid():
    assert _evidence_level(100, 100) == "solid"


def test_trend_detection_handles_zero_baseline():
    client = MagicMock()
    mock_row = {
        "current_volume": 50, "baseline_volume": 0,
        "current_positive": 0.6, "baseline_positive": None,
        "current_negative": 0.2, "baseline_negative": None,
        "current_avg_likes": 10.0, "baseline_avg_likes": None,
    }
    client.query.return_value.result.return_value = [mock_row]
    result = trend_detection(
        client, "proj", "gold",
        "2026-01-01", "2026-01-31", "2025-12-01", "2025-12-31",
        "positive_ratio",
    )
    assert result["status"] == "success"
    assert result["direction"] == "flat"
    assert result["percent_change"] is None


def test_topes_de_bytes_por_herramienta():
    """semantic_search necesita 50 MB (VECTOR_SEARCH exhaustivo, ~20.9 MB reales);
    las herramientas de analítica escanean ~80 KB y se quedan en el tope general
    de 10 MB. Ver .claude/skills/rag-quota-limits/SKILL.md."""
    assert SEARCH_MAX_BYTES == 50 * 1024 * 1024
    assert ANALYTICS_MAX_BYTES == 10 * 1024 * 1024
    assert TREND_MAX_BYTES == 10 * 1024 * 1024
    # El corpus medido pesa ~20.9 MB: el tope debe dejarlo pasar con margen.
    assert SEARCH_MAX_BYTES > 20_856_549
