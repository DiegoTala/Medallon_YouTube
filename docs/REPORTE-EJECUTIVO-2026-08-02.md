# YouTube DJ Analytics — Pipeline Medallón Serverless en GCP

**Reporte de Arquitectura y Evidencia de Verificación**

**Autor:** Diego Talamantes Sánchez

**Repositorio:** [github.com/DiegoTala/Medallon_YouTube](https://github.com/DiegoTala/Medallon_YouTube)

**Fecha:** 2 de agosto de 2026

**Proyecto GCP:** `medallon-youtube`

---

## 1. Resumen de Arquitectura

**YouTube DJ Analytics** es un pipeline de datos medallón (Bronze → Silver → Gold), 100% serverless, que extrae videos y comentarios de 10 canales de DJs de música electrónica desde la YouTube Data API v3, los valida y estructura, y aplica clasificación de sentimiento y búsqueda semántica con Vertex AI Gemini directamente en SQL sobre BigQuery.

La orquestación se centraliza en un único **Cloud Run Job** (contenedor Python), disparado semanalmente por **Cloud Scheduler** — se descartó Cloud Composer deliberadamente para evitar costos fijos mínimos. Toda la infraestructura se provisiona de forma declarativa con **Terraform**.

### 1.1 Componentes y costo estimado

| Componente | Servicio GCP | Región | Función | Costo estimado/mes |
| :--- | :--- | :--- | :--- | :--- |
| Orquestación | Cloud Scheduler | `us-central1` | Disparador cron semanal | $0.00 (nivel gratuito) |
| Cómputo / ETL | Cloud Run Jobs | `us-central1` | Contenedor de ingesta + validación Pydantic | < $0.50 |
| Data Lake (Bronze) | Cloud Storage (GCS) | `us` | JSON crudo, inmutable | < $0.10 |
| Data Warehouse (Silver/Gold) | BigQuery | `us-central1` | Tablas estructuradas, `MERGE` idempotente | < $1.00 |
| LLM / Sentimiento | Vertex AI Gemini (remoto) | `us-central1` | `ML.GENERATE_TEXT` sobre `gemini-2.5-flash` | ~$0.80–1.20 |
| Embeddings / Búsqueda | BigQuery Vector Search | `us-central1` | `ML.GENERATE_EMBEDDING` + `VECTOR_SEARCH` | ~$0.80–1.20 |
| Secretos | Secret Manager | Global | API Key de YouTube | $0.00 |
| IaC | Terraform | N/A | Provisión declarativa de todo lo anterior | $0.00 |

**Costo total estimado: ~$1.40–$1.80 USD/mes, contra un techo operativo de $15.00 USD/mes.**

> **Nota de co-ubicación regional:** BigQuery, Vertex AI y Cloud Run Jobs residen todos en `us-central1` — `ML.GENERATE_TEXT` y `ML.GENERATE_EMBEDDING` fallan si hay mismatch de región entre el dataset de BigQuery y el modelo remoto de Vertex AI.

### 1.2 Las tres capas

- **Bronze:** extracción cruda de la YouTube Data API v3 → JSON Lines inmutable en GCS, particionado por fecha (`anio=/mes=/dia=`) y con `batch_execution_id` en el nombre del archivo (evita sobrescritura entre corridas del mismo día).
- **Silver:** validación estricta con **Pydantic v2** contra el contrato de datos; registros válidos se cargan a staging y se aplican con `MERGE` idempotente sobre la clave natural (`video_id` / `comment_id`) — reprocesar el mismo lote nunca genera filas nuevas. Todo lo que falla validación o integridad referencial va a `silver_dead_letter_queue`, nunca se descarta silenciosamente.
- **Gold:** clasificación de sentimiento (`ML.GENERATE_TEXT` sobre `gemini-2.5-flash`) y generación de embeddings de 768 dimensiones (`ML.GENERATE_EMBEDDING` sobre `text-embedding-004`), ambos **estrictamente incrementales** (`LEFT JOIN ... WHERE IS NULL`) para no reprocesar comentarios ya analizados y controlar el costo de Vertex AI. Búsqueda semántica nativa con `VECTOR_SEARCH` (distancia coseno).

---

## 2. Evidencia de Verificación

Toda la evidencia de esta sección se generó con comandos de **solo lectura** (`SELECT`, `gcloud ... list/describe`, `gcloud storage ls/cat`) contra el proyecto real `medallon-youtube` — ninguno muta infraestructura. El detalle completo, con cada comando y su salida íntegra, vive en [`docs/EVIDENCIA-QA-2026-08-02.md`](EVIDENCIA-QA-2026-08-02.md) de este mismo repositorio.

### 2.1 Reporte inicial de evidencia (generado en sesión)

Resumen consolidado de la ingesta repetida de Bronze y la verificación de cero duplicados, tal como se presentó durante la sesión de trabajo:

![Reporte inicial de evidencia](evidencia-imagenes/01-reporte-inicial-evidencia.png)

### 2.2 Verificación de idempotencia — ejecutada manualmente en BigQuery Console

Para confirmar de forma independiente (sin depender únicamente de la ejecución asistida), se corrió manualmente en BigQuery Console la query consolidada de detección de duplicados sobre las 4 tablas críticas (`silver_youtube_videos`, `silver_youtube_comments`, `gold_sentiment_analysis`, `gold_youtube_embeddings`):

```sql
SELECT
  (SELECT COUNT(*) FROM (
    SELECT video_id FROM `medallon-youtube.silver.silver_youtube_videos`
    GROUP BY video_id HAVING COUNT(*) > 1
  )) AS dup_videos,
  (SELECT COUNT(*) FROM (
    SELECT comment_id FROM `medallon-youtube.silver.silver_youtube_comments`
    GROUP BY comment_id HAVING COUNT(*) > 1
  )) AS dup_silver_comments,
  (SELECT COUNT(*) FROM (
    SELECT comment_id FROM `medallon-youtube.gold.gold_sentiment_analysis`
    GROUP BY comment_id HAVING COUNT(*) > 1
  )) AS dup_sentiment,
  (SELECT COUNT(*) FROM (
    SELECT comment_id FROM `medallon-youtube.gold.gold_youtube_embeddings`
    GROUP BY comment_id HAVING COUNT(*) > 1
  )) AS dup_embeddings;
```

**Resultado real, corrido directamente en BigQuery Console:**

![Verificación de idempotencia en BigQuery Console](evidencia-imagenes/02-idempotencia-silver-gold.png)

`dup_videos = 0`, `dup_silver_comments = 0`, `dup_sentiment = 0`, `dup_embeddings = 0` — **cero duplicados** en las 4 tablas, pese a que Bronze se ingestó entre 5 y 18 veces durante los smoke tests del día (ver detalle cuantitativo en §2.3 de `EVIDENCIA-QA-2026-08-02.md`: 216 líneas de video y 26,685 threads de comentarios crudos, colapsados a 13 y 1,635 filas únicas respectivamente).

### 2.3 Búsqueda semántica — ejecutada manualmente en BigQuery Console

Verificación adicional e independiente de `VECTOR_SEARCH`, con un `comment_id` distinto al usado en la sesión asistida y `top_k` extendido a 10 resultados:

```sql
SELECT base.comment_id AS similar_comment_id,
       silver.comment_text AS similar_text,
       distance
FROM VECTOR_SEARCH(
    TABLE `medallon-youtube.gold.gold_youtube_embeddings`,
    'text_embedding',
    (SELECT text_embedding FROM `medallon-youtube.gold.gold_youtube_embeddings`
     WHERE comment_id = 'Ugy5Wyt_fM84GtsMhq54AaABAg'),
    top_k => 10,
    distance_type => 'COSINE'
)
JOIN `medallon-youtube.silver.silver_youtube_comments` AS silver
  ON base.comment_id = silver.comment_id
ORDER BY distance;
```

**Resultado real, corrido directamente en BigQuery Console:**

![Búsqueda semántica con 10 resultados en BigQuery Console](evidencia-imagenes/03-busqueda-semantica-10-resultados.png)

Los 10 vecinos más cercanos por similitud de coseno son todos comentarios de tono muy positivo ("I LOVE THIS SOOOO MUCH", "I LOVE IT", "Love it!", "YESS!! LOVE THIS ONE!"), con distancias crecientes de forma monótona (`0.0 → 0.0975 → 0.1138 → ... → 0.1525`) — exactamente el comportamiento esperado de una búsqueda semántica funcionando correctamente: agrupa por significado/tono, no por coincidencia de palabras exactas.

---

## 3. Conclusión

- **Arquitectura desplegada y operando** en el proyecto real `medallon-youtube`, dentro del techo de $15.00 USD/mes.
- **Idempotencia de Silver e incrementalidad de Gold confirmadas empíricamente**, no solo por diseño — verificado de dos formas independientes (asistida y manual en BigQuery Console), con resultado idéntico: cero duplicados.
- **Búsqueda semántica verificada de forma independiente**, con un ejemplo distinto al usado en la sesión asistida, confirmando resultados semánticamente coherentes.

Registro completo de aprobaciones de infraestructura en [`infra/APPROVALS.md`](../infra/APPROVALS.md); bitácora operativa de la sesión en [`docs/HANDOFF.md`](HANDOFF.md); especificación completa del sistema en [`docs/PRD.md`](PRD.md).
