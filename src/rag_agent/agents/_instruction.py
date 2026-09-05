"""Compone la instrucción base de un agente con el contexto situacional.

ADK acepta `instruction` como str o como callable. La diferencia NO es solo de
forma: `LlmAgent.canonical_instruction` devuelve `bypass_state_injection=True`
cuando la instrucción es un callable, y con eso **desactiva la sustitución de
variables de estado** (`{search_result}` y compañía).

Por eso el provider llama a `inject_session_state` explícitamente. Sin esa
llamada, envolver una instrucción para agregarle la fecha rompería en silencio
cualquier `{variable}` que ese prompt tuviera — y el síntoma sería un agente
que no ve los datos, no un error.
"""

from __future__ import annotations

from typing import Callable

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils.instructions_utils import inject_session_state


def with_context(base: str, context_provider: Callable[[], str] | None):
    """Devuelve la instrucción: el str tal cual, o un callable que la compone.

    El str se devuelve sin envolver a propósito: ADK ya le inyecta el estado.
    Envolverlo sin necesidad sería desactivar esa inyección para nada.
    """
    if context_provider is None:
        return base

    async def provider(readonly_context: ReadonlyContext) -> str:
        contexto = context_provider()
        plantilla = f"{base}\n\n{contexto}" if contexto else base
        # Restituye a mano lo que el callable desactiva.
        return await inject_session_state(plantilla, readonly_context)

    return provider
