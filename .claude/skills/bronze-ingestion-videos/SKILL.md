---
name: bronze-ingestion-videos
description: Cómo extraer metadatos de videos (no comentarios) de los canales de DJs configurados vía YouTube Data API v3 y persistirlos como JSON Lines inmutable en GCS. Úsalo al escribir o modificar el paso de ingesta de videos del Cloud Run Job.
---

# bronze-ingestion-videos

## Alcance

Extraer, por cada uno de los canales configurados (10 al 2026-09-05), los videos publicados en los últimos 7 días ($T-7$) y escribirlos **tal cual los devuelve la API** (sin transformar) a GCS. La validación de esquema ocurre después, en [[silver-validation-videos]] — esta capa nunca rechaza ni transforma datos.

## Atributos a extraer (PRD §2)

Video ID, Título, Descripción, Fecha de publicación, Idioma predeterminado, Canal propietario, Duración, Vistas, Me gusta.

## Autenticación

API Key de servidor (sin OAuth 2.0, sin usuario interactivo), leída desde Secret Manager y montada como variable de entorno en el Cloud Run Job — nunca hardcodeada ni en texto plano en el repo. El aprovisionamiento del secreto es responsabilidad de [[terraform-provision]]; este skill solo consume la env var ya inyectada.

## Flujo

1. `search.list` (o `playlistItems.list` sobre el uploads playlist del canal) filtrando por `publishedAfter = now - 7 días`, `maxResults=50`, paginado hasta agotar `nextPageToken` (tope duro: 100 elementos por query según matriz de riesgos del PRD).
2. `videos.list` con `part=snippet,contentDetails,statistics` para los IDs obtenidos, para traer duración/vistas/likes en una sola llamada por lote (hasta 50 IDs por request).
3. Cada respuesta cruda se serializa como una línea JSON (JSON Lines) por video.
4. Escribir a `gs://bucket-yt-bronze/raw/anio=YYYY/mes=MM/dia=DD/videos_batch_data_<batch_execution_id>.json`, particionado por la **fecha de ejecución** del batch (no por fecha de publicación del video). El sufijo `<batch_execution_id>` es obligatorio: sin él, una segunda corrida el mismo día sobreescribiría silenciosamente el archivo del batch anterior, violando la invariante de inmutabilidad (ver más abajo; corregido 2026-08-02).

## Snippet de ejemplo (Python)

```python
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone
import json

def fetch_recent_videos(youtube, channel_id: str, days: int = 7) -> list[dict]:
    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    video_ids: list[str] = []
    page_token = None

    while True:
        resp = youtube.search().list(
            part="id",
            channelId=channel_id,
            publishedAfter=published_after,
            type="video",
            maxResults=50,
            pageToken=page_token,
        ).execute()
        video_ids.extend(item["id"]["videoId"] for item in resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token or len(video_ids) >= 100:  # tope de la matriz de riesgos
            break

    videos_raw: list[dict] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        detail = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=",".join(chunk),
        ).execute()
        videos_raw.extend(detail.get("items", []))
    return videos_raw


def write_bronze_jsonl(records: list[dict], bucket, batch_date: datetime, batch_execution_id: str) -> str:
    path = (
        f"raw/anio={batch_date:%Y}/mes={batch_date:%m}/dia={batch_date:%d}"
        f"/videos_batch_data_{batch_execution_id}.json"
    )
    blob = bucket.blob(path)
    blob.upload_from_string(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        content_type="application/json",
    )
    return path
```

## Invariantes

- **Inmutable:** una vez escrito, un archivo bronze nunca se sobreescribe ni edita; una re-ejecución del mismo día genera un nuevo archivo o se anexa, nunca reemplaza el histórico. Se garantiza incluyendo `batch_execution_id` en el nombre del archivo (no solo la partición por fecha, que por sí sola no es suficiente para distinguir dos corridas el mismo día).
- **Sin validación aquí:** no se descarta ningún registro en esta capa, ni siquiera si luce corrupto — eso es trabajo de [[silver-validation-videos]] / [[silver-dead-letter-queue]].
- **Límite de canales:** entre 1 y 20, validado en `infra/variables.tf`; hoy 10. Siempre configurados fuera del código (`infra/terraform.tfvars`), nunca hardcodeados en el script. El número no es parte del contrato de este skill — leerlo del tfvars, no de aquí.

## Relación con otros skills

- Alimenta a [[silver-validation-videos]].
- El bucket y su ciclo de vida (borrado >90 días) se aprovisionan en [[terraform-provision]].
- El costo de las llamadas a la API de YouTube y el almacenamiento en GCS se estima en [[cost-guardrail]].
