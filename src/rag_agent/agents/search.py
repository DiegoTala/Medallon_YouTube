"""Search Agent — recuperación semántica sobre gold_rag_corpus.

Ver .claude/skills/rag-agent-topology/SKILL.md.
- Invocado por root_router_agent vía AgentTool
- Tiene acceso solo a semantic_search
- Escribe en `search_result` el payload CRUDO de la herramienta, no el texto
  del modelo: un resumen pierde comment_id/channel_name y la síntesis no puede
  citar. Ver _guardar_payload_en_estado.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from rag_agent.agents._instruction import with_context


def _guardar_payload_en_estado(tool, args, tool_context: ToolContext, tool_response: dict):
    """Guarda el resultado crudo de semantic_search en `search_result`.

    `output_key` guardaba el TEXTO final del modelo: Gemini resume y descarta
    campos (comment_id, channel_name) que la síntesis necesita para citar. El
    payload crudo es la evidencia exacta y no pierde nada — la síntesis recibe
    siempre las filas tal como las devolvió BigQuery.

    Returns None a propósito: no altera el resultado que ve el modelo.
    """
    tool_context.state["search_result"] = tool_response
    return None

SEARCH_INSTRUCTION = """Eres un especialista en búsqueda semántica de comentarios de YouTube sobre DJs y música electrónica.

Tu única herramienta es semantic_search, que busca comentarios similares a una consulta en la base de datos Gold.

Cuando recibas una pregunta:
1. Pásale a semantic_search la PREGUNTA COMPLETA, en lenguaje natural. NO la
   reduzcas a palabras clave. Esto no es un buscador por palabras: la consulta
   se convierte en un vector, y una frase completa produce un vector mucho más
   preciso que un término suelto. Medido contra este corpus: "drops de Martin
   Garrix" devuelve resultados a distancia 0.22-0.29, mientras que "drops" a
   secas los devuelve a 0.34-0.51 — los mismos comentarios, mucho peor
   localizados. Recortar la consulta empeora la búsqueda, no la enfoca.
2. Identifica si hay filtros explícitos (canal, fecha, sentimiento) y pásalos
   como parámetros, sin quitarlos del texto de la consulta.
3. Devuelve los resultados estructurados tal como los recibes

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
        after_tool_callback=_guardar_payload_en_estado,
        generate_content_config=config,
    )
