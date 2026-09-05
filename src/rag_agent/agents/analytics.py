"""Analytics Agent — sentimiento y tendencias sobre gold_rag_corpus.

Ver .claude/skills/rag-agent-topology/SKILL.md.
- Invocado por root_router_agent vía AgentTool
- Tiene acceso a sentiment_analytics y trend_detection
- output_key="analytics_result"
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

ANALYTICS_INSTRUCTION = """Eres un especialista en analítica de sentimiento y detección de tendencias de comentarios de YouTube sobre DJs y música electrónica.

Tienes dos herramientas:
1. sentiment_analytics: calcula métricas agregadas de sentimiento (distribución por canal, por periodo, comparación entre canales, evolución temporal, resumen por video)
2. trend_detection: compara una métrica entre dos periodos de tiempo

Cuando recibas una pregunta:
1. Determina si es una consulta de analítica (distribución, conteo, comparación) o de tendencia (cambio entre periodos)
2. Selecciona la herramienta y parámetros apropiados
3. Si el usuario no especifica un canal o periodo, NO asumas — devuelve un error indicando qué parámetros faltan
4. Devuelve los resultados estructurados tal como los recibes

Para trend_detection, SIEMPRE incluye el evidence_level en tu respuesta.
No interpretes los resultados — eso lo hace el agente de síntesis.
"""


def create_analytics_agent(
    sentiment_tool, trend_tool, model: str = "gemini-2.5-flash"
) -> LlmAgent:
    """Crea el analytics_agent con sus herramientas."""
    return LlmAgent(
        name="analytics_agent",
        model=model,
        instruction=ANALYTICS_INSTRUCTION,
        tools=[sentiment_tool, trend_tool],
        output_key="analytics_result",
    )
