resource "google_artifact_registry_repository" "yt_pipeline" {
  location      = var.region
  repository_id = "yt-pipeline"
  format        = "DOCKER"
  description   = "Imagen Docker del contenedor de ingesta (bronze + silver) — ver deploy-release."
}
