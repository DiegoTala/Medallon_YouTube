---
name: gold-vector-search
description: Cómo crear/mantener el índice vectorial IVF sobre gold_youtube_embeddings y ejecutar búsquedas de similitud semántica con VECTOR_SEARCH. Úsalo al escribir o modificar el índice vectorial o consultas de búsqueda semántica.
---

# gold-vector-search

## Alcance

Mantener un índice vectorial nativo de BigQuery sobre `gold_youtube_embeddings` (generado por [[gold-embeddings-generation]]) y exponer búsquedas de similitud por coseno con `VECTOR_SEARCH`.

## Creación del índice (una sola vez, actualización incremental automática)

```sql
CREATE VECTOR INDEX IF NOT EXISTS yt_comments_vector_index
ON `proyecto.dataset.gold_youtube_embeddings`(text_embedding)
OPTIONS(distance_type='COSINE', index_type='IVF');
```

`IF NOT EXISTS` es intencional y no debe quitarse: BigQuery actualiza el índice IVF incrementalmente a medida que [[gold-embeddings-generation]] inserta nuevas filas — **no se debe recrear el índice en cada ejecución del batch**, eso desperdiciaría cómputo y podría generar costo innecesario. Recrear el índice solo se justifica si cambia la dimensionalidad del embedding (ver invariantes de [[gold-embeddings-generation]]), y eso requiere pasar por [[approval-gate]].

## Búsqueda semántica por similitud de coseno

`gold_youtube_embeddings` solo tiene `(comment_id, text_embedding)` — nunca
`comment_text` (ver invariantes de [[gold-embeddings-generation]], que tampoco
lo inserta). Para devolver el texto del comentario similar, se hace `JOIN`
contra `silver_youtube_comments`, la única fuente de verdad de ese texto, en
vez de duplicarlo en la tabla de embeddings:

```sql
SELECT
  candidate.comment_id AS similar_comment_id,
  silver.comment_text AS similar_text,
  distance
FROM
  VECTOR_SEARCH(
    TABLE `proyecto.dataset.gold_youtube_embeddings`,
    'text_embedding',
    (
      SELECT text_embedding
      FROM `proyecto.dataset.gold_youtube_embeddings`
      WHERE comment_id = 'QUERY_COMMENT_ID'
    ),
    top_k => 10,
    distance_type => 'COSINE'
  )
JOIN `proyecto.dataset.silver_youtube_comments` AS silver
  ON candidate.comment_id = silver.comment_id;
```

> **Decisión (2026-08-02):** se evaluó agregar `comment_text` como columna
> duplicada en `gold_youtube_embeddings` (evita el JOIN) contra hacer el JOIN
> en cada búsqueda. Se eligió el JOIN: evita desincronización de texto entre
> tablas y el costo incremental de bytes escaneados es despreciable al volumen
> del proyecto (~2,500 comentarios/mes). Ver [[cost-guardrail]] si el volumen
> crece lo suficiente para reconsiderarlo.

## Snippet de ejemplo (parametrizar desde Python con el cliente de BigQuery)

```python
from google.cloud import bigquery

def semantic_search(
    client: bigquery.Client,
    embeddings_table: str,
    silver_comments_table: str,
    query_comment_id: str,
    top_k: int = 10,
):
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
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("query_comment_id", "STRING", query_comment_id),
        bigquery.ScalarQueryParameter("top_k", "INT64", top_k),
    ])
    return list(client.query(query, job_config=job_config).result())
```

## Invariantes

- **No recrear el índice en cada corrida del batch** — solo `CREATE VECTOR INDEX IF NOT EXISTS`.
- **`top_k` acotado:** no exponer búsquedas con `top_k` sin límite superior razonable (ej. máx. 50) para evitar consultas costosas si esto se conecta a un endpoint público en el futuro.
- **La columna indexada (`text_embedding`) debe coincidir en dimensionalidad** con lo que produce el modelo activo en [[gold-embeddings-generation]].
- **`comment_text` nunca se duplica en `gold_youtube_embeddings`:** toda búsqueda semántica que necesite el texto lo trae vía `JOIN` a `silver_youtube_comments`, nunca agregando la columna a la tabla de embeddings (ver decisión 2026-08-02 arriba).

## Relación con otros skills

- Depende directamente de la tabla que produce [[gold-embeddings-generation]].
- El `JOIN` de `semantic_search` depende también de `silver_youtube_comments`, la tabla que produce [[silver-validation-comments]] — es la única fuente de verdad del texto del comentario.
- Cambios en el índice (tipo de distancia, tipo de índice) son cambios de infraestructura de datos y deben cotizarse con [[cost-guardrail]] y aprobarse vía [[approval-gate]] si implican recreación completa.
