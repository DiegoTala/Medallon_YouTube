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

variable "vertex_connection_id" {
  description = <<-EOT
    Id de la conexión BigQuery → Vertex AI creada por Fase 1
    (infra/bigquery.tf, google_bigquery_connection.vertex_ai). Fase 2 solo
    concede un binding sobre ella; no la declara ni la posee.
  EOT
  type        = string
  default     = "vertex-ai-connection"
}

variable "quota_overrides" {
  description = <<-EOT
    Excepciones a la cuota diaria de 30 consultas, como "correo=limite"
    separadas por coma. Un límite de 0 significa SIN TOPE.
    Cambiarlo altera un guardrail de costo: cotizar con cost-guardrail y pasar
    por approval-gate, como cualquier otro cambio de infraestructura.
  EOT
  type        = string
  default     = ""
}

variable "global_daily_limit" {
  description = <<-EOT
    Tope agregado de consultas por día sumando a todos los usuarios — el
    circuito de protección de rag-quota-limits. Es la última defensa cuando
    alguna identidad no tiene tope propio.
  EOT
  type        = number
  default     = 300

  validation {
    condition     = var.global_daily_limit >= 30 && var.global_daily_limit <= 1000
    error_message = "global_daily_limit debe estar entre 30 y 1000."
  }
}
