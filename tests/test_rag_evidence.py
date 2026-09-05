"""Tests del nivel de evidencia y de qué no se cachea.

Con 3,261 comentarios en 7 canales, Zedd tiene 6 y Martin Garrix 1,869.
Comparar sus porcentajes es aritmética sin significado, y hasta ahora se
reportaba con el mismo aplomo que una muestra de mil filas.
"""
from unittest.mock import MagicMock

from rag_agent.middleware.citations import es_cacheable
from rag_agent.tools.evidence import INSUFFICIENT_BELOW, WEAK_BELOW, evidence_level
from rag_agent.tools.sentiment_analytics import sentiment_analytics


# ── la escala ────────────────────────────────────────────────────────────

def test_los_tres_niveles():
    assert evidence_level(10) == "insufficient"
    assert evidence_level(50) == "weak"
    assert evidence_level(500) == "solid"


def test_manda_la_muestra_mas_pequena():
    """Una comparación vale lo que vale su lado más flaco."""
    assert evidence_level(1869, 6) == "insufficient"
    assert evidence_level(1869, 90) == "weak"
    assert evidence_level(1869, 500) == "solid"


def test_sin_muestras_es_insuficiente():
    assert evidence_level() == "insufficient"


def test_los_umbrales_son_los_del_skill():
    assert (INSUFFICIENT_BELOW, WEAK_BELOW) == (30, 100)


def test_trend_detection_usa_la_misma_escala():
    """Estaba duplicada dentro de trend_detection y solo se aplicaba ahí."""
    from rag_agent.tools.trend_detection import _evidence_level

    assert _evidence_level(1869, 6) == evidence_level(1869, 6)
    assert _evidence_level(200, 200) == "solid"


# ── sentiment_analytics ──────────────────────────────────────────────────

def _client(rows):
    client = MagicMock()
    client.query.return_value.result.return_value = rows
    return client


def test_compare_channels_se_mide_por_el_canal_mas_flaco():
    rows = [
        {"channel_name": "Martin Garrix", "sentiment_label": "POSITIVO", "n": 1869, "pct": 82.0},
        {"channel_name": "Zedd", "sentiment_label": "POSITIVO", "n": 6, "pct": 100.0},
    ]
    r = sentiment_analytics(_client(rows), "p", "gold", "compare_channels",
                            channels=["Martin Garrix", "Zedd"])
    assert r["evidence_level"] == "insufficient"
    assert r["sample_sizes"] == {"Martin Garrix": 1869, "Zedd": 6}


def test_distribucion_de_un_canal_suma_sus_filas():
    rows = [
        {"sentiment_label": "POSITIVO", "n": 200, "pct": 80.0},
        {"sentiment_label": "NEGATIVO", "n": 50, "pct": 20.0},
    ]
    r = sentiment_analytics(_client(rows), "p", "gold", "distribution_by_channel",
                            channel_name="ILLENIUM")
    assert r["evidence_level"] == "solid"
    assert r["sample_sizes"] == {"total": 250}


def test_evolucion_se_mide_por_el_mes_mas_flaco():
    rows = [
        {"month": "2026-07", "sentiment_label": "POSITIVO", "n": 400},
        {"month": "2026-09", "sentiment_label": "POSITIVO", "n": 8},
    ]
    r = sentiment_analytics(_client(rows), "p", "gold", "evolution_over_time")
    assert r["evidence_level"] == "insufficient"
    assert r["sample_sizes"] == {"2026-07": 400, "2026-09": 8}


def test_sin_filas_es_insuficiente():
    r = sentiment_analytics(_client([]), "p", "gold", "distribution_by_channel",
                            channel_name="Nadie")
    assert r["evidence_level"] == "insufficient"


def test_toda_respuesta_lleva_evidencia():
    """Ninguna herramienta devuelve un porcentaje sin decir sobre cuántas filas."""
    rows = [{"sentiment_label": "POSITIVO", "n": 10, "pct": 100.0}]
    r = sentiment_analytics(_client(rows), "p", "gold", "distribution_by_channel")
    assert "evidence_level" in r
    assert "sample_sizes" in r


# ── qué no se cachea ─────────────────────────────────────────────────────

def test_no_se_cachea_evidencia_insuficiente():
    """Una conclusión de 6 comentarios no debe ser la respuesta permanente a
    esa pregunta durante 7 días."""
    assert es_cacheable([("sentiment_analytics",
                          {"status": "success", "evidence_level": "insufficient"})]) is False


def test_no_se_cachea_evidencia_debil():
    assert es_cacheable([("sentiment_analytics",
                          {"status": "success", "evidence_level": "weak"})]) is False


def test_si_se_cachea_evidencia_solida():
    assert es_cacheable([("sentiment_analytics",
                          {"status": "success", "evidence_level": "solid"})]) is True


def test_no_se_cachean_los_errores():
    """Un 503 transitorio de BigQuery no debe volverse la respuesta a esa
    pregunta durante una semana."""
    assert es_cacheable([("semantic_search", {"status": "error", "error": "503"})]) is False


def test_una_sola_herramienta_debil_basta_para_no_cachear():
    assert es_cacheable([
        ("semantic_search", {"status": "success"}),
        ("sentiment_analytics", {"status": "success", "evidence_level": "weak"}),
    ]) is False


def test_sin_herramientas_se_puede_cachear():
    """Un saludo o un rechazo de dominio no pasa por ninguna herramienta."""
    assert es_cacheable([]) is True
