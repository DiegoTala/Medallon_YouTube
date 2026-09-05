"""Materialización incremental de gold_rag_corpus, la frontera entre Fase 1 y Fase 2.

Ver .claude/skills/gold-rag-corpus/SKILL.md. El MERGE es incremental sobre
comment_id como clave natural: inserta comentarios nuevos ya clasificados/embebidos
y actualiza únicamente metadatos de video/canal cuando cambien, sin reprocesar
sentimiento ni embeddings existentes.
"""

from __future__ import annotations

from google.cloud import bigquery

MERGE_SQL_TEMPLATE = """
MERGE `{corpus_table}` AS target
USING (
  SELECT
    c.comment_id,
    c.comment_text,
    e.text_embedding,
    s.sentiment_label,
    c.video_id,
    v.title              AS video_title,
    v.channel_name,
    v.published_at       AS video_published_at,
    c.published_at       AS comment_published_at,
    c.like_count,
    v.default_language   AS language,
    CONCAT('https://www.youtube.com/watch?v=', c.video_id) AS video_url
  FROM `{silver_comments_table}` c
  JOIN `{silver_videos_table}`   v USING (video_id)
  JOIN `{gold_sentiment_table}`  s USING (comment_id)
  JOIN `{gold_embeddings_table}` e USING (comment_id)
) AS source
ON target.comment_id = source.comment_id
WHEN MATCHED THEN UPDATE SET
  video_title        = source.video_title,
  channel_name       = source.channel_name,
  video_published_at = source.video_published_at,
  video_url          = source.video_url,
  language           = source.language,
  like_count         = source.like_count,
  gold_snapshot_id   = @batch_execution_id,
  updated_at         = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
  comment_id, comment_text, text_embedding, sentiment_label, video_id,
  video_title, channel_name, video_published_at, comment_published_at,
  like_count, language, video_url, gold_snapshot_id, updated_at
) VALUES (
  source.comment_id, source.comment_text, source.text_embedding, source.sentiment_label,
  source.video_id, source.video_title, source.channel_name, source.video_published_at,
  source.comment_published_at, source.like_count, source.language, source.video_url,
  @batch_execution_id, CURRENT_TIMESTAMP()
);
"""


def run_rag_corpus_merge(
    client: bigquery.Client,
    corpus_table: str,
    silver_comments_table: str,
    silver_videos_table: str,
    gold_sentiment_table: str,
    gold_embeddings_table: str,
    batch_execution_id: str,
) -> None:
    """Materializa gold_rag_corpus de forma incremental.

    INNER JOIN garantiza que solo entran filas con sentimiento Y embedding.
    El WHEN MATCHED solo toca metadatos de video/canal — nunca reescribe
    sentiment_label ni text_embedding (invariante de incrementalidad).
    """
    merge_sql = MERGE_SQL_TEMPLATE.format(
        corpus_table=corpus_table,
        silver_comments_table=silver_comments_table,
        silver_videos_table=silver_videos_table,
        gold_sentiment_table=gold_sentiment_table,
        gold_embeddings_table=gold_embeddings_table,
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("batch_execution_id", "STRING", batch_execution_id),
        ],
    )
    client.query(merge_sql, job_config=job_config).result()
