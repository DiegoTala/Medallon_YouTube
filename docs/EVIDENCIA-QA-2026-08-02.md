# Evidencia QA — Búsqueda semántica, idempotencia y no-duplicados

**Fecha:** 2026-08-02/03. **Propósito:** documentar, con comandos exactos y resultados reales contra el proyecto `medallon-youtube`, la verificación manual de (1) que `VECTOR_SEARCH` funciona correctamente y (2) que las tablas de Silver y Gold no tienen duplicados pese a que Bronze se ingestó repetidamente durante los smoke tests de esta sesión. Todos los comandos son de solo lectura (`SELECT`, `gcloud ... list/describe`, `gcloud storage ls/cat`) — ninguno muta infraestructura ni requiere `approval-gate`. Contexto completo del día en `docs/HANDOFF.md`.

---

## 1. Verificación manual de la búsqueda semántica (`VECTOR_SEARCH`)

### 1.1 Vía `bq query` (CLI)

```bash
bq query --use_legacy_sql=false --location=us-central1 --format=pretty \
  --parameter="query_comment_id:STRING:UgwFeYEDTMSjnrioe4Z4AaABAg" \
  --parameter="top_k:INT64:5" \
"SELECT base.comment_id AS similar_comment_id,
        silver.comment_text AS similar_text,
        ROUND(distance, 4) AS distance
 FROM VECTOR_SEARCH(
     TABLE \`medallon-youtube.gold.gold_youtube_embeddings\`,
     'text_embedding',
     (SELECT text_embedding FROM \`medallon-youtube.gold.gold_youtube_embeddings\`
      WHERE comment_id = @query_comment_id),
     top_k => @top_k,
     distance_type => 'COSINE'
 )
 JOIN \`medallon-youtube.silver.silver_youtube_comments\` AS silver
   ON base.comment_id = silver.comment_id
 ORDER BY distance"
```

**Resultado real:**

| similar_comment_id | similar_text | distance |
| :--- | :--- | :--- |
| UgwFeYEDTMSjnrioe4Z4AaABAg | Intro song is going to be a wedding song | 0.0 |
| Ugz0giewrua__MN_jHV4AaABAg | The intro song ❤❤❤❤❤❤ | 0.2651 |
| UgzzTB2iXKb5v73A94d4AaABAg | Need the release of the intro song! | 0.2937 |
| Ugyy7OhdksNMiIr05pN4AaABAg | Need the lyrics of the intro asap | 0.3238 |
| UgxXiqDxad-DrDscshF4AaABAg | The intro😮‍💨🔥 | 0.3258 |

Los 4 comentarios más cercanos (excluyendo el mismo, distancia `0.0`) son todos semánticamente sobre "el intro" del set — no coincidencia de palabras exactas, sino relación semántica real. `distance_type='COSINE'`: `0` = idéntico, mientras más chico más similar.

### 1.2 Vía BigQuery Console (alternativa visual)

Misma query de §1.1 pegada directamente en [console.cloud.google.com/bigquery](https://console.cloud.google.com/bigquery) → proyecto `medallon-youtube`, reemplazando el parámetro `@query_comment_id` por un literal. Útil para explorar distintos `comment_id` sin volver a la terminal.

### 1.3 Vía la función Python del pipeline (mismo código que usará producción)

```bash
uv run python -c "
from google.cloud import bigquery
from medallon_youtube.gold.vector_search import semantic_search

client = bigquery.Client(project='medallon-youtube')
results = semantic_search(
    client,
    'medallon-youtube.gold.gold_youtube_embeddings',
    'medallon-youtube.silver.silver_youtube_comments',
    'UgwFeYEDTMSjnrioe4Z4AaABAg',
    top_k=5,
)
for r in results:
    print(r)
"
```

---

## 2. Evidencia de que Bronze se ingestó repetidamente hoy

### 2.1 Ejecuciones del Cloud Run Job

```bash
gcloud run jobs executions list --job=yt-ingestion-job --region=us-central1 --project=medallon-youtube \
  --format="table(metadata.name,status.startTime,status.completionTime,status.conditions[0].message)"
```

**Resultado real:**

| Ejecución | Inicio (UTC) | Fin (UTC) | Resultado |
| :--- | :--- | :--- | :--- |
| yt-ingestion-job-6snbt | 2026-08-02T23:35:55 | 2026-08-02T23:41:33 | Falló (bug dead-letter, corregido commit `1055137`) |
| yt-ingestion-job-lzlg6 | 2026-08-02T23:50:13 | 2026-08-02T23:56:59 | Falló (IAM gold faltante, corregido) |
| yt-ingestion-job-bwg7n | 2026-08-03T00:01:53 | 2026-08-03T00:08:23 | Falló (modelos remotos no existían, corregido) |
| yt-ingestion-job-ltrtn | 2026-08-03T00:53:37 | 2026-08-03T01:00:18 | Bronze+Silver OK, falló en Gold (bug `comment_text`, corregido commit `1191c8b`) |
| yt-ingestion-job-7bl89 | 2026-08-03T01:04:51 | 2026-08-03T01:11:47 | Bronze OK, luego `429` cuota YouTube agotada en reintentos |
| yt-ingestion-job-mzqnk | 2026-08-03T02:00:01 | 2026-08-03T02:06:34 | Disparo automático del Cloud Scheduler semanal (lunes 02:00 UTC) — no iniciado manualmente; falló (cuota aún agotada) |

Cada ejecución reintenta hasta 4 veces (`max-retries=3` del Cloud Run Job), y cada intento vuelve a correr Bronze desde cero — de ahí el volumen de escrituras del siguiente punto.

### 2.2 Archivos Bronze en GCS (inmutables, un archivo por `batch_execution_id`)

```bash
gcloud storage ls "gs://medallon-youtube-yt-bronze/raw/anio=2026/mes=08/dia=02/"
gcloud storage ls "gs://medallon-youtube-yt-bronze/raw/anio=2026/mes=08/dia=03/"
```

**Resultado real:** 18 pares de archivos (`videos_batch_data_*.json` + `comments_batch_data_*.json`), cada uno con un `batch_execution_id` distinto (ej. `batch-20260802T233652-4c4e55aa`, `batch-20260803T005954-e8f45882`, etc.) — ninguno sobreescribió a otro, confirmando que el fix de inmutabilidad de Bronze (incluir `batch_execution_id` en el nombre del archivo) funciona como se diseñó.

### 2.3 Volumen crudo ingerido vs. lo que sobrevivió en Silver

```bash
# Total de líneas (registros) en TODOS los archivos bronze de videos:
TOTAL_V=0
for f in $(gcloud storage ls "gs://medallon-youtube-yt-bronze/raw/anio=2026/mes=08/dia=02/videos_*" \
                              "gs://medallon-youtube-yt-bronze/raw/anio=2026/mes=08/dia=03/videos_*"); do
  n=$(gcloud storage cat "$f" | wc -l)
  TOTAL_V=$((TOTAL_V + n))
done
echo "TOTAL líneas de video en bronze: $TOTAL_V"

# Análogo para comments_*
TOTAL_C=0
for f in $(gcloud storage ls "gs://medallon-youtube-yt-bronze/raw/anio=2026/mes=08/dia=02/comments_*" \
                              "gs://medallon-youtube-yt-bronze/raw/anio=2026/mes=08/dia=03/comments_*"); do
  n=$(gcloud storage cat "$f" | wc -l)
  TOTAL_C=$((TOTAL_C + n))
done
echo "TOTAL líneas (threads) de comments en bronze: $TOTAL_C"
```

**Resultado real:** `216` líneas de video (18 archivos × 12) y `26,685` líneas de threads de comentarios, sumando todas las corridas.

```bash
bq query --use_legacy_sql=false --format=pretty \
  "SELECT COUNT(*) AS n_videos FROM \`medallon-youtube.silver.silver_youtube_videos\`"
bq query --use_legacy_sql=false --format=pretty \
  "SELECT COUNT(*) AS n_comments FROM \`medallon-youtube.silver.silver_youtube_comments\`"
```

**Resultado real:** `13` videos, `1,635` comentarios únicos en Silver.

| | Bronze (crudo, todas las corridas) | Silver (único, post-`MERGE`) |
| :--- | :--- | :--- |
| Videos | 216 líneas | 13 filas |
| Comentarios (threads) | 26,685 líneas | 1,635 filas |

El mismo lote se re-ingirió entre 5 y 18 veces según la tabla, y Silver terminó exactamente con las filas únicas esperadas.

---

## 3. Verificación de cero duplicados (Silver y Gold)

### 3.1 Una query por tabla (patrón general, clave natural)

```bash
bq query --use_legacy_sql=false --format=pretty \
  "SELECT video_id, COUNT(*) AS n FROM \`medallon-youtube.silver.silver_youtube_videos\` GROUP BY video_id HAVING COUNT(*) > 1"

bq query --use_legacy_sql=false --format=pretty \
  "SELECT comment_id, COUNT(*) AS n FROM \`medallon-youtube.silver.silver_youtube_comments\` GROUP BY comment_id HAVING COUNT(*) > 1"

bq query --use_legacy_sql=false --format=pretty \
  "SELECT comment_id, COUNT(*) AS n FROM \`medallon-youtube.gold.gold_sentiment_analysis\` GROUP BY comment_id HAVING COUNT(*) > 1"

bq query --use_legacy_sql=false --format=pretty \
  "SELECT comment_id, COUNT(*) AS n FROM \`medallon-youtube.gold.gold_youtube_embeddings\` GROUP BY comment_id HAVING COUNT(*) > 1"
```

**Resultado real:** las 4 queries devolvieron **0 filas** — ningún `video_id`/`comment_id` aparece más de una vez en ninguna de las 4 tablas.

### 3.2 Confirmación consolidada (una sola query, conteos explícitos)

```bash
bq query --use_legacy_sql=false --format=pretty \
"SELECT
  (SELECT COUNT(*) FROM (SELECT video_id FROM \`medallon-youtube.silver.silver_youtube_videos\` GROUP BY video_id HAVING COUNT(*)>1)) AS dup_videos,
  (SELECT COUNT(*) FROM (SELECT comment_id FROM \`medallon-youtube.silver.silver_youtube_comments\` GROUP BY comment_id HAVING COUNT(*)>1)) AS dup_silver_comments,
  (SELECT COUNT(*) FROM (SELECT comment_id FROM \`medallon-youtube.gold.gold_sentiment_analysis\` GROUP BY comment_id HAVING COUNT(*)>1)) AS dup_sentiment,
  (SELECT COUNT(*) FROM (SELECT comment_id FROM \`medallon-youtube.gold.gold_youtube_embeddings\` GROUP BY comment_id HAVING COUNT(*)>1)) AS dup_embeddings"
```

**Resultado real:**

| dup_videos | dup_silver_comments | dup_sentiment | dup_embeddings |
| :--- | :--- | :--- | :--- |
| 0 | 0 | 0 | 0 |

---

## 4. Conclusión

- **Idempotencia de Silver confirmada empíricamente**, no solo por diseño: 216 registros crudos de video y 26,685 threads de comentarios, ingeridos en al menos 5 corridas reales del Job (más reintentos internos = 18 escrituras físicas en GCS), colapsaron a 13 videos y 1,635 comentarios únicos en Silver — cero duplicados verificados por consulta directa.
- **Incrementalidad de Gold confirmada**: `gold_sentiment_analysis` y `gold_youtube_embeddings` tienen exactamente 1,635 filas cada una (una por comentario válido), sin duplicados, pese a que el pipeline se ejecutó Gold-only manualmente además de las corridas fallidas del Job.
- **Búsqueda semántica funcionando correctamente**: `VECTOR_SEARCH` devuelve vecinos semánticamente coherentes (verificado con ejemplo real "intro song").

Ver `infra/APPROVALS.md` para el registro de los cambios de infraestructura/despliegue asociados, y `docs/HANDOFF.md` §6/§6-bis/§6-ter para el detalle completo de los bugs encontrados y corregidos en el camino.
