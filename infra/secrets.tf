# Contenedor del secreto únicamente. El valor real de la API Key de YouTube
# NUNCA se declara aquí ni en terraform.tfvars (invariante: ningún secreto en
# texto plano en archivos versionados). Se agrega manualmente, fuera de
# Terraform, una sola vez:
#   gcloud secrets versions add youtube-api-key --data-file=-
# Ese comando lo ejecuta Diego directamente (no un agente), y no pasa por el
# approval-gate porque no mueve infraestructura ni tiene costo — es carga de
# un valor de configuración sensible.
resource "google_secret_manager_secret" "youtube_api_key" {
  secret_id = "youtube-api-key"

  replication {
    auto {}
  }
}
