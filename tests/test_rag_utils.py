"""Tests para las utilidades de normalización."""
from rag_agent.utils.normalize import cache_key, normalize_query, query_hash


def test_normalize_query_lowercase():
    assert normalize_query("Hola MUNDO") == "hola mundo"


def test_normalize_query_collapses_spaces():
    assert normalize_query("  mucho   espacio  ") == "mucho espacio"


def test_normalize_query_strips():
    assert normalize_query("  hola  ") == "hola"


def test_query_hash_deterministic():
    h1 = query_hash("hola mundo", {}, "es")
    h2 = query_hash("hola mundo", {}, "es")
    assert h1 == h2


def test_query_hash_differs_by_language():
    h1 = query_hash("hola", {}, "es")
    h2 = query_hash("hola", {}, "en")
    assert h1 != h2


def test_query_hash_differs_by_filter():
    h1 = query_hash("hola", {"channel": "A"}, "es")
    h2 = query_hash("hola", {"channel": "B"}, "es")
    assert h1 != h2


def test_cache_key_includes_versions():
    k1 = cache_key("q", {}, "es", "v1", "p1", "m1")
    k2 = cache_key("q", {}, "es", "v2", "p1", "m1")
    assert k1 != k2


def test_cache_key_personalized_by_user():
    k1 = cache_key("q", {}, "es", "v1", "p1", "m1", user_id="u1")
    k2 = cache_key("q", {}, "es", "v1", "p1", "m1", user_id="u2")
    k3 = cache_key("q", {}, "es", "v1", "p1", "m1", user_id=None)
    assert k1 != k2
    assert k1 != k3
