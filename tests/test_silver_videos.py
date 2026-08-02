import json
from unittest.mock import MagicMock

from medallon_youtube.silver.videos import (
    load_staging_videos,
    merge_videos_to_silver,
    validate_video_batch,
)

VALID_VIDEO = {
    "video_id": "dQw4w9WgXcQ",
    "channel_name": "DJ Test",
    "title": "Awesome Mix",
    "description": "A test video",
    "published_at": "2026-07-01T12:00:00Z",
    "default_language": "en",
    "duration": "PT3M30S",
    "view_count": 1000,
    "like_count": 50,
}

INVALID_VIDEO = {**VALID_VIDEO, "title": "   "}


def test_validate_video_batch_splits_valid_and_dead_letters() -> None:
    raw_lines = [json.dumps(VALID_VIDEO), json.dumps(INVALID_VIDEO)]

    valid, dead_letters = validate_video_batch(raw_lines, "batch-1")

    assert len(valid) == 1
    assert valid[0].video_id == "dQw4w9WgXcQ"
    assert len(dead_letters) == 1
    assert dead_letters[0]["video_id"] == "dQw4w9WgXcQ"
    assert dead_letters[0]["batch_execution_id"] == "batch-1"


def test_validate_video_batch_reprocess_is_deterministic() -> None:
    raw_lines = [json.dumps(VALID_VIDEO)]
    valid1, dead1 = validate_video_batch(raw_lines, "batch-1")
    valid2, dead2 = validate_video_batch(raw_lines, "batch-2")
    assert len(valid1) == len(valid2) == 1
    assert dead1 == dead2 == []


def test_load_staging_videos_noop_on_empty() -> None:
    client = MagicMock()
    load_staging_videos(client, "staging", [])
    client.load_table_from_json.assert_not_called()


def test_load_staging_videos_loads_records() -> None:
    client = MagicMock()
    job = MagicMock()
    client.load_table_from_json.return_value = job
    valid, _ = validate_video_batch([json.dumps(VALID_VIDEO)], "batch-1")

    load_staging_videos(client, "proj.ds.staging_youtube_videos", valid)

    client.load_table_from_json.assert_called_once()
    args, kwargs = client.load_table_from_json.call_args
    assert args[0][0]["video_id"] == "dQw4w9WgXcQ"
    assert args[1] == "proj.ds.staging_youtube_videos"
    job.result.assert_called_once()


def test_merge_videos_to_silver_runs_merge_then_truncate() -> None:
    client = MagicMock()
    job = MagicMock()
    client.query.return_value = job

    merge_videos_to_silver(client, "proj.ds.silver_youtube_videos", "proj.ds.staging_youtube_videos")

    assert client.query.call_count == 2
    merge_call, truncate_call = client.query.call_args_list
    assert "MERGE INTO" in merge_call.args[0]
    assert "silver_youtube_videos" in merge_call.args[0]
    assert "TRUNCATE TABLE" in truncate_call.args[0]
    assert "staging_youtube_videos" in truncate_call.args[0]
