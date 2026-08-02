"""Ingesta Bronze de metadatos de video (YouTube Data API v3 -> GCS).

Ver .claude/skills/bronze-ingestion-videos/SKILL.md. Esta capa no valida ni
transforma: persiste la respuesta cruda de la API tal cual, particionada por
fecha de ejecución del batch.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from google.cloud.storage import Bucket
from googleapiclient.discovery import Resource, build

MAX_VIDEOS_PER_CHANNEL = 100
PAGE_SIZE = 50


def load_channel_ids() -> list[str]:
    """Lee los 5 canales configurados desde la variable de entorno CHANNEL_IDS.

    Nunca hardcodeados en el código (invariante de bronze-ingestion-videos).
    """
    raw = os.environ.get("CHANNEL_IDS", "")
    channel_ids = [c.strip() for c in raw.split(",") if c.strip()]
    if not channel_ids:
        raise ValueError("CHANNEL_IDS no está configurado (se esperan 5 canales separados por coma)")
    return channel_ids


def build_youtube_client(api_key: str) -> Resource:
    return build("youtube", "v3", developerKey=api_key)


def fetch_recent_videos(youtube: Resource, channel_id: str, days: int = 7) -> list[dict]:
    """Trae, para un canal, los videos publicados en los últimos `days` días.

    Tope duro de MAX_VIDEOS_PER_CHANNEL por canal por corrida (matriz de riesgos del PRD).
    """
    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    video_ids: list[str] = []
    page_token: str | None = None

    while True:
        resp = (
            youtube.search()
            .list(
                part="id",
                channelId=channel_id,
                publishedAfter=published_after,
                type="video",
                maxResults=PAGE_SIZE,
                pageToken=page_token,
            )
            .execute()
        )
        video_ids.extend(item["id"]["videoId"] for item in resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token or len(video_ids) >= MAX_VIDEOS_PER_CHANNEL:
            break

    video_ids = video_ids[:MAX_VIDEOS_PER_CHANNEL]
    videos_raw: list[dict] = []
    for i in range(0, len(video_ids), PAGE_SIZE):
        chunk = video_ids[i : i + PAGE_SIZE]
        detail = youtube.videos().list(part="snippet,contentDetails,statistics", id=",".join(chunk)).execute()
        videos_raw.extend(detail.get("items", []))
    return videos_raw


def write_bronze_jsonl(records: list[dict], bucket: Bucket, batch_date: datetime, batch_execution_id: str) -> str:
    """Escribe los registros crudos como JSON Lines, particionado por fecha de ejecución.

    El nombre de archivo incluye `batch_execution_id`: una re-ejecución el mismo
    día genera un archivo nuevo en vez de sobreescribir el anterior (invariante
    de inmutabilidad — ver .claude/skills/bronze-ingestion-videos/SKILL.md).
    """
    path = (
        f"raw/anio={batch_date:%Y}/mes={batch_date:%m}/dia={batch_date:%d}"
        f"/videos_batch_data_{batch_execution_id}.json"
    )
    blob = bucket.blob(path)
    blob.upload_from_string(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        content_type="application/json",
    )
    return path


def run_bronze_video_ingestion(
    youtube: Resource,
    bucket: Bucket,
    channel_ids: list[str],
    batch_execution_id: str,
    batch_date: datetime | None = None,
    days: int = 7,
) -> tuple[str, list[dict]]:
    """Orquesta la ingesta de videos para todos los canales configurados y la persiste en GCS.

    Devuelve también los registros crudos: el orquestador del pipeline (main.py)
    los necesita para extraer los video_id que alimentan bronze-ingestion-comments,
    sin tener que releer el blob recién escrito.
    """
    batch_date = batch_date or datetime.now(timezone.utc)
    all_videos: list[dict] = []
    for channel_id in channel_ids:
        all_videos.extend(fetch_recent_videos(youtube, channel_id, days=days))
    path = write_bronze_jsonl(all_videos, bucket, batch_date, batch_execution_id)
    return path, all_videos
