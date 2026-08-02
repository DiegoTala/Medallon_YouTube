"""Validación Pydantic + integridad referencial + carga staging + MERGE idempotente
para silver_youtube_comments.

Ver .claude/skills/silver-validation-comments/SKILL.md. Depende de que
silver-validation-videos ya haya corrido su MERGE en el mismo batch: ningún
comentario huérfano entra a silver_youtube_comments.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from google.cloud import bigquery
from pydantic import ValidationError

from medallon_youtube.schemas import YouTubeCommentSchema
from medallon_youtube.silver.dead_letter import build_dead_letter_row

MERGE_SQL_TEMPLATE = """
MERGE INTO `{silver_table}` T
USING `{staging_table}` S
ON T.comment_id = S.comment_id
WHEN MATCHED THEN
  UPDATE SET
    T.like_count = S.like_count,
    T.updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (comment_id, video_id, author, comment_text, like_count, published_at, ingested_at)
  VALUES (S.comment_id, S.video_id, S.author, S.comment_text, S.like_count, S.published_at, CURRENT_TIMESTAMP());
"""


def fetch_known_video_ids(client: bigquery.Client, silver_videos_table: str) -> set[str]:
    """SELECT video_id FROM silver_youtube_videos, para la verificación de integridad referencial."""
    rows = client.query(f"SELECT video_id FROM `{silver_videos_table}`").result()
    return {row["video_id"] for row in rows}


def validate_comment_batch(
    raw_lines: list[str],
    known_video_ids: set[str],
    batch_execution_id: str,
) -> tuple[list[YouTubeCommentSchema], list[dict[str, Any]]]:
    valid: list[YouTubeCommentSchema] = []
    dead_letters: list[dict[str, Any]] = []

    for line in raw_lines:
        raw = json.loads(line)
        try:
            record = YouTubeCommentSchema.model_validate(raw)
        except ValidationError as e:
            dead_letters.append(
                build_dead_letter_row(
                    e,
                    raw,
                    batch_execution_id,
                    video_id=raw.get("video_id"),
                    comment_id=raw.get("comment_id"),
                )
            )
            continue

        if record.video_id not in known_video_ids:
            dead_letters.append(
                {
                    "error_timestamp": datetime.now(timezone.utc).isoformat(),
                    "comment_id": record.comment_id,
                    "video_id": record.video_id,
                    "raw_payload": raw,
                    "validation_error": f"video_id '{record.video_id}' no existe en silver_youtube_videos",
                    "error_field": "video_id",
                    "batch_execution_id": batch_execution_id,
                }
            )
            continue

        valid.append(record)

    return valid, dead_letters


def load_staging_comments(client: bigquery.Client, staging_table: str, records: list[YouTubeCommentSchema]) -> None:
    if not records:
        return
    rows = [json.loads(r.model_dump_json()) for r in records]
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.load_table_from_json(rows, staging_table, job_config=job_config)
    job.result()


def merge_comments_to_silver(client: bigquery.Client, silver_table: str, staging_table: str) -> None:
    merge_sql = MERGE_SQL_TEMPLATE.format(silver_table=silver_table, staging_table=staging_table)
    client.query(merge_sql).result()
    client.query(f"TRUNCATE TABLE `{staging_table}`").result()
