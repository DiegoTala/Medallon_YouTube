"""Tests para el middleware de caché."""
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from rag_agent.middleware.cache import get_cached_response, store_response


def test_cache_miss_returns_none():
    db = MagicMock()
    doc = MagicMock()
    doc.exists = False
    db.collection.return_value.document.return_value.get.return_value = doc

    result = get_cached_response(db, "query", {}, "es", "v1", "p1", "m1")
    assert result is None


def test_cache_hit_returns_data():
    db = MagicMock()
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "response": "respuesta",
        "citations": [],
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
    }
    db.collection.return_value.document.return_value.get.return_value = doc

    result = get_cached_response(db, "query", {}, "es", "v1", "p1", "m1")
    assert result is not None
    assert result["response"] == "respuesta"


def test_cache_expired_returns_none():
    db = MagicMock()
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "response": "old",
        "citations": [],
        "expires_at": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    db.collection.return_value.document.return_value.get.return_value = doc

    result = get_cached_response(db, "query", {}, "es", "v1", "p1", "m1")
    assert result is None


def test_store_response_writes_to_firestore():
    db = MagicMock()
    store_response(db, "query", {}, "es", "v1", "p1", "m1", "resp", ["c1"])

    db.collection.return_value.document.return_value.set.assert_called_once()
    call_args = db.collection.return_value.document.return_value.set.call_args[0][0]
    assert call_args["response"] == "resp"
    assert call_args["citations"] == ["c1"]
    assert call_args["hit_count"] == 0
    assert "expires_at" in call_args
