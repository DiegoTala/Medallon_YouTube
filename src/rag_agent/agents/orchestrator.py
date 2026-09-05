"""Orquestación ADK — wiring de agentes y herramientas.

Ver .claude/skills/rag-agent-topology/SKILL.md.

    root_router_agent            <- ÚNICO agente que le habla al usuario
      +-- AgentTool(search_agent)       -> semantic_search
      +-- AgentTool(analytics_agent)    -> sentiment_analytics, trend_detection
      +-- AgentTool(memory_agent)       -> consultas frecuentes y preferencias
      +-- AgentTool(hybrid_pipeline)    -> ParallelAgent(search, analytics)
                                           seguido de synthesis_agent
      +-- AgentTool(synthesis_agent)    -> redacta la respuesta final con citas

`AgentTool` y no `sub_agents`: con transferencia, un especialista puede
responderle al usuario sin pasar por la validación de citas ni por el tope de
tokens. Con llamada, el control siempre regresa al router.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from google.cloud import bigquery, firestore
from google.adk.models import Gemini
from google.genai import types

from rag_agent.agents.analytics import create_analytics_agent
from rag_agent.agents.context import make_context_provider
from rag_agent.agents.memory_agent import create_memory_agent
from rag_agent.agents.router import create_router_agent
from rag_agent.agents.search import create_search_agent
from rag_agent.agents.synthesis import create_synthesis_agent
from rag_agent.tools.adk_tools import (
    make_common_queries_tool,
    make_preferences_tool,
    make_semantic_search_tool,
    make_sentiment_analytics_tool,
    make_trend_detection_tool,
)

MODEL = "gemini-2.5-flash"

# Tope de 3.000 tokens del PRD Fase 2 §12, aplicado en la GENERACIÓN y no solo
# pedido en el prompt. Un "máximo 3.000 tokens" en la instrucción es una
# sugerencia; esto es un límite. Ver rag-quota-limits y rag-synthesis-citations.
MAX_OUTPUT_TOKENS = 3000

# Temperatura baja: el trabajo es reportar lo que dicen los comentarios, no
# redactar con variedad. La creatividad aquí se manifiesta como números que no
# están en los datos.
TEMPERATURE = 0.2


def _generation_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        max_output_tokens=MAX_OUTPUT_TOKENS,
        temperature=TEMPERATURE,
    )


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
    db: firestore.Client | None = None,
) -> LlmAgent:
    """Construye el pipeline completo de agentes y lo retorna como root.

    Args:
        bq_client: Cliente BigQuery autenticado.
        project: ID del proyecto GCP.
        dataset: Nombre del dataset Gold.
        region: Región de Vertex AI (co-ubicación us-central1).
        db: Cliente Firestore para el agente de memoria. Si es None, el
            pipeline se arma sin memory_agent — el resto funciona igual.

    Returns:
        LlmAgent: El root_router_agent listo para ser invocado por el Runner.
    """
    # 1. Herramientas con el client pre-configurado
    search_tool = make_semantic_search_tool(bq_client, project, dataset)
    sentiment_tool = make_sentiment_analytics_tool(bq_client, project, dataset)
    trend_tool = make_trend_detection_tool(bq_client, project, dataset)

    # 2. Agentes especializados (modelo vía Vertex AI, con tope de tokens)
    model = _vertex_model(project, region)
    config = _generation_config()

    # Fecha de hoy y canales reales, recalculados por request. Sin esto el
    # agente no puede resolver "el último mes" y termina pidiendo fechas en
    # AAAA-MM-DD, que es lo que se sentía como rigidez.
    contexto = make_context_provider(bq_client, project, dataset)

    search_agent = create_search_agent(search_tool, model, config, contexto)
    analytics_agent = create_analytics_agent(
        sentiment_tool, trend_tool, model, config, contexto
    )
    # La síntesis no recibe contexto: no elige filtros ni resuelve fechas, y su
    # prompt ya es el más largo del sistema.
    synthesis_agent = create_synthesis_agent(model, config)

    # 3. Preguntas híbridas: las dos ramas en paralelo y la síntesis DESPUÉS.
    #
    # El SequentialAgent es lo que garantiza el orden. Sin él, la síntesis leería
    # search_result y analytics_result vacíos. Las ramas del ParallelAgent no
    # comparten estado durante la ejecución — eso es deseable: se encuentran en
    # el output_key que la síntesis lee después, no antes.
    hybrid_pipeline = SequentialAgent(
        name="hybrid_pipeline",
        description=(
            "Responde preguntas que combinan búsqueda de comentarios con "
            "analítica de sentimiento. Ejecuta ambas y redacta la respuesta "
            "final con citas."
        ),
        sub_agents=[
            ParallelAgent(
                name="hybrid_fanout",
                sub_agents=[search_agent, analytics_agent],
            ),
            synthesis_agent,
        ],
    )

    # 4. Memoria: solo si hay Firestore.
    memory_agent = None
    if db is not None:
        memory_agent = create_memory_agent(
            make_common_queries_tool(db),
            make_preferences_tool(db),
            model,
            config,
        )

    # 5. Router que coordina todo
    return create_router_agent(
        search_agent=search_agent,
        analytics_agent=analytics_agent,
        synthesis_agent=synthesis_agent,
        hybrid_pipeline=hybrid_pipeline,
        memory_agent=memory_agent,
        model=model,
        config=config,
        context_provider=contexto,
    )
