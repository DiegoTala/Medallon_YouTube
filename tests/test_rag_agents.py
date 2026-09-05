"""Tests para los agentes ADK."""
from unittest.mock import MagicMock

from rag_agent.agents.analytics import create_analytics_agent
from rag_agent.agents.orchestrator import build_agent_pipeline
from rag_agent.agents.router import create_router_agent
from rag_agent.agents.search import create_search_agent
from rag_agent.agents.synthesis import create_synthesis_agent
from rag_agent.tools.adk_tools import (
    make_semantic_search_tool,
    make_sentiment_analytics_tool,
    make_trend_detection_tool,
)


def test_search_agent_escribe_el_payload_crudo_en_el_estado():
    """`search_result` lo escribe el callback con el payload crudo de la
    herramienta, no el texto final del modelo (que perdía comment_id y
    channel_name — por eso las citas salían con marcadores literales)."""
    tool = MagicMock()
    agent = create_search_agent(tool)
    assert agent.name == "search_agent"
    assert agent.output_key is None
    assert callable(agent.after_tool_callback)


def test_analytics_agent_escribe_los_payloads_crudos_en_el_estado():
    sentiment = MagicMock()
    trend = MagicMock()
    agent = create_analytics_agent(sentiment, trend)
    assert agent.name == "analytics_agent"
    assert agent.output_key is None
    assert callable(agent.after_tool_callback)


class _Estado:
    def __init__(self):
        self._d = {}

    def get(self, key, default=None):
        return self._d.get(key, default)

    def __getitem__(self, key):
        return self._d[key]

    def __setitem__(self, key, value):
        self._d[key] = value


class _ToolCtx:
    def __init__(self):
        self.state = _Estado()


def test_el_callback_de_search_escribe_el_payload_crudo():
    """El estado guarda el dict crudo de la herramienta, no una reescritura."""
    from rag_agent.agents.search import _guardar_payload_en_estado as guardar_search

    ctx = _ToolCtx()
    payload = {"status": "success", "results": [{"comment_id": "UgxKREWxIgDrf8Ug4AEC"}]}
    assert guardar_search(None, {}, ctx, payload) is None
    assert ctx.state["search_result"] is payload


def test_el_callback_de_analytics_acumula_por_tool():
    """Si corren las dos herramientas en una pregunta, ninguna pisa a la otra."""
    from rag_agent.agents.analytics import _guardar_payload_en_estado as guardar_analytics

    ctx = _ToolCtx()
    sent = MagicMock(name="sentiment_analytics")
    sent.name = "sentiment_analytics"
    trend = MagicMock(name="trend_detection")
    trend.name = "trend_detection"

    guardar_analytics(sent, {}, ctx, {"status": "success", "sample_sizes": {"total": 5}})
    guardar_analytics(trend, {}, ctx, {"status": "success", "n_current": 3})
    assert ctx.state["analytics_result"] == {
        "sentiment_analytics": {"status": "success", "sample_sizes": {"total": 5}},
        "trend_detection": {"status": "success", "n_current": 3},
    }


def test_synthesis_agent_has_no_tools():
    agent = create_synthesis_agent()
    assert agent.name == "synthesis_agent"
    assert agent.output_key == "final_answer"
    assert agent.tools == []


def test_router_agent_uses_agent_tools():
    search = MagicMock()
    analytics = MagicMock()
    synthesis = MagicMock()
    router = create_router_agent(search, analytics, synthesis)
    assert router.name == "root_router_agent"


def test_build_agent_pipeline_returns_root():
    bq_client = MagicMock()
    root = build_agent_pipeline(bq_client, "proj", "gold")
    assert root.name == "root_router_agent"


def test_adk_tools_create_wrappers():
    client = MagicMock()
    search_tool = make_semantic_search_tool(client, "proj", "gold")
    sentiment_tool = make_sentiment_analytics_tool(client, "proj", "gold")
    trend_tool = make_trend_detection_tool(client, "proj", "gold")
    assert callable(search_tool)
    assert callable(sentiment_tool)
    assert callable(trend_tool)
