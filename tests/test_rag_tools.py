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


def test_compare_channels_recibe_la_lista():
    """El wrapper de ADK no exponía `channels`, así que la plantilla filtraba con
    UNNEST([]) y devolvía cero filas SIN fallar: status success, count 0. Una de
    las cinco plantillas era inalcanzable y nada lo delataba."""
    from unittest.mock import MagicMock

    from rag_agent.tools.adk_tools import make_sentiment_analytics_tool

    client = MagicMock()
    client.query.return_value.result.return_value = []
    tool = make_sentiment_analytics_tool(client, "proj", "gold")
    tool("compare_channels", channels=["ILLENIUM", "Alesso"])

    job_config = client.query.call_args.kwargs["job_config"]
    arrays = {p.name: p.values for p in job_config.query_parameters if hasattr(p, "values")}
    assert arrays["channels"] == ["ILLENIUM", "Alesso"]


def test_toda_plantilla_tiene_sus_parametros_en_el_wrapper():
    """Un @parametro que la plantilla usa y el wrapper no expone no produce un
    error: produce una respuesta vacía que el agente reporta como 'no hay datos'."""
    import inspect
    import re

    from rag_agent.tools.adk_tools import make_sentiment_analytics_tool
    from rag_agent.tools.sentiment_analytics import TEMPLATES

    from unittest.mock import MagicMock

    tool = make_sentiment_analytics_tool(MagicMock(), "proj", "gold")
    expuestos = set(inspect.signature(tool).parameters)

    usados = set()
    for sql in TEMPLATES.values():
        usados |= set(re.findall(r"@(\w+)", sql))

    assert usados <= expuestos, f"parámetros sin exponer: {usados - expuestos}"


# ── umbral de relevancia ─────────────────────────────────────────────────

def _fila(distance, cid="Ugx_test_1234567890"):
    return {"comment_id": cid, "comment_text": "...", "distance": distance}


def test_descarta_los_resultados_lejanos():
    """VECTOR_SEARCH siempre devuelve top_k, tenga o no que ver: preguntar por
    un DJ ausente devolvía 5 comentarios de otro y el modelo los 'rescataba'."""
    from unittest.mock import MagicMock

    from rag_agent.tools.semantic_search import MAX_DISTANCE, semantic_search

    client = MagicMock()
    client.query.return_value.result.return_value = [
        _fila(0.22), _fila(0.30), _fila(0.50), _fila(0.55),
    ]
    r = semantic_search(client, "proj", "gold", "consulta")
    assert r["count"] == 2
    assert r["descartados_por_relevancia"] == 2
    assert all(x["distance"] <= MAX_DISTANCE for x in r["results"])


def test_cero_relevantes_no_es_cero_resultados():
    """La distinción que necesita la síntesis: hay comentarios, pero ninguno
    habla de lo que se preguntó."""
    from unittest.mock import MagicMock

    from rag_agent.tools.semantic_search import semantic_search

    client = MagicMock()
    client.query.return_value.result.return_value = [_fila(0.49), _fila(0.52)]
    r = semantic_search(client, "proj", "gold", "drops de Fisher")
    assert r["status"] == "success"
    assert r["count"] == 0
    assert r["descartados_por_relevancia"] == 2


def test_el_umbral_cae_en_el_hueco_medido():
    """Calibrado el 2026-09-05: lo relevante llegó a 0.307 como máximo, lo
    irrelevante empezó en 0.379."""
    from rag_agent.tools.semantic_search import MAX_DISTANCE

    assert 0.31 < MAX_DISTANCE < 0.38
