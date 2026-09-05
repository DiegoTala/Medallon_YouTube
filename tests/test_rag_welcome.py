"""Tests del catálogo de canales y del saludo de la bienvenida.

Ver .claude/skills/rag-fastapi-service/SKILL.md.
"""
from unittest.mock import MagicMock

import pytest

from rag_agent import catalog
from rag_agent.middleware.auth import DISPLAY_NAMES, display_name


@pytest.fixture(autouse=True)
def _limpia_memo():
    catalog.reset_cache()
    yield
    catalog.reset_cache()


def _client(filas=None):
    if filas is None:
        filas = [
            {"channel_name": "Martin Garrix", "n_comments": 1869,
             "desde": "2026-07-28", "hasta": "2026-09-04"},
            {"channel_name": "Zedd", "n_comments": 6,
             "desde": "2026-09-03", "hasta": "2026-09-03"},
        ]
    client = MagicMock()
    client.query.return_value.result.return_value = filas
    return client


# ── catálogo de canales ──────────────────────────────────────────────────

def test_lee_los_canales_del_corpus():
    canales = catalog.get_available_channels(_client(), "proj", "gold")
    assert [c["channel_name"] for c in canales] == ["Martin Garrix", "Zedd"]
    assert canales[0]["n_comments"] == 1869


def test_consulta_solo_el_corpus_rag():
    """Invariante §8: Fase 2 no lee Bronze, Silver ni la DLQ."""
    client = _client()
    catalog.get_available_channels(client, "proj", "gold")
    sql = client.query.call_args.args[0]
    assert "gold_rag_corpus" in sql
    for prohibido in ("bronze", "silver", "dead_letter"):
        assert prohibido not in sql


def test_respeta_el_tope_de_bytes():
    client = _client()
    catalog.get_available_channels(client, "proj", "gold")
    job_config = client.query.call_args.kwargs["job_config"]
    assert job_config.maximum_bytes_billed == catalog.MAX_BYTES_BILLED


def test_memoiza_para_no_consultar_por_refresh():
    client = _client()
    catalog.get_available_channels(client, "proj", "gold")
    catalog.get_available_channels(client, "proj", "gold")
    assert client.query.call_count == 1


def test_degrada_a_lista_vacia_si_falla():
    """Sin catálogo la bienvenida no lista DJs, pero la página carga."""
    client = MagicMock()
    client.query.side_effect = RuntimeError("403")
    assert catalog.get_available_channels(client, "proj", "gold") == []


def test_un_fallo_no_se_memoiza():
    client = MagicMock()
    client.query.side_effect = RuntimeError("503")
    assert catalog.get_available_channels(client, "proj", "gold") == []

    client.query.side_effect = None
    client.query.return_value.result.return_value = [
        {"channel_name": "Avicii", "n_comments": 368,
         "desde": "2026-08-28", "hasta": "2026-09-05"},
    ]
    canales = catalog.get_available_channels(client, "proj", "gold")
    assert [c["channel_name"] for c in canales] == ["Avicii"]


# ── nombre visible ───────────────────────────────────────────────────────

def test_nombre_de_las_identidades_conocidas():
    assert display_name("diego@talamantes.com.mx") == "Diego"


def test_nombre_cae_a_la_parte_local_si_no_esta_mapeada():
    assert display_name("alguien.nuevo@talamantes.com.mx") == "alguien.nuevo"


def test_nombre_tolera_email_vacio():
    assert display_name("") == ""


def test_toda_identidad_permitida_tiene_nombre():
    from rag_agent.middleware.auth import ALLOWED_EMAILS
    assert ALLOWED_EMAILS <= set(DISPLAY_NAMES)
