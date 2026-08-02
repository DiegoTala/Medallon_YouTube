"""Ingesta Bronze de comentarios y replies de primer nivel (YouTube Data API v3 -> GCS).

Ver .claude/skills/bronze-ingestion-comments/SKILL.md. Solo procesa videos que ya
pasaron por bronze-ingestion-videos en el mismo batch_execution_id; no valida ni
transforma nada (eso ocurre en silver-validation-comments).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from google.cloud.storage import Bucket
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

PAGE_SIZE = 100


def fetch_comment_threads(youtube: Resource, video_id: str) -> list[dict]:
    """Trae todos los comment threads (con replies) de un video.

    Comentarios deshabilitados (403 commentsDisabled) no son un error de batch:
    el video se registra como "sin comentarios" y se continúa.
    """
    threads: list[dict] = []
    page_token: str | None = None
    try:
        while True:
            resp = (
                youtube.commentThreads()
                .list(
                    part="snippet,replies",
                    videoId=video_id,
                    maxResults=PAGE_SIZE,
                    pageToken=page_token,
                    textFormat="plainText",
                )
                .execute()
            )
            threads.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except HttpError as e:
        if e.resp.status == 403 and "commentsDisabled" in str(e):
            return []
        raise
    return threads


def write_bronze_comments_jsonl(
    all_threads: dict[str, list[dict]], bucket: Bucket, batch_date: datetime, batch_execution_id: str
) -> str:
    """El nombre de archivo incluye `batch_execution_id`: una re-ejecución el mismo
    día genera un archivo nuevo en vez de sobreescribir el anterior (invariante
    de inmutabilidad — ver .claude/skills/bronze-ingestion-comments/SKILL.md)."""
    path = (
        f"raw/anio={batch_date:%Y}/mes={batch_date:%m}/dia={batch_date:%d}"
        f"/comments_batch_data_{batch_execution_id}.json"
    )
    lines = [
        json.dumps({"video_id": video_id, "thread": thread}, ensure_ascii=False)
        for video_id, threads in all_threads.items()
        for thread in threads
    ]
    blob = bucket.blob(path)
    blob.upload_from_string("\n".join(lines), content_type="application/json")
    return path


def run_bronze_comment_ingestion(
    youtube: Resource,
    bucket: Bucket,
    video_ids: list[str],
    batch_execution_id: str,
    batch_date: datetime | None = None,
) -> str:
    """Orquesta la ingesta de comentarios para los videos del batch actual."""
    batch_date = batch_date or datetime.now(timezone.utc)
    all_threads = {video_id: fetch_comment_threads(youtube, video_id) for video_id in video_ids}
    return write_bronze_comments_jsonl(all_threads, bucket, batch_date, batch_execution_id)
