import json
from unittest.mock import MagicMock

from medallon_youtube.silver.comments import (
    fetch_known_video_ids,
    load_staging_comments,
    merge_comments_to_silver,
    validate_comment_batch,
)

VALID_COMMENT = {
    "comment_id": "Ugyy1abc2def3ghi",
    "video_id": "dQw4w9WgXcQ",
    "author": "TestUser",
    "comment_text": "Great video!",
    "like_count": 5,
    "published_at": "2026-07-01T12:30:00Z",
}

KNOWN_VIDEO_IDS = {"dQw4w9WgXcQ"}


def test_fetch_known_video_ids_returns_set() -> None:
    client = MagicMock()
    client.query.return_value.result.return_value = [{"video_id": "v1"}, {"video_id": "v2"}]

    result = fetch_known_video_ids(client, "proj.ds.silver_youtube_videos")

    assert result == {"v1", "v2"}


def test_validate_comment_batch_accepts_known_video() -> None:
    raw_lines = [json.dumps(VALID_COMMENT)]

    valid, dead_letters = validate_comment_batch(raw_lines, KNOWN_VIDEO_IDS, "batch-1")

    assert len(valid) == 1
    assert dead_letters == []


def test_validate_comment_batch_rejects_pydantic_failure() -> None:
    invalid = {**VALID_COMMENT, "comment_text": "   "}
    raw_lines = [json.dumps(invalid)]

    valid, dead_letters = validate_comment_batch(raw_lines, KNOWN_VIDEO_IDS, "batch-1")

    assert valid == []
    assert len(dead_letters) == 1
    assert dead_letters[0]["comment_id"] == VALID_COMMENT["comment_id"]


def test_validate_comment_batch_rejects_orphan_video_id() -> None:
    orphan = {**VALID_COMMENT, "video_id": "unknownVideoId"}
    raw_lines = [json.dumps(orphan)]

    valid, dead_letters = validate_comment_batch(raw_lines, KNOWN_VIDEO_IDS, "batch-1")

    assert valid == []
    assert len(dead_letters) == 1
    assert dead_letters[0]["error_field"] == "video_id"
    assert "no existe en silver_youtube_videos" in dead_letters[0]["validation_error"]


def test_load_staging_comments_noop_on_empty() -> None:
    client = MagicMock()
    load_staging_comments(client, "staging", [])
    client.load_table_from_json.assert_not_called()


def test_merge_comments_to_silver_runs_merge_then_truncate() -> None:
    client = MagicMock()
    client.query.return_value = MagicMock()

    merge_comments_to_silver(client, "proj.ds.silver_youtube_comments", "proj.ds.staging_youtube_comments")

    assert client.query.call_count == 2
    merge_call, truncate_call = client.query.call_args_list
    assert "MERGE INTO" in merge_call.args[0]
    assert "silver_youtube_comments" in merge_call.args[0]
    assert "TRUNCATE TABLE" in truncate_call.args[0]
