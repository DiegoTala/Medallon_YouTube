# Service account de mínimo privilegio para el Cloud Run Job de ingesta.
# Nunca roles/editor ni roles/owner — solo lo que el job necesita tocar.
resource "google_service_account" "yt_ingestion_job" {
  account_id   = "yt-ingestion-job"
  display_name = "YouTube DJ Analytics - Ingestion Cloud Run Job"
}

resource "google_storage_bucket_iam_member" "yt_ingestion_job_bronze_writer" {
  bucket = google_storage_bucket.bronze.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.yt_ingestion_job.email}"
}

resource "google_bigquery_dataset_iam_member" "yt_ingestion_job_silver_editor" {
  dataset_id = google_bigquery_dataset.silver.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.yt_ingestion_job.email}"
}

# roles/bigquery.jobUser es un rol de proyecto (no existe a nivel dataset):
# necesario para que el job pueda lanzar load jobs y queries (MERGE/TRUNCATE).
resource "google_project_iam_member" "yt_ingestion_job_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.yt_ingestion_job.email}"
}

resource "google_secret_manager_secret_iam_member" "yt_ingestion_job_secret_accessor" {
  secret_id = google_secret_manager_secret.youtube_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.yt_ingestion_job.email}"
}

# Service account dedicada para que Cloud Scheduler invoque el Cloud Run Job —
# separada de la del propio job (principio de mínimo privilegio: solo necesita
# poder invocar, nada de acceso a GCS/BigQuery/Secret Manager).
resource "google_service_account" "scheduler_invoker" {
  account_id   = "yt-scheduler-invoker"
  display_name = "YouTube DJ Analytics - Cloud Scheduler Invoker"
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_can_invoke" {
  name     = google_cloud_run_v2_job.yt_ingestion.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_invoker.email}"
}

# Google dejó de auto-otorgar roles a la default Compute Engine SA en proyectos
# nuevos. deploy-release usa `gcloud builds submit` con esta SA (default de
# Cloud Build) para construir/publicar la imagen de ingesta — sin estos 2 roles
# ni siquiera puede leer el tarball de source que sube a GCS.
resource "google_project_iam_member" "cloudbuild_default_sa_storage_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_project_iam_member" "cloudbuild_default_sa_artifactregistry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}
