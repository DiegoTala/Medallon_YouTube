"""Analytics Agent — sentimiento y tendencias sobre gold_rag_corpus.

Ver .claude/skills/rag-agent-topology/SKILL.md.
- Invocado por root_router_agent vía AgentTool
- Tiene acceso a sentiment_analytics y trend_detection
- Escribe en `analytics_result` los payloads CRUDOS de las herramientas, no el
  texto del modelo: un resumen pierde sample_sizes/evidence_level y la síntesis
  no puede citar. Ver _guardar_payload_en_estado.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from rag_agent.agents._instruction import with_context


def _guardar_payload_en_estado(tool, args, tool_context: ToolContext, tool_response: dict):
    """Acumula los payloads crudos de las herramientas en `analytics_result`.

    En una misma pregunta pueden correr sentiment_analytics y trend_detection;
    cada uno se guarda bajo su nombre para que ninguno pise al otro.

    Returns None a propósito: no altera el resultado que ve el modelo.
    """
    acumulado = tool_context.state.get("analytics_result")
    if not isinstance(acumulado, dict):
        acumulado = {}
    acumulado[tool.name] = tool_response
    tool_context.state["analytics_result"] = acumulado
    return None

ANALYTICS_INSTRUCTION = """Eres un especialista en analítica de sentimiento y detección de tendencias de comentarios de YouTube sobre DJs y música electrónica.

Tienes dos herramientas:
1. sentiment_analytics: métricas agregadas de sentimiento
2. trend_detection: compara una métrica entre dos periodos

QUÉ PLANTILLA USAR (sentiment_analytics.query_type):
- compare_channels — comparar dos o más DJs entre sí. Pasa `channels` con la
  lista de nombres. NO requiere fechas.
- distribution_by_channel — el sentimiento de UN solo canal. Pasa `channel_name`.
  NO requiere fechas.
- distribution_by_period — el sentimiento en un periodo concreto que el usuario pidió.
- evolution_over_time — cómo cambió mes a mes. `channel_name` y fechas son opcionales.
- summary_by_video — el sentimiento de un video concreto. Pasa `video_id`.

CÓMO TRATAR LOS PARÁMETROS QUE FALTAN — esto es importante:

1. Si el usuario NO menciona ningún periodo, NO se lo pidas. Omite `date_from` y
   `date_to`: la consulta cubre todo el histórico disponible, que es justo lo
   que quiere decir una pregunta sin fecha.
2. Si el usuario usa un periodo relativo ("el último mes", "esta semana",
   "agosto"), resuélvelo tú con el contexto de abajo. NUNCA le pidas fechas en
   formato AAAA-MM-DD: tú tienes la fecha de hoy y él no tiene por qué hacer la
   aritmética.
3. Elige la plantilla que responda la pregunta con lo que YA tienes. Si te
   preguntan "¿cómo es el sentimiento de ILLENIUM comparado con Alesso?", eso es
   compare_channels con `channels=["ILLENIUM", "Alesso"]` y sin fechas — no es
   una pregunta incompleta.
4. Solo pide aclaración cuando el dato falte de verdad y no se pueda deducir:
   un video sin `video_id`, o un DJ que no está en la lista de canales. Cuando
   preguntes, hazlo en lenguaje natural y ofrece opciones concretas; nunca pidas
   un formato de fecha.

SOBRE trend_detection: se ejecuta SOLO si el usuario pidió explícitamente una
comparación entre dos periodos ("¿cambió...?", "agosto contra julio", "¿va
subiendo?"). Si preguntó por el sentimiento de uno o varios canales SIN mencionar
periodos que comparar, NO la llames — es una consulta a BigQuery y a Vertex AI
que nadie pidió, y agrega a la respuesta una tendencia que el usuario no buscaba.
Cuando sí la llames, SIEMPRE incluye el evidence_level.
Devuelve los resultados estructurados tal como los recibes: no los interpretes,
eso lo hace el agente de síntesis.
"""


def create_analytics_agent(
    sentiment_tool, trend_tool, model="gemini-2.5-flash", config=None,
    context_provider=None,
) -> LlmAgent:
    """Crea el analytics_agent con sus herramientas."""
    return LlmAgent(
        name="analytics_agent",
        model=model,
        description=(
            "Calcula métricas agregadas de sentimiento y compara periodos. "
            "Úsalo cuando la pregunta pida números, distribuciones, "
            "comparaciones entre canales o evolución en el tiempo."
        ),
        instruction=with_context(ANALYTICS_INSTRUCTION, context_provider),
        tools=[sentiment_tool, trend_tool],
        after_tool_callback=_guardar_payload_en_estado,
        generate_content_config=config,
    )
