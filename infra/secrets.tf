# La API Key de YouTube vive en el secreto "API-YouTube", creado manualmente
# por Diego fuera de Terraform (con su valor real ya cargado) — nunca se
# declara aquí como resource ni se referencia su valor en texto plano
# (invariante: ningún secreto en texto plano en archivos versionados).
# Este data source solo lo referencia para IAM/env var; Terraform nunca
# gestiona su ciclo de vida ni su contenido.
data "google_secret_manager_secret" "youtube_api_key" {
  secret_id = "API-YouTube"
}
