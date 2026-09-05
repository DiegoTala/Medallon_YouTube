variable "project_id" {
  type    = string
  default = "medallon-youtube"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "rag_service_name" {
  description = "Nombre del Cloud Run Service de Fase 2."
  type        = string
  default     = "rag-chat-service"
}

variable "rag_image_tag" {
  description = "Tag de la imagen Docker del agente RAG en Artifact Registry."
  type        = string
  default     = "latest"
}

variable "allowed_emails" {
  description = "Identidades autorizadas para IAP (PRD Fase 2 §2)."
  type        = set(string)
  default = [
    "diego@talamantes.com.mx",
    "medallon.rag.test01@talamantes.com.mx",
    "medallon.rag.test02@talamantes.com.mx",
  ]
}
