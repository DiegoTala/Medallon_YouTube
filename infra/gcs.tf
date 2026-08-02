# Bucket de Terraform state remoto. El nombre debe coincidir literalmente con
# el bucket declarado en el backend "gcs" de main.tf (los bloques backend no
# admiten interpolación de variables). Ver la nota de bootstrap en main.tf.
resource "google_storage_bucket" "tfstate" {
  name                        = "medallon-youtube-tfstate"
  location                    = var.region
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

# Bronze: almacenamiento inmutable de JSON Lines crudo, multirregional (PRD §3/§4.1).
resource "google_storage_bucket" "bronze" {
  name                        = "${var.project_id}-yt-bronze"
  location                    = "US"
  uniform_bucket_level_access = true

  lifecycle_rule {
    condition { age = 90 }
    action { type = "Delete" }
  }
}
