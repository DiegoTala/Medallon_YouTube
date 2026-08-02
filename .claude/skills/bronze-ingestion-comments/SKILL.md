---
name: bronze-ingestion-comments
description: Cómo extraer comentarios y respuestas de primer nivel de los videos ya ingeridos vía YouTube Data API v3 y persistirlos como JSON Lines inmutable en GCS. Úsalo al escribir o modificar el paso de ingesta de comentarios del Cloud Run Job.
---

# bronze-ingestion-comments

## Alcance

Para cada video obtenido por [[bronze-ingestion-videos]] en el batch actual, extraer sus comentarios de nivel superior y las respuestas de primer nivel (reply thread), y escribirlos crudos a GCS. Igual que en bronze-ingestion-videos, **no se valida ni transforma nada aquí**.

## Atributos a extraer (PRD §2)

Comment ID, Video ID padre, Autor, Conteo de likes, Fecha de publicación, Texto del comentario, Respuestas de primer nivel.

## Flujo

1. Recibe la lista de `video_id` del batch actual (misma ejecución que bronze-ingestion-videos, mismo `batch_execution_id`).
2. Por cada video: `commentThreads.list` con `part=snippet,replies`, `maxResults=100`, paginando con `nextPageToken` hasta agotar o alcanzar el tope de la matriz de riesgos del PRD.
3. Si `commentThreads.list` marca el video con comentarios deshabilitados (error 403 `commentsDisabled`), se registra el video como "sin comentarios" y se continúa — no se detiene el batch completo.
4. Cada comment thread crudo (incluye sus replies anidadas) se serializa como una línea JSON.
5. Escribir a `gs://bucket-yt-bronze/raw/anio=YYYY/mes=MM/dia=DD/comments_batch_data_<batch_execution_id>.json`. El sufijo `<batch_execution_id>` es obligatorio por la misma razón que en [[bronze-ingestion-videos]]: sin él, una segunda corrida el mismo día sobreescribiría el archivo del batch anterior (corregido 2026-08-02).

## Snippet de ejemplo (Python)

```python
from googleapiclient.errors import HttpError
import json

def fetch_comment_threads(youtube, video_id: str) -> list[dict]:
    threads: list[dict] = []
    page_token = None
    try:
        while True:
            resp = youtube.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=100,
                pageToken=page_token,
                textFormat="plainText",
            ).execute()
            threads.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except HttpError as e:
        if e.resp.status == 403 and "commentsDisabled" in str(e):
            return []  # video sin comentarios habilitados, no es un error de batch
        raise
    return threads


def write_bronze_comments_jsonl(all_threads: dict[str, list[dict]], bucket, batch_date, batch_execution_id: str) -> str:
    path = (
        f"raw/anio={batch_date:%Y}/mes={batch_date:%m}/dia={batch_date:%d}"
        f"/comments_batch_data_{batch_execution_id}.json"
    )
    lines = [
        json.dumps({"video_id": video_id, "thread": thread}, ensure_ascii=False)
        for video_id, threads in all_threads.items()
        for thread in threads
    ]
    blob = bucket.blob(path)
    blob.upload_from_string("\n".join(lines), content_type="application/json")
    return path
```

## Invariantes

- **Inmutable**, igual que bronze-ingestion-videos: el nombre del archivo incluye `batch_execution_id`, nunca solo la partición por fecha.
- **Dependencia de orden:** solo se ingieren comentarios de videos que ya pasaron por bronze-ingestion-videos en el mismo `batch_execution_id` — no se procesan videos "sueltos".
- **Comentarios deshabilitados no son error:** se documenta y se sigue; no se reintenta ni se manda a dead-letter (no es un fallo de validación, es un estado válido del video).

## Relación con otros skills

- Alimenta a [[silver-validation-comments]], que a su vez valida `video_id` contra `silver_youtube_videos` (integridad referencial).
- El costo marginal de comentarios (mayor volumen que videos) es el driver principal del costo de GCS/BigQuery en [[cost-guardrail]].
