import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from googleapiclient.errors import HttpError

from medallon_youtube.bronze.comments import (
    fetch_comment_threads,
    run_bronze_comment_ingestion,
    write_bronze_comments_jsonl,
)


def test_fetch_comment_threads_paginates() -> None:
    page1 = {"items": [{"id": "c1"}], "nextPageToken": "tok"}
    page2 = {"items": [{"id": "c2"}]}
    youtube = MagicMock()
    youtube.commentThreads.return_value.list.return_value.execute.side_effect = [page1, page2]

    result = fetch_comment_threads(youtube, "v1")

    assert [t["id"] for t in result] == ["c1", "c2"]


def test_fetch_comment_threads_disabled_returns_empty() -> None:
    youtube = MagicMock()
    response = MagicMock(status=403)
    content = (
        b'{"error": {"errors": [{"reason": "commentsDisabled"}], '
        b'"message": "The video has disabled comments (commentsDisabled)."}}'
    )
    error = HttpError(response, content)
    youtube.commentThreads.return_value.list.return_value.execute.side_effect = error

    result = fetch_comment_threads(youtube, "v1")

    assert result == []


def test_fetch_comment_threads_other_http_error_raises() -> None:
    youtube = MagicMock()
    response = MagicMock(status=500)
    error = HttpError(response, b'{"error": {"errors": [{"reason": "backendError"}]}}')
    youtube.commentThreads.return_value.list.return_value.execute.side_effect = error

    try:
        fetch_comment_threads(youtube, "v1")
        assert False, "Expected HttpError to propagate"
    except HttpError:
        pass


def test_write_bronze_comments_jsonl_flattens_by_video() -> None:
    bucket = MagicMock()
    blob = MagicMock()
    bucket.blob.return_value = blob
    all_threads = {"v1": [{"id": "c1"}, {"id": "c2"}], "v2": [{"id": "c3"}]}
    batch_date = datetime(2026, 8, 2, tzinfo=timezone.utc)

    path = write_bronze_comments_jsonl(all_threads, bucket, batch_date, "batch-1")

    assert path == "raw/anio=2026/mes=08/dia=02/comments_batch_data_batch-1.json"
    written = blob.upload_from_string.call_args.args[0]
    lines = [json.loads(line) for line in written.split("\n")]
    assert [(line["video_id"], line["thread"]["id"]) for line in lines] == [
        ("v1", "c1"),
        ("v1", "c2"),
        ("v2", "c3"),
    ]


def test_run_bronze_comment_ingestion_covers_all_videos() -> None:
    youtube = MagicMock()
    youtube.commentThreads.return_value.list.return_value.execute.side_effect = [
        {"items": [{"id": "c1"}]},
        {"items": [{"id": "c2"}]},
    ]
    bucket = MagicMock()
    blob = MagicMock()
    bucket.blob.return_value = blob

    path = run_bronze_comment_ingestion(
        youtube, bucket, ["v1", "v2"], "batch-1", batch_date=datetime(2026, 8, 2, tzinfo=timezone.utc)
    )

    assert path == "raw/anio=2026/mes=08/dia=02/comments_batch_data_batch-1.json"
    written = blob.upload_from_string.call_args.args[0]
    video_ids = [json.loads(line)["video_id"] for line in written.split("\n")]
    assert video_ids == ["v1", "v2"]
