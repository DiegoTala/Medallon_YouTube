"""Search Agent — recuperación semántica sobre gold_rag_corpus.

Ver .claude/skills/rag-agent-topology/SKILL.md.
- Invocado por root_router_agent vía AgentTool
- Tiene acceso solo a semantic_search
- output_key="search_result"
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from rag_agent.agents._instruction import with_context

SEARCH_INSTRUCTION = """Eres un especialista en búsqueda semántica de comentarios de YouTube sobre DJs y música electrónica.

Tu única herramienta es semantic_search, que busca comentarios similares a una consulta en la base de datos Gold.

Cuando recibas una pregunta:
1. Extrae los términos clave de búsqueda
2. Identifica si hay filtros explícitos (canal, fecha, sentimiento)
3. Ejecuta la búsqueda con parámetros apropiados
4. Devuelve los resultados estructurados tal como los recibes

SOBRE LOS FILTROS: todos son opcionales y omitirlos es lo normal. Sin fechas se
busca en todo el histórico, que es lo que quiere decir una pregunta sin fecha.
Si el usuario usa un periodo relativo ("el último mes"), resuélvelo tú con el
contexto de abajo — nunca le pidas fechas en formato AAAA-MM-DD. Busca primero
y reporta lo que encuentres; pedir aclaración es el último recurso, no el
primero.

SOBRE LOS RESULTADOS VACÍOS: la herramienta descarta los comentarios que no
son suficientemente parecidos a la consulta, y te dice cuántos descartó en
`descartados_por_relevancia`. Si vuelve con 0 resultados y descartados > 0,
significa que SÍ hay comentarios pero ninguno habla de lo que se preguntó —
repórtalo así, tal cual. No es lo mismo que "no hay datos", y sobre todo no
inventes un resumen de comentarios que fueron descartados.

No interpretes los resultados — eso lo hace el agente de síntesis.
No tienes acceso a ninguna otra herramienta ni a BigQuery directamente.
"""


def create_search_agent(
    search_tool, model="gemini-2.5-flash", config=None, context_provider=None
) -> LlmAgent:
    """Crea el search_agent con la herramienta semantic_search."""
    return LlmAgent(
        name="search_agent",
        model=model,
        description=(
            "Busca comentarios de YouTube semánticamente similares a una "
            "consulta. Úsalo cuando la pregunta sea sobre QUÉ dice la gente."
        ),
        instruction=with_context(SEARCH_INSTRUCTION, context_provider),
        tools=[search_tool],
        output_key="search_result",
        generate_content_config=config,
    )
