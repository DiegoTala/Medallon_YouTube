"""Validación Pydantic + carga staging + MERGE idempotente para silver_youtube_videos.

Ver .claude/skills/silver-validation-videos/SKILL.md.
"""

from __future__ import annotations

import json
from typing import Any

from google.cloud import bigquery
from pydantic import ValidationError

from medallon_youtube.schemas import YouTubeVideoSchema
from medallon_youtube.silver.dead_letter import build_dead_letter_row

MERGE_SQL_TEMPLATE = """
MERGE INTO `{silver_table}` T
USING `{staging_table}` S
ON T.video_id = S.video_id
WHEN MATCHED THEN
  UPDATE SET
    T.view_count = S.view_count,
    T.like_count = S.like_count,
    T.updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (video_id, channel_name, title, description, published_at, default_language, duration, view_count, like_count, ingested_at)
  VALUES (S.video_id, S.channel_name, S.title, S.description, S.published_at, S.default_language, S.duration, S.view_count, S.like_count, CURRENT_TIMESTAMP());
"""


def validate_video_batch(
    raw_lines: list[str], batch_execution_id: str
) -> tuple[list[YouTubeVideoSchema], list[dict[str, Any]]]:
    """Separa registros válidos de rechazados. Ningún registro se descarta sin rastro."""
    valid: list[YouTubeVideoSchema] = []
    dead_letters: list[dict[str, Any]] = []

    for line in raw_lines:
        raw = json.loads(line)
        try:
            valid.append(YouTubeVideoSchema.model_validate(raw))
        except ValidationError as e:
            dead_letters.append(
                build_dead_letter_row(
                    e, raw, batch_execution_id, video_id=raw.get("video_id"), comment_id=None
                )
            )
    return valid, dead_letters


def load_staging_videos(client: bigquery.Client, staging_table: str, records: list[YouTubeVideoSchema]) -> None:
    """Carga por load job (no streaming insert, para evitar costos de streaming)."""
    if not records:
        return
    rows = [json.loads(r.model_dump_json()) for r in records]
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.load_table_from_json(rows, staging_table, job_config=job_config)
    job.result()


def merge_videos_to_silver(client: bigquery.Client, silver_table: str, staging_table: str) -> None:
    """Aplica el MERGE idempotente y trunca staging inmediatamente después (obligatorio)."""
    merge_sql = MERGE_SQL_TEMPLATE.format(silver_table=silver_table, staging_table=staging_table)
    client.query(merge_sql).result()
    client.query(f"TRUNCATE TABLE `{staging_table}`").result()
