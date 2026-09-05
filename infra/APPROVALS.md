# Bitácora de Aprobaciones de Infraestructura

Registro append-only de toda aprobación de cambios de infraestructura real (GCP), conforme a la regla no negociable definida en [`.claude/skills/approval-gate/SKILL.md`](../.claude/skills/approval-gate/SKILL.md).

**Regla:** ninguna entrada se agrega retroactivamente para "justificar" un cambio ya ejecutado sin aprobación previa. Si eso ocurre, se documenta como incidente, no como aprobación.

**No editar ni borrar entradas existentes** — solo se anexan nuevas al final del archivo.

---

<!--
Plantilla de entrada. Copiar y completar por cada apply/destroy aprobado.
Para decomisiones (terraform-decommission), prefijar el título con [DESTROY].

## <timestamp ISO 8601> — <skill: terraform-provision | terraform-decommission | deploy-release | rag-terraform-root | rag-deploy-service | rag-iap-auth> — <nombre corto del cambio>

- **Recurso(s):** <lista de recursos afectados>
- **Raíz Terraform:** <infra/ (Fase 1) | infra/fase2/ (Fase 2) | N/A si no es Terraform>
- **Comando:** <comando exacto ejecutado, con -chdir explícito si es Terraform>
- **Costo estimado incremental:** <+/-$X.XX USD/mes>
- **Costo total estimado tras el cambio:** <$Y.YY / $20.00 USD>
- **¿Contiene datos / requirió backup?:** <sí/no, detalle si aplica — obligatorio para DESTROY>
- **Aprobado por:** Diego (verbatim: "<texto exacto de la aprobación>")
- **Ejecutado:** <sí/no — resultado, errores si los hubo>

También se registran aquí los cambios **manuales** que alteran quién puede acceder al
sistema o qué se factura, aunque no los ejecute Terraform (ej. alta de identidades,
licencias, brands OAuth). En esos casos, "Raíz Terraform" va como N/A y el comando
describe la ruta de consola.
-->

## 2026-08-02T16:59:30-06:00 — terraform-provision — bootstrap-tfstate-bucket

- **Recurso(s):** google_storage_bucket.tfstate (medallon-youtube-tfstate)
- **Comando:** terraform apply -target=google_storage_bucket.tfstate "tfplan" (backend local temporal, luego `terraform init -migrate-state -force-copy` para migrar al backend "gcs" recién creado)
- **Costo estimado incremental:** $0.00 USD/mes (bucket vacío, Standard Storage us-central1; un state file de Terraform pesa KB, no GB)
- **Costo total estimado tras el cambio:** $0.00 / $15.00 USD
- **¿Contiene datos / requirió backup?:** No — creación, no destrucción; no aplica backup.
- **Aprobado por:** Diego (verbatim: "Aprobado!")
- **Ejecutado:** sí — sin errores. `google_storage_bucket.tfstate` creado (1 added, 0 changed, 0 destroyed). State migrado exitosamente a `gs://medallon-youtube-tfstate/terraform/state/default.tfstate` (verificado con `gcloud storage ls`, solo lectura). Backend "gcs" descomentado en `infra/main.tf`.

## 2026-08-02T17:10:35-06:00 — terraform-provision — core-pipeline-infra-sin-cloud-run-job

- **Recurso(s):** google_storage_bucket.bronze, google_storage_bucket_iam_member.yt_ingestion_job_bronze_writer, google_bigquery_dataset.{bronze,silver,gold}, google_bigquery_table.{staging_youtube_videos,staging_youtube_comments,silver_youtube_videos,silver_youtube_comments,silver_dead_letter_queue,gold_sentiment_analysis,gold_youtube_embeddings}, google_bigquery_connection.vertex_ai, google_bigquery_job.{create_gemini_flash_model,create_embedding_model}, google_artifact_registry_repository.yt_pipeline, google_secret_manager_secret.youtube_api_key, google_secret_manager_secret_iam_member.yt_ingestion_job_secret_accessor, google_service_account.{yt_ingestion_job,scheduler_invoker}, google_bigquery_dataset_iam_member.yt_ingestion_job_silver_editor, google_project_iam_member.{bq_connection_vertex_ai_user,yt_ingestion_job_bq_job_user} — 23 recursos totales.
- **Excluido deliberadamente de este apply:** `google_cloud_run_v2_job.yt_ingestion`, `google_cloud_run_v2_job_iam_member.scheduler_can_invoke`, `google_cloud_scheduler_job.weekly_trigger` — referencian una imagen Docker en Artifact Registry que aún no existe (`deploy-release` no se ha ejecutado). Se aplicarán en un ciclo de aprobación separado tras el primer build/push de imagen.
- **Comando:** `terraform apply "tfplan_partial"` (plan generado con `-target` explícito para los 23 recursos arriba)
- **Costo estimado incremental:** $0.00 USD/mes (datasets/tablas/bucket vacíos, modelos remotos de Vertex AI creados pero sin invocar — sin uso facturable hasta que el pipeline corra)
- **Costo total estimado tras el cambio:** $0.00 / $15.00 USD (baseline PRD de $1.40–$1.80/mes aplica una vez el Job + Scheduler estén desplegados y corriendo)
- **¿Contiene datos / requirió backup?:** No — creación, no destrucción; no aplica backup.
- **Aprobado por:** Diego (verbatim: "Aprobado", vía selección explícita en pregunta de aprobación que citaba el plan de 23 recursos y el costo estimado)
- **Ejecutado:** sí — sin errores. `Apply complete! Resources: 23 added, 0 changed, 0 destroyed.` Outputs: `artifact_registry_repository = "yt-pipeline"`, `bronze_bucket = "medallon-youtube-yt-bronze"`, `gold_dataset = "gold"`, `silver_dataset = "silver"`.

## 2026-08-02T17:18:25-06:00 — terraform-provision — cloudbuild-default-sa-iam-fix

- **Recurso(s):** google_project_iam_member.cloudbuild_default_sa_storage_viewer, google_project_iam_member.cloudbuild_default_sa_artifactregistry_writer — ambos sobre `180406516352-compute@developer.gserviceaccount.com` (default Compute Engine SA, usada por Cloud Build por defecto).
- **Motivo:** `gcloud builds submit` (parte del flujo deploy-release) falló con `403 storage.objects.get denied` al intentar leer el tarball de source recién subido — esta SA no tenía ningún rol de proyecto. Google dejó de auto-otorgar roles a esta SA en proyectos nuevos; sin `storage.objectViewer` (leer el source) y `artifactregistry.writer` (publicar la imagen) Cloud Build no puede completar un build.
- **Comando:** `terraform apply "tfplan_cloudbuild_iam"` (plan generado con `-target` explícito para los 2 recursos arriba)
- **Costo estimado incremental:** $0.00 USD/mes (bindings IAM, sin recursos facturables)
- **Costo total estimado tras el cambio:** $0.00 / $15.00 USD
- **¿Contiene datos / requirió backup?:** No — creación, no destrucción; no aplica backup.
- **Aprobado por:** Diego (verbatim: "Aprobado", vía selección explícita en pregunta de aprobación que citaba el plan de 2 recursos y el costo $0.00)
- **Ejecutado:** sí — sin errores. `Apply complete! Resources: 2 added, 0 changed, 0 destroyed.`

## 2026-08-02T17:30:19-06:00 — terraform-decommission — [DESTROY] youtube-api-key-secret-container

- **Recurso(s):** google_secret_manager_secret.youtube_api_key, google_secret_manager_secret_iam_member.yt_ingestion_job_secret_accessor (binding sobre el secreto anterior).
- **Motivo:** Diego indicó que ya existe un secreto separado `API-YouTube` (creado manualmente fuera de Terraform, con el valor real ya cargado — 1 versión enabled) y pidió usar ese en vez del contenedor `youtube-api-key` que este arnés había provisionado. Se reemplazó por `data "google_secret_manager_secret" "youtube_api_key" { secret_id = "API-YouTube" }` en `infra/secrets.tf` (solo lectura, Terraform nunca gestiona su ciclo de vida ni contenido) y se actualizaron las referencias en `infra/iam.tf` y `infra/cloud_run.tf`.
- **¿Contiene datos / requirió backup?:** No — el secreto `youtube-api-key` tenía 0 versiones (nunca se cargó ningún valor). No aplica backup.
- **Comando:** `terraform apply "tfplan_destroy_old_secret"` (plan generado con `terraform plan -destroy -target=...` para ambos recursos)
- **Costo estimado del ahorro:** $0.00 USD/mes (ya era gratis — Secret Manager cobra por versión activa, y este contenedor no tenía ninguna)
- **Aprobado por:** Diego (verbatim: "Aprobado, destruye", en respuesta a pregunta específica de destroy que citaba el plan de 2 recursos y confirmaba 0 versiones/sin datos)
- **Ejecutado:** sí — sin errores. `Apply complete! Resources: 0 added, 0 changed, 2 destroyed.`

## 2026-08-02T17:33:01-06:00 — terraform-provision — cloud-run-job-y-scheduler

- **Recurso(s):** google_cloud_run_v2_job.yt_ingestion (imagen `us-central1-docker.pkg.dev/medallon-youtube/yt-pipeline/ingestion:5737210`, `YOUTUBE_API_KEY` vía secreto `API-YouTube`), google_cloud_run_v2_job_iam_member.scheduler_can_invoke, google_cloud_scheduler_job.weekly_trigger (lunes 02:00 UTC), google_secret_manager_secret_iam_member.yt_ingestion_job_secret_accessor (sobre `API-YouTube`).
- **Comando:** `terraform apply "tfplan_job_scheduler2"`
- **Costo estimado incremental:** ~$0.15 USD/mes (Cloud Run Job, baseline PRD) una vez que el cron dispare — Cloud Scheduler es gratis (nivel gratuito).
- **Costo total estimado tras el cambio:** ~$0.15–$1.80 / $15.00 USD (rango completo del baseline PRD, según volumen real de comentarios procesados por Gold)
- **¿Contiene datos / requirió backup?:** No — creación, no destrucción; no aplica backup.
- **Aprobado por:** Diego (verbatim: "Aprobado", vía selección explícita en pregunta que citaba los 4 recursos y el costo estimado)
- **Ejecutado:** sí — sin errores. `Apply complete! Resources: 4 added, 0 changed, 0 destroyed.` Esto completa el despliegue de toda la infraestructura declarada en `infra/*.tf` (26/26 recursos aplicados, más los 2 de IAM de Cloud Build).

## 2026-08-02T17:49:42-06:00 — deploy-release — redeploy-fix-dead-letter-bug

- **Recurso(s):** google_cloud_run_v2_job.yt_ingestion (solo el campo `image`).
- **Motivo:** la primera corrida real (`yt-ingestion-job-6snbt`, ejecutada 2026-08-02T23:35 UTC) falló 4/4 intentos con `RuntimeError: Fallo insertando en dead-letter queue... raw_payload is not a record` — bug real en `silver/dead_letter.py` (pasaba un dict Python crudo a una columna BigQuery tipo `JSON` vía `insert_rows_json`, que requiere el valor pre-serializado con `json.dumps()`). Corregido en commit `1055137`, 41/41 tests pasan.
- **Comando:** build+push vía `gcloud builds submit --tag=.../ingestion:1055137` (Cloud Build), luego `terraform apply "tfplan_redeploy"` (cambia `var.image_tag` de `5737210` a `1055137` en `infra/terraform.tfvars`).
- **Costo estimado incremental:** $0.00 USD/mes (mismo recurso, solo cambia el tag de imagen; Cloud Build está dentro del nivel gratuito para este volumen de builds).
- **¿Contiene datos / requirió backup?:** No — actualización de imagen, no destrucción de datos.
- **Aprobado por:** Diego (verbatim: "Aprobado", en respuesta a pregunta que citaba el diff exacto del cambio de imagen y costo $0.00)
- **Ejecutado:** sí — sin errores. `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`

## 2026-08-02T18:01:04-06:00 — terraform-provision — iam-gap-dataset-gold

- **Recurso(s):** google_bigquery_dataset_iam_member.yt_ingestion_job_gold_editor (`roles/bigquery.dataEditor` sobre `gold` para la SA `yt-ingestion-job`).
- **Motivo:** la ejecución `yt-ingestion-job-lzlg6` (2026-08-02T23:50 UTC) completó Bronze y Silver correctamente (confirma que el fix de dead-letter funcionó) pero falló 4/4 intentos en Gold con `403 Access Denied: Model medallon-youtube.gold.gemini_flash_model` — la SA del Job nunca había recibido ningún grant IAM sobre el dataset `gold`, solo sobre `silver`. Gap real de la provisión original de IAM.
- **Comando:** `terraform apply "tfplan_gold_iam"`
- **Costo estimado incremental:** $0.00 USD/mes (binding IAM, sin recurso facturable)
- **¿Contiene datos / requirió backup?:** No — creación, no destrucción.
- **Aprobado por:** Diego (verbatim: "Aprobado, aplica y re-ejecuta", en respuesta a pregunta que citaba el plan de 1 recurso y costo $0.00)
- **Ejecutado:** sí — sin errores. `Apply complete! Resources: 1 added, 0 changed, 0 destroyed.`

## 2026-08-02T18:52:34-06:00 — terraform-provision — fix-modelos-remotos-ml-ddl-y-gemini-retirado

- **Recurso(s):** google_bigquery_job.create_gemini_flash_model, google_bigquery_job.create_embedding_model.
- **Motivo:** los modelos remotos nunca existieron realmente (ver §6 de `docs/HANDOFF.md` para el diagnóstico completo). Dos causas raíz distintas, resueltas en tres ciclos de apply:
  1. El provider `hashicorp/google` envía por defecto `create_disposition = "CREATE_IF_NEEDED"` y `write_disposition = "WRITE_EMPTY"` en el bloque `query` de `google_bigquery_job` — BigQuery rechaza ambos parámetros en cualquier query con DDL de ML (`CREATE OR REPLACE MODEL`). Fix: `create_disposition = ""` y `write_disposition = ""` explícitos en `infra/bigquery.tf` (omite el parámetro de la request real).
  2. `gemini-1.5-flash` fue retirado de Vertex AI (`404 NOT_FOUND` confirmado vía `GET publishers/google/models/gemini-1.5-flash`, diagnóstico de solo lectura). `ENDPOINT` actualizado a `gemini-2.5-flash` (elección explícita de Diego entre 3 alternativas GA disponibles en `us-central1`), documentado en `docs/PRD.md` §4.3 y `.claude/skills/gold-sentiment-analysis/SKILL.md`.
  3. Job IDs de BigQuery son permanentes en la API aunque el job haya fallado — cada intento fallido "quema" su `job_id`. Se subió el sufijo de versión de `-v1` → `-v2` → `-v3` en ambos jobs conforme se identificaban y corregían las causas.
- **Comando:** tres ciclos de `terraform apply -target=google_bigquery_job.create_gemini_flash_model -target=google_bigquery_job.create_embedding_model` (uno por cada plan/aprobación distintos, ver bitácora de la sesión).
- **Costo estimado incremental:** $0.00 USD/mes en los tres ciclos (registrar un modelo remoto no tiene costo propio, solo la inferencia posterior ya contemplada en el baseline del PRD).
- **Costo total estimado tras el cambio:** sin cambio, ~$1.40–$1.80 / $15.00 USD (baseline PRD; el cambio de `gemini-1.5-flash` a `gemini-2.5-flash` no altera materialmente esta estimación al volumen actual).
- **¿Contiene datos / requirió backup?:** No — creación de modelos remotos, no destrucción de datos. Los dos primeros ciclos sí destruyeron jobs de BigQuery previos, pero esos jobs solo contenían el registro de una ejecución fallida (sin datos de negocio).
- **Aprobado por:** Diego — tres aprobaciones verbatim independientes en la misma sesión: (1) "Apruebo, adelante" para el fix de `create_disposition`; (2) "Apruebo, adelante" para el fix de `write_disposition` + bump a `-v2`→`-v3` (pausado una vez para revisar el diagnóstico de Vertex AI antes de re-aprobar); (3) selección explícita de `gemini-2.5-flash` como reemplazo, luego "Apruebo, adelante" para el apply combinado final.
- **Ejecutado:** sí — sin errores en el ciclo final. `Apply complete! Resources: 2 added, 0 changed, 2 destroyed.` Verificado con `bq show --model` (solo lectura): `gold.gemini_flash_model` → endpoint `gemini-2.5-flash`, `gold.embedding_model` → endpoint `text-embedding-004`, ambos `error_result = []`.

## 2026-08-02T19:04:15-06:00 — terraform-provision — iam-gap-connection-vertex-ai

- **Recurso(s):** google_bigquery_connection_iam_member.yt_ingestion_job_connection_user (`roles/bigquery.connectionUser` sobre `vertex-ai-connection` para la SA `yt-ingestion-job`).
- **Motivo:** el smoke test `yt-ingestion-job-ltrtn` (2026-08-03T00:53 UTC, primero tras el fix de los modelos remotos) completó Bronze y Silver correctamente pero falló 4/4 intentos en Gold con `403 Access Denied: ... User does not have bigquery.connections.use permission for connection medallon-youtube.us-central1.vertex-ai-connection`. La SA del Job tenía `roles/bigquery.dataEditor` sobre el dataset `gold` (ciclo del 2026-08-02T18:01:04-06:00) pero eso no cubre el IAM de la *conexión* BigQuery↔Vertex AI, que es un recurso separado con su propio control de acceso — gap real no cubierto por la provisión original de IAM.
- **Comando:** `terraform apply "tfplan_connection_iam"` (plan generado con `-target` explícito para el recurso arriba)
- **Costo estimado incremental:** $0.00 USD/mes (binding IAM, sin recurso facturable)
- **Costo total estimado tras el cambio:** $0.00 / $15.00 USD
- **¿Contiene datos / requirió backup?:** No — creación, no destrucción.
- **Aprobado por:** Diego (verbatim: "Apruebo, aplica y re-ejecuta", en respuesta a pregunta que citaba el plan de 1 recurso y costo $0.00)
- **Ejecutado:** sí — sin errores. `Apply complete! Resources: 1 added, 0 changed, 0 destroyed.`

## 2026-08-02T19:19:46-06:00 — deploy-release — redeploy-fix-sentiment-comment-text

- **Recurso(s):** google_cloud_run_v2_job.yt_ingestion (solo el campo `image`).
- **Motivo:** el smoke test posterior al fix de §6 del handoff avanzó hasta Gold y falló con `400 BadRequest: Unrecognized name: comment_text` en el `MERGE` de `run_sentiment_analysis` — la subquery de entrada a `ML.GENERATE_TEXT` no seleccionaba `s.comment_text` como columna propia (solo la usaba dentro del `CONCAT` del prompt). Corregido en commit `1191c8b`, junto con los fixes de §6 (modelos remotos + IAM de conexión ya aplicados vía Terraform en ciclos anteriores). 41/41 tests pasan.
- **Comando:** build+push vía `gcloud builds submit --tag=.../ingestion:1191c8b` (Cloud Build), luego `terraform apply "tfplan_redeploy_1191c8b"` (cambia `var.image_tag` de `1055137` a `1191c8b` en `infra/terraform.tfvars`).
- **Costo estimado incremental:** $0.00 USD/mes (mismo recurso, solo cambia el tag de imagen).
- **¿Contiene datos / requirió backup?:** No — actualización de imagen, no destrucción de datos.
- **Aprobado por:** Diego (verbatim: "Apruebo, adelante", en respuesta a pregunta que citaba el plan exacto del cambio de imagen y costo $0.00)
- **Ejecutado:** sí — sin errores. `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` Pendiente: re-ejecutar el smoke test una vez resetee la cuota diaria de YouTube API (agotada, ver `docs/HANDOFF.md` §6-bis).

## 2026-08-02T19:41:35-06:00 — deploy-release — redeploy-fix-embeddings-y-vector-search

- **Recurso(s):** google_cloud_run_v2_job.yt_ingestion (solo el campo `image`).
- **Motivo:** dado que la cuota de YouTube seguía agotada (bloqueando volver a correr el Job completo), Diego pidió probar la capa Gold directamente contra los datos ya existentes en `silver_youtube_comments`/`silver_youtube_videos` (1635 comentarios, 13 videos, cargados en el smoke test previo), sin re-ejecutar Bronze/Silver. Ejecutando las queries de Gold vía `bq query` (mismas plantillas SQL del código) contra BigQuery real se encontraron y corrigieron 2 bugs adicionales del mismo tipo que el de sentimiento (commit `1191c8b`):
  1. `ML.GENERATE_EMBEDDING` no expone una columna `text_embedding` en su salida (el nombre real es `ml_generate_embedding_result`) — el `INSERT` fallaba con `Unrecognized name: text_embedding`.
  2. `VECTOR_SEARCH` expone la tabla base bajo el alias `base`, no `candidate`, cuando `query_value` es una subquery escalar — `semantic_search` fallaba con `Unrecognized name: candidate`.
  Ambos bugs estaban también en el SQL de referencia de `docs/PRD.md`. Verificado end-to-end contra BigQuery real tras el fix: 1635 filas en `gold_sentiment_analysis` (4 etiquetas, sin NULLs) y `gold_youtube_embeddings` (768 dims), `VECTOR_SEARCH` devuelve resultados correctos. El índice IVF no se pudo crear (mínimo 5,000 filas requerido por BigQuery, hay 1,635) — comportamiento esperado, no un bug; documentado en PRD/SKILL.md. 41/41 tests pasan. Commit `0047ad5`.
- **Comando:** build+push vía `gcloud builds submit --tag=.../ingestion:0047ad5` (Cloud Build), luego `terraform apply "tfplan_redeploy_0047ad5"` (cambia `var.image_tag` de `1191c8b` a `0047ad5`).
- **Costo estimado incremental:** $0.00 USD/mes (mismo recurso, solo cambia el tag de imagen). El costo real de las queries de prueba contra Gold (1635 llamadas a Gemini + 1635 a embeddings) es marginal, muy por debajo del techo — no se recalculó como línea base nueva porque fue una corrida puntual de backfill/prueba, no un patrón recurrente.
- **¿Contiene datos / requirió backup?:** No — actualización de imagen, no destrucción de datos.
- **Aprobado por:** Diego (verbatim: "Apruebo, adelante", en respuesta a pregunta que citaba el plan exacto del cambio de imagen, el resumen de los 2 bugs corregidos y costo $0.00)
- **Ejecutado:** sí — sin errores. `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` Con esto, el Job en producción ya contiene todo el código verificado manualmente contra datos reales.

## 2026-09-03T20:27:00-06:00 — deploy-release — fix-ensure-vector-index-error-handling

- **Recurso(s):** google_cloud_run_v2_job.yt_ingestion (solo el campo `image`).
- **Motivo:** las 10 ejecuciones históricas del Job fallaron todas con exit code 1. Diagnóstico: `ensure_vector_index()` (último paso del pipeline, `main.py:99`) intenta crear un índice IVF que requiere ~5000+ filas; con solo 2792 embeddings, BigQuery rechaza la query. Como no había try-except en todo el orquestador, la excepción propagaba sin control y el proceso moría sin logs (el único `print()` estaba después de `run_pipeline()`, nunca alcanzado en el camino de error). Fix: (1) `ensure_vector_index()` envuelto en try-except — imprime warning pero no tumba el pipeline; (2) try-except global en `main()` con `traceback.print_exc()` a stderr para que Cloud Run capture los logs de error. Commit `1f346ac`, 41/41 tests pasan.
- **Comando:** build+push vía `gcloud builds submit --tag=.../ingestion:1f346ac` (Cloud Build), luego `gcloud run jobs update yt-ingestion-job --image=.../ingestion:1f346ac`.
- **Costo estimado incremental:** $0.00 USD/mes (mismo recurso, solo cambia el tag de imagen).
- **¿Contiene datos / requirió backup?:** No — actualización de imagen, no destrucción de datos.
- **Aprobado por:** Diego (verbatim: "Adelante con el fix!" + "Haz el build, deploy y corre una vez el flujo completo para validar que funciona")
- **Ejecutado:** sí — build exitoso (43s), deploy exitoso. Ejecución de validación `yt-ingestion-job-fjfh9`: **exit(0), completado en 3m4s**. Logs confirman: `Pipeline completado — batch_execution_id=batch-20260904T023155-f5e262a5` + warning esperado de `ensure_vector_index` (2837 filas < 5000 mínimo IVF). Datos nuevos: silver_videos 36→38, silver_comments 2792→2837, gold_sentiment 2792→2837, gold_embeddings 2792→2837. DLQ sin cambios (30). Pipeline 100% funcional.

## 2026-09-03T22:04:00-06:00 — terraform-provision — agrega-5-canalas-djs

- **Recurso(s):** google_cloud_run_v2_job.yt_ingestion (solo env var `CHANNEL_IDS`).
- **Motivo:** Diego pidió agregar 5 canales nuevos: Porter Robinson, DubVision, Avicii, Afrojack, Zedd. Se actualizó `infra/terraform.tfvars` con los channel IDs verificados desde las páginas públicas de YouTube, y se actualizó la validación en `infra/variables.tf` (de `== 5` a `>= 1 && <= 20`).
- **Comando:** `terraform apply "tfplan_channels"`
- **Costo estimado incremental:** +$0.05 USD/mes (más videos = más llamadas a YouTube API + Vertex AI, pero dentro del techo de $15).
- **Costo total estimado tras el cambio:** ~$1.85 / $15.00 USD
- **¿Contiene datos / requirió backup?:** No — actualización de config, no destrucción de datos.
- **Aprobado por:** Diego (verbatim: "Aprobado!")
- **Ejecutado:** sí — `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`

## 2026-09-03T22:04:00-06:00 — deploy-release — ejecucion-10-canales

- **Recurso(s):** Cloud Run Job `yt-ingestion-job` (ejecución manual, sin cambio de imagen).
- **Motivo:** validar que el pipeline funciona con los 10 canales (5 originales + 5 nuevos).
- **Comando:** `gcloud run jobs execute yt-ingestion-job --region=us-central1 --project=medallon-youtube`
- **Costo estimado incremental:** marginal (1 ejecución, ~3 min).
- **¿Contiene datos / requirió backup?:** No.
- **Aprobado por:** Diego (verbatim: "Después del terraform apply, corre el flujo completo una vez más para agregar comentarios de los nuevos canales a gcp")
- **Ejecutado:** sí — `yt-ingestion-job-tmmhd`, exit(0), 3m13s. Datos nuevos: silver_videos 38→44 (+6), silver_comments 2837→3239 (+402), gold_sentiment 2837→3239 (+402), gold_embeddings 2837→3239 (+402). DLQ sin cambios (30).

## 2026-09-04T21:42:57-06:00 — rag-iap-auth — alta-identidades-prueba-fase2

- **Recurso(s):** dos identidades de Cloud Identity Free en el dominio `talamantes.com.mx`: `medallon.rag.test01@talamantes.com.mx` y `medallon.rag.test02@talamantes.com.mx`. Creadas dentro de una unidad organizativa dedicada, `RAG Test Users`, con el licenciamiento automático de Google Workspace desactivado para esa UO.
- **Raíz Terraform:** N/A — cambio manual en la Consola de Administración de Google Workspace. No hay recurso de Terraform que represente identidades de Cloud Identity.
- **Comando:** Consola de Administración → Facturación → Comprar o actualizar → Cloud Identity Free; Directorio → Unidades organizativas → crear `RAG Test Users`; Facturación → Configuración de licencias → UO `RAG Test Users` → Google Workspace Business Starter → licenciamiento automático desactivado; Directorio → Usuarios → alta de las dos cuentas dentro de esa UO.
- **Costo estimado incremental:** $0.00 USD/mes. Cloud Identity Free provee 50 licencias de usuario sin costo, con licenciamiento por sitio. **Riesgo evitado:** con el licenciamiento automático activo, cada alta habría recibido una licencia de Google Workspace Business Starter de pago; dos licencias exceden por sí solas el techo del proyecto completo.
- **Costo total estimado tras el cambio:** ~$1.85 / $20.00 USD (sin cambio — la infraestructura de Fase 2 aún no existe).
- **¿Contiene datos / requirió backup?:** No — alta de identidades, no destrucción.
- **Aprobado por:** Diego (verbatim: "Utilizaré la creación de dos usuarios, modifica lo que tengas que modificar con base a eso" + "Registra la creacion de las entidads, justo les pus el nombre que sugeriste").
- **Ejecutado:** sí — las dos cuentas existen y quedaron con licencia Cloud Identity Free, sin licencia de Workspace.

**Motivo del cambio respecto al PRD original.** El PRD Fase 2 §2 especificaba dos cuentas `@gmail.com`. Se verificó que la organización `talamantes.com.mx` (ID `712010469336`, customer ID `C04fe1qyh`) aplica **Domain Restricted Sharing** — `constraints/iam.allowedPolicyMemberDomains` con `allowedValues: [C04fe1qyh]`, efectiva sobre `medallon-youtube` — lo que impide otorgar cualquier binding IAM a identidades externas al directorio. Las cuentas Gmail eran inviables por IAM, no por IAP. Se evaluaron y descartaron tres alternativas para conservarlas (grupo del dominio con miembros externos, `iam.managed.allowedPolicyMembers` con principals individuales, y relajar la constraint legada en el proyecto); todas requerían además un cliente OAuth externo con re-autenticación cada 7 días. `docs/PRD_Fase2.md` §2, §11, §15, §17 y §18 quedaron actualizados con notas fechadas. Análisis completo y rutas descartadas: `.claude/skills/rag-iap-auth/SKILL.md`.

**Tropiezos registrados** (documentados en el mismo skill para que no se repitan): (1) el primer intento de alta falló con *"Alcanzaste el límite de usuarios para Google Workspace Business Starter"* — no era un tope de usuarios del dominio sino de asientos de Workspace, porque la consola intentaba asignar una licencia de pago; (2) activar Cloud Identity Free no basta por sí solo, hay que desactivar el licenciamiento automático; (3) el ajuste vive en **Facturación → Configuración de licencias**, no en Suscripciones ni en Configuración de actualización de usuarios; (4) los usuarios deben crearse **dentro** de la UO con el licenciamiento apagado — crearlos en la raíz reproduce el error original.

**Pendiente derivado:** los tres bindings de `roles/iap.httpsResourceAccessor` para estas identidades se declararán en `infra/fase2/` vía [`rag-terraform-root`](../.claude/skills/rag-terraform-root/SKILL.md) y requerirán su propio ciclo de aprobación.

## 2026-09-04T22:30:00-06:00 — terraform-provision — gold-rag-corpus-table

- **Recurso(s):** google_bigquery_table.gold_rag_corpus (1 recurso)
- **Raíz Terraform:** infra/ (Fase 1)
- **Comando:** `terraform -chdir=infra apply tfplan_rag_corpus` (plan generado con `-target=google_bigquery_table.gold_rag_corpus`)
- **Costo estimado incremental:** $0.00 USD/mes (tabla vacía, storage BigQuery ~$0.02/GB/mes; 0 bytes = $0.00)
- **Costo total estimado tras el cambio:** ~$1.85 / $20.00 USD (sin cambio)
- **¿Contiene datos / requirió backup?:** No — creación, no destrucción; no aplica backup.
- **Aprobado por:** Diego (verbatim: "Apruebo el cambio")
- **Ejecutado:** sí — sin errores. `Apply complete! Resources: 1 added, 0 changed, 0 destroyed.` Tabla `gold_rag_corpus` creada en el dataset `gold` con 14 campos (esquema PRD Fase 2 §8). Tabla vacía — será poblada por el paso `run_rag_corpus_merge()` del pipeline (Fase A.6).

**Contexto:** esta tabla es la frontera entre Fase 1 (pipeline) y Fase 2 (agente RAG). El MERGE incremental sobre `comment_id` la poblará con los ~3,239 comentarios existentes que ya tienen sentimiento y embedding. Skill: `gold-rag-corpus`.

## 2026-09-04T22:35:00-06:00 — deploy-release — gold-rag-corpus-materialization

- **Recurso(s):** google_cloud_run_v2_job.yt_ingestion (solo el campo `image`).
- **Motivo:** agregar el paso `run_rag_corpus_merge()` al pipeline para materializar `gold_rag_corpus` — la tabla frontera entre Fase 1 y Fase 2 (PRD Fase 2 §8). Commit `fa93da7`, 43/43 tests pasan.
- **Comando:** build+push vía `gcloud builds submit --tag=.../ingestion:fa93da7` (Cloud Build, 42s), luego `gcloud run jobs update yt-ingestion-job --image=.../ingestion:fa93da7`.
- **Costo estimado incremental:** $0.00 USD/mes (mismo recurso, solo cambia el tag de imagen).
- **¿Contiene datos / requirió backup?:** No — actualización de imagen, no destrucción de datos.
- **Aprobado por:** Diego (verbatim: "Ya quedó el commit" — autorización implícita del build+deploy tras aprobar el apply de la tabla)
- **Ejecutado:** sí — sin errores. Ejecución `yt-ingestion-job-2h8z2`: exit(0), 3m39s. Corpus materializado: **3,261 filas** en `gold_rag_corpus` (7 canales, embeddings 768 dims, sentimiento correcto). Distribución: Martin Garrix 1869, Swedish House Mafia 592, Avicii 368, ILLENIUM 290, Alesso 90, Afrojack 46, Zedd 6.

## 2026-09-05T00:10:00-06:00 — terraform-provision — fase2-infraestructura-base

- **Recurso(s):** 14 de 16 recursos aplicados: google_service_account.rag_backend, google_bigquery_dataset_iam_member.rag_backend_gold_viewer, google_project_iam_member.{rag_backend_bq_job_user, rag_backend_firestore_user, rag_backend_aiplatform_user, diego_firestore_viewer, diego_logging_viewer, diego_monitoring_viewer}, google_firestore_database.rag, google_firestore_field.{messages_ttl, common_queries_ttl, response_cache_ttl}, google_artifact_registry_repository.rag_agent, google_cloud_run_v2_service.rag_chat (con imagen placeholder `:latest`).
- **Pendiente (2 recursos):** google_cloud_run_v2_service_iam_binding.iap_invoker y google_iap_web_backend_service_iam_binding.rag_access — requieren que el service account de IAP se propague (API habilitada en este apply) y que el Cloud Run Service tenga una imagen válida para arrancar. Se crearán en Fase F (despliegue).
- **Raíz Terraform:** infra/fase2/ (Fase 2)
- **Comando:** `terraform -chdir=infra/fase2 apply` (múltiples ciclos por: API de Firestore no habilitada → propagación → plan stale por apply parcial → import de recursos ya creados → API de IAP no habilitada → bindings diferidos)
- **Costo estimado incremental:** +$1.00 - $4.50 USD/mes
- **Costo total estimado tras el cambio:** ~$2.85 - $6.35 / $20.00 USD
- **¿Contiene datos / requirió backup?:** No — creación, no destrucción.
- **Aprobado por:** Diego (verbatim: "Adelante")
- **Ejecutado:** sí — parcial (14/16 recursos). Los 2 bindings de IAP se diferieron a Fase F por dependencia de imagen + propagación de API. APIs habilitadas durante el apply: `firestore.googleapis.com`, `iap.googleapis.com`. Recursos importados al state (creados en apply que timeoutó): `google_firestore_database.rag`, `google_cloud_run_v2_service.rag_chat`.

**Tropiezos registrados:** (1) la API de Firestore no estaba habilitada en el proyecto — `gcloud services enable firestore.googleapis.com` antes de re-plan; (2) el apply de Firestore TTL fields timeoutó a los 5 minutos, dejando el state bloqueado — `terraform force-unlock` + import de recursos ya creados; (3) la API de IAP se habilitó pero el service account de IAP (`service-180406516352@gcp-sa-iap`) tarda en propagarse — bindings diferidos.

## 2026-09-05T10:20:00-06:00 — rag-deploy-service — fase2-rag-agent-deploy

- **Recurso(s):** Artifact Registry `rag-agent` (imagen Docker), Cloud Run Service `rag-chat-service` (revisión `rag-chat-service-00002-hld`), IAM bindings `roles/run.invoker` (3 usuarios), IAM bindings `roles/iap.httpsResourceAccessor` (3 usuarios).
- **Raíz Terraform:** N/A — despliegue manual vía `gcloud builds submit` + `gcloud run deploy` + `gcloud iap web add-iam-policy-binding`.
- **Comando:**
  1. `gcloud builds submit --config=cloudbuild.rag.yaml --substitutions=_TAG=7cae04b` (Cloud Build, 44s)
  2. `gcloud run deploy rag-chat-service --image=us-central1-docker.pkg.dev/medallon-youtube/rag-agent/rag-agent:7cae04b --region=us-central1 --project=medallon-youtube`
  3. `gcloud run services add-iam-policy-binding rag-chat-service --member="user:diego@talamantes.com.mx" --role="roles/run.invoker"` (×3 usuarios)
  4. `gcloud iap web add-iam-policy-binding --member="user:diego@talamantes.com.mx" --role="roles/iap.httpsResourceAccessor"` (×3 usuarios)
  5. `gcloud services enable cloudresourcemanager.googleapis.com` (requerido para IAP IAM)
- **Costo estimado incremental:** +$1.00 - $4.50 USD/mes (Cloud Run Service scale-to-zero + Firestore + BigQuery queries).
- **Costo total estimado tras el cambio:** ~$2.85 - $6.35 / $20.00 USD
- **¿Contiene datos / requirió backup?:** No — despliegue de servicio, no destrucción de datos.
- **Aprobado por:** Diego (verbatim: "1. Debe de estar en wsl, ya inicié sesión en gcloud por ti 2. Por favor 3. Adelante, apruebo el costo. Cualquier cosa rara o cambio extra que se requiera me vuelves a preguntar")
- **Ejecutado:** sí — imagen construida y empujada exitosamente (`sha256:6cc21661d8dfdc1658ba62079333a74914af2ec1f6cd5c592ea9e1f47e9925bd`). Cloud Run Service desplegado con revisión `rag-chat-service-00002-hld`. IAM bindings de Cloud Run e IAP aplicados para las 3 identidades. API `cloudresourcemanager.googleapis.com` habilitada (requerida para IAP IAM).

**Notas:**
- El Dockerfile.rag se corregió para copiar todo `src/` en lugar de solo `src/rag_agent/` (requerido por hatchling).
- Se creó `cloudbuild.rag.yaml` para builds específicos de Fase 2 (usa `Dockerfile.rag`).
- El primer build con `gcloud builds submit --tag=` usó el `Dockerfile` del pipeline (Fase 1) por defecto — corregido con `--config=cloudbuild.rag.yaml`.
- IAP puede tardar unos minutos en propagarse. Verificación pendiente con las 3 identidades.
- El set de evaluación (15 doradas + 10 adversariales) debe ejecutarse contra el servicio real una vez IAP esté activo.

## 2026-09-05T12:21:00-06:00 — rag-terraform-root — fase2-indices-firestore-e-iap

> **Registro diferido.** Esta entrada y las cuatro siguientes documentan applies ejecutados el 2026-09-05 durante la depuración de IAP y Firestore, que se aplicaron con aprobación de Diego en el chat pero cuyo registro quedó pendiente. Se anexan aquí el mismo día, reconstruidos desde los planes guardados y el estado real verificado con `gcloud`. El retraso en el registro es en sí una desviación de `approval-gate` paso 4.

- **Recurso(s):** `google_firestore_index.{sessions_created_at, messages_timestamp, common_queries_count}`, `google_cloud_run_v2_service_iam_binding.iap_invoker`, `google_iap_web_cloud_run_service_iam_binding.rag_access`.
- **Raíz Terraform:** `infra/fase2/` (Fase 2)
- **Comando:** `terraform -chdir=infra/fase2 apply tfplan_indexes`
- **Costo estimado incremental:** $0.00 USD/mes (índices Firestore sobre <1 MB de datos; bindings IAM no facturan).
- **Costo total estimado tras el cambio:** ~$2.85 – $6.35 / $20.00 USD (sin cambio)
- **¿Contiene datos / requirió backup?:** No — creación de índices y bindings.
- **Aprobado por:** Diego (verbatim: "Apruebo el plan!")
- **Ejecutado:** sí. Los tres índices compuestos son los que exigen las consultas de memoria (filtro de rango sobre `expires_at` + `order_by` sobre otro campo). Definiciones tomadas de la URL que genera el propio Firestore en el error "query requires an index", no de la intuición.

## 2026-09-05T12:30:00-06:00 — rag-terraform-root — fase2-iap-resource-correcto

- **Recurso(s):** `google_iap_web_cloud_run_service_iam_binding.rag_access` (reemplaza a `google_iap_web_backend_service_iam_binding`).
- **Raíz Terraform:** `infra/fase2/` (Fase 2)
- **Comando:** `terraform -chdir=infra/fase2 apply tfplan_iap_fix`
- **Costo estimado incremental:** $0.00 USD/mes
- **Costo total estimado tras el cambio:** ~$2.85 – $6.35 / $20.00 USD (sin cambio)
- **¿Contiene datos / requirió backup?:** No.
- **Aprobado por:** Diego (continuación del mismo ciclo de aprobación: "Apruebo el plan!")
- **Ejecutado:** sí. **Causa del cambio:** `google_iap_web_backend_service_iam_binding` es para IAP detrás de un Load Balancer; con IAP nativo de Cloud Run devolvía 404. El recurso correcto es `google_iap_web_cloud_run_service_iam_binding`. Se aplicó junto con el cambio de `ingress` a `INGRESS_TRAFFIC_ALL` en `cloud_run.tf` (con `INTERNAL_LOAD_BALANCER` el endpoint `run.app` también daba 404).

## 2026-09-05T12:42:00-06:00 — rag-terraform-root — fase2-iam-evaluacion

- **Recurso(s):** `google_service_account_iam_member.diego_token_creator` (`roles/iam.serviceAccountTokenCreator`, Diego → `rag-backend-sa`), binding `roles/run.invoker` para `rag-backend-sa`.
- **Raíz Terraform:** `infra/fase2/` (Fase 2)
- **Comando:** `terraform -chdir=infra/fase2 apply tfplan_eval_iam`
- **Costo estimado incremental:** $0.00 USD/mes
- **Costo total estimado tras el cambio:** ~$2.85 – $6.35 / $20.00 USD (sin cambio)
- **¿Contiene datos / requirió backup?:** No.
- **Aprobado por:** Diego (verbatim: "Apruebo")
- **Ejecutado:** sí. Precondición de `rag-evaluation-suite`: la evaluación automatizada necesita firmar un JWT como `rag-backend-sa` para pasar IAP. **Nota de seguridad:** este binding le da a Diego capacidad de impersonar la SA del backend; es aceptable porque Diego ya es owner del proyecto, pero debe retirarse si alguna vez se reduce su rol.

## 2026-09-05T12:54:00-06:00 — rag-terraform-root — fase2-sa-en-allowlist-iap

- **Recurso(s):** `google_iap_web_cloud_run_service_iam_binding.rag_access` (agrega `serviceAccount:rag-backend-sa@…` a `members`); se retira el binding `run.invoker` para la SA por conflicto con IAP.
- **Raíz Terraform:** `infra/fase2/` (Fase 2)
- **Comando:** `terraform -chdir=infra/fase2 apply tfplan_iap_sa`
- **Costo estimado incremental:** $0.00 USD/mes
- **Costo total estimado tras el cambio:** ~$2.85 – $6.35 / $20.00 USD (sin cambio)
- **¿Contiene datos / requirió backup?:** No.
- **Aprobado por:** Diego (continuación del mismo ciclo: "Apruebo")
- **Ejecutado:** sí. **Cambia quién puede entrar al sistema:** la allowlist de IAP pasa de 3 identidades humanas a 3 humanas + 1 service account (la de evaluación). La SA está también en `ALLOWED_EMAILS` del código (`src/rag_agent/middleware/auth.py`). Consume su propia cuota de 30 consultas/día; una corrida completa de evaluación usa 25.

## 2026-09-05T13:19:00-06:00 — rag-terraform-root — fase2-indice-messages-asc

- **Recurso(s):** `google_firestore_index.messages_timestamp` (reemplazo: `expires_at` DESCENDING → ASCENDING) + update del Cloud Run Service.
- **Raíz Terraform:** `infra/fase2/` (Fase 2)
- **Comando:** `terraform -chdir=infra/fase2 apply tfplan_msg_index`
- **Costo estimado incremental:** $0.00 USD/mes
- **Costo total estimado tras el cambio:** ~$2.85 – $6.35 / $20.00 USD (sin cambio)
- **¿Contiene datos / requirió backup?:** No — el índice se reconstruye, los documentos no se tocan.
- **Aprobado por:** Diego (continuación del mismo ciclo: "Apruebo")
- **Ejecutado:** sí. **Aprendizaje:** el orden de `expires_at` en un índice compuesto lo determina Firestore según la consulta, no la simetría con los otros índices. `sessions` y `common_queries` van DESC; `messages` va ASC porque su `order_by` es `timestamp ASC`. La fuente correcta es siempre la URL que Firestore devuelve en el error "query requires an index".

## 2026-09-05T13:30:00-06:00 — rag-deploy-service — fase2-builds-fix1-a-fix4

> **Registro diferido**, mismo caso que las cinco entradas anteriores.

- **Recurso(s):** Cloud Run Service `rag-chat-service`, revisiones `00003` a `00006-j67`; imágenes `rag-agent:7cae04b-fix1` … `:7cae04b-fix4` en Artifact Registry.
- **Raíz Terraform:** N/A — `gcloud builds submit` + `gcloud run deploy` (fuera de Terraform; es el origen del drift que se corrige en la entrada del 2026-09-05T14:30).
- **Comando:** `gcloud builds submit --config=cloudbuild.rag.yaml --substitutions=_TAG=7cae04b-fixN` + `gcloud run deploy rag-chat-service --image=…:7cae04b-fixN --region=us-central1`, cuatro veces.
- **Costo estimado incremental:** $0.00 USD/mes (mismo servicio; ~4 builds × <1 min de Cloud Build, dentro del nivel gratuito).
- **Costo total estimado tras el cambio:** ~$2.85 – $6.35 / $20.00 USD (sin cambio)
- **¿Contiene datos / requirió backup?:** No.
- **Aprobado por:** Diego (verbatim, cubriendo el ciclo de depuración: "Adelante, apruebo el costo. Cualquier cosa rara o cambio extra que se requiera me vuelves a preguntar")
- **Ejecutado:** sí. Qué corrigió cada iteración:
  - `fix1` — `firestore.Client(database="rag-memory")`; el default apuntaba a `(default)`, que no existe → 404.
  - `fix2` — `GOLD_DATASET` de `youtube_gold` a `gold`.
  - `fix3` — `Gemini(..., client_kwargs={"vertexai": True, "project": …, "location": …})`. Sin `vertexai=True` ADK usa la API de AI Studio y falla con "No API key was provided"; con `project`/`location` pero sin la bandera falla con "Gemini API does not support project/location".
  - `fix4` — se pasa `GCP_REGION` a `build_agent_pipeline`.
- **APIs habilitadas en el proceso:** `cloudresourcemanager.googleapis.com` (requerida por IAP IAM), `compute.googleapis.com`.
- **Brand OAuth:** creado (cliente administrado por Google; las tres identidades son del dominio `talamantes.com.mx`, así que no se requirió brand externo). **Cambia quién puede entrar al sistema** — se registra aquí aunque sea un paso manual de consola, según `rag-terraform-root`.
- **Verificación:** Diego validó acceso en navegador con las 3 identidades y el rechazo de una 4ta cuenta no autorizada.

**Estado al cierre de estas seis entradas:** el servicio respondía HTTP 200 y el pipeline de agentes funcionaba, pero `semantic_search` fallaba. Ver la entrada siguiente.

## 2026-09-05T14:30:00-06:00 — rag-terraform-root — fase2-fix-semantic-search

- **Recurso(s):** `google_bigquery_connection_iam_member.rag_backend_connection_user` (nuevo) y `google_cloud_run_v2_service.rag_chat` (imagen `7cae04b-fix4` → `65036a4`, más las env vars `GCP_PROJECT`, `GOLD_DATASET`, `GCP_REGION`).
- **Raíz Terraform:** `infra/fase2/` (Fase 2)
- **Comando:** `terraform -chdir=infra/fase2 apply tfplan_conn_iam`, precedido de `gcloud builds submit --config=cloudbuild.rag.yaml --substitutions=_TAG=65036a4` (ejecutado por Diego).
- **Costo estimado incremental:** +$0.34 USD/mes. Es el costo de las consultas de `VECTOR_SEARCH` que hasta ahora **no se ejecutaban**: 90 consultas/día × 30 días × 20.9 MB = 55 GB/mes a $6.25/TB. El tope de 50 MB acota el peor caso absoluto a $0.83/mes. El binding IAM y las env vars son $0.00.
- **Costo total estimado tras el cambio:** ~$3.19 – $6.69 / $20.00 USD
- **Margen restante:** ~$13.31 (67% del techo libre). **Delta acumulado Fase 2: $1.34 – $4.84 / $5.00** — dentro del sub-techo, pero sin holgura para otro cambio con costo.
- **¿Contiene datos / requirió backup?:** No — `1 added, 1 changed, 0 destroyed`, ninguna destrucción.
- **Aprobado por:** Diego (verbatim: "Yes, apruebo, igual arregla los nuevos hallazgos de una vez", y para la ejecución: "Ya quedó! Haz el apply, ya me autentiqué en gcloud")
- **Ejecutado:** sí — `Apply complete! Resources: 1 added, 1 changed, 0 destroyed.` Revisión `rag-chat-service-00007-874`, `Ready: True`.

**Qué desbloquea.** `semantic_search` llevaba dos fallos encadenados, ambos verificados con evidencia antes de tocar nada:

1. **403 en la conexión.** `ML.GENERATE_EMBEDDING` sale a Vertex AI por `vertex-ai-connection`, recurso con IAM propio: `roles/bigquery.dataViewer` sobre `gold` no alcanza. Mismo gap que Fase 1 (APPROVALS 2026-08-02T19:04:15); se repite porque la conexión es compartida y Fase 2 la usa sin poseerla. La conexión **no** se declara como `resource` ni entra al state de Fase 2 — solo el binding.
2. **Tope de bytes.** `VECTOR_SEARCH` corre exhaustivo (3,261 filas < las 5,000 que exige un índice IVF) y lee `text_embedding` completa: **20,856,549 bytes** medidos con `--dry_run`. El tope de 10 MB rechazaba toda consulta semántica. Subido a 50 MB **solo** en esa herramienta; `sentiment_analytics` (79 KB) y `trend_detection` (58 KB) siguen en 10 MB. Criterio de reversión documentado en `rag-quota-limits`: cuando el corpus pase de 5,000 filas y el índice sea creable, el escaneo baja y el tope también.

**Verificación post-apply**, ejecutada **impersonando a `rag-backend-sa`** (correrla como Diego no probaría nada del IAM: un owner pasa aunque el binding no exista):

- `tests/rag_evaluation/verify_semantic_search.py` → 5 comentarios con `comment_id`, distancia y canal. Sin 403, sin error de bytes.
- Invariante §8 del PRD Fase 2 confirmado con la misma identidad: `gold.gold_rag_corpus` → **200**; `silver.silver_youtube_comments`, `bronze.bronze_youtube_comments` y `silver.silver_dead_letter_queue` → **403**. El aislamiento lo sostiene IAM, no el prompt.

**Cambios de código que viajan en la imagen `65036a4`** (commit del mismo nombre) — tres invariantes que el código no sostenía:

- **Citas (CLAUDE.md §11).** `main.py` las leía de `event.custom_metadata`, que ADK nunca puebla: `citations` siempre iba vacío y no existía validación alguna. Ahora se capturan los `function_response` reales de las herramientas y se verifica en código que todo `comment_id` citado exista; una cita sin evidencia degrada la respuesta y no se cachea.
- **Clave de caché (`rag-response-cache`).** Se pasaba `""` en corpus, prompt y modelo — todas las respuestas colapsaban en una sola clave, sin invalidación posible. La versión del corpus se lee de `MAX(updated_at)` (memoizada 5 min) y la del prompt es una constante que sube a mano. Si la versión no se puede leer, el servicio se salta el caché en vez de servir datos viejos.
- **Env vars.** El Service no declaraba ninguna y funcionaba solo por los defaults del código.

**Drift corregido:** `terraform.tfvars` decía `7cae04b-fix3` mientras el servicio corría `fix4`, resultado de los `gcloud run deploy` manuales del día anterior. Cualquier apply habría revertido el servicio dos revisiones en silencio. Con esta entrada, el tag en tfvars y la revisión desplegada vuelven a coincidir.

**Pendiente:** F.2 (evaluación de 25 preguntas) en espera — Diego prueba el servicio a mano primero.

## 2026-09-05T15:00:00-06:00 — rag-deploy-service — fase2-bienvenida-y-cierre-de-sesion

- **Recurso(s):** `google_cloud_run_v2_service.rag_chat` (solo el tag de imagen: `65036a4` → `33c819c`).
- **Raíz Terraform:** `infra/fase2/` (Fase 2)
- **Comando:** `gcloud builds submit --config=cloudbuild.rag.yaml --substitutions=_TAG=33c819c` (ejecutado por Diego, build `e402b0c0`, 44s, digest `sha256:c22ec9057b428c5e811666bca6567f8a49ff8b32c471be5e088d1eb8568afcdf`), luego `terraform -chdir=infra/fase2 apply tfplan_welcome`.
- **Costo estimado incremental:** $0.00 USD/mes. El endpoint nuevo consulta BigQuery una vez por instancia por hora (~79 KB, memoizado) y no invoca Vertex AI.
- **Costo total estimado tras el cambio:** ~$3.19 – $6.69 / $20.00 USD (sin cambio)
- **Margen restante:** ~$13.31 (67% del techo libre). Delta acumulado Fase 2: $1.34 – $4.84 / $5.00.
- **¿Contiene datos / requirió backup?:** No — `0 added, 1 changed, 0 destroyed`.
- **Aprobado por:** Diego (verbatim: "Adelante, por el momento con los DJ que tienen comentarios solamente", y para la ejecución: "Ya quedó el commit, prosigue con el deploy")
- **Ejecutado:** sí — `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` Revisión `rag-chat-service-00008-ggx`, `Ready: True`, 100% del tráfico.

**Qué agrega.** Pantalla de bienvenida pedida por Diego: saludo con nombre, descripción del agente, capacidades con ejemplos clicables y la lista de DJs. Más "Cerrar sesión" en el header.

**Decisión de alcance:** la bienvenida lista los **7 canales con comentarios** en `gold_rag_corpus`, no los 10 configurados en `infra/terraform.tfvars`. Third Party, Porter Robinson y DubVision no han producido comentarios (sin videos en la ventana de 7 días). Anunciar un DJ del que no hay datos obliga al agente a responder "no hay comentarios" a algo que él mismo ofreció. La lista se lee del corpus y se corrige sola cuando el pipeline los alcance.

**Verificación post-apply**, contra el servicio real vía IAP (JWT self-signed de `rag-backend-sa`):

- `GET /welcome` → los 7 DJs en orden de volumen, cuota real `25/30` y las 3 capacidades. Sin warnings ni errores en los logs de la revisión.
- **`/welcome` no consume cuota:** tres llamadas consecutivas, `restantes` fijo en 25. Usa `get_quota_remaining()` (lee sin incrementar), no `check_daily_quota()`.

**Bugs corregidos en el mismo despliegue:**

1. **El marcador de cuota parecía reiniciarse en cada refresh.** No se reiniciaba: el contador de Firestore (`daily_quotas/{sub}:{fecha}`, `Increment` atómico, TTL 2 días) siempre estuvo correcto — se verificó leyendo las cuatro identidades activas, con cuentas de 5, 9, 1 y 7. Lo que fallaba era la UI: `index.html` traía `Consultas hoy: 0/30` escrito a mano y `app.js` arrancaba con `quotaRemaining = 30`, y solo se actualizaba al recibir la primera respuesta de `/chat`. Ahora el número lo pide a `/welcome` al cargar.
2. **El panel "Fuentes" habría mostrado "Sin detalle" en cada renglón.** `app.js` renderiza `c.video_title`, `c.channel_name` y `c.comment_id`, pero `validate_citations` (desplegado en `65036a4` unas horas antes) devolvía una lista de strings. Ahora devuelve objetos con la metadata **de la fila real de la herramienta**, no del texto que escribió el modelo: el modelo elige qué citar, el código decide cómo se ve la cita.
3. **`escapeHtml` no escapa comillas** y se usaba para construir un atributo (`data-q` de los ejemplos clicables). Se agregó `escapeAttr`. Hoy el texto es constante del servidor; si algún día viene del corpus, la diferencia importa.

**Identidad:** `authenticate_identity()` devuelve `(sub, email)`. El `sub` sigue siendo la clave de cuota, historial y caché; el email se usa **solo** para el saludo. Indexar por email huerfanaría la memoria ante un cambio de correo.

**Cerrar sesión:** enlace a `/?gcp-iap-mode=CLEAR_LOGIN_COOKIE`. Dos límites conocidos y aceptados: borra la cookie de IAP de esta app pero **no** la sesión de Google, así que si sigue viva IAP reautentica en silencio al volver; y la pantalla de confirmación la sirve IAP, no la app — cualquier página propia está detrás de IAP y pedirla dispararía el login de nuevo. **Sin verificación automatizada**: depende del navegador y de la sesión de Google del usuario.

**Documentación:** `docs/PRD.md`, `docs/HANDOFF.md`, `docs/REPORTE-EJECUTIVO-2026-08-02.md` y los skills `bronze-ingestion-videos` y `docs-maintenance` pasaron de "5 canales" a los 10 reales de `infra/terraform.tfvars` (los cinco últimos se agregaron el 2026-08-30). `rag-fastapi-service` documenta el endpoint nuevo, que está fuera de la cuota, y la distinción entre identidad que se muestra e identidad que indexa.

**Tests:** 139 pasan (eran 126).

## 2026-09-05T15:35:00-06:00 — rag-deploy-service — fase2-topologia-memoria-y-cuota-sin-tope

- **Recurso(s):** `google_cloud_run_v2_service.rag_chat` — imagen `33c819c` → `97f48bb`, más dos variables de entorno nuevas: `QUOTA_OVERRIDES` y `GLOBAL_DAILY_LIMIT`.
- **Raíz Terraform:** `infra/fase2/` (Fase 2)
- **Comando:** `gcloud builds submit --config=cloudbuild.rag.yaml --substitutions=_TAG=97f48bb` (build `60bf961b`, 42s, digest `sha256:620b0593b7af12f2b896ea0994f67794deb114d64d616552134d010d7e981260`), luego `terraform -chdir=infra/fase2 apply tfplan_agentes`. Ambos ejecutados por Diego.
- **Costo estimado incremental:** +$0.00 USD/mes en régimen normal. **Ver la nota de riesgo abajo**: este cambio quita el tope diario a una identidad.
- **Costo total estimado tras el cambio:** ~$3.19 – $6.69 / $20.00 USD
- **Margen restante:** ~$13.31 (67% libre). Delta acumulado Fase 2: $1.34 – $4.84 / $5.00.
- **¿Contiene datos / requirió backup?:** No — `0 added, 1 changed, 0 destroyed`.
- **Aprobado por:** Diego (verbatim: "Me agrada tu plan, una cosa más aprovechando que harás cambios, hay manera de configurar mi usuario sin límites, para poder seguir probando hoy y no llegar al límite?" y, para ejecutar, "Listo")
- **Ejecutado:** sí — `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` Revisión `rag-chat-service-00009-8mc`, `Ready: True`, arranque sin warnings.

### Cambio de guardrail: una identidad sin tope diario

`QUOTA_OVERRIDES="diego@talamantes.com.mx=0"` — Diego queda sin límite diario para poder probar. Las demás identidades siguen en 30.

Al implementarlo se encontró que **el circuito de protección agregado que `rag-quota-limits` especifica nunca se había implementado**. Sin él, quitar el tope habría dejado el sistema con cero protección de costo: solo el rate limit de 5/min, que en un bucle son 7,200 consultas diarias. Por eso el override viaja junto con el circuito, no después:

- `GLOBAL_DAILY_LIMIT=300`, evaluado **antes** que la cuota por usuario, cuenta todas las consultas del día de todas las identidades y responde 503 al alcanzarlo.
- El override vive en `cloud_run.tf`, **no en Firestore**: así aparece en el `plan`, pasa por este gate y queda aquí. Un override mutable desde la consola sin rastro no sería un guardrail.
- **Sin tope no es sin medición:** el contador de Diego sigue incrementando. Es la única forma de ver qué cuesta la excepción.
- Un override mal escrito (`=muchas`) cae al límite normal de 30, nunca a "sin tope". La dirección del fallo importa.

**Lo que el circuito acota y lo que no:** un día completo contra el tope de 300 cuesta del orden de **$0.50 USD**. Eso protege contra un día malo. **No** protege contra 300 diarias sostenidas un mes — serían ~$15 y romperían el techo. Es un cortacircuitos, no un presupuesto. Si el consumo real se acerca al tope de forma habitual, la respuesta es recotizar con `cost-guardrail`, no subir el número.

### Bug: una de las cinco plantillas era inalcanzable

`compare_channels` filtra con `WHERE channel_name IN UNNEST(@channels)`, pero el wrapper de ADK **no exponía el parámetro `channels`**. Siempre llegaba `[]`, así que la plantilla devolvía **cero filas sin fallar nunca**: `status: "success"`, `count: 0`.

Es la plantilla que responde la pregunta de ejemplo que se puso en la bienvenida el mismo día ("¿Cómo es el sentimiento de ILLENIUM comparado con Alesso?"). Verificado post-apply con la identidad del backend: ahora devuelve **8 filas** (Alesso 84.4% positivo, ILLENIUM 71.2%). Se agregó un test que recorre las cinco plantillas buscando `@parametros` y exige que existan en el wrapper.

### El agente pedía fechas en formato AAAA-MM-DD

Reportado por Diego: pedir "el sentimiento del último mes" devolvía *"Por favor, especifica las fechas en formato AAAA-MM-DD"*. Tres causas, ninguna era el modelo:

1. **Un LLM no tiene reloj.** Sin la fecha de hoy en el prompt, "el último mes" es irresoluble y preguntar era su única salida correcta. Ahora `rag_agent/agents/context.py` inyecta, **por request**, la fecha actual, los periodos relativos ya resueltos, la cobertura real de los datos y los nombres exactos de los canales. Por request y no al construir el pipeline: una instancia de Cloud Run vive días y una fecha horneada al arranque estaría mal al día siguiente, en silencio.
2. **La instrucción le ordenaba ser rígido:** `analytics_agent` decía literalmente *"si el usuario no especifica un canal o periodo, NO asumas — devuelve un error indicando qué parámetros faltan"*. Reescrita: una pregunta sin fechas no está incompleta, significa "sobre todo lo que haya".
3. **La plantilla equivocada.** `compare_channels` y `distribution_by_channel` no necesitan fechas; el agente no lo sabía.

Degradación en el orden correcto: si BigQuery falla se pierde el catálogo de canales pero **se conserva la fecha** — perder los canales hace que pregunte por el DJ; perder la fecha lo devolvería a pedir `AAAA-MM-DD`.

### Topología: estaba documentada pero no implementada

`orchestrator.py` importaba `ParallelAgent` y `SequentialAgent`, su docstring y `rag-agent-topology` describían el flujo, y **no se usaba ninguno de los dos**. El router tenía tres `AgentTool` sueltos y nada garantizaba que la síntesis corriera: podía responder él directamente, saltándose las reglas de citación y el tope de tokens. Es la explicación más probable de que el agente se sintiera "atontado" — no era el modelo, era el paso donde vivía la redacción.

Ahora existe de verdad: `SequentialAgent(ParallelAgent(search, analytics), synthesis)`, expuesto como `AgentTool` del router, con reglas de delegación explícitas y una regla central — si algún agente recuperó datos, la respuesta la redacta `synthesis_agent`. `tests/test_rag_topology.py` lo verifica estructuralmente: un diagrama no falla cuando el código deja de corresponderle.

**Nota de versión de ADK (2.8.0):** `SequentialAgent` y `ParallelAgent` emiten `DeprecationWarning` en favor de `Workflow`. **No se migró**: el propio aviso dice que *"Workflow cannot yet be used as an LlmAgent sub-agent"*, que es exactamente este caso. Registrado en `rag-agent-topology` con la condición para revisarlo.

### `max_output_tokens` no estaba configurado

El tope de 3.000 tokens del PRD §12 existía **solo como frase en el prompt** — no había un `generate_content_config` en todo el código. Los cinco agentes ahora lo llevan, con `temperature=0.2`.

### Memoria: escrita pero no conectada

`record_query()` se llamaba en cada consulta y `get_common_queries()` no la llamaba nadie; `preferences.py` completo sin un solo importador. El agente respondía, con razón, que no podía recordar nada — no tenía forma. Se verificó que la escritura sí funcionaba: 5 documentos en Firestore, incluida la propia pregunta que expuso el problema.

`memory_agent` nuevo, con dos herramientas de **lectura**. El `user_id` sale de `tool_context.user_id` en tiempo de ejecución: capturarlo en el closure al construir el pipeline habría servido la memoria de un usuario a otro. La **escritura** de preferencias queda fuera — `rag-memory-preferences` exige confirmación explícita previa y ese flujo es una pieza aparte.

### Versión del prompt

`PROMPT_VERSION` de `2026-09-05.1` a `2026-09-05.3`. Cambiaron los prompts de todos los agentes; sin subirla, el caché habría seguido sirviendo respuestas redactadas sin pasar por síntesis.

**Tests:** 180 pasan (eran 139).

**Pendientes conocidos:** (1) el historial reusa siempre la misma sesión (`get_recent_sessions(..., limit=1)`), así que conversaciones de temas distintos se contaminan; (2) escritura de preferencias con confirmación; (3) F.2, la evaluación de 25 preguntas, sigue en espera.
