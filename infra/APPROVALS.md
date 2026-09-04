# Bitácora de Aprobaciones de Infraestructura

Registro append-only de toda aprobación de cambios de infraestructura real (GCP), conforme a la regla no negociable definida en [`.claude/skills/approval-gate/SKILL.md`](../.claude/skills/approval-gate/SKILL.md).

**Regla:** ninguna entrada se agrega retroactivamente para "justificar" un cambio ya ejecutado sin aprobación previa. Si eso ocurre, se documenta como incidente, no como aprobación.

**No editar ni borrar entradas existentes** — solo se anexan nuevas al final del archivo.

---

<!--
Plantilla de entrada. Copiar y completar por cada apply/destroy aprobado.
Para decomisiones (terraform-decommission), prefijar el título con [DESTROY].

## <timestamp ISO 8601> — <skill: terraform-provision | terraform-decommission | deploy-release> — <nombre corto del cambio>

- **Recurso(s):** <lista de recursos afectados>
- **Comando:** <comando exacto ejecutado>
- **Costo estimado incremental:** <+/-$X.XX USD/mes>
- **Costo total estimado tras el cambio:** <$Y.YY / $15.00 USD>
- **¿Contiene datos / requirió backup?:** <sí/no, detalle si aplica — obligatorio para DESTROY>
- **Aprobado por:** Diego (verbatim: "<texto exacto de la aprobación>")
- **Ejecutado:** <sí/no — resultado, errores si los hubo>
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
