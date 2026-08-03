"""Generación incremental de embeddings de 768 dimensiones con ML.GENERATE_EMBEDDING.

Ver .claude/skills/gold-embeddings-generation/SKILL.md. `INSERT` (no `MERGE`):
un embedding existe o no existe para un comment_id, nunca se actualiza.
"""

from __future__ import annotations

from google.cloud import bigquery

INSERT_SQL_TEMPLATE = """
INSERT INTO `{gold_table}` (comment_id, text_embedding)
SELECT
  comment_id,
  ml_generate_embedding_result AS text_embedding
FROM
  ML.GENERATE_EMBEDDING(
    MODEL `{embedding_model}`,
    (
      SELECT s.comment_id, s.comment_text AS content
      FROM `{silver_comments_table}` s
      LEFT JOIN `{gold_table}` e
        ON s.comment_id = e.comment_id
      WHERE e.comment_id IS NULL
    )
  );
"""


def run_embeddings_generation(
    client: bigquery.Client,
    gold_table: str,
    silver_comments_table: str,
    embedding_model: str,
) -> None:
    """Genera embeddings solo para comentarios que aún no los tienen."""
    insert_sql = INSERT_SQL_TEMPLATE.format(
        gold_table=gold_table,
        silver_comments_table=silver_comments_table,
        embedding_model=embedding_model,
    )
    client.query(insert_sql).result()
