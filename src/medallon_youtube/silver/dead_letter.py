"""silver_dead_letter_queue: receptor único de registros que fallan validación.

Ver .claude/skills/silver-dead-letter-queue/SKILL.md. Inserción directa, sin MERGE:
cada rechazo es un evento inmutable, no se deduplica.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.cloud import bigquery
from pydantic import ValidationError

DEAD_LETTER_TABLE = "silver_dead_letter_queue"


def build_dead_letter_row(
    error: ValidationError,
    raw_payload: dict[str, Any],
    batch_execution_id: str,
    *,
    video_id: str | None = None,
    comment_id: str | None = None,
) -> dict[str, Any]:
    first_error = error.errors()[0]
    return {
        "error_timestamp": datetime.now(timezone.utc).isoformat(),
        "comment_id": comment_id,
        "video_id": video_id,
        "raw_payload": raw_payload,
        "validation_error": str(error),
        "error_field": ".".join(str(p) for p in first_error["loc"]),
        "batch_execution_id": batch_execution_id,
    }


def insert_dead_letters(client: bigquery.Client, table_id: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    errors = client.insert_rows_json(table_id, rows)
    if errors:
        raise RuntimeError(f"Fallo insertando en dead-letter queue: {errors}")
