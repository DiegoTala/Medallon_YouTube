"""Entrypoint del Cloud Run Job: orquesta Bronze -> Silver -> Gold en secuencia.

Ver docs/PRD.md y CLAUDE.md. El orden entre capas importa: silver-validation-videos
siempre corre antes que silver-validation-comments (integridad referencial), y
ambos siempre antes de la capa Gold (que depende de silver_youtube_comments).
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

from google.cloud import bigquery, storage
from googleapiclient.discovery import Resource

from medallon_youtube.bronze import (
    build_youtube_client,
    run_bronze_comment_ingestion,
    run_bronze_video_ingestion,
)
from medallon_youtube.config import PipelineConfig, load_config
from medallon_youtube.gold import ensure_vector_index, run_embeddings_generation, run_rag_corpus_merge, run_sentiment_analysis
from medallon_youtube.mapping import flatten_comment_thread, flatten_video
from medallon_youtube.silver import (
    fetch_known_video_ids,
    insert_dead_letters,
    load_staging_comments,
    load_staging_videos,
    merge_comments_to_silver,
    merge_videos_to_silver,
    validate_comment_batch,
    validate_video_batch,
)

VECTOR_INDEX_NAME = "yt_comments_vector_index"


def _read_jsonl(bucket: storage.Bucket, path: str) -> list[str]:
    text = bucket.blob(path).download_as_text()
    return [line for line in text.splitlines() if line.strip()]


def _flatten_video_lines(raw_lines: list[str]) -> list[str]:
    """Bronze guarda el shape crudo de la API; Silver espera el shape plano del
    schema. Ver medallon_youtube.mapping para el porqué de este puente."""
    return [json.dumps(flatten_video(json.loads(line))) for line in raw_lines]


def _flatten_comment_lines(raw_lines: list[str]) -> list[str]:
    """Cada línea de bronze (un thread) puede expandirse a varias filas planas:
    el comentario de nivel superior + sus respuestas de primer nivel."""
    flat_lines: list[str] = []
    for line in raw_lines:
        for flat_comment in flatten_comment_thread(json.loads(line)):
            flat_lines.append(json.dumps(flat_comment))
    return flat_lines


def run_pipeline(
    youtube: Resource,
    gcs_client: storage.Client,
    bq_client: bigquery.Client,
    config: PipelineConfig,
    batch_execution_id: str,
    batch_date: datetime,
) -> None:
    bucket = gcs_client.bucket(config.bronze_bucket)

    # Bronze: sin validar ni transformar, tal cual lo devuelve la API.
    videos_path, videos_raw = run_bronze_video_ingestion(
        youtube, bucket, config.channel_ids, batch_execution_id, batch_date=batch_date
    )
    video_ids = [v["id"] for v in videos_raw]
    comments_path = run_bronze_comment_ingestion(youtube, bucket, video_ids, batch_execution_id, batch_date=batch_date)

    # Silver: videos primero — silver_youtube_comments depende de su integridad referencial.
    video_lines = _flatten_video_lines(_read_jsonl(bucket, videos_path))
    valid_videos, video_dead_letters = validate_video_batch(video_lines, batch_execution_id)
    load_staging_videos(bq_client, config.staging_videos_table, valid_videos)
    merge_videos_to_silver(bq_client, config.silver_videos_table, config.staging_videos_table)
    insert_dead_letters(bq_client, config.dead_letter_table, video_dead_letters)

    known_video_ids = fetch_known_video_ids(bq_client, config.silver_videos_table)

    comment_lines = _flatten_comment_lines(_read_jsonl(bucket, comments_path))
    valid_comments, comment_dead_letters = validate_comment_batch(comment_lines, known_video_ids, batch_execution_id)
    load_staging_comments(bq_client, config.staging_comments_table, valid_comments)
    merge_comments_to_silver(bq_client, config.silver_comments_table, config.staging_comments_table)
    insert_dead_letters(bq_client, config.dead_letter_table, comment_dead_letters)

    # Gold: incremental, nunca reprocesa lo ya existente (control de costo de Vertex AI).
    run_sentiment_analysis(bq_client, config.gold_sentiment_table, config.silver_comments_table, config.gemini_model)
    run_embeddings_generation(
        bq_client, config.gold_embeddings_table, config.silver_comments_table, config.embedding_model
    )

    # Gold RAG Corpus: materializa la frontera entre Fase 1 y Fase 2.
    # INNER JOIN garantiza que solo entran filas con sentimiento Y embedding.
    run_rag_corpus_merge(
        bq_client,
        config.gold_rag_corpus_table,
        config.silver_comments_table,
        config.silver_videos_table,
        config.gold_sentiment_table,
        config.gold_embeddings_table,
        batch_execution_id,
    )

    # El índice IVF requiere ~5000+ filas; con menos, VECTOR_SEARCH funciona
    # sin índice (scan bruto). Log warning pero no tumbar el pipeline.
    try:
        ensure_vector_index(bq_client, VECTOR_INDEX_NAME, config.gold_embeddings_table)
    except Exception as exc:
        print(f"WARNING: ensure_vector_index falló (no crítico): {exc}", flush=True)


def main() -> None:
    try:
        api_key = os.environ["YOUTUBE_API_KEY"]
        config = load_config()
        batch_date = datetime.now(timezone.utc)
        batch_execution_id = f"batch-{batch_date:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"

        youtube = build_youtube_client(api_key)
        gcs_client = storage.Client(project=config.project_id)
        bq_client = bigquery.Client(project=config.project_id)

        run_pipeline(youtube, gcs_client, bq_client, config, batch_execution_id, batch_date)

        print(f"Pipeline completado — batch_execution_id={batch_execution_id}", flush=True)
        sys.exit(0)
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
