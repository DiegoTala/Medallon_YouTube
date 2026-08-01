---
name: silver-validation-videos
description: Cómo validar registros de video contra YouTubeVideoSchema (Pydantic v2), cargarlos a staging_youtube_videos y aplicar el MERGE idempotente hacia silver_youtube_videos. Úsalo al escribir o modificar el paso de validación/carga de videos.
---

# silver-validation-videos

## Alcance

Tomar el JSON Lines crudo de [[bronze-ingestion-videos]], validarlo registro por registro contra un contrato Pydantic estricto, separar válidos de inválidos, y aplicar un `MERGE` idempotente sobre `silver_youtube_videos`. Los inválidos van a [[silver-dead-letter-queue]], nunca se descartan silenciosamente.

## Contrato de datos (Pydantic v2)

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

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El título no puede estar vacío")
        return v
```

## Flujo de validación → staging → MERGE

```python
from pydantic import ValidationError
import json

def validate_batch(raw_lines: list[str], batch_execution_id: str) -> tuple[list[YouTubeVideoSchema], list[dict]]:
    valid: list[YouTubeVideoSchema] = []
    dead_letters: list[dict] = []

    for line in raw_lines:
        raw = json.loads(line)
        try:
            valid.append(YouTubeVideoSchema.model_validate(raw))
        except ValidationError as e:
            first_error = e.errors()[0]
            dead_letters.append({
                "error_timestamp": datetime.utcnow().isoformat(),
                "comment_id": None,
                "video_id": raw.get("video_id"),
                "raw_payload": raw,
                "validation_error": str(e),
                "error_field": ".".join(str(p) for p in first_error["loc"]),
                "batch_execution_id": batch_execution_id,
            })
    return valid, dead_letters
```

Los `valid` se insertan (load job, no streaming, para evitar costos de streaming insert) en `staging_youtube_videos`; los `dead_letters` van directo a `silver_dead_letter_queue` (ver [[silver-dead-letter-queue]]).

## MERGE idempotente

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

-- Limpieza obligatoria inmediatamente después del MERGE exitoso:
TRUNCATE TABLE `proyecto.dataset.staging_youtube_videos`;
```

## Invariantes

- **Idempotencia:** reprocesar el mismo batch produce `filas_nuevas = 0` en `silver_youtube_videos` (solo actualiza `view_count`/`like_count` si cambiaron).
- **Nunca se salta la validación:** ni siquiera para "arreglar rápido" un dato — un registro inválido siempre pasa por [[silver-dead-letter-queue]], jamás se descarta sin rastro ni se inserta a la fuerza en silver.
- **TRUNCATE de staging es obligatorio** tras cada MERGE exitoso, para no reprocesar en la siguiente corrida.

## Relación con otros skills

- Consume la salida de [[bronze-ingestion-videos]].
- Es prerrequisito de [[silver-validation-comments]] (integridad referencial `video_id`).
- Alimenta [[gold-sentiment-analysis]] y [[gold-embeddings-generation]] indirectamente vía `silver_youtube_comments`.
