import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from medallon_youtube.config import PipelineConfig
from medallon_youtube.main import run_pipeline

VALID_VIDEO_RAW = {
    "id": "dQw4w9WgXcQ",
    "snippet": {
        "title": "Awesome Mix",
        "description": "A test video",
        "channelTitle": "DJ Test",
        "publishedAt": "2026-07-01T12:00:00Z",
    },
    "contentDetails": {"duration": "PT3M30S"},
    "statistics": {"viewCount": "1000", "likeCount": "50"},
}

VALID_COMMENT_THREAD = {
    "snippet": {
        "topLevelComment": {
            "id": "Ugyy1abc2def3ghi",
            "snippet": {
                "authorDisplayName": "TestUser",
                "textOriginal": "Great video!",
                "likeCount": 5,
                "publishedAt": "2026-07-01T12:30:00Z",
            },
        }
    }
}


def _flat_video(raw: dict) -> dict:
    """Aplana el JSON crudo de la API al shape de YouTubeVideoSchema."""
    return {
        "video_id": raw["id"],
        "channel_name": raw["snippet"]["channelTitle"],
        "title": raw["snippet"]["title"],
        "description": raw["snippet"]["description"],
        "published_at": raw["snippet"]["publishedAt"],
        "default_language": None,
        "duration": raw["contentDetails"]["duration"],
        "view_count": int(raw["statistics"]["viewCount"]),
        "like_count": int(raw["statistics"]["likeCount"]),
    }


def test_run_pipeline_executes_layers_in_order() -> None:
    youtube = MagicMock()
    youtube.search.return_value.list.return_value.execute.return_value = {
        "items": [{"id": {"videoId": "dQw4w9WgXcQ"}}]
    }
    youtube.videos.return_value.list.return_value.execute.return_value = {"items": [VALID_VIDEO_RAW]}
    youtube.commentThreads.return_value.list.return_value.execute.return_value = {
        "items": [VALID_COMMENT_THREAD]
    }

    written_blobs: dict[str, str] = {}

    def make_blob(path: str) -> MagicMock:
        blob = MagicMock()

        def upload(content: str, **kwargs: object) -> None:
            written_blobs[path] = content

        blob.upload_from_string.side_effect = upload
        blob.download_as_text.side_effect = lambda: written_blobs[path]
        return blob

    bucket = MagicMock()
    bucket.blob.side_effect = make_blob

    gcs_client = MagicMock()
    gcs_client.bucket.return_value = bucket

    bq_client = MagicMock()
    bq_client.query.return_value.result.return_value = [{"video_id": "dQw4w9WgXcQ"}]

    config = PipelineConfig(
        project_id="proj",
        bronze_bucket="proj-yt-bronze",
        channel_ids=["UC1"],
    )

    run_pipeline(
        youtube,
        gcs_client,
        bq_client,
        config,
        batch_execution_id="batch-1",
        batch_date=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )

    # Bronze escribió ambos archivos, con el batch_execution_id en el nombre
    # (inmutabilidad: una re-ejecución el mismo día no sobreescribe).
    assert "raw/anio=2026/mes=08/dia=02/videos_batch_data_batch-1.json" in written_blobs
    assert "raw/anio=2026/mes=08/dia=02/comments_batch_data_batch-1.json" in written_blobs

    # Silver: videos cargados a staging antes del MERGE, luego comentarios.
    bq_client.load_table_from_json.assert_any_call(
        [_flat_video(VALID_VIDEO_RAW)],
        "proj.silver.staging_youtube_videos",
        job_config=bq_client.load_table_from_json.call_args_list[0].kwargs["job_config"],
    )
    load_calls = bq_client.load_table_from_json.call_args_list
    assert load_calls[0].args[1] == "proj.silver.staging_youtube_videos"
    assert load_calls[1].args[1] == "proj.silver.staging_youtube_comments"

    query_calls = [c.args[0] for c in bq_client.query.call_args_list]
    merge_video_idx = next(i for i, q in enumerate(query_calls) if "silver_youtube_videos" in q and "MERGE" in q)
    known_ids_idx = next(i for i, q in enumerate(query_calls) if "SELECT video_id FROM" in q)
    merge_comment_idx = next(i for i, q in enumerate(query_calls) if "silver_youtube_comments" in q and "MERGE" in q)
    sentiment_idx = next(i for i, q in enumerate(query_calls) if "gold_sentiment_analysis" in q)
    embeddings_idx = next(i for i, q in enumerate(query_calls) if "gold_youtube_embeddings" in q and "INSERT" in q)
    rag_corpus_idx = next(i for i, q in enumerate(query_calls) if "gold_rag_corpus" in q and "MERGE" in q)
    vector_index_idx = next(i for i, q in enumerate(query_calls) if "CREATE VECTOR INDEX" in q)

    assert merge_video_idx < known_ids_idx < merge_comment_idx < sentiment_idx < embeddings_idx < rag_corpus_idx < vector_index_idx
