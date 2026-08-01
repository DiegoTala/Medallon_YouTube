---
name: silver-validation-comments
description: Cómo validar comentarios contra YouTubeCommentSchema (Pydantic v2), verificar integridad referencial contra silver_youtube_videos, cargarlos a staging_youtube_comments y aplicar el MERGE idempotente hacia silver_youtube_comments. Úsalo al escribir o modificar el paso de validación/carga de comentarios.
---

# silver-validation-comments

## Alcance

Tomar el JSON Lines crudo de [[bronze-ingestion-comments]], validarlo contra un contrato Pydantic estricto **más** una verificación de integridad referencial (`video_id` debe existir en `silver_youtube_videos`), y aplicar `MERGE` idempotente sobre `silver_youtube_comments`.

## Contrato de datos (Pydantic v2)

```python
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class YouTubeCommentSchema(BaseModel):
    comment_id: str = Field(..., min_length=5, description="ID único del comentario de YT")
    video_id: str = Field(..., min_length=5, description="ID del video asociado")
    author: str = Field(..., min_length=1, description="Nombre del autor del comentario")
    comment_text: str = Field(..., min_length=1, description="Contenido en texto del comentario")
    like_count: int = Field(ge=0, description="Número de likes debe ser mayor o igual a cero")
    published_at: datetime = Field(..., description="Fecha de publicación válida en ISO 8601")

    @field_validator("comment_text")
    @classmethod
    def text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El comentario no puede contener únicamente espacios en blanco")
        return v
```

## Integridad referencial (FK aplicada en código, no en BigQuery)

BigQuery no aplica constraints de FK nativamente. La integridad se garantiza en esta capa: **todo comentario cuyo `video_id` no exista en `silver_youtube_videos` se rechaza** y se registra en la dead-letter queue con `error_field="video_id"`.

```python
def validate_comment_batch(
    raw_lines: list[str],
    known_video_ids: set[str],
    batch_execution_id: str,
) -> tuple[list[YouTubeCommentSchema], list[dict]]:
    valid: list[YouTubeCommentSchema] = []
    dead_letters: list[dict] = []

    for line in raw_lines:
        raw = json.loads(line)
        try:
            record = YouTubeCommentSchema.model_validate(raw)
        except ValidationError as e:
            first_error = e.errors()[0]
            dead_letters.append({
                "error_timestamp": datetime.utcnow().isoformat(),
                "comment_id": raw.get("comment_id"),
                "video_id": raw.get("video_id"),
                "raw_payload": raw,
                "validation_error": str(e),
                "error_field": ".".join(str(p) for p in first_error["loc"]),
                "batch_execution_id": batch_execution_id,
            })
            continue

        if record.video_id not in known_video_ids:
            dead_letters.append({
                "error_timestamp": datetime.utcnow().isoformat(),
                "comment_id": record.comment_id,
                "video_id": record.video_id,
                "raw_payload": raw,
                "validation_error": f"video_id '{record.video_id}' no existe en silver_youtube_videos",
                "error_field": "video_id",
                "batch_execution_id": batch_execution_id,
            })
            continue

        valid.append(record)

    return valid, dead_letters
```

`known_video_ids` se obtiene con un `SELECT video_id FROM silver_youtube_videos` **después** de que [[silver-validation-videos]] haya corrido su MERGE en el mismo batch — el orden de ejecución importa.

## MERGE idempotente

```sql
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

TRUNCATE TABLE `proyecto.dataset.staging_youtube_comments`;
```

## Invariantes

- **Orden estricto:** silver-validation-videos siempre corre antes que este skill dentro del mismo batch.
- **Idempotencia:** reprocesar el batch da `filas_nuevas = 0`.
- **Ningún comentario huérfano** entra a `silver_youtube_comments`.

## Relación con otros skills

- Depende de [[silver-validation-videos]] (orden de ejecución) y consume [[bronze-ingestion-comments]].
- Los rechazados van a [[silver-dead-letter-queue]].
- `silver_youtube_comments` es la fuente de [[gold-sentiment-analysis]] y [[gold-embeddings-generation]].
