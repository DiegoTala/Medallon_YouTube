"""Índice vectorial IVF sobre gold_youtube_embeddings y búsqueda por coseno.

Ver .claude/skills/gold-vector-search/SKILL.md. `gold_youtube_embeddings` solo
tiene (comment_id, text_embedding) — semantic_search trae `comment_text` con un
JOIN a silver_youtube_comments en vez de duplicarlo en la tabla de embeddings
(decisión 2026-08-02: evita desincronización si el texto de origen cambiara).
"""

from __future__ import annotations

from typing import Any

from google.cloud import bigquery

MAX_TOP_K = 50


def ensure_vector_index(client: bigquery.Client, index_name: str, embeddings_table: str) -> None:
    """CREATE VECTOR INDEX IF NOT EXISTS — nunca recrear en cada corrida del batch."""
    sql = f"""
        CREATE VECTOR INDEX IF NOT EXISTS {index_name}
        ON `{embeddings_table}`(text_embedding)
        OPTIONS(distance_type='COSINE', index_type='IVF');
    """
    client.query(sql).result()


def semantic_search(
    client: bigquery.Client,
    embeddings_table: str,
    silver_comments_table: str,
    query_comment_id: str,
    top_k: int = 10,
) -> list[Any]:
    """Búsqueda de similitud por coseno. top_k acotado a MAX_TOP_K (invariante).

    `comment_text` no vive en `embeddings_table` (solo comment_id + text_embedding):
    se trae con un JOIN a silver_youtube_comments, la única fuente de verdad del
    texto del comentario.
    """
    if top_k > MAX_TOP_K:
        raise ValueError(f"top_k no puede exceder {MAX_TOP_K} (invariante de gold-vector-search)")

    query = f"""
        SELECT candidate.comment_id AS similar_comment_id,
               silver.comment_text AS similar_text,
               distance
        FROM VECTOR_SEARCH(
            TABLE `{embeddings_table}`,
            'text_embedding',
            (SELECT text_embedding FROM `{embeddings_table}`
             WHERE comment_id = @query_comment_id),
            top_k => @top_k,
            distance_type => 'COSINE'
        )
        JOIN `{silver_comments_table}` AS silver
          ON candidate.comment_id = silver.comment_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("query_comment_id", "STRING", query_comment_id),
            bigquery.ScalarQueryParameter("top_k", "INT64", top_k),
        ]
    )
    return list(client.query(query, job_config=job_config).result())
