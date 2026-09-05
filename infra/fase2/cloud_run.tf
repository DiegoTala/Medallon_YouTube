# Artifact Registry para la imagen del agente RAG (separado del pipeline de Fase 1).
resource "google_artifact_registry_repository" "rag_agent" {
  location      = var.region
  repository_id = "rag-agent"
  description   = "Imagen Docker del agente RAG conversacional (Fase 2)"
  format        = "DOCKER"
}

# Cloud Run Service con IAP habilitado, scale-to-zero y sin acceso público.
# Ver .claude/skills/rag-fastapi-service/SKILL.md y rag-deploy-service/SKILL.md.
resource "google_cloud_run_v2_service" "rag_chat" {
  name     = var.rag_service_name
  location = var.region

  # IAP nativo de Cloud Run, sin Load Balancer (PRD §11).
  # Ver rag-iap-auth/SKILL.md.
  # INGRESS_TRAFFIC_ALL es necesario: IAP nativo intercepta el endpoint
  # run.app directamente; INTERNAL_LOAD_BALANCER requiere un LB externo
  # (verificado en el despliegue del 2026-09-05 — con INTERNAL_LOAD_BALANCER
  # el servicio devolvía 404 al acceso directo).
  ingress = "INGRESS_TRAFFIC_ALL"

  iap_enabled = true

  template {
    service_account = google_service_account.rag_backend.email

    # Scale-to-zero: costo $0 cuando no hay tráfico (PRD §15).
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.rag_agent.repository_id}/rag-agent:${var.rag_image_tag}"

      ports {
        container_port = 8080
      }

      # Configuración explícita. El código tiene defaults que coinciden con
      # estos valores, pero un default no es una declaración: sin estas
      # variables, apuntar el servicio a otro dataset o región deja de ser un
      # cambio de infraestructura y pasa a ser un cambio de código, y un
      # dataset equivocado falla en silencio (devuelve vacío, no error).
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GOLD_DATASET"
        value = data.google_bigquery_dataset.gold.dataset_id
      }

      env {
        name  = "GCP_REGION"
        value = var.region
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }

    # Sin estado en memoria entre requests (rag-fastapi-service).
    max_instance_request_concurrency = 80
  }

  # Depende de que Firestore exista antes de que el servicio arranque.
  depends_on = [
    google_firestore_database.rag,
    google_project_iam_member.rag_backend_bq_job_user,
    google_project_iam_member.rag_backend_firestore_user,
    google_project_iam_member.rag_backend_aiplatform_user,
  ]
}

# IAP habilitado sobre el servicio.
resource "google_cloud_run_v2_service_iam_binding" "iap_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.rag_chat.name
  role     = "roles/run.invoker"
  members = [
    "serviceAccount:service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com",
  ]
}
