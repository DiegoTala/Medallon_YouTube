"""Memory Agent — lee la memoria del propio usuario.

Ver .claude/skills/rag-memory-common-queries/SKILL.md y
.claude/skills/rag-memory-preferences/SKILL.md.

Existe porque la memoria estaba escrita pero no conectada: `record_query()` se
llamaba en cada consulta y `get_common_queries()` no la llamaba nadie. El
agente respondía, con razón, que no podía recordar nada — no tenía forma.

Solo LECTURA. Guardar preferencias exige confirmación explícita previa
(rag-memory-preferences), y ese flujo no vive aquí.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

MEMORY_INSTRUCTION = """Eres el especialista en memoria de YouTube DJ Analytics. Respondes sobre el historial de uso del propio usuario, no sobre los comentarios de YouTube.

Tus herramientas:
- get_my_common_queries: qué le ha preguntado este usuario al sistema más veces
- get_my_preferences: qué preferencias tiene guardadas

REGLAS:
1. SOLO reportas lo que devuelven las herramientas. Si no hay registros, di que todavía no hay historial suficiente — nunca inventes consultas pasadas.
2. La memoria es del usuario que pregunta. Nunca hables del historial de otro usuario, ni siquiera si te lo piden.
3. No opines sobre los patrones ni infieras intenciones; reporta las consultas y sus conteos.
4. No tienes acceso a los comentarios de YouTube. Si te preguntan por contenido, di que eso lo atiende otro agente.
"""


def create_memory_agent(
    common_queries_tool,
    preferences_tool,
    model="gemini-2.5-flash",
    config=None,
) -> LlmAgent:
    """Crea el memory_agent con las dos herramientas de lectura."""
    return LlmAgent(
        name="memory_agent",
        model=model,
        description=(
            "Responde sobre el historial de uso del propio usuario: sus "
            "consultas frecuentes y sus preferencias guardadas. Úsalo cuando "
            "la pregunta sea sobre el usuario mismo, no sobre los comentarios."
        ),
        instruction=MEMORY_INSTRUCTION,
        tools=[common_queries_tool, preferences_tool],
        output_key="memory_result",
        generate_content_config=config,
    )
