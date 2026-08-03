---
name: gold-embeddings-generation
description: Cómo generar embeddings de 768 dimensiones para comentarios con ML.GENERATE_EMBEDDING sobre el modelo remoto text-embedding-004, de forma incremental hacia gold_youtube_embeddings. Úsalo al escribir o modificar la generación de embeddings de la capa Gold.
---

# gold-embeddings-generation

## Alcance

Generar vectores densos de 768 dimensiones para comentarios de `silver_youtube_comments` que **aún no tienen embedding**, usando el modelo remoto `text-embedding-004` de Vertex AI vía `ML.GENERATE_EMBEDDING`. Al igual que [[gold-sentiment-analysis]], el control de costo depende enteramente del filtro incremental.

## Prerrequisito de co-ubicación regional

Igual que en sentiment: dataset BigQuery y modelo remoto deben estar en `us-central1`. El modelo remoto (`embedding_model`) se crea vía [[terraform-provision]].

## INSERT incremental (nunca reprocesa embeddings ya generados)

```sql
INSERT INTO `proyecto.dataset.gold_youtube_embeddings` (comment_id, text_embedding)
SELECT
  comment_id,
  ml_generate_embedding_result AS text_embedding
FROM
  ML.GENERATE_EMBEDDING(
    MODEL `proyecto.dataset.embedding_model`,
    (
      SELECT s.comment_id, s.comment_text AS content
      FROM `proyecto.dataset.silver_youtube_comments` s
      LEFT JOIN `proyecto.dataset.gold_youtube_embeddings` e
        ON s.comment_id = e.comment_id
      WHERE e.comment_id IS NULL   -- clave del control de costo: solo lo nuevo
    )
  );
```

> **Nota (2026-08-02):** `ML.GENERATE_EMBEDDING` no expone una columna llamada `text_embedding` en su salida — el nombre real es `ml_generate_embedding_result` (hay que aliasearlo). Sin el alias, el `INSERT` falla con `Unrecognized name: text_embedding`. Bug real encontrado al correr la capa Gold end-to-end contra datos reales — el snippet de arriba ya lo tiene corregido.

## Por qué es `INSERT` y no `MERGE`

A diferencia de sentiment, aquí no hay un `WHEN MATCHED` que tenga sentido: un embedding no se "actualiza" campo por campo, o existe o no existe para un `comment_id`. El filtro `LEFT JOIN ... WHERE e.comment_id IS NULL` en la subconsulta ya garantiza que nunca se reinserta un `comment_id` existente — no hace falta la semántica de MERGE.

## Invariantes

- **Nunca quitar el filtro incremental** sin pasar por [[approval-gate]] con cotización explícita — es la misma mitigación de riesgo que en sentiment (PRD §6).
- **768 dimensiones fijas** (propias de `text-embedding-004`): si se cambia de modelo de embeddings en el futuro, la dimensión de la columna `text_embedding` y el índice vectorial de [[gold-vector-search]] deben actualizarse juntos — nunca de forma aislada.
- **No se generan embeddings para registros en dead-letter:** solo `silver_youtube_comments` (ya validados) es fuente.

## Relación con otros skills

- Consume `silver_youtube_comments` de [[silver-validation-comments]].
- Su tabla de salida (`gold_youtube_embeddings`) es la fuente directa de [[gold-vector-search]] — ese skill crea y mantiene el índice vectorial sobre esta misma tabla.
- El modelo remoto `embedding_model` se provisiona vía [[terraform-provision]] bajo [[approval-gate]].
- Costo estimado con [[cost-guardrail]].
