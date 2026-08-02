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
