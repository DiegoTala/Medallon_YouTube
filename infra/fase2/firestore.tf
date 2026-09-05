# Firestore en modo nativo, co-ubicado en us-central1 (PRD §5, §14).
# Ver .claude/skills/rag-terraform-root/SKILL.md y rag-memory-session/SKILL.md.
resource "google_firestore_database" "rag" {
  project     = var.project_id
  name        = "rag-memory"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # Prevenir borrado accidental de la base de datos con datos de producción.
  deletion_policy = "DELETE"
}

# TTL para mensajes de sesión (7 días, PRD §9).
# La política marca el campo; la aplicación escribe expires_at.
# Sin expires_at escrito por la app, el TTL no borra nada.
# Ver rag-memory-session/SKILL.md.
resource "google_firestore_field" "messages_ttl" {
  project    = var.project_id
  database   = google_firestore_database.rag.name
  collection = "messages"
  field      = "expires_at"
  ttl_config {}
}

# TTL para consultas frecuentes (180 días, PRD §9).
# Ver rag-memory-common-queries/SKILL.md.
resource "google_firestore_field" "common_queries_ttl" {
  project    = var.project_id
  database   = google_firestore_database.rag.name
  collection = "common_queries"
  field      = "expires_at"
  ttl_config {}
}

# TTL para caché de respuestas (7 días).
# Ver rag-response-cache/SKILL.md.
resource "google_firestore_field" "response_cache_ttl" {
  project    = var.project_id
  database   = google_firestore_database.rag.name
  collection = "response_cache"
  field      = "expires_at"
  ttl_config {}
}

# Índices compuestos requeridos por las consultas de memoria.
# Firestore exige un índice compuesto cuando hay filtro de rango (expires_at > now)
# combinado con order_by sobre otro campo. Definición generada por el propio
# Firestore en el error "query requires an index" — replicada aquí.
# Ver rag-memory-session/SKILL.md y rag-memory-common-queries/SKILL.md.

# sessions: where(expires_at > now).order_by(created_at DESC)
resource "google_firestore_index" "sessions_created_at" {
  project     = var.project_id
  database    = google_firestore_database.rag.name
  collection  = "sessions"
  query_scope = "COLLECTION"
  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }
  fields {
    field_path = "expires_at"
    order      = "DESCENDING"
  }
}

# messages: where(expires_at > now).order_by(timestamp ASC)
# Definición generada por Firestore (timestamp ASC, expires_at ASC).
resource "google_firestore_index" "messages_timestamp" {
  project     = var.project_id
  database    = google_firestore_database.rag.name
  collection  = "messages"
  query_scope = "COLLECTION"
  fields {
    field_path = "timestamp"
    order      = "ASCENDING"
  }
  fields {
    field_path = "expires_at"
    order      = "ASCENDING"
  }
}

# common_queries: where(expires_at > now).order_by(count DESC)
resource "google_firestore_index" "common_queries_count" {
  project     = var.project_id
  database    = google_firestore_database.rag.name
  collection  = "common_queries"
  query_scope = "COLLECTION"
  fields {
    field_path = "count"
    order      = "DESCENDING"
  }
  fields {
    field_path = "expires_at"
    order      = "DESCENDING"
  }
}
