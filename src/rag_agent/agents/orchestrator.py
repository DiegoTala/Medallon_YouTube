"""Orquestación ADK — wiring de agentes y herramientas.

Ver .claude/skills/rag-agent-topology/SKILL.md.
Topología: root_router → (search | analytics) → synthesis

Usa AgentTool (llamada, no transferencia) para que el control siempre
regrese al router. ParallelAgent para search+analytics en paralelo.
SequentialAgent para garantizar que la síntesis corre después.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.adk.models import Gemini
from google.cloud import bigquery

from rag_agent.agents.analytics import create_analytics_agent
from rag_agent.agents.router import create_router_agent
from rag_agent.agents.search import create_search_agent
from rag_agent.agents.synthesis import create_synthesis_agent
from rag_agent.tools.adk_tools import (
    make_semantic_search_tool,
    make_sentiment_analytics_tool,
    make_trend_detection_tool,
)

MODEL = "gemini-2.5-flash"


def _vertex_model(project: str, region: str) -> Gemini:
    """Crea el modelo Gemini vía Vertex AI (google-genai activa el backend
    de Vertex con vertexai=True + project/location). Sin esto, ADK intenta
    usar la API de Gemini (AI Studio) y falla con 'No API key was provided'."""
    return Gemini(
        model=MODEL,
        client_kwargs={"vertexai": True, "project": project, "location": region},
    )


def build_agent_pipeline(
    bq_client: bigquery.Client,
    project: str,
    dataset: str,
    region: str = "us-central1",
) -> LlmAgent:
    """Construye el pipeline completo de agentes y lo retorna como root.

    Args:
        bq_client: Cliente BigQuery autenticado.
        project: ID del proyecto GCP.
        dataset: Nombre del dataset Gold.
        region: Región de Vertex AI (co-ubicación us-central1).

    Returns:
        LlmAgent: El root_router_agent listo para ser invocado por el Runner.
    """
    # 1. Crear herramientas con el client pre-configurado
    search_tool = make_semantic_search_tool(bq_client, project, dataset)
    sentiment_tool = make_sentiment_analytics_tool(bq_client, project, dataset)
    trend_tool = make_trend_detection_tool(bq_client, project, dataset)

    # 2. Crear agentes especializados (modelo vía Vertex AI)
    model = _vertex_model(project, region)
    search_agent = create_search_agent(search_tool, model)
    analytics_agent = create_analytics_agent(sentiment_tool, trend_tool, model)
    synthesis_agent = create_synthesis_agent(model)

    # 3. Crear el router que coordina todo
    root = create_router_agent(search_agent, analytics_agent, synthesis_agent, model)

    return root
