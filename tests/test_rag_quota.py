"""Tests para el middleware de cuota y rate limit."""
from unittest.mock import MagicMock, patch

from rag_agent.middleware.quota import (
    DAILY_QUOTA,
    RATE_LIMIT_PER_MINUTE,
    check_daily_quota,
    check_rate_limit,
    get_quota_remaining,
)


def test_rate_limit_allows_under_limit():
    db = MagicMock()
    doc = MagicMock()
    doc.exists = False
    db.collection.return_value.document.return_value.get.return_value = doc

    result = check_rate_limit(db, "user1")
    assert result is True


def test_rate_limit_blocks_at_limit():
    db = MagicMock()
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"count": RATE_LIMIT_PER_MINUTE}
    db.collection.return_value.document.return_value.get.return_value = doc

    result = check_rate_limit(db, "user1")
    assert result is False


def test_daily_quota_allows_under_limit():
    db = MagicMock()
    doc = MagicMock()
    doc.exists = False
    db.collection.return_value.document.return_value.get.return_value = doc

    allowed, remaining = check_daily_quota(db, "user1")
    assert allowed is True
    assert remaining == DAILY_QUOTA - 1


def test_daily_quota_blocks_at_limit():
    db = MagicMock()
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"count": DAILY_QUOTA}
    db.collection.return_value.document.return_value.get.return_value = doc

    allowed, remaining = check_daily_quota(db, "user1")
    assert allowed is False
    assert remaining == 0


def test_get_quota_remaining_no_doc():
    db = MagicMock()
    doc = MagicMock()
    doc.exists = False
    db.collection.return_value.document.return_value.get.return_value = doc

    assert get_quota_remaining(db, "user1") == DAILY_QUOTA


def test_get_quota_remaining_with_usage():
    db = MagicMock()
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"count": 10}
    db.collection.return_value.document.return_value.get.return_value = doc

    assert get_quota_remaining(db, "user1") == DAILY_QUOTA - 10
