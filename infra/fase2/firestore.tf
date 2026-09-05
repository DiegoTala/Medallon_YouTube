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
