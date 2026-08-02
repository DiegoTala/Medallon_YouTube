import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from medallon_youtube.bronze.videos import (
    fetch_recent_videos,
    load_channel_ids,
    run_bronze_video_ingestion,
    write_bronze_jsonl,
)


def test_load_channel_ids_parses_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHANNEL_IDS", "UC1, UC2 ,UC3")
    assert load_channel_ids() == ["UC1", "UC2", "UC3"]


def test_load_channel_ids_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHANNEL_IDS", raising=False)
    with pytest.raises(ValueError):
        load_channel_ids()


def _mock_youtube(search_pages: list[dict], video_details: dict) -> MagicMock:
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute.side_effect = search_pages
    youtube.videos.return_value.list.return_value.execute.return_value = video_details
    return youtube


def test_fetch_recent_videos_single_page() -> None:
    search_pages = [
        {"items": [{"id": {"videoId": "v1"}}, {"id": {"videoId": "v2"}}]},
    ]
    video_details = {"items": [{"id": "v1", "snippet": {}}, {"id": "v2", "snippet": {}}]}
    youtube = _mock_youtube(search_pages, video_details)

    result = fetch_recent_videos(youtube, "UC1")

    assert [v["id"] for v in result] == ["v1", "v2"]


def test_fetch_recent_videos_paginates() -> None:
    page1 = {"items": [{"id": {"videoId": f"v{i}"}} for i in range(50)], "nextPageToken": "tok"}
    page2 = {"items": [{"id": {"videoId": "v50"}}]}
    detail_chunk1 = {"items": [{"id": f"v{i}"} for i in range(50)]}
    detail_chunk2 = {"items": [{"id": "v50"}]}
    youtube = _mock_youtube([page1, page2], detail_chunk1)
    youtube.videos.return_value.list.return_value.execute.side_effect = [detail_chunk1, detail_chunk2]

    result = fetch_recent_videos(youtube, "UC1")

    assert len(result) == 51
    assert youtube.search.return_value.list.return_value.execute.call_count == 2


def test_fetch_recent_videos_caps_at_100() -> None:
    page1 = {"items": [{"id": {"videoId": f"v{i}"}} for i in range(50)], "nextPageToken": "tok"}
    page2 = {"items": [{"id": {"videoId": f"v{i}"}} for i in range(50, 120)], "nextPageToken": "tok2"}
    detail_chunk1 = {"items": [{"id": f"v{i}"} for i in range(50)]}
    detail_chunk2 = {"items": [{"id": f"v{i}"} for i in range(50, 100)]}
    youtube = _mock_youtube([page1, page2], detail_chunk1)
    youtube.videos.return_value.list.return_value.execute.side_effect = [detail_chunk1, detail_chunk2]

    result = fetch_recent_videos(youtube, "UC1")

    assert len(result) == 100
    videos_list_call = youtube.videos.return_value.list
    assert videos_list_call.call_count == 2


def test_write_bronze_jsonl_partitions_by_execution_date() -> None:
    bucket = MagicMock()
    blob = MagicMock()
    bucket.blob.return_value = blob
    records = [{"id": "v1"}, {"id": "v2"}]
    batch_date = datetime(2026, 8, 2, tzinfo=timezone.utc)

    path = write_bronze_jsonl(records, bucket, batch_date, "batch-1")

    assert path == "raw/anio=2026/mes=08/dia=02/videos_batch_data_batch-1.json"
    bucket.blob.assert_called_once_with(path)
    written = blob.upload_from_string.call_args.args[0]
    lines = written.split("\n")
    assert [json.loads(line)["id"] for line in lines] == ["v1", "v2"]


def test_run_bronze_video_ingestion_aggregates_all_channels() -> None:
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute.side_effect = [
        {"items": [{"id": {"videoId": "v1"}}]},
        {"items": [{"id": {"videoId": "v2"}}]},
    ]
    youtube.videos.return_value.list.return_value.execute.side_effect = [
        {"items": [{"id": "v1"}]},
        {"items": [{"id": "v2"}]},
    ]
    bucket = MagicMock()
    blob = MagicMock()
    bucket.blob.return_value = blob

    path, videos_raw = run_bronze_video_ingestion(
        youtube, bucket, ["UC1", "UC2"], "batch-1", batch_date=datetime(2026, 8, 2, tzinfo=timezone.utc)
    )

    assert path == "raw/anio=2026/mes=08/dia=02/videos_batch_data_batch-1.json"
    assert [v["id"] for v in videos_raw] == ["v1", "v2"]
    written = blob.upload_from_string.call_args.args[0]
    ids = [json.loads(line)["id"] for line in written.split("\n")]
    assert ids == ["v1", "v2"]
