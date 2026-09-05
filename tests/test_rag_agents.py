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


def test_search_agent_has_output_key():
    tool = MagicMock()
    agent = create_search_agent(tool)
    assert agent.name == "search_agent"
    assert agent.output_key == "search_result"


def test_analytics_agent_has_output_key():
    sentiment = MagicMock()
    trend = MagicMock()
    agent = create_analytics_agent(sentiment, trend)
    assert agent.name == "analytics_agent"
    assert agent.output_key == "analytics_result"


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
