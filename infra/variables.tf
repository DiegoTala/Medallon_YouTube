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
    IDs de canal (formato UC..., NO @handle) de los 5 canales de DJs a ingerir.
    Exactamente 5 (PRD §2), nunca hardcodeados en el código Python — ver
    .claude/skills/bronze-ingestion-videos/SKILL.md.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.channel_ids) == 5
    error_message = "channel_ids debe tener exactamente 5 elementos (PRD §2: 5 canales de DJs)."
  }
}

variable "image_tag" {
  description = "Tag de la imagen Docker de ingesta en Artifact Registry, actualizado por deploy-release."
  type        = string
  default     = "latest"
}
