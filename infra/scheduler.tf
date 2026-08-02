# Disparador cron semanal, lunes 02:00 UTC (PRD §2).
resource "google_cloud_scheduler_job" "weekly_trigger" {
  name      = "yt-ingestion-weekly"
  region    = var.region
  schedule  = "0 2 * * 1"
  time_zone = "UTC"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.yt_ingestion.name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler_invoker.email
    }
  }

  retry_config {
    retry_count = 3
  }

  depends_on = [google_cloud_run_v2_job_iam_member.scheduler_can_invoke]
}
