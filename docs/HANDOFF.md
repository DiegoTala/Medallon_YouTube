# Handoff de sesión — YouTube DJ Analytics

**Fecha de corte:** 2026-08-02 (actualizado 19:20 -06:00) — el bug de §6 (modelos remotos) quedó **resuelto y verificado**, y en el smoke test siguiente apareció + se corrigió un segundo bug real (SQL de sentimiento, ver §6-bis). Corte actual: cuota diaria de YouTube API agotada por las múltiples corridas de hoy — el pipeline no puede re-ejecutarse completo hasta que resetee (ver §4, primer próximo paso).
**Propósito:** retomar el trabajo en otra sesión sin perder contexto. No es especificación (eso es `docs/PRD.md`) ni changelog de git — es una foto del estado + próximos pasos.

---

## 1. Estado del código (completo y probado)

Todo el pipeline está implementado en `src/medallon_youtube/` y pasa **41/41 tests** (`uv run pytest -q`):

| Capa | Módulo | Qué hace |
| :--- | :--- | :--- |
| Bronze | `bronze/videos.py`, `bronze/comments.py` | Extrae videos/comentarios de YouTube Data API v3 → JSON Lines inmutable en GCS. Nombre de archivo incluye `batch_execution_id` (evita sobreescritura en re-ejecuciones el mismo día — bug encontrado y corregido esta sesión). |
| Puente Bronze→Silver | `mapping.py` | Aplana el JSON crudo de la API (`item["snippet"]["channelTitle"]`, etc.) al shape plano que esperan los schemas Pydantic (`channel_name`, etc.). **Sin este módulo la validación de Silver rechazaría el 100% de los datos** — fue un gap real que no estaba en ningún SKILL.md, descubierto al escribir el test de integración. |
| Silver | `silver/dead_letter.py`, `silver/videos.py`, `silver/comments.py` | Validación Pydantic, FK de `video_id` contra `silver_youtube_videos`, staging + `MERGE` idempotente, dead-letter queue. |
| Gold | `gold/sentiment.py`, `gold/embeddings.py`, `gold/vector_search.py` | Sentimiento incremental (Gemini), embeddings incrementales (768-dim), índice vectorial + búsqueda semántica. |
| Config | `config.py` | Lee `PROJECT_ID`, `BRONZE_BUCKET`, `CHANNEL_IDS` de env vars; construye los nombres de tabla fully-qualified. |
| Orquestador | `main.py` | Entrypoint del Cloud Run Job — corre Bronze → Silver → Gold en secuencia estricta (videos antes que comentarios, ambos antes de Gold). |

### Decisiones tomadas esta sesión (documentadas en el arnés)

1. **`gold/vector_search.py` — Opción B (JOIN, no duplicar columna):** `gold_youtube_embeddings` solo tiene `(comment_id, text_embedding)`. `semantic_search` ahora recibe `silver_comments_table` y hace `JOIN` para traer `comment_text`, en vez de duplicarlo en la tabla de embeddings. Documentado en `.claude/skills/gold-vector-search/SKILL.md` y `docs/PRD.md` §4.3 (nota fechada, sin borrar el original).
2. **Inmutabilidad de Bronze:** el nombre de archivo bronze ahora incluye `batch_execution_id` (`videos_batch_data_<id>.json`). Sin esto, dos corridas el mismo día se sobreescribían — violaba la invariante ya escrita en el SKILL.md. Corregido en código + `.claude/skills/bronze-ingestion-videos/SKILL.md` + `bronze-ingestion-comments/SKILL.md`.

---

## 2. Estado de infraestructura (GCP real)

**Todo lo declarativo está aplicado.** `terraform plan` sin `-target` da "No changes. Your infrastructure matches the configuration." (verificado 2026-08-02T17:33 -06:00, y de nuevo tras el fix de IAM de gold a las 18:01). 8 ciclos de approval-gate en total, ver `infra/APPROVALS.md` para el registro completo con costos y aprobaciones verbatim:

1. Bucket de Terraform state (`medallon-youtube-tfstate`) — 2026-08-02T16:59:30-06:00.
2. 23 recursos base (GCS bronze, BigQuery bronze/silver/gold + staging + dead-letter, conexión Vertex AI + modelos remotos, Artifact Registry `yt-pipeline`, IAM, service accounts) — 2026-08-02T17:10:35-06:00.
3. IAM fix para la SA por defecto de Compute (`storage.objectViewer` + `artifactregistry.writer`) — necesario para que `gcloud builds submit` (Cloud Build) pudiera leer su propio source upload; Google ya no otorga estos roles automáticamente en proyectos nuevos — 2026-08-02T17:18:25-06:00.
4. **[DESTROY]** contenedor `google_secret_manager_secret.youtube_api_key` (0 versiones, sin datos) + su IAM binding — reemplazado por referencia (`data` source, no gestionado por Terraform) al secreto `API-YouTube` que Diego ya tenía creado manualmente con el valor real cargado — 2026-08-02T17:30:19-06:00.
5. Cloud Run Job (imagen `yt-pipeline/ingestion:5737210`) + su IAM binding + Cloud Scheduler (lunes 02:00 UTC) + IAM accessor sobre `API-YouTube` — 2026-08-02T17:33:01-06:00.
6. Redeploy de imagen a `:1055137` (fix de dead-letter, ver §6) — 2026-08-02T17:49:42-06:00.
7. IAM: `roles/bigquery.dataEditor` sobre `gold` para la SA del Job (faltaba, solo tenía `silver`) — 2026-08-02T18:01:04-06:00.

**Imagen desplegada actualmente:** `us-central1-docker.pkg.dev/medallon-youtube/yt-pipeline/ingestion:1055137` (commit `1055137`), construida vía `gcloud builds submit` (Cloud Build, no Docker local — el daemon local requiere permisos que el usuario WSL no tiene). `infra/terraform.tfvars` fija `image_tag = "1055137"`.

**Bug real encontrado y corregido en el `Dockerfile`** (commit `5737210`): `RUN uv sync --frozen --no-dev` corría *antes* de `COPY src/ ./src/`, así que hatchling no encontraba el paquete a empaquetar dentro del build de Cloud Build (invisible en local porque `src/` ya existe en el repo). Corregido también en el snippet de `.claude/skills/deploy-release/SKILL.md`.

**Secreto usado:** `API-YouTube` (Secret Manager, 1 versión enabled, creado manualmente por Diego fuera de Terraform) — no `youtube-api-key` como decían las sesiones anteriores de este handoff; ese nombre se descartó y se destruyó (ver ciclo 4 arriba). `infra/secrets.tf` ahora solo tiene un `data` source de solo lectura sobre `API-YouTube`.

### Los 5 canales configurados (`infra/terraform.tfvars`)

Resueltos por scraping de solo lectura (sin API key), verificados contra el `<title>` de cada página:

- Alesso → `UC05i95k-w8CvrtZ-yGTob7A`
- ILLENIUM → `UCv0tIDoaBZCTXQvVO4zosng`
- Swedish House Mafia → `UC5HEq5U--O5nn134mizyCcw`
- Third Party → `UCD0LPhlTZ9XANWXQh3t-VsQ`
- Martin Garrix → `UC5H_KXkPbEsGs0tFt8R35mA`

---

## 3. Nota operativa importante: autenticación local para Terraform en WSL

`gcloud auth application-default login` **no funciona en este entorno WSL** (no puede abrir navegador; `--no-browser` tampoco completó el flujo). El workaround que sí funcionó para correr `terraform plan`/`apply` localmente:

```bash
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)
terraform plan ...   # el provider google detecta esta env var automáticamente
```

`gcloud auth login` (no ADC) ya está autenticado como `diego@talamantes.com.mx` contra el proyecto `medallon-youtube` — de ahí sale el token. **El token expira en ~1 hora**, hay que regenerarlo (`gcloud auth print-access-token`) en cada sesión nueva de terminal antes de correr Terraform. Esto es solo para uso interactivo local; el Cloud Run Job en producción usa su propia service account vía metadata server, sin este problema.

---

## 4. Próximos pasos, en orden

1. **Esperar a que resetee la cuota diaria de YouTube API** (`Search Queries per day`, `youtube.googleapis.com`) — se agotó por las múltiples corridas completas de hoy (cada intento fallido de un Job con `max-retries=3` vuelve a correr Bronze desde cero, multiplicando las llamadas a `search.list`). Resetea a medianoche Pacific Time.
2. **Re-ejecutar el Cloud Run Job** una vez reseteada la cuota, ya con la imagen nueva desplegada (ver §6-bis para el estado del build/deploy):
   ```bash
   gcloud run jobs execute yt-ingestion-job --region=us-central1 --project=medallon-youtube
   ```
   No pasa por approval-gate (no es mutación de infraestructura declarativa), pero gasta cuota real de YouTube API y Vertex AI.
3. **Verificación con `gcloud-diagnostics`** (solo lectura) tras la corrida: logs del Job, filas nuevas en `silver_youtube_videos`/`silver_youtube_comments`/`gold_sentiment_analysis`/`gold_youtube_embeddings`, y revisar `silver_dead_letter_queue` por si algo falló validación.
4. Si el smoke test pasa completo (Bronze → Silver → Gold sin errores): no queda nada pendiente — el pipeline corre solo cada lunes vía Cloud Scheduler.

## 5. Sin commitear

Ver `git status` al retomar. Si el commit de esta sesión (fix de modelos remotos + bug de sentimiento) ya se hizo, este archivo (`docs/HANDOFF.md`) puede seguir mostrando cambios sin commitear por la naturaleza de ir documentando sobre la marcha — no es señal de nada pendiente salvo que se indique explícitamente aquí.

---

## 6. [RESUELTO] Los modelos remotos de Vertex AI nunca se crearon

**Historial del smoke test (3 corridas, cada una avanzó más lejos):**

| Corrida | Resultado | Causa |
| :--- | :--- | :--- |
| `yt-ingestion-job-6snbt` (imagen `:5737210`) | Falló 4/4 intentos en Silver | `insert_rows_json` recibía un dict Python crudo para la columna `raw_payload` (tipo `JSON`) — BigQuery lo interpreta como intento de RECORD y lo rechaza (`"raw_payload is not a record"`). **Corregido** en `silver/dead_letter.py` con `json.dumps()` (commit `1055137`). |
| `yt-ingestion-job-lzlg6` (imagen `:1055137`) | Bronze + Silver OK, falló 4/4 en Gold | La SA `yt-ingestion-job` nunca tuvo ningún IAM grant sobre el dataset `gold` (solo `silver`) → `403 Access Denied` al intentar `ML.GENERATE_TEXT` contra `gold.gemini_flash_model`. **Corregido** con `google_bigquery_dataset_iam_member.yt_ingestion_job_gold_editor` (aplicado, ciclo 7 de §2). |
| `yt-ingestion-job-bwg7n` (mismo IAM ya corregido) | Bronze + Silver OK, falló 4/4 en Gold con error distinto | `404 Not found: Model medallon-youtube:gold.gemini_flash_model` — **el modelo nunca existió**, ver diagnóstico abajo. **Sin corregir.** |

**Diagnóstico confirmado** (`terraform state show google_bigquery_job.create_gemini_flash_model`, y lo mismo para `create_embedding_model`): el job de Terraform reporta `state = "DONE"` (por eso el primer `terraform apply` de la sesión, ciclo 2 de §2, no falló y nadie lo notó), pero dentro de ese mismo `status` viene:

```
error_result = {
  message = "Cannot set create disposition in jobs with ML DDL statements"
  reason  = "invalidQuery"
}
```

**Causa raíz:** el recurso `google_bigquery_job` (proveedor `hashicorp/google`) aplica por defecto `create_disposition = "CREATE_IF_NEEDED"` en el bloque `query` — pero BigQuery rechaza ese parámetro en cualquier query con una sentencia DDL de ML (`CREATE OR REPLACE MODEL ...`). El job "corrió" (por eso `state = DONE`), pero la query subyacente falló de inmediato — y **Terraform no propaga ese `error_result` como fallo del `apply`**, así que el recurso se marcó como creado exitosamente sin que nadie lo viera hasta que el pipeline intentó usar el modelo.

**Fix necesario en `infra/bigquery.tf`** (recursos `google_bigquery_job.create_gemini_flash_model` y `google_bigquery_job.create_embedding_model`, ambos con el mismo problema): agregar `create_disposition = ""` dentro del bloque `query {}` de cada uno, para que el provider no envíe ese parámetro en absoluto — es lo que exige BigQuery para queries con DDL de ML. Verificar con `terraform plan` que el cambio efectivamente marca el recurso para recrear/re-ejecutar (el `job_id` fijo puede requerir que Terraform lo destruya y recree, no solo "update in place", dado que un BigQuery Job es inmutable una vez creado — confirmar el comportamiento exacto del provider antes de aplicar).

**Resolución real (2026-08-02, sesión siguiente), en 3 vueltas — cada una destapó la siguiente:**

1. `create_disposition = ""` (como se planteó arriba) resolvió ese error específico, pero el mismo `job_id` (`-v1`) ya estaba "quemado" en la API de BigQuery — un job nunca se puede re-crear con un `job_id` ya usado, aunque haya fallado y Terraform lo haya "destruido" de su state (BigQuery no tiene delete real de jobs). Subir el sufijo de versión (`-v2`) fue necesario.
2. Con `-v2` + `create_disposition = ""`, apareció un segundo error del mismo tipo: `Cannot set write disposition in jobs with ML DDL statements` — el provider también manda `write_disposition = "WRITE_EMPTY"` por defecto. Fix: `write_disposition = ""` también. Requirió subir a `-v3` (mismo motivo: `-v2` ya quemado).
3. Con ambas disposiciones vacías, el job por fin corrió limpio — pero entonces surgió que **`gemini-1.5-flash` fue retirado de Vertex AI** (`404 NOT_FOUND` confirmado vía diagnóstico de solo lectura contra la API pública de Vertex AI). Diego eligió `gemini-2.5-flash` como reemplazo (mismo tier "flash", GA en `us-central1`) entre 3 alternativas disponibles. `text-embedding-004` seguía vigente, sin cambios.

Los 3 ciclos de apply están registrados en `infra/APPROVALS.md` (entrada `fix-modelos-remotos-ml-ddl-y-gemini-retirado`, 2026-08-02T18:52:34-06:00). Verificado con `bq show --model` (solo lectura): ambos modelos existen, `error_result = []`, endpoints correctos.

**Gap adicional encontrado en el smoke test posterior:** con los modelos ya existiendo, el Job seguía fallando en Gold — esta vez con `403 Access Denied: ... bigquery.connections.use` sobre `vertex-ai-connection`. La SA del Job tenía `roles/bigquery.dataEditor` sobre el dataset `gold`, pero la *conexión* BigQuery↔Vertex AI es un recurso IAM separado. Fix: `google_bigquery_connection_iam_member` (`roles/bigquery.connectionUser`) agregado en `infra/iam.tf`, aplicado (`infra/APPROVALS.md`, entrada `iam-gap-connection-vertex-ai`, 2026-08-02T19:04:15-06:00).

## 6-bis. Bug real encontrado tras resolver §6: SQL de sentimiento (corregido) + cuota YouTube agotada (bloqueador temporal, no requiere acción)

Con los modelos y el IAM de la conexión ya corregidos, el siguiente smoke test avanzó hasta Gold y falló con `400 BadRequest: Unrecognized name: comment_text; Did you mean comment_id?` en el `MERGE` de `run_sentiment_analysis`.

**Causa raíz:** la subquery de entrada a `ML.GENERATE_TEXT` en `src/medallon_youtube/gold/sentiment.py` seleccionaba `s.comment_id` y armaba `prompt` con `CONCAT(..., s.comment_text)`, pero nunca seleccionaba `s.comment_text` como columna propia. `ML.GENERATE_TEXT` solo pasa a la salida las columnas presentes en el `SELECT` de entrada — el `MERGE` externo referencia `S.comment_text`, que nunca llegó. Este bug estaba también en el SQL de referencia del propio `docs/PRD.md` §4.3 (no era solo un typo del código, sino un error en la especificación original).

**Fix aplicado:** agregado `s.comment_text,` al `SELECT` de entrada, en `src/medallon_youtube/gold/sentiment.py`, `docs/PRD.md` §4.3 y `.claude/skills/gold-sentiment-analysis/SKILL.md`. Test `tests/test_gold.py::test_run_sentiment_analysis_runs_merge_with_incremental_filter` actualizado para verificar la columna — el test anterior usaba un mock de BigQuery y nunca habría detectado este bug (no ejecuta SQL real). 41/41 tests siguen pasando.

**Por qué el mismo run también falló en los reintentos con `429 rateLimitExceeded` (YouTube API):** cada ejecución del Cloud Run Job corre Bronze→Silver→Gold desde cero; con `max-retries=3`, un fallo en Gold dispara hasta 4 corridas completas de Bronze en la misma ejecución. Sumado a las corridas previas de la sesión (antes de resolver §6), se agotó la cuota diaria de `Search Queries` de YouTube Data API v3. **No es un bug — resetea solo, a medianoche Pacific Time.** No se pidió (ni se debe pedir sin aprobación explícita) un aumento de cuota vía consola — eso tampoco sería un cambio de Terraform, sería una acción manual fuera del arnés.

**Pendiente al cierre de esta sesión:** el fix del bug de sentimiento está en código pero **no desplegado** — la imagen corriendo (`:1055137`) es anterior. Ver §4 para los próximos pasos (build/deploy vía `deploy-release` + re-run tras reset de cuota).
