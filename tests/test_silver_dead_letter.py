from unittest.mock import MagicMock

from pydantic import ValidationError

from medallon_youtube.schemas import YouTubeVideoSchema
from medallon_youtube.silver.dead_letter import build_dead_letter_row, insert_dead_letters


def _validation_error() -> ValidationError:
    try:
        YouTubeVideoSchema(
            video_id="dQw4w9WgXcQ",
            channel_name="DJ",
            title="",
            description="d",
            published_at="2026-07-01T00:00:00Z",
            duration="PT1M",
            view_count=1,
            like_count=1,
        )
    except ValidationError as e:
        return e
    raise AssertionError("expected ValidationError")


def test_build_dead_letter_row_captures_first_error_field() -> None:
    error = _validation_error()
    raw = {"video_id": "dQw4w9WgXcQ", "title": ""}

    row = build_dead_letter_row(error, raw, "batch-1", video_id="dQw4w9WgXcQ")

    assert row["video_id"] == "dQw4w9WgXcQ"
    assert row["comment_id"] is None
    assert row["batch_execution_id"] == "batch-1"
    assert row["raw_payload"] == raw
    assert "title" in row["error_field"]


def test_insert_dead_letters_noop_on_empty() -> None:
    client = MagicMock()
    insert_dead_letters(client, "table", [])
    client.insert_rows_json.assert_not_called()


def test_insert_dead_letters_raises_on_errors() -> None:
    client = MagicMock()
    client.insert_rows_json.return_value = [{"index": 0, "errors": ["boom"]}]
    try:
        insert_dead_letters(client, "table", [{"a": 1}])
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


def test_insert_dead_letters_success() -> None:
    client = MagicMock()
    client.insert_rows_json.return_value = []
    insert_dead_letters(client, "table", [{"a": 1}])
    client.insert_rows_json.assert_called_once_with("table", [{"a": 1}])
