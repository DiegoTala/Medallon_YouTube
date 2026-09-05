"""Tests de la validación de citas en código.

Ver .claude/skills/rag-synthesis-citations/SKILL.md — el invariante es que una
cita sin evidencia en los resultados reales de las herramientas degrada la
respuesta, sin depender de que el prompt se cumpla.
"""
from types import SimpleNamespace

from rag_agent.middleware.citations import (
    collect_tool_payloads,
    extract_cited_ids,
    tools_used,
    valid_comment_ids,
    validate_citations,
)

REAL = "UgxKREWxIgDrf8Ug4AEC"
INVENTADO = "UgzFAKEfakefake000AAA"


def _payload(*comment_ids):
    return [(
        "semantic_search",
        {
            "status": "success",
            "count": len(comment_ids),
            "results": [{"comment_id": cid, "comment_text": "..."} for cid in comment_ids],
        },
    )]


def _event(name, response):
    part = SimpleNamespace(function_response=SimpleNamespace(name=name, response=response))
    return SimpleNamespace(content=SimpleNamespace(parts=[part]))


# ── extracción ───────────────────────────────────────────────────────────

def test_extrae_citas_en_el_formato_del_skill():
    texto = f'Al público le gustó el drop [{REAL} · "Tomorrowland 2024" · Martin Garrix · 2024-07-21].'
    assert extract_cited_ids(texto) == {REAL}


def test_texto_sin_citas_no_extrae_nada():
    assert extract_cited_ids("No hay comentarios en los datos disponibles.") == set()


def test_ignora_corchetes_que_no_son_citas():
    assert extract_cited_ids("Un rango [1-5] y una lista [a, b].") == set()


# ── evidencia real ───────────────────────────────────────────────────────

def test_solo_cuentan_los_resultados_exitosos():
    fallido = [("semantic_search", {"status": "error", "error": "403"})]
    assert valid_comment_ids(fallido) == set()


def test_reune_ids_de_varias_herramientas():
    payloads = _payload(REAL) + _payload("otro_id_valido_123")
    assert valid_comment_ids(payloads) == {REAL, "otro_id_valido_123"}


# ── validación ───────────────────────────────────────────────────────────

def test_cita_respaldada_pasa():
    texto = f'[{REAL} · "video" · canal · 2024-07-21]'
    ok, validas, inventadas = validate_citations(texto, _payload(REAL))
    assert ok is True
    assert validas == [REAL]
    assert inventadas == []


def test_cita_inventada_falla():
    texto = f'[{INVENTADO} · "video" · canal · 2024-07-21]'
    ok, validas, inventadas = validate_citations(texto, _payload(REAL))
    assert ok is False
    assert validas == []
    assert inventadas == [INVENTADO]


def test_una_cita_inventada_entre_varias_reales_falla():
    texto = f'[{REAL} · "a" · c · f] y también [{INVENTADO} · "b" · c · f]'
    ok, validas, inventadas = validate_citations(texto, _payload(REAL))
    assert ok is False
    assert validas == [REAL]
    assert inventadas == [INVENTADO]


def test_respuesta_sin_citas_es_valida():
    """Admitir ausencia de evidencia es una respuesta correcta, no una falla."""
    ok, validas, inventadas = validate_citations(
        "No hay comentarios en los datos disponibles que hablen de eso.",
        [("semantic_search", {"status": "success", "results": []})],
    )
    assert ok is True
    assert validas == []
    assert inventadas == []


def test_citar_sin_que_ninguna_herramienta_haya_corrido_falla():
    texto = f'[{REAL} · "video" · canal · 2024-07-21]'
    ok, _validas, inventadas = validate_citations(texto, [])
    assert ok is False
    assert inventadas == [REAL]


# ── extracción desde eventos de ADK ──────────────────────────────────────

def test_collect_tool_payloads_lee_function_response():
    payload = {"status": "success", "results": [{"comment_id": REAL}]}
    assert collect_tool_payloads(_event("semantic_search", payload)) == [
        ("semantic_search", payload)
    ]


def test_collect_tool_payloads_tolera_eventos_sin_contenido():
    assert collect_tool_payloads(SimpleNamespace(content=None)) == []
    assert collect_tool_payloads(SimpleNamespace()) == []


def test_collect_tool_payloads_ignora_partes_de_texto():
    part = SimpleNamespace(function_response=None, text="hola")
    evento = SimpleNamespace(content=SimpleNamespace(parts=[part]))
    assert collect_tool_payloads(evento) == []


def test_tools_used_deduplica():
    payloads = _payload(REAL) + _payload("x_valido_1234")
    assert tools_used(payloads) == ["semantic_search"]
