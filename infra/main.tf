terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.42"
    }
  }

  # Backend remoto declarado (PRD §6: state versionado para colaboración/auditoría).
  # Bootstrap con problema del huevo y la gallina: este bucket no puede existir antes
  # de que Terraform lo cree. Secuencia obligatoria antes de que este backend funcione:
  #   1. Comentar este bloque `backend "gcs"` temporalmente.
  #   2. `terraform init` (backend local) + aprobar y aplicar solo
  #      `google_storage_bucket.tfstate` (ver gcs.tf) vía approval-gate.
  #   3. Descomentar este bloque y correr `terraform init -migrate-state`.
  # Hasta completar ese bootstrap, NO ejecutar `terraform init` tal cual está —
  # fallará porque "medallon-youtube-tfstate" todavía no existe.
  backend "gcs" {
    bucket = "medallon-youtube-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
