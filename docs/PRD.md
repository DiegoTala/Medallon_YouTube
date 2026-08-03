# Product Design Document (PRD)
## Arquitectura Medallón Serverless para Análisis de Sentimiento de Canales de DJs en YouTube

**Proyecto:** YouTube DJ Analytics  
**Rol:** Data Engineering Project Manager  
**Entorno:** Google Cloud Platform (GCP) Serverless  
**Frecuencia de Ingesta:** Batch Semanal  
**Presupuesto Máximo:** $15.00 USD / mes
**Infraestructura como Código:** Terraform (provisionamiento declarativo de todos los recursos GCP)  

---

## 1. Resumen Ejecutivo y Objetivos

El presente documento de diseño de producto (PDR) define la arquitectura técnica y el pipeline de datos para la ingesta, validación, procesamiento, análisis de sentimiento y búsqueda semántica de contenidos publicados en YouTube por una lista acotada de **5 canales de DJs**.

El objetivo principal es proveer analítica avanzada sobre los comentarios de los videos lanzados en la última semana, categorizando el sentimiento mediante **Vertex AI Gemini** y ofreciendo capacidades de búsqueda vectorial semántica directamente en **BigQuery Vector Search**. Todo el pipeline se diseña bajo strictly criterios de idempotencia, arquitectura serverless con contenedores y un techo presupuestario operativo inferior a **$15 USD mensuales**.

---

## 2. Especificaciones de Ingesta y Alcance de Datos

* **Unidades de Selección:** 5 canales objetivo de DJs de música electrónica/dance.
* **Frecuencia de Carga:** Batch semanal (ejecutado cada lunes a las 02:00 UTC).
* **Ventana Temporal de Ingesta:** Videos publicados dentro de los últimos 7 días ($T - 7 \text{ días}$).
* **Atributos Extraídos por Video:** Video ID, Título, Descripción, Fecha de Publicación, Idioma predeterminado, Canal Propietario, Duración, Vista (Views), Me Gusta (Likes).
* **Atributos Extraídos por Comentario:** Comment ID, Video ID Padre, Autor, Conteo de Likes, Fecha de Publicación, Texto del Comentario y Respuestas de primer nivel (Reply Thread).

---

## 3. Arquitectura General del Sistema

Se descarta el uso de Cloud Composer para evitar costos fijos mínimos. Toda la orquestación se centraliza en **Cloud Scheduler** disparando un **Cloud Run Job** empaquetado en un contenedor Docker en Artifact Registry.

| Componente | Servicio GCP | Región | Función Técnica | Costo Estimado / Mes |
| :--- | :--- | :--- | :--- | :--- |
| **Orquestación** | Cloud Scheduler | `us-central1` | Disparador cron semanal para iniciar el Job. | $0.00 USD (Nivel Gratuito) |
| **Cómputo / ETL** | Cloud Run Jobs | `us-central1` | Ejecución de contenedor Python (Ingesta + Pydantic). | < $0.50 USD |
| **Data Lake (Bronze)** | Cloud Storage (GCS) | `us` (multirregional) | Almacenamiento inmutable de respuestas JSON raw de API. | < $0.10 USD |
| **Data Warehouse (Silver/Gold)** | BigQuery | `us-central1` | Almacenamiento estructurado, MERGE idempotente y Staging. | < $1.00 USD |
| **LLM & Sentimiento** | Vertex AI Gemini Remote Function | `us-central1` | Clasificación de sentimiento en SQL con `ML.GENERATE_TEXT`. | ~$1.50 - $3.00 USD |
| **Embeddings & Búsqueda** | BigQuery Vector Search | `us-central1` | Generación con `ML.GENERATE_EMBEDDING` e índice VECTOR. | ~$1.00 - $2.00 USD |
| **Gestión de Secretos** | Secret Manager | Global | Almacenamiento seguro de la API Key de YouTube. | $0.00 USD |
| **Infraestructura como Código** | Terraform | N/A | Provisionamiento declarativo de todos los recursos GCP. | $0.00 USD |

> **Nota sobre co-ubicación regional:** BigQuery, Vertex AI y Cloud Run Jobs deben residir en la misma región (`us-central1`). `ML.GENERATE_TEXT` y `ML.GENERATE_EMBEDDING` no funcionan si los datasets de BigQuery están en una región diferente a los modelos de Vertex AI.

---

## 4. Diseño de Capas Medallón

### 4.1 Capa Bronze (Ingesta Cruda)
El contenedor Python consulta la API de YouTube Data v3 utilizando una API Key de servidor sin autenticación interactiva de usuario (sin OAuth 2.0).

* **Formato de Almacenamiento:** Archivos JSON Lines en GCS particionados por fecha de ejecución: `gs://bucket-yt-bronze/raw/anio=YYYY/mes=MM/dia=DD/batch_data.json`.
* **Comportamiento:** Inmutable. Los datos raw se persisten exactamente como los devuelve la API para permitir relecturas e inspección forense.

### 4.2 Capa Silver (Calidad de Datos con Pydantic y MERGE Idempotente)
En esta capa se ejecuta la validación cliente con **Pydantic v2** dentro del contenedor antes de la carga a tablas finales de BigQuery.

#### Flujo de Validación y Carga Idempotente (Pydantic + BQ MERGE):
1. El contenedor descarga/lee el buffer de objetos JSON de la ingesta Bronze.
2. Cada registro se evalúa contra contratos de datos estrictos (`YouTubeVideoSchema` y `YouTubeCommentSchema`).
3. **Registros Válidos:** Se insertan en una tabla temporal de Staging en BigQuery (`staging_youtube_comments`).
4. **Registros Inválidos:** Se capturan los errores de validación de Pydantic y se insertan directamente en la tabla `silver_dead_letter_queue` con el motivo detallado del rechazo.

   **Schema de `silver_dead_letter_queue`:**

   | Columna | Tipo | Descripción |
   | :--- | :--- | :--- |
   | `error_timestamp` | TIMESTAMP | Momento en que se detectó el error de validación. |
   | `comment_id` | STRING | ID del comentario fallido (NULL si no está disponible). |
   | `video_id` | STRING | ID del video asociado (NULL si no está disponible). |
   | `raw_payload` | JSON | Registro original completo en formato JSON. |
   | `validation_error` | STRING | Mensaje de error detallado de Pydantic. |
   | `error_field` | STRING | Campo específico que falló la validación. |
   | `batch_execution_id` | STRING | Identificador de la ejecución del batch para trazabilidad. |

5. **Garantía de Idempotencia:** Se ejecuta una instrucción `MERGE SQL` sobre la tabla `silver_youtube_comments` usando la clave natural `comment_id`. Si el lote se reprocesa, **filas_nuevas = 0**.

```sql
-- Sentencia SQL de MERGE Idempotente en Capa Silver
MERGE INTO `proyecto.dataset.silver_youtube_comments` T
USING `proyecto.dataset.staging_youtube_comments` S
ON T.comment_id = S.comment_id
WHEN MATCHED THEN
  UPDATE SET 
    T.like_count = S.like_count,
    T.updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (comment_id, video_id, author, comment_text, like_count, published_at, ingested_at)
  VALUES (S.comment_id, S.video_id, S.author, S.comment_text, S.like_count, S.published_at, CURRENT_TIMESTAMP());
```

   > **Limpieza de Staging:** Inmediatamente después del MERGE exitoso, se ejecuta `TRUNCATE TABLE` sobre `staging_youtube_comments` para evitar reprocesamiento de datos ya migrados en la siguiente ejecución.

#### 4.2.1 Validación y Carga de Videos

Los videos pasan por el mismo flujo de validación y MERGE idempotente que los comentarios, usando su propio contrato de datos:

```python
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional

class YouTubeVideoSchema(BaseModel):
    video_id: str = Field(..., min_length=5, description="ID único del video de YT")
    channel_name: str = Field(..., min_length=1, description="Nombre del canal propietario")
    title: str = Field(..., min_length=1, description="Título del video")
    description: str = Field(..., description="Descripción del video")
    published_at: datetime = Field(..., description="Fecha de publicación en ISO 8601")
    default_language: Optional[str] = Field(None, description="Idioma predeterminado del video")
    duration: str = Field(..., description="Duración en formato ISO 8601 (PT#H#M#S)")
    view_count: int = Field(ge=0, description="Número de vistas")
    like_count: int = Field(ge=0, description="Número de me gusta")

    @field_validator('title')
    def title_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('El título no puede estar vacío')
        return v
```

Los registros de video se validan contra `YouTubeVideoSchema` y se cargan en `staging_youtube_videos`. Luego se ejecuta un MERGE idempotente sobre `silver_youtube_videos`:

```sql
MERGE INTO `proyecto.dataset.silver_youtube_videos` T
USING `proyecto.dataset.staging_youtube_videos` S
ON T.video_id = S.video_id
WHEN MATCHED THEN
  UPDATE SET
    T.view_count = S.view_count,
    T.like_count = S.like_count,
    T.updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (video_id, channel_name, title, description, published_at, default_language, duration, view_count, like_count, ingested_at)
  VALUES (S.video_id, S.channel_name, S.title, S.description, S.published_at, S.default_language, S.duration, S.view_count, S.like_count, CURRENT_TIMESTAMP());
```

   > **Limpieza de Staging:** Análogo a comentarios, se ejecuta `TRUNCATE TABLE staging_youtube_videos` tras el MERGE exitoso.

   > **Integridad Referencial:** La tabla `silver_youtube_comments` incluye una clave foránea (`video_id`) que referencia `silver_youtube_videos(video_id)`. BigQuery no aplica constraints de FK nativamente, por lo que la integridad se garantiza en la capa de validación: todo comentario cuyo `video_id` no exista en `silver_youtube_videos` se rechaza y se registra en la dead letter queue.

### 4.3 Capa Gold (Machine Learning y Búsqueda Vectorial)

Toda la capa Gold se procesa directamente en BigQuery utilizando funciones remotas e integraciones nativas con los modelos de Vertex AI. A diferencia de las capas Bronze y Silver, aquí se aplica un enfoque **incremental estricto** para no reprocesar datos ya analizados y controlar los costos de Vertex AI.

* **Análisis de Sentimiento:** Se utiliza `ML.GENERATE_TEXT` conectada al modelo `gemini-1.5-flash` de Vertex AI. Los resultados se persisten en `gold_sentiment_analysis` mediante un `MERGE` que solo procesa comentarios nuevos (identificados con `LEFT JOIN ... WHERE IS NULL`). La respuesta del modelo se parsea con `JSON_EXTRACT_SCALAR` para extraer la etiqueta de sentimiento.

  > **Actualización (2026-08-02):** `gemini-1.5-flash` fue retirado de Vertex AI (confirmado vía `GET publishers/google/models/gemini-1.5-flash` → `404 NOT_FOUND`). El `ENDPOINT` del modelo remoto `gold.gemini_flash_model` (`infra/bigquery.tf`) se actualizó a `gemini-2.5-flash` — mismo tier "flash", GA en `us-central1`, sin impacto material en el presupuesto estimado de esta sección dado el volumen (~125 comentarios/semana, prompts cortos). Decisión de Diego, ver `.claude/skills/gold-sentiment-analysis/SKILL.md`.
* **Generación de Embeddings:** Se crean vectores densos de 768 dimensiones mediante `ML.GENERATE_EMBEDDING` con el modelo `text-embedding-004`. Solo se generan embeddings para comentarios que aún no existen en `gold_youtube_embeddings`.
* **Búsqueda Semántica Nativa:** Se construye un índice vectorial con `CREATE VECTOR INDEX IF NOT EXISTS`, que se actualiza incrementalmente. Las consultas de similitud usan la función `VECTOR_SEARCH` nativa de BigQuery con distancia coseno.

#### Consultas SQL de la Capa Gold:

```sql
-- 1. Análisis de Sentimiento con Vertex AI Gemini (MERGE Idempotente)
-- docs-maintenance (2026-08-02): la subquery de entrada a ML.GENERATE_TEXT debe
-- seleccionar s.comment_text explícitamente (no solo comment_id) — ML.GENERATE_TEXT
-- únicamente pasa a la salida las columnas presentes en su SELECT de entrada, y el
-- MERGE externo referencia S.comment_text. Bug real encontrado en el primer smoke
-- test end-to-end (BadRequest: "Unrecognized name: comment_text").
MERGE INTO `proyecto.dataset.gold_sentiment_analysis` T
USING (
  SELECT
    comment_id,
    comment_text,
    ml_generate_text_result
  FROM
    ML.GENERATE_TEXT(
      MODEL `proyecto.dataset.gemini_flash_model`,
      (
        SELECT
          s.comment_id,
          s.comment_text,
          CONCAT(
            'Clasifica el sentimiento del siguiente comentario de un video/DJ set como POSITIVO, NEGATIVO, NEUTRO o MIXTO. ',
            'Responde ÚNICAMENTE con una de estas cuatro palabras.',
            '\n\nComentario: ',
            s.comment_text
          ) AS prompt
        FROM `proyecto.dataset.silver_youtube_comments` s
        LEFT JOIN `proyecto.dataset.gold_sentiment_analysis` g
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

-- 2. Generación de Embeddings (INSERT incremental)
-- docs-maintenance (2026-08-02): ML.GENERATE_EMBEDDING no devuelve una columna
-- llamada "text_embedding" — el nombre real de salida es
-- ml_generate_embedding_result, hay que aliasearlo. Bug real encontrado al
-- correr la capa Gold end-to-end (InvalidQuery: "Unrecognized name: text_embedding").
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
      WHERE e.comment_id IS NULL
    )
  );

-- 3. Índice Vectorial (no se recrea, se actualiza incrementalmente)
CREATE VECTOR INDEX IF NOT EXISTS yt_comments_vector_index
ON `proyecto.dataset.gold_youtube_embeddings`(text_embedding)
OPTIONS(distance_type='COSINE', index_type='IVF');

-- 4. Ejemplo de Búsqueda Semántica por Similitud de Coseno
SELECT
  base.comment_id AS similar_comment_id,
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
  ON base.comment_id = silver.comment_id;
```

> **Nota sobre el índice vectorial:** `CREATE VECTOR INDEX IF NOT EXISTS` asegura que el índice no se recree en cada ejecución. BigQuery actualiza el índice incrementalmente a medida que se insertan nuevos embeddings; no requiere reconstrucción manual.
>
> **Actualización (2026-08-02):** `gold_youtube_embeddings` solo almacena `(comment_id, text_embedding)` — nunca `comment_text` (ver §4.3 arriba, `ML.GENERATE_EMBEDDING` solo inserta esas dos columnas). La versión original de esta consulta asumía `candidate.comment_text` disponible directamente en el resultado de `VECTOR_SEARCH`, lo cual habría fallado en ejecución. Se corrigió agregando el `JOIN` contra `silver_youtube_comments` — decisión documentada en `.claude/skills/gold-vector-search/SKILL.md`.
>
> **Actualización (2026-08-02, corrección adicional):** el alias `candidate` para la tabla base de `VECTOR_SEARCH` era incorrecto — cuando `query_value` se pasa como subquery escalar (no como un segundo argumento `TABLE`), BigQuery expone las columnas de la tabla base bajo el alias `base`, no `candidate`. Bug real confirmado en ejecución (`Unrecognized name: candidate`), corregido arriba y en `src/medallon_youtube/gold/vector_search.py`.
>
> **Actualización (2026-08-02, límite mínimo de filas para IVF):** `CREATE VECTOR INDEX ... OPTIONS(index_type='IVF')` requiere un mínimo de 5,000 filas en la tabla — BigQuery rechaza la creación por debajo de ese umbral con un mensaje explícito, sugiriendo usar `VECTOR_SEARCH` directamente (sin índice) mientras tanto. Al volumen actual del proyecto (~1,600-2,500 comentarios acumulados), el índice **no se puede crear todavía**; esto no es un bug — `VECTOR_SEARCH` funciona igual de correcto sin índice (búsqueda exhaustiva/brute-force), solo sin la optimización de latencia que el índice aportaría a partir de 5,000 filas. `ensure_vector_index` sigue siendo correcto tal cual está (`CREATE VECTOR INDEX IF NOT EXISTS`); simplemente no tendrá efecto hasta que se cruce el umbral, momento en el que BigQuery lo creará sin cambios de código.

---

## 5. Esquema del Contrato de Datos (Pydantic Model)

A continuación se especifica el modelo Pydantic que ejecuta la validación cliente en Python para separar registros válidos e inválidos hacia la `dead_letter_queue`:

```python
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional

class YouTubeCommentSchema(BaseModel):
    comment_id: str = Field(..., min_length=5, description="ID único del comentario de YT")
    video_id: str = Field(..., min_length=5, description="ID del video asociado")
    author: str = Field(..., min_length=1, description="Nombre del autor del comentario")
    comment_text: str = Field(..., min_length=1, description="Contenido en texto del comentario")
    like_count: int = Field(ge=0, description="Número de likes debe ser mayor o igual a cero")
    published_at: datetime = Field(..., description="Fecha de publicación válida en ISO 8601")

    @field_validator('comment_text')
    def text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('El comentario no puede contener únicamente espacios en blanco')
        return v
```

---

## 6. Plan de Monitoreo, Control de Costos y Matriz de Riesgos

### Presupuesto Operativo Estimado (Máximo $15.00 USD / Mes)

Para un escenario de 5 canales de DJs procesando aproximadamente ~2,500 comentarios al mes (~125 comentarios semanales en promedio, considerando que solo se ingieren videos de los últimos 7 días):

* **Cloud Scheduler:** $0.00 USD (Dentro de la cuota gratuita).
* **Cloud Run Jobs:** ~$0.15 USD (Ejecución semanal de < 3 minutos).
* **Cloud Storage (GCS):** ~$0.03 USD (< 20 MB de JSONs al mes).
* **BigQuery (Storage + Queries):** ~$0.40 USD.
* **Vertex AI (Gemini + Embeddings):** ~$0.80 - $1.20 USD.
* **Costo Total Estimado:** **~$1.40 - $1.80 USD / mes** *(Deja un margen libre del ~88% respecto al límite de $15 USD)*.

### Estrategia de Reintentos ante Fallos

Para garantizar resiliencia sin riesgo de loops infinitos, se aplica un esquema de reintentos en dos niveles:

| Nivel | Mecanismo | Configuración |
| :--- | :--- | :--- |
| **Orquestación** | Cloud Scheduler | `maxRetryAttempts=3` con exponential backoff. Solo reintenta 3 veces por ventana semanal. |
| **Ejecución** | Cloud Run Job | `--max-retries=3 --task-timeout=30m`. El job reintenta internamente hasta 3 veces antes de marcarse como fallido. |

- **Máximo total de intentos:** 9 (3 a nivel Scheduler × 3 a nivel Job).
- **Comportamiento ante fallo permanente:** Si se agotan los 9 intentos, el error se registra en Cloud Logging y no se vuelve a intentar hasta la siguiente ventana semanal (lunes siguiente). No hay reintentos ad-infinitum.
- **Monitoreo:** Se configura una alerta en Cloud Monitoring que notifica si un Cloud Run Job falla después de agotar todos los reintentos.

### Despliegue de Infraestructura con Terraform

Todos los recursos del pipeline se provisionan de forma declarativa mediante Terraform, incluyendo:

- **Cloud Scheduler:** Job cron con destino HTTP a Cloud Run.
- **Cloud Run Job:** Definición del job, variables de entorno (sin secrets en texto plano) y límites de recursos.
- **Artifact Registry:** Repositorio Docker para la imagen del contenedor.
- **BigQuery:** Datasets (`bronze`, `silver`, `gold`), tablas y modelos remotos de Vertex AI.
- **Cloud Storage:** Buckets GCS con reglas de ciclo de vida (borrado automático de raw data > 90 días).
- **Secret Manager:** Secreto para la API Key de YouTube, montado como variable de entorno en Cloud Run.
- **IAM:** Service account con permisos mínimos necesarios (principio de least privilege).

El estado de Terraform se almacena en un bucket GCS remoto con versionado habilitado, permitiendo colaboración y auditoría de cambios en infraestructura.

### Matriz de Riesgos

| Riesgo Identificado | Impacto | Mitigación Implementada |
| :--- | :--- | :--- |
| **Exceso de cuota en API de YouTube** | Medio | Límite estricto a 5 canales y paginado máximo de 100 elementos por query. |
| **Sobrecosto inesperado en Vertex AI** | Alto | Filtro incremental SQL para procesar únicamente comentarios nuevos que no existan en la tabla Gold. |
| **Fallo en esquema de origen (Breakage)** | Bajo | Captura automática en `silver_dead_letter_queue` mediante Pydantic sin detener el pipeline. |