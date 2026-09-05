output "rag_service_url" {
  description = "URL del Cloud Run Service de Fase 2."
  value       = google_cloud_run_v2_service.rag_chat.uri
}

output "rag_service_name" {
  description = "Nombre del Cloud Run Service."
  value       = google_cloud_run_v2_service.rag_chat.name
}

output "rag_backend_sa_email" {
  description = "Email de la service account del backend RAG."
  value       = google_service_account.rag_backend.email
}

output "rag_artifact_registry" {
  description = "Repositorio de Artifact Registry para la imagen del agente."
  value       = google_artifact_registry_repository.rag_agent.name
}

output "firestore_database" {
  description = "Nombre de la base de datos Firestore."
  value       = google_firestore_database.rag.name
}
