"""Tests del contexto situacional que se inyecta en las instrucciones.

Existe porque el agente pedía fechas en formato AAAA-MM-DD para responder
"el último mes": un LLM no tiene reloj, y sin la fecha de hoy en el prompt
preguntar era su única salida correcta.
"""
import asyncio
from datetime import date
from unittest.mock import MagicMock

import pytest

from rag_agent import catalog
from rag_agent.agents._instruction import with_context
from rag_agent.agents.context import build_situational_context, make_context_provider


@pytest.fixture(autouse=True)
def _limpia_memo():
    catalog.reset_cache()
    yield
    catalog.reset_cache()


def _client():
    client = MagicMock()
    client.query.return_value.result.return_value = [
        {"channel_name": "ILLENIUM", "n_comments": 290,
         "desde": "2026-07-27", "hasta": "2026-09-04"},
        {"channel_name": "Alesso", "n_comments": 90,
         "desde": "2026-08-21", "hasta": "2026-08-23"},
    ]
    return client


# ── contenido del contexto ───────────────────────────────────────────────

def test_incluye_la_fecha_de_hoy():
    texto = build_situational_context(_client(), "proj", "gold")
    assert date.today().isoformat() in texto


def test_resuelve_los_periodos_relativos():
    """Lo que el agente no puede calcular solo."""
    texto = build_situational_context(_client(), "proj", "gold")
    for periodo in ("el último mes", "el mes pasado", "este mes", "últimos 7 días"):
        assert periodo in texto


def test_prohibe_pedir_formato_de_fecha():
    texto = build_situational_context(_client(), "proj", "gold")
    assert "NO le pidas al usuario" in texto


def test_lista_los_canales_con_su_nombre_exacto():
    texto = build_situational_context(_client(), "proj", "gold")
    assert "ILLENIUM" in texto
    assert "Alesso" in texto


def test_declara_la_cobertura_real_de_los_datos():
    """Para que no consulte periodos donde no hay nada."""
    texto = build_situational_context(_client(), "proj", "gold")
    assert "2026-07-27" in texto   # el mínimo de los canales
    assert "2026-09-04" in texto   # el máximo


def test_sin_canales_no_revienta():
    client = MagicMock()
    client.query.return_value.result.return_value = []
    texto = build_situational_context(client, "proj", "gold")
    assert date.today().isoformat() in texto
    assert "Canales disponibles" not in texto


def test_si_bigquery_falla_se_conserva_la_fecha():
    """La degradación es parcial y en el orden correcto: el catálogo de canales
    necesita BigQuery, la fecha no. Perder los canales hace que el agente
    pregunte por el DJ; perder la fecha lo haría pedir AAAA-MM-DD otra vez."""
    client = MagicMock()
    client.query.side_effect = RuntimeError("403")
    texto = make_context_provider(client, "proj", "gold")()
    assert date.today().isoformat() in texto
    assert "Canales disponibles" not in texto


# ── composición de la instrucción ────────────────────────────────────────
#
# El provider es async y llama a inject_session_state, porque ADK desactiva la
# sustitución de {variables} cuando la instrucción es un callable. Ver
# rag_agent/agents/_instruction.py.
#
# Se usa asyncio.run() en vez de pytest-asyncio para no agregar una dependencia
# ni tocar uv.lock, que el Dockerfile consume con `uv sync --frozen`.


class _CtxFalso:
    """ReadonlyContext mínimo, suficiente para inject_session_state."""

    def __init__(self, state=None):
        self._invocation_context = MagicMock()
        self._invocation_context.session.state = state or {}


def test_sin_provider_la_instruccion_es_el_string():
    """Un str se devuelve sin envolver: ADK ya le inyecta el estado, y
    envolverlo sería desactivar esa inyección para nada."""
    assert with_context("BASE", None) == "BASE"


def test_con_provider_es_un_callable_que_compone():
    instr = with_context("BASE", lambda: "CONTEXTO")
    assert callable(instr)
    assert asyncio.run(instr(_CtxFalso())) == "BASE\n\nCONTEXTO"


def test_contexto_vacio_no_ensucia_la_instruccion():
    instr = with_context("BASE", lambda: "")
    assert asyncio.run(instr(_CtxFalso())) == "BASE"


def test_el_contexto_se_recalcula_en_cada_llamada():
    """El pipeline se construye una vez por instancia y esa instancia vive días.
    Una fecha horneada al arranque estaría mal al día siguiente."""
    valores = iter(["DIA 1", "DIA 2"])
    instr = with_context("BASE", lambda: next(valores))
    assert asyncio.run(instr(_CtxFalso())) == "BASE\n\nDIA 1"
    assert asyncio.run(instr(_CtxFalso())) == "BASE\n\nDIA 2"


def test_el_provider_sigue_inyectando_estado():
    """La razón de ser del async: envolver la instrucción en un callable
    desactiva la sustitución de {variables} de ADK, y hay que restituirla a
    mano. Sin esto, agregar la fecha rompería {search_result} en silencio."""
    instr = with_context("Datos: {mi_var}", lambda: "CONTEXTO")
    resultado = asyncio.run(instr(_CtxFalso({"mi_var": "VALOR REAL"})))
    assert resultado == "Datos: VALOR REAL\n\nCONTEXTO"
