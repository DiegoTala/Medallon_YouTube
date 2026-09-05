"""Root Router Agent — clasificación de intención y coordinación.

Ver .claude/skills/rag-agent-topology/SKILL.md.
- ÚNICO agente que le habla al usuario
- Clasifica la intención y coordina agentes especializados vía AgentTool
- Puede ejecutar Search y Analytics en paralelo para preguntas híbridas
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

ROUTER_INSTRUCTION = """Eres el router principal de YouTube DJ Analytics, un sistema que analiza comentarios de YouTube sobre DJs y música electrónica.

Tu trabajo es:
1. CLASIFICAR la intención del usuario en una de estas categorías:
   - semantic_search: el usuario quiere encontrar comentarios específicos
   - sentiment_analytics: el usuario quiere métricas de sentimiento (distribución, comparación, evolución)
   - trend_detection: el usuario quiere comparar métricas entre dos periodos
   - hybrid: el usuario combina búsqueda + analítica en una misma pregunta
   - out_of_domain: la pregunta no tiene relación con YouTube DJs ni comentarios

2. DELEGAR al agente apropiado:
   - Para semantic_search → usa search_agent
   - Para sentiment_analytics o trend_detection → usa analytics_agent
   - Para hybrid → usa search_agent Y analytics_agent en paralelo
   - Para out_of_domain → responde directamente que el sistema solo analiza datos de YouTube DJs

3. Después de recibir los resultados de los agentes especializados, pasa TODO al synthesis_agent para que redacte la respuesta final.

REGLAS:
- NUNCA consultes BigQuery directamente
- NUNCA respondas con datos sin que un agente especializado los haya recuperado primero
- Si la pregunta es ambigua, pide aclaración antes de delegar
- Las preguntas sobre DJs, música electrónica, sets, tracks, comentarios de YouTube están DENTRO del dominio
- Las preguntas sobre otros temas (política, deportes, ciencia, etc.) están FUERA del dominio
"""


def create_router_agent(
    search_agent,
    analytics_agent,
    synthesis_agent,
    model: str = "gemini-2.5-flash",
) -> LlmAgent:
    """Crea el root_router_agent con los tres agentes especializados."""
    from google.adk.tools import AgentTool

    return LlmAgent(
        name="root_router_agent",
        model=model,
        instruction=ROUTER_INSTRUCTION,
        tools=[
            AgentTool(agent=search_agent),
            AgentTool(agent=analytics_agent),
            AgentTool(agent=synthesis_agent),
        ],
    )
