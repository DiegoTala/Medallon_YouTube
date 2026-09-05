"""Contexto situacional que se inyecta en las instrucciones de los agentes.

Un LLM no tiene reloj. Sin la fecha de hoy en el prompt, "el último mes" es
literalmente irresoluble, y el agente hace lo único correcto que puede hacer:
pedirle al usuario fechas exactas en AAAA-MM-DD. Eso se leía como rigidez y era
una carencia de contexto.

Lo mismo con los canales: sin la lista, el agente no puede saber si "Garrix" es
un canal válido ni cuál es su nombre exacto para el filtro, así que pregunta.

Las instrucciones de ADK aceptan un callable, y por eso este bloque se calcula
**por request** y no al construir el pipeline. Una instancia de Cloud Run vive
horas o días: una fecha horneada al arranque estaría equivocada al día
siguiente, que es el peor tipo de error — silencioso y plausible.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from google.cloud import bigquery

from rag_agent.catalog import get_available_channels
from rag_agent.middleware.quota import PROJECT_TZ

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def build_situational_context(
    client: bigquery.Client,
    project: str,
    dataset: str,
) -> str:
    """Arma el bloque de contexto: fecha de hoy, periodos y canales reales."""
    hoy = datetime.now(PROJECT_TZ).date()

    inicio_mes_actual = hoy.replace(day=1)
    fin_mes_pasado = inicio_mes_actual - timedelta(days=1)
    inicio_mes_pasado = fin_mes_pasado.replace(day=1)

    lineas = [
        "CONTEXTO DE LA CONSULTA — calculado ahora. NO le pidas al usuario nada",
        "que puedas resolver con esto.",
        "",
        f"Hoy es {DIAS[hoy.weekday()]} {hoy.isoformat()} (hora de México).",
        "",
        "Periodos relativos ya resueltos (úsalos tal cual):",
        f"  - hoy                : {hoy} a {hoy}",
        f"  - últimos 7 días     : {hoy - timedelta(days=7)} a {hoy}",
        f"  - últimos 30 días    : {hoy - timedelta(days=30)} a {hoy}",
        f"  - 'el último mes'    : {hoy - timedelta(days=30)} a {hoy}",
        f"  - 'este mes'         : {inicio_mes_actual} a {hoy}",
        f"  - 'el mes pasado'    : {inicio_mes_pasado} a {fin_mes_pasado}",
        f"  - últimos 90 días    : {hoy - timedelta(days=90)} a {hoy}",
    ]

    canales = get_available_channels(client, project, dataset)
    if canales:
        desde = min(c["desde"] for c in canales)
        hasta = max(c["hasta"] for c in canales)
        lineas += [
            "",
            f"Los comentarios disponibles van del {desde} al {hasta}. Fuera de ese",
            "rango no hay datos: si el usuario pide un periodo anterior, dilo en vez",
            "de consultar.",
            "",
            "Canales disponibles. Estos son los nombres EXACTOS para los filtros —",
            "úsalos literales, no los reescribas:",
        ]
        lineas += [f"  - {c['channel_name']}" for c in canales]
        lineas += [
            "",
            "Si el usuario menciona un DJ que no está en esta lista, dilo claramente",
            "en vez de buscar. Si escribe un nombre parcial o con otra grafía y",
            "corresponde sin ambigüedad a uno de la lista, úsalo sin preguntar.",
        ]

    return "\n".join(lineas)


def make_context_provider(client: bigquery.Client, project: str, dataset: str):
    """Devuelve un callable sin argumentos que arma el contexto al vuelo."""

    def provider() -> str:
        try:
            return build_situational_context(client, project, dataset)
        except Exception:
            # Sin contexto el agente vuelve a preguntar fechas, que es molesto
            # pero correcto. Nunca vale la pena tumbar la consulta por esto.
            return ""

    return provider
