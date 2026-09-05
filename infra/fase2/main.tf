terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.42"
    }
  }

  # Mismo bucket de state que Fase 1, prefijo aislado.
  # Un `terraform destroy` desde aquí es incapaz de tocar el pipeline de Fase 1.
  backend "gcs" {
    bucket = "medallon-youtube-tfstate"
    prefix = "terraform/fase2"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {
  project_id = var.project_id
}

# Referencia al dataset Gold de Fase 1 — data source, nunca resource.
# Si se declarara como resource, un destroy de Fase 2 borraría el dataset.
data "google_bigquery_dataset" "gold" {
  dataset_id = "gold"
  project    = var.project_id
}
