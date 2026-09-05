"""Tests para el middleware de sanitización."""
from rag_agent.middleware.sanitize import MAX_QUERY_LENGTH, sanitize


def test_sanitize_normalizes_nfkc():
    # Caracteres Unicode visualmente idénticos deben normalizarse igual
    result = sanitize("café")  # é ya es NFKC
    assert result == "café"


def test_sanitize_removes_control_characters():
    result = sanitize("hola\x00mundo\x01\x02")
    assert result == "holamundo"


def test_sanitize_preserves_newlines():
    result = sanitize("línea uno\nlínea dos")
    assert result == "línea uno\nlínea dos"


def test_sanitize_removes_tab_characters():
    # Tabs son category "Cc" (control) — se eliminan, no se colapsan
    result = sanitize("hola\t\tmundo")
    assert result == "holamundo"


def test_sanitize_truncates_at_500():
    long_text = "a" * 600
    result = sanitize(long_text)
    assert len(result) == MAX_QUERY_LENGTH


def test_sanitize_strips_edges():
    result = sanitize("  hola mundo  ")
    assert result == "hola mundo"


def test_sanitize_empty_string():
    result = sanitize("")
    assert result == ""


def test_sanitize_only_control_chars():
    result = sanitize("\x00\x01\x02")
    assert result == ""
