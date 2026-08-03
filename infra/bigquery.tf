# Datasets bronze/silver/gold (PRD §6). "bronze" queda vacío de tablas por diseño:
# la capa Bronze vive en GCS (ver bronze.tf... ver gcs.tf); este dataset se reserva
# para eventuales external tables sobre esos datos crudos, si algún día se necesitan.
resource "google_bigquery_dataset" "bronze" {
  dataset_id = "bronze"
  location   = var.region
}

resource "google_bigquery_dataset" "silver" {
  dataset_id = "silver"
  location   = var.region
}

resource "google_bigquery_dataset" "gold" {
  dataset_id = "gold"
  location   = var.region
}

# ── Staging (sin MERGE, se trunca tras cada corrida exitosa) ──────────────

resource "google_bigquery_table" "staging_youtube_videos" {
  dataset_id = google_bigquery_dataset.silver.dataset_id
  table_id   = "staging_youtube_videos"

  schema = jsonencode([
    { name = "video_id", type = "STRING", mode = "REQUIRED" },
    { name = "channel_name", type = "STRING", mode = "REQUIRED" },
    { name = "title", type = "STRING", mode = "REQUIRED" },
    { name = "description", type = "STRING", mode = "NULLABLE" },
    { name = "published_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "default_language", type = "STRING", mode = "NULLABLE" },
    { name = "duration", type = "STRING", mode = "REQUIRED" },
    { name = "view_count", type = "INTEGER", mode = "REQUIRED" },
    { name = "like_count", type = "INTEGER", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "staging_youtube_comments" {
  dataset_id = google_bigquery_dataset.silver.dataset_id
  table_id   = "staging_youtube_comments"

  schema = jsonencode([
    { name = "comment_id", type = "STRING", mode = "REQUIRED" },
    { name = "video_id", type = "STRING", mode = "REQUIRED" },
    { name = "author", type = "STRING", mode = "REQUIRED" },
    { name = "comment_text", type = "STRING", mode = "REQUIRED" },
    { name = "like_count", type = "INTEGER", mode = "REQUIRED" },
    { name = "published_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

# ── Silver (MERGE idempotente sobre clave natural) ─────────────────────────

resource "google_bigquery_table" "silver_youtube_videos" {
  dataset_id = google_bigquery_dataset.silver.dataset_id
  table_id   = "silver_youtube_videos"

  schema = jsonencode([
    { name = "video_id", type = "STRING", mode = "REQUIRED" },
    { name = "channel_name", type = "STRING", mode = "REQUIRED" },
    { name = "title", type = "STRING", mode = "REQUIRED" },
    { name = "description", type = "STRING", mode = "NULLABLE" },
    { name = "published_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "default_language", type = "STRING", mode = "NULLABLE" },
    { name = "duration", type = "STRING", mode = "REQUIRED" },
    { name = "view_count", type = "INTEGER", mode = "REQUIRED" },
    { name = "like_count", type = "INTEGER", mode = "REQUIRED" },
    { name = "ingested_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "updated_at", type = "TIMESTAMP", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "silver_youtube_comments" {
  dataset_id = google_bigquery_dataset.silver.dataset_id
  table_id   = "silver_youtube_comments"

  schema = jsonencode([
    { name = "comment_id", type = "STRING", mode = "REQUIRED" },
    { name = "video_id", type = "STRING", mode = "REQUIRED" },
    { name = "author", type = "STRING", mode = "REQUIRED" },
    { name = "comment_text", type = "STRING", mode = "REQUIRED" },
    { name = "like_count", type = "INTEGER", mode = "REQUIRED" },
    { name = "published_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "ingested_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "updated_at", type = "TIMESTAMP", mode = "NULLABLE" },
  ])
}

# ── Dead letter queue (append-only, particionada por fecha de error) ───────

resource "google_bigquery_table" "silver_dead_letter_queue" {
  dataset_id = google_bigquery_dataset.silver.dataset_id
  table_id   = "silver_dead_letter_queue"

  time_partitioning {
    type  = "DAY"
    field = "error_timestamp"
  }

  schema = jsonencode([
    { name = "error_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "comment_id", type = "STRING", mode = "NULLABLE" },
    { name = "video_id", type = "STRING", mode = "NULLABLE" },
    { name = "raw_payload", type = "JSON", mode = "REQUIRED" },
    { name = "validation_error", type = "STRING", mode = "REQUIRED" },
    { name = "error_field", type = "STRING", mode = "NULLABLE" },
    { name = "batch_execution_id", type = "STRING", mode = "REQUIRED" },
  ])
}

# ── Gold ─────────────────────────────────────────────────────────────────

resource "google_bigquery_table" "gold_sentiment_analysis" {
  dataset_id = google_bigquery_dataset.gold.dataset_id
  table_id   = "gold_sentiment_analysis"

  schema = jsonencode([
    { name = "comment_id", type = "STRING", mode = "REQUIRED" },
    { name = "comment_text", type = "STRING", mode = "REQUIRED" },
    { name = "sentiment_raw", type = "JSON", mode = "NULLABLE" },
    { name = "sentiment_label", type = "STRING", mode = "NULLABLE" },
    { name = "processed_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "gold_youtube_embeddings" {
  dataset_id = google_bigquery_dataset.gold.dataset_id
  table_id   = "gold_youtube_embeddings"

  schema = jsonencode([
    { name = "comment_id", type = "STRING", mode = "REQUIRED" },
    # 768 dimensiones fijas (text-embedding-004) — ver invariante en
    # .claude/skills/gold-embeddings-generation/SKILL.md.
    { name = "text_embedding", type = "FLOAT64", mode = "REPEATED" },
  ])
}

# ── Conexión BigQuery -> Vertex AI (co-ubicada en us-central1, PRD §3) ─────

resource "google_bigquery_connection" "vertex_ai" {
  connection_id = "vertex-ai-connection"
  location      = var.region

  cloud_resource {}
}

# Mínimo privilegio: la service account autogenerada de la conexión solo
# necesita invocar Vertex AI, nunca roles/editor ni roles/owner.
resource "google_project_iam_member" "bq_connection_vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_bigquery_connection.vertex_ai.cloud_resource[0].service_account_id}"
}

# Modelos remotos: se crean aquí (Terraform), nunca manualmente — ver
# .claude/skills/gold-sentiment-analysis y gold-embeddings-generation.
# job_id fijo: CREATE OR REPLACE es idempotente, así que reaplicar con el mismo
# job_id es un no-op una vez creado. Si cambia la definición del modelo, subir
# el sufijo de versión del job_id.
resource "google_bigquery_job" "create_gemini_flash_model" {
  job_id   = "create-gemini-flash-model-v3"
  location = var.region

  query {
    query              = <<-SQL
      CREATE OR REPLACE MODEL `${var.project_id}.gold.gemini_flash_model`
      REMOTE WITH CONNECTION `${var.project_id}.${var.region}.${google_bigquery_connection.vertex_ai.connection_id}`
      OPTIONS (ENDPOINT = 'gemini-2.5-flash');
    SQL
    use_legacy_sql     = false
    create_disposition = ""
    write_disposition  = ""
  }

  depends_on = [
    google_bigquery_dataset.gold,
    google_project_iam_member.bq_connection_vertex_ai_user,
  ]
}

resource "google_bigquery_job" "create_embedding_model" {
  job_id   = "create-embedding-model-v3"
  location = var.region

  query {
    query              = <<-SQL
      CREATE OR REPLACE MODEL `${var.project_id}.gold.embedding_model`
      REMOTE WITH CONNECTION `${var.project_id}.${var.region}.${google_bigquery_connection.vertex_ai.connection_id}`
      OPTIONS (ENDPOINT = 'text-embedding-004');
    SQL
    use_legacy_sql     = false
    create_disposition = ""
    write_disposition  = ""
  }

  depends_on = [
    google_bigquery_dataset.gold,
    google_project_iam_member.bq_connection_vertex_ai_user,
  ]
}
