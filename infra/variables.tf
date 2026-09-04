variable "project_id" {
  type    = string
  default = "medallon-youtube"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "channel_ids" {
  description = <<-EOT
    IDs de canal (formato UC..., NO @handle) de los canales de DJs a ingerir.
    Nunca hardcodeados en el código Python — ver .claude/skills/bronze-ingestion-videos/SKILL.md.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.channel_ids) >= 1 && length(var.channel_ids) <= 20
    error_message = "channel_ids debe tener entre 1 y 20 elementos."
  }
}

variable "image_tag" {
  description = "Tag de la imagen Docker de ingesta en Artifact Registry, actualizado por deploy-release."
  type        = string
  default     = "latest"
}
