"""Tests de las versiones que componen la clave del caché.

Ver .claude/skills/rag-response-cache/SKILL.md.
"""
from unittest.mock import MagicMock

import pytest

from rag_agent import versions
from rag_agent.utils.normalize import cache_key


@pytest.fixture(autouse=True)
def _limpia_memo():
    versions.reset_cache()
    yield
    versions.reset_cache()


def _client(version="20260904T221500Z"):
    client = MagicMock()
    client.query.return_value.result.return_value = [{"version": version}]
    return client


def test_lee_la_version_del_corpus():
    client = _client()
    assert versions.get_corpus_version(client, "proj", "gold") == "20260904T221500Z"
    sql = client.query.call_args.args[0]
    assert "gold_rag_corpus" in sql
    assert "MAX(updated_at)" in sql


def test_memoiza_para_no_consultar_por_request():
    client = _client()
    versions.get_corpus_version(client, "proj", "gold")
    versions.get_corpus_version(client, "proj", "gold")
    assert client.query.call_count == 1


def test_respeta_el_tope_de_bytes():
    client = _client()
    versions.get_corpus_version(client, "proj", "gold")
    job_config = client.query.call_args.kwargs["job_config"]
    assert job_config.maximum_bytes_billed == versions.MAX_BYTES_BILLED


def test_devuelve_none_si_bigquery_falla():
    """None significa 'no sé contra qué datos estoy' — quien llama salta el caché
    en vez de sustituir un valor fijo que serviría respuestas viejas."""
    client = MagicMock()
    client.query.side_effect = RuntimeError("403")
    assert versions.get_corpus_version(client, "proj", "gold") is None


def test_devuelve_none_si_el_corpus_esta_vacio():
    client = MagicMock()
    client.query.return_value.result.return_value = [{"version": None}]
    assert versions.get_corpus_version(client, "proj", "gold") is None


def test_un_fallo_no_se_memoiza():
    client = MagicMock()
    client.query.side_effect = RuntimeError("503 transitorio")
    assert versions.get_corpus_version(client, "proj", "gold") is None

    client.query.side_effect = None
    client.query.return_value.result.return_value = [{"version": "20260905T000000Z"}]
    assert versions.get_corpus_version(client, "proj", "gold") == "20260905T000000Z"


# ── invalidación por clave (el mecanismo completo) ───────────────────────

def test_cambiar_la_version_del_corpus_cambia_la_clave():
    a = cache_key("q", {}, "es", "v1", versions.PROMPT_VERSION, "gemini-2.5-flash")
    b = cache_key("q", {}, "es", "v2", versions.PROMPT_VERSION, "gemini-2.5-flash")
    assert a != b


def test_cambiar_la_version_del_prompt_cambia_la_clave():
    a = cache_key("q", {}, "es", "v1", "2026-09-05.1", "gemini-2.5-flash")
    b = cache_key("q", {}, "es", "v1", "2026-09-05.2", "gemini-2.5-flash")
    assert a != b


def test_cambiar_el_modelo_cambia_la_clave():
    a = cache_key("q", {}, "es", "v1", versions.PROMPT_VERSION, "gemini-2.5-flash")
    b = cache_key("q", {}, "es", "v1", versions.PROMPT_VERSION, "gemini-3-pro")
    assert a != b


def test_las_versiones_vacias_eran_el_bug():
    """Antes del fix, main.py pasaba "" en los tres componentes versionados:
    todas las respuestas del historial del proyecto colapsaban en la misma clave."""
    con_version = cache_key("q", {}, "es", "20260904T221500Z", versions.PROMPT_VERSION, "gemini-2.5-flash")
    sin_version = cache_key("q", {}, "es", "", "", "")
    assert con_version != sin_version
