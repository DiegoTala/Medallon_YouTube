"""Compone la instrucción base de un agente con el contexto situacional.

ADK acepta `instruction` como str o como callable que recibe un ReadonlyContext.
Usamos el callable para que la fecha se recalcule por request — ver
`rag_agent.agents.context`.
"""

from __future__ import annotations

from typing import Callable


def with_context(base: str, context_provider: Callable[[], str] | None):
    """Devuelve la instrucción: el str tal cual, o un callable que la compone."""
    if context_provider is None:
        return base

    def provider(_readonly_context=None) -> str:
        contexto = context_provider()
        return f"{base}\n\n{contexto}" if contexto else base

    return provider
