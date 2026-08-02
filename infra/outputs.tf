output "bronze_bucket" {
  value = google_storage_bucket.bronze.name
}

output "artifact_registry_repository" {
  value = google_artifact_registry_repository.yt_pipeline.name
}

output "cloud_run_job_name" {
  value = google_cloud_run_v2_job.yt_ingestion.name
}

output "silver_dataset" {
  value = google_bigquery_dataset.silver.dataset_id
}

output "gold_dataset" {
  value = google_bigquery_dataset.gold.dataset_id
}
