"""Clasificación de sentimiento incremental con ML.GENERATE_TEXT (Gemini remoto).

Ver .claude/skills/gold-sentiment-analysis/SKILL.md. El filtro
`WHERE g.comment_id IS NULL` es el control de costo central: nunca reprocesa
comentarios ya clasificados.
"""

from __future__ import annotations

from google.cloud import bigquery

MERGE_SQL_TEMPLATE = """
MERGE INTO `{gold_table}` T
USING (
  SELECT
    comment_id,
    comment_text,
    ml_generate_text_result
  FROM
    ML.GENERATE_TEXT(
      MODEL `{gemini_model}`,
      (
        SELECT
          s.comment_id,
          s.comment_text,
          CONCAT(
            'Clasifica el sentimiento del siguiente comentario de un video/DJ set como POSITIVO, NEGATIVO, NEUTRO o MIXTO. ',
            'Responde ÚNICAMENTE con una de estas cuatro palabras.',
            '\\n\\nComentario: ',
            s.comment_text
          ) AS prompt
        FROM `{silver_comments_table}` s
        LEFT JOIN `{gold_table}` g
          ON s.comment_id = g.comment_id
        WHERE g.comment_id IS NULL
      ),
      STRUCT(0.2 AS temperature, 100 AS max_output_tokens)
    )
) S
ON T.comment_id = S.comment_id
WHEN NOT MATCHED THEN
  INSERT (comment_id, comment_text, sentiment_raw, sentiment_label, processed_at)
  VALUES (
    S.comment_id,
    S.comment_text,
    S.ml_generate_text_result,
    JSON_EXTRACT_SCALAR(S.ml_generate_text_result, '$.candidates[0].content.parts[0].text'),
    CURRENT_TIMESTAMP()
  );
"""


def run_sentiment_analysis(
    client: bigquery.Client,
    gold_table: str,
    silver_comments_table: str,
    gemini_model: str,
) -> None:
    """Clasifica únicamente comentarios nuevos (WHEN NOT MATCHED, nunca UPDATE)."""
    merge_sql = MERGE_SQL_TEMPLATE.format(
        gold_table=gold_table,
        silver_comments_table=silver_comments_table,
        gemini_model=gemini_model,
    )
    client.query(merge_sql).result()
