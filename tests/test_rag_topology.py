"""Tests de la topología multiagente.

Ver .claude/skills/rag-agent-topology/SKILL.md.

Estos tests existen porque la topología estuvo documentada pero no
implementada: `orchestrator.py` importaba ParallelAgent y SequentialAgent y no
usaba ninguno. El router tenía tres AgentTool y nada garantizaba que la
síntesis corriera. Un test que solo mire "el pipeline se construye" no habría
detectado eso.
"""
from unittest.mock import MagicMock

from google.adk.agents import ParallelAgent, SequentialAgent

from rag_agent.agents.orchestrator import (
    MAX_OUTPUT_TOKENS,
    TEMPERATURE,
    build_agent_pipeline,
)


def _pipeline(con_memoria=True):
    return build_agent_pipeline(
        MagicMock(), "proj", "gold", "us-central1",
        db=MagicMock() if con_memoria else None,
    )


def _tool(root, nombre):
    return next(t for t in root.tools if t.name == nombre)


# ── estructura ───────────────────────────────────────────────────────────

def test_el_router_es_la_raiz():
    assert _pipeline().name == "root_router_agent"


def test_expone_los_cinco_agentes():
    nombres = {t.name for t in _pipeline().tools}
    assert nombres == {
        "search_agent", "analytics_agent", "memory_agent",
        "hybrid_pipeline", "synthesis_agent",
    }


def test_sin_firestore_no_hay_memory_agent():
    nombres = {t.name for t in _pipeline(con_memoria=False).tools}
    assert "memory_agent" not in nombres
    assert "search_agent" in nombres


def test_el_pipeline_hibrido_es_secuencial_con_fanout_paralelo():
    """El SequentialAgent es lo que garantiza que la síntesis corra DESPUÉS.
    Sin él, synthesis leería search_result y analytics_result vacíos."""
    hibrido = _tool(_pipeline(), "hybrid_pipeline").agent
    assert isinstance(hibrido, SequentialAgent)

    fanout, sintesis = hibrido.sub_agents
    assert isinstance(fanout, ParallelAgent)
    assert sintesis.name == "synthesis_agent"
    assert [a.name for a in fanout.sub_agents] == ["search_agent", "analytics_agent"]


# ── invariantes de aislamiento ───────────────────────────────────────────

def test_synthesis_no_tiene_herramientas_de_datos():
    """PRD Fase 2 §6: la síntesis trabaja solo con resultados estructurados."""
    assert _tool(_pipeline(), "synthesis_agent").agent.tools == []


def test_cada_especialista_solo_ve_lo_suyo():
    root = _pipeline()
    search = _tool(root, "search_agent").agent
    analytics = _tool(root, "analytics_agent").agent

    assert [t.__name__ for t in search.tools] == ["semantic_search"]
    assert sorted(t.__name__ for t in analytics.tools) == [
        "sentiment_analytics", "trend_detection",
    ]


def test_el_memory_agent_no_toca_bigquery():
    memoria = _tool(_pipeline(), "memory_agent").agent
    assert sorted(t.__name__ for t in memoria.tools) == [
        "get_my_common_queries", "get_my_preferences",
    ]


def test_los_output_key_son_los_que_lee_la_sintesis():
    root = _pipeline()
    assert _tool(root, "search_agent").agent.output_key == "search_result"
    assert _tool(root, "analytics_agent").agent.output_key == "analytics_result"
    assert _tool(root, "memory_agent").agent.output_key == "memory_result"


# ── tope de tokens ───────────────────────────────────────────────────────

def test_todos_los_agentes_llevan_el_tope_de_tokens():
    """El tope de 3.000 se aplica en la generación, no solo en el prompt.
    Antes no había un solo generate_content_config en el código."""
    root = _pipeline()
    agentes = [root] + [
        _tool(root, n).agent
        for n in ("search_agent", "analytics_agent", "memory_agent", "synthesis_agent")
    ]
    for agente in agentes:
        config = agente.generate_content_config
        assert config is not None, f"{agente.name} sin generate_content_config"
        assert config.max_output_tokens == MAX_OUTPUT_TOKENS
        assert config.temperature == TEMPERATURE


def test_el_tope_es_el_del_prd():
    assert MAX_OUTPUT_TOKENS == 3000
