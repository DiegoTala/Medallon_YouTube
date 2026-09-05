"""Nivel de evidencia — una sola escala para todo el sistema.

Vivía dentro de trend_detection y solo se aplicaba ahí. Pero el problema es de
`sentiment_analytics` por igual: con 3,261 comentarios repartidos en 7 canales,
Zedd tiene 6 y Martin Garrix 1,869. Comparar sus porcentajes es aritmética sin
significado, y hasta ahora se reportaba con el mismo aplomo que una muestra de
mil filas.

Los umbrales son un piso pragmático para el volumen actual, no una prueba
estadística. Si el corpus crece un orden de magnitud, revísalos — pero nunca
los quites: ninguna herramienta devuelve un porcentaje sin decir sobre cuántas
filas se calculó.
"""

from __future__ import annotations

INSUFFICIENT_BELOW = 30
WEAK_BELOW = 100


def evidence_level(*sample_sizes: int) -> str:
    """Clasifica la evidencia por el tamaño de muestra MÁS PEQUEÑO.

    Se toma el mínimo a propósito: una comparación vale lo que vale su lado más
    flaco. Martin Garrix con 1,869 comentarios frente a Zedd con 6 no es una
    comparación sólida — es una cifra sólida al lado de una anécdota.
    """
    if not sample_sizes:
        return "insufficient"
    n = min(sample_sizes)
    if n < INSUFFICIENT_BELOW:
        return "insufficient"
    if n < WEAK_BELOW:
        return "weak"
    return "solid"
