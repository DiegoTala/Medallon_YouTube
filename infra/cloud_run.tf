resource "google_cloud_run_v2_job" "yt_ingestion" {
  name     = "yt-ingestion-job"
  location = var.region

  template {
    template {
      service_account = google_service_account.yt_ingestion_job.email

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.yt_pipeline.repository_id}/ingestion:${var.image_tag}"

        env {
          name  = "CHANNEL_IDS"
          value = join(",", var.channel_ids)
        }

        env {
          name = "YOUTUBE_API_KEY"
          value_source {
            secret_key_ref {
              secret  = data.google_secret_manager_secret.youtube_api_key.secret_id
              version = "latest"
            }
          }
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }

      max_retries = 3
      timeout     = "1800s" # 30m, coincide con --task-timeout del PRD §6
    }
  }
}
