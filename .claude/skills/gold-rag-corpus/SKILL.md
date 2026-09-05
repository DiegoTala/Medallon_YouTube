---
name: gold-rag-corpus
description: Cómo construir y mantener gold_rag_corpus, la tabla denormalizada que es la ÚNICA fuente de datos de los agentes de Fase 2. Úsalo al escribir o modificar el paso del pipeline Gold que materializa el corpus RAG, o al cambiar su esquema.
---

# gold-rag-corpus

## Alcance

`gold_rag_corpus` es **la frontera entre las dos fases**. La produce el pipeline medallón (Fase 1) y la consume el sistema agéntico (Fase 2). Este skill lleva prefijo `gold-` a propósito: la escritura pertenece a Fase 1; Fase 2 solo lee.

El corpus denormaliza en una sola tabla lo que hoy vive repartido en cuatro (`silver_youtube_comments`, `silver_youtube_videos`, `gold_sentiment_analysis`, `gold_youtube_embeddings`), para que las herramientas del agente resuelvan una consulta con un solo escaneo acotado en vez de tres `JOIN` — lo que a su vez es lo que hace viable el techo de 10 MB facturados por consulta de [[rag-quota-limits]].

## Contrato de dirección única (no negociable)

```
Fase 1 (pipeline)  --escribe-->  gold_rag_corpus  --lee-->  Fase 2 (agentes)
```

Ningún agente, tool ni service account de Fase 2 escribe en esta tabla. Ningún componente de Fase 2 lee ninguna otra tabla. Ver [[rag-security-guardrails]] para el lado del agente y [[rag-terraform-root]] para el lado de IAM.

## Esquema (PRD Fase 2 §8)

| Campo | Tipo | Origen |
| :--- | :--- | :--- |
| `comment_id` | STRING | `silver_youtube_comments.comment_id` (clave natural) |
| `comment_text` | STRING | `silver_youtube_comments.comment_text` |
| `text_embedding` | ARRAY&lt;FLOAT64&gt; | `gold_youtube_embeddings.text_embedding` (768 dims) |
| `sentiment_label` | STRING | `gold_sentiment_analysis.sentiment_label` |
| `video_id` | STRING | `silver_youtube_comments.video_id` |
| `video_title` | STRING | `silver_youtube_videos.title` |
| `channel_name` | STRING | `silver_youtube_videos.channel_name` |
| `video_published_at` | TIMESTAMP | `silver_youtube_videos.published_at` |
| `comment_published_at` | TIMESTAMP | `silver_youtube_comments.published_at` |
| `like_count` | INT64 | `silver_youtube_comments.like_count` |
| `language` | STRING | `silver_youtube_videos.default_language` — ver advertencia abajo |
| `video_url` | STRING | derivado: `CONCAT('https://www.youtube.com/watch?v=', video_id)` |
| `gold_snapshot_id` | STRING | el `batch_execution_id` de la corrida que insertó/actualizó la fila |
| `updated_at` | TIMESTAMP | `CURRENT_TIMESTAMP()` al momento del MERGE |

> **Advertencia de semántica en `language` (2026-09-04):** el PRD lo lista sin especificar origen. La única fuente disponible en Silver es `silver_youtube_videos.default_language`, que es el idioma **del video**, no del comentario, y es `NULLABLE` (la mayoría de los videos de los canales de DJs no lo declaran). No lo trates como el idioma del comentario ni lo uses como filtro duro en [[rag-tool-semantic-search]] sin decírselo al usuario. Si en el futuro se necesita idioma real por comentario, eso es detección nueva en el pipeline y pasa por [[cost-guardrail]] — no se resuelve inventando el campo aquí.

## MERGE incremental sobre `comment_id`

```sql
MERGE `proyecto.gold.gold_rag_corpus` AS target
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
  FROM `proyecto.silver.silver_youtube_comments` c
  JOIN `proyecto.silver.silver_youtube_videos`   v USING (video_id)
  JOIN `proyecto.gold.gold_sentiment_analysis`   s USING (comment_id)
  JOIN `proyecto.gold.gold_youtube_embeddings`   e USING (comment_id)
) AS source
ON target.comment_id = source.comment_id
WHEN MATCHED THEN UPDATE SET
  -- SOLO metadatos de video/canal: nunca se reescribe sentimiento ni embedding.
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
```

### Por qué los `JOIN` son `INNER` y no `LEFT`

Un comentario **solo entra al corpus cuando ya tiene sentimiento y embedding**. Si todavía no los tiene, el `INNER JOIN` lo deja fuera y entrará solo en una corrida posterior, cuando [[gold-sentiment-analysis]] y [[gold-embeddings-generation]] lo hayan procesado. Esto es deliberado: evita filas con `text_embedding` nulo que romperían `VECTOR_SEARCH` en [[rag-tool-semantic-search]], y hace que el corpus sea siempre consultable sin defensas contra nulos en el lado del agente.

### `gold_snapshot_id` como versión del corpus

Reutiliza el `batch_execution_id` que ya genera el pipeline (`batch-YYYYMMDDTHHMMSS-<uuid8>`). No es decorativo: es un **componente obligatorio de la clave de caché** de [[rag-response-cache]]. La versión vigente del corpus se obtiene con:

```sql
SELECT MAX(updated_at) AS corpus_version FROM `proyecto.gold.gold_rag_corpus`;
```

Si esa versión cambia, todo el caché de respuestas queda invalidado. Cambiar el formato o la semántica de `gold_snapshot_id` sin actualizar [[rag-response-cache]] rompe la invalidación en silencio — es decir, el agente serviría respuestas viejas sobre datos nuevos sin ninguna señal de error.

## Índice vectorial

Aplica exactamente lo mismo que ya está documentado en [[gold-vector-search]]: mínimo de 5,000 filas para `CREATE VECTOR INDEX`, y `VECTOR_SEARCH` funciona igual de correcto sin índice (solo sin la optimización de latencia). Al 2026-09-04 el volumen es ~3,239 comentarios, es decir **por debajo del umbral**: el corpus opera en búsqueda exhaustiva y eso es lo esperado, no un defecto a corregir.

> **Nota (verificada 2026-09-04, [doc de índices vectoriales de BigQuery](https://docs.cloud.google.com/bigquery/docs/vector-index)):** además del mínimo de 5,000 filas, una tabla de menos de 10 MB **no puebla** el índice aunque se cree. Y para tablas base pequeñas (&lt;500k filas) Google documenta que `IVF` sufre un cuello de botella por el bajo número de shards, y recomienda `TreeAH` como mejor opción. Si algún día se cruza el umbral, evaluar `TreeAH` antes de copiar el `IVF` de [[gold-vector-search]] — la decisión se cotiza con [[cost-guardrail]] y se aplica vía [[approval-gate]].

## Invariantes

- **Dirección única:** Fase 1 escribe, Fase 2 lee. Sin excepciones.
- **Nunca reprocesar:** el `WHEN MATCHED` toca solo metadatos de video/canal. Reescribir `sentiment_label` o `text_embedding` desde aquí significaría volver a pagar Vertex AI por trabajo ya hecho, y viola el invariante de incrementalidad del proyecto.
- **Reprocesar es idempotente:** correr el MERGE dos veces seguidas sin datos nuevos deja 0 filas insertadas.
- **La tabla se declara en `infra/bigquery.tf`** (raíz Terraform de Fase 1), nunca en `infra/fase2/` — ver [[rag-terraform-root]].
- **Sin nulos en `text_embedding`:** garantizado por los `INNER JOIN`. Si algún día se relajan, [[rag-tool-semantic-search]] debe blindarse en la misma entrega.

## Relación con otros skills

- Consume las salidas de [[silver-validation-comments]], [[silver-validation-videos]], [[gold-sentiment-analysis]] y [[gold-embeddings-generation]].
- Es la única fuente de [[rag-tool-semantic-search]], [[rag-tool-sentiment-analytics]] y [[rag-tool-trend-detection]].
- Su versión alimenta la clave de [[rag-response-cache]].
- Hereda las reglas de índice vectorial de [[gold-vector-search]].
