"""Tests de las excepciones de cuota y del circuito de protección agregado.

Ver .claude/skills/rag-quota-limits/SKILL.md.
"""
from unittest.mock import MagicMock

import pytest

from rag_agent.middleware import quota
from rag_agent.middleware.quota import (
    DAILY_QUOTA,
    check_daily_quota,
    check_global_circuit,
    get_quota_remaining,
    quota_limit_for,
)


@pytest.fixture
def _sin_overrides(monkeypatch):
    monkeypatch.delenv("QUOTA_OVERRIDES", raising=False)


def _db(count=0, exists=True):
    db = MagicMock()
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = {"count": count}
    db.collection.return_value.document.return_value.get.return_value = doc
    return db


# ── quota_limit_for ──────────────────────────────────────────────────────

def test_sin_override_todos_tienen_30(_sin_overrides):
    assert quota_limit_for("diego@talamantes.com.mx") == DAILY_QUOTA


def test_override_a_cero_significa_sin_tope(monkeypatch):
    monkeypatch.setenv("QUOTA_OVERRIDES", "diego@talamantes.com.mx=0")
    assert quota_limit_for("diego@talamantes.com.mx") is None


def test_override_a_un_numero_lo_eleva(monkeypatch):
    monkeypatch.setenv("QUOTA_OVERRIDES", "diego@talamantes.com.mx=200")
    assert quota_limit_for("diego@talamantes.com.mx") == 200


def test_el_override_no_alcanza_a_los_demas(monkeypatch):
    monkeypatch.setenv("QUOTA_OVERRIDES", "diego@talamantes.com.mx=0")
    assert quota_limit_for("medallon.rag.test01@talamantes.com.mx") == DAILY_QUOTA


def test_varios_overrides(monkeypatch):
    monkeypatch.setenv(
        "QUOTA_OVERRIDES",
        "diego@talamantes.com.mx=0, medallon.rag.test01@talamantes.com.mx=100",
    )
    assert quota_limit_for("diego@talamantes.com.mx") is None
    assert quota_limit_for("medallon.rag.test01@talamantes.com.mx") == 100


def test_override_es_insensible_a_mayusculas(monkeypatch):
    monkeypatch.setenv("QUOTA_OVERRIDES", "Diego@Talamantes.com.MX=0")
    assert quota_limit_for("diego@talamantes.com.mx") is None


def test_valor_basura_cae_al_limite_normal(monkeypatch):
    """Un override mal escrito no debe abrir la cuota por accidente."""
    monkeypatch.setenv("QUOTA_OVERRIDES", "diego@talamantes.com.mx=muchas")
    assert quota_limit_for("diego@talamantes.com.mx") == DAILY_QUOTA


def test_formato_basura_se_ignora(monkeypatch):
    monkeypatch.setenv("QUOTA_OVERRIDES", "esto no tiene formato")
    assert quota_limit_for("diego@talamantes.com.mx") == DAILY_QUOTA


def test_email_vacio_tiene_limite_normal(monkeypatch):
    monkeypatch.setenv("QUOTA_OVERRIDES", "diego@talamantes.com.mx=0")
    assert quota_limit_for(None) == DAILY_QUOTA
    assert quota_limit_for("") == DAILY_QUOTA


# ── check_daily_quota con override ───────────────────────────────────────

def test_sin_tope_nunca_bloquea_aunque_haya_mil():
    permitido, restantes = check_daily_quota(_db(count=1000), "sub", limit=None)
    assert permitido is True
    assert restantes == -1


def test_sin_tope_sigue_contando():
    """Sin tope no es sin medición: es la única forma de ver el gasto."""
    db = _db(count=1000)
    check_daily_quota(db, "sub", limit=None)
    db.collection.return_value.document.return_value.set.assert_called_once()


def test_con_tope_bloquea_al_llegar():
    permitido, restantes = check_daily_quota(_db(count=30), "sub", limit=30)
    assert permitido is False
    assert restantes == 0


def test_tope_elevado_permite_mas():
    permitido, restantes = check_daily_quota(_db(count=30), "sub", limit=200)
    assert permitido is True
    assert restantes == 169


def test_restantes_sin_tope_es_menos_uno():
    assert get_quota_remaining(_db(count=500), "sub", limit=None) == -1


# ── circuito agregado ────────────────────────────────────────────────────

def test_circuito_permite_por_debajo_del_tope(monkeypatch):
    monkeypatch.setattr(quota, "GLOBAL_DAILY_LIMIT", 300)
    assert check_global_circuit(_db(count=299)) is True


def test_circuito_corta_al_alcanzar_el_tope(monkeypatch):
    monkeypatch.setattr(quota, "GLOBAL_DAILY_LIMIT", 300)
    assert check_global_circuit(_db(count=300)) is False


def test_circuito_no_incrementa_cuando_corta(monkeypatch):
    monkeypatch.setattr(quota, "GLOBAL_DAILY_LIMIT", 300)
    db = _db(count=300)
    check_global_circuit(db)
    db.collection.return_value.document.return_value.set.assert_not_called()


def test_circuito_cuenta_en_un_documento_global(monkeypatch):
    monkeypatch.setattr(quota, "GLOBAL_DAILY_LIMIT", 300)
    db = _db(count=0)
    check_global_circuit(db)
    doc_id = db.collection.return_value.document.call_args.args[0]
    assert doc_id.startswith("_global:")
