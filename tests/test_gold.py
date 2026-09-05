from unittest.mock import MagicMock

import pytest

from medallon_youtube.gold.embeddings import run_embeddings_generation
from medallon_youtube.gold.rag_corpus import run_rag_corpus_merge
from medallon_youtube.gold.sentiment import run_sentiment_analysis
from medallon_youtube.gold.vector_search import MAX_TOP_K, ensure_vector_index, semantic_search


def test_run_sentiment_analysis_runs_merge_with_incremental_filter() -> None:
    client = MagicMock()

    run_sentiment_analysis(
        client,
        gold_table="proj.gold.gold_sentiment_analysis",
        silver_comments_table="proj.silver.silver_youtube_comments",
        gemini_model="proj.gold.gemini_flash_model",
    )

    client.query.assert_called_once()
    sql = client.query.call_args.args[0]
    assert "MERGE INTO" in sql
    assert "gold_sentiment_analysis" in sql
    assert "WHERE g.comment_id IS NULL" in sql
    assert "WHEN MATCHED" not in sql  # nunca reclasifica lo ya existente
    # ML.GENERATE_TEXT solo pasa a la salida columnas presentes en su SELECT de
    # entrada: sin seleccionar s.comment_text explícitamente (no solo dentro del
    # CONCAT del prompt), el MERGE externo fallaría con "Unrecognized name:
    # comment_text" (bug real encontrado en el smoke test end-to-end).
    assert "s.comment_id,\n          s.comment_text," in sql


def test_run_embeddings_generation_runs_insert_with_incremental_filter() -> None:
    client = MagicMock()

    run_embeddings_generation(
        client,
        gold_table="proj.gold.gold_youtube_embeddings",
        silver_comments_table="proj.silver.silver_youtube_comments",
        embedding_model="proj.gold.embedding_model",
    )

    client.query.assert_called_once()
    sql = client.query.call_args.args[0]
    assert "INSERT INTO" in sql
    assert "gold_youtube_embeddings" in sql
    assert "WHERE e.comment_id IS NULL" in sql
    # ML.GENERATE_EMBEDDING no expone una columna "text_embedding" en su salida
    # (el nombre real es ml_generate_embedding_result) — sin el alias explícito,
    # el INSERT falla con "Unrecognized name: text_embedding" (bug real
    # encontrado al correr la capa Gold end-to-end contra datos reales).
    assert "ml_generate_embedding_result AS text_embedding" in sql


def test_ensure_vector_index_uses_if_not_exists() -> None:
    client = MagicMock()

    ensure_vector_index(client, "yt_comments_vector_index", "proj.gold.gold_youtube_embeddings")

    client.query.assert_called_once()
    sql = client.query.call_args.args[0]
    assert "CREATE VECTOR INDEX IF NOT EXISTS" in sql
    assert "distance_type='COSINE'" in sql


def test_semantic_search_rejects_top_k_over_limit() -> None:
    client = MagicMock()
    with pytest.raises(ValueError):
        semantic_search(
            client,
            "proj.gold.gold_youtube_embeddings",
            "proj.silver.silver_youtube_comments",
            "c1",
            top_k=MAX_TOP_K + 1,
        )
    client.query.assert_not_called()


def test_semantic_search_joins_silver_comments_for_text() -> None:
    client = MagicMock()
    client.query.return_value.result.return_value = [
        {"similar_comment_id": "c2", "similar_text": "hi", "distance": 0.1}
    ]

    result = semantic_search(
        client,
        "proj.gold.gold_youtube_embeddings",
        "proj.silver.silver_youtube_comments",
        "c1",
        top_k=5,
    )

    assert result == [{"similar_comment_id": "c2", "similar_text": "hi", "distance": 0.1}]
    sql = client.query.call_args.args[0]
    assert "JOIN `proj.silver.silver_youtube_comments`" in sql
    assert "silver.comment_text AS similar_text" in sql
    # VECTOR_SEARCH no expone un alias "candidate" para la tabla base cuando
    # query_value es una subquery escalar (no una segunda TABLE) — el alias
    # real es "base". Bug real encontrado al correr la búsqueda semántica
    # contra datos reales ("Unrecognized name: candidate").
    assert "base.comment_id AS similar_comment_id" in sql
    assert "ON base.comment_id = silver.comment_id" in sql
    _, kwargs = client.query.call_args
    params = {p.name: p.value for p in kwargs["job_config"].query_parameters}
    assert params == {"query_comment_id": "c1", "top_k": 5}


def test_run_rag_corpus_merge_uses_inner_joins() -> None:
    client = MagicMock()

    run_rag_corpus_merge(
        client,
        corpus_table="proj.gold.gold_rag_corpus",
        silver_comments_table="proj.silver.silver_youtube_comments",
        silver_videos_table="proj.silver.silver_youtube_videos",
        gold_sentiment_table="proj.gold.gold_sentiment_analysis",
        gold_embeddings_table="proj.gold.gold_youtube_embeddings",
        batch_execution_id="batch-20260904T120000-abc12345",
    )

    client.query.assert_called_once()
    sql = client.query.call_args.args[0]
    # INNER JOINs garantizan que solo entran filas con sentimiento Y embedding.
    assert "JOIN `proj.silver.silver_youtube_videos`" in sql
    assert "JOIN `proj.gold.gold_sentiment_analysis`" in sql
    assert "JOIN `proj.gold.gold_youtube_embeddings`" in sql
    # MERGE sobre comment_id como clave natural.
    assert "MERGE `proj.gold.gold_rag_corpus`" in sql
    assert "ON target.comment_id = source.comment_id" in sql
    # WHEN MATCHED solo toca metadatos de video/canal, nunca sentimiento ni embedding.
    assert "WHEN MATCHED THEN UPDATE SET" in sql
    assert "video_title" in sql
    assert "sentiment_label" not in sql.split("WHEN MATCHED")[1].split("WHEN NOT MATCHED")[0]
    # WHEN NOT MATCHED inserta todos los campos.
    assert "WHEN NOT MATCHED THEN INSERT" in sql


def test_run_rag_corpus_merge_passes_batch_execution_id_as_parameter() -> None:
    client = MagicMock()

    run_rag_corpus_merge(
        client,
        corpus_table="proj.gold.gold_rag_corpus",
        silver_comments_table="proj.silver.silver_youtube_comments",
        silver_videos_table="proj.silver.silver_youtube_videos",
        gold_sentiment_table="proj.gold.gold_sentiment_analysis",
        gold_embeddings_table="proj.gold.gold_youtube_embeddings",
        batch_execution_id="batch-20260904T120000-abc12345",
    )

    _, kwargs = client.query.call_args
    params = {p.name: p.value for p in kwargs["job_config"].query_parameters}
    assert params == {"batch_execution_id": "batch-20260904T120000-abc12345"}
