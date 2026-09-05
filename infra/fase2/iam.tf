# Service account de mínimo privilegio para el backend de Fase 2.
# Ver .claude/skills/rag-terraform-root/SKILL.md.
#
# Acceso a BigQuery: SOLO lectura sobre el dataset Gold (nunca a nivel de proyecto).
# Sin esto, la SA podría leer Bronze, Silver y la DLQ — el invariante §8 del PRD
# dependería de que ningún prompt falle, en vez de de un permiso ausente.
resource "google_service_account" "rag_backend" {
  account_id   = "rag-backend-sa"
  display_name = "YouTube DJ Analytics - RAG Backend Service"
}

# Lectura SOLO del dataset Gold — data source de Fase 1, nunca resource.
resource "google_bigquery_dataset_iam_member" "rag_backend_gold_viewer" {
  dataset_id = data.google_bigquery_dataset.gold.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.rag_backend.email}"
}

# Ejecutar consultas BigQuery (SELECT sobre Gold).
resource "google_project_iam_member" "rag_backend_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.rag_backend.email}"
}

# Firestore: lectura y escritura para memoria, caché y cuotas.
resource "google_project_iam_member" "rag_backend_firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.rag_backend.email}"
}

# Vertex AI: Gemini para síntesis + embeddings para búsqueda semántica.
resource "google_project_iam_member" "rag_backend_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.rag_backend.email}"
}

# Diego: solo lectura sobre Firestore, Logging y Monitoring para administrar
# desde Cloud Console (PRD Fase 2 §14). Sin acceso a BigQuery ni Vertex AI.
resource "google_project_iam_member" "diego_firestore_viewer" {
  project = var.project_id
  role    = "roles/datastore.viewer"
  member  = "user:diego@talamantes.com.mx"
}

resource "google_project_iam_member" "diego_logging_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "user:diego@talamantes.com.mx"
}

resource "google_project_iam_member" "diego_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "user:diego@talamantes.com.mx"
}
