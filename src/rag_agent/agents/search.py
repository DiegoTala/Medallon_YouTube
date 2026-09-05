"""Search Agent — recuperación semántica sobre gold_rag_corpus.

Ver .claude/skills/rag-agent-topology/SKILL.md.
- Invocado por root_router_agent vía AgentTool
- Tiene acceso solo a semantic_search
- output_key="search_result"
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

SEARCH_INSTRUCTION = """Eres un especialista en búsqueda semántica de comentarios de YouTube sobre DJs y música electrónica.

Tu única herramienta es semantic_search, que busca comentarios similares a una consulta en la base de datos Gold.

Cuando recibas una pregunta:
1. Extrae los términos clave de búsqueda
2. Identifica si hay filtros explícitos (canal, fecha, sentimiento)
3. Ejecuta la búsqueda con parámetros apropiados
4. Devuelve los resultados estructurados tal como los recibes

No interpretes los resultados — eso lo hace el agente de síntesis.
No tienes acceso a ninguna otra herramienta ni a BigQuery directamente.
"""


def create_search_agent(search_tool, model: str = "gemini-2.5-flash") -> LlmAgent:
    """Crea el search_agent con la herramienta semantic_search."""
    return LlmAgent(
        name="search_agent",
        model=model,
        instruction=SEARCH_INSTRUCTION,
        tools=[search_tool],
        output_key="search_result",
    )
