# IAP: acceso a las tres identidades del PRD §2.
# Ver .claude/skills/rag-iap-auth/SKILL.md.
#
# El brand OAuth no se declara aquí — con identidades del dominio (talamantes.com.mx),
# el cliente OAuth administrado por Google basta. No se requiere brand externo.
# Verificación del JWT en el backend: rag-iap-auth/SKILL.md (código Python).

resource "google_iap_web_cloud_run_service_iam_binding" "rag_access" {
  project                = var.project_id
  location               = var.region
  cloud_run_service_name = google_cloud_run_v2_service.rag_chat.name
  role                   = "roles/iap.httpsResourceAccessor"
  members = concat(
    [for email in var.allowed_emails : "user:${email}"],
    ["serviceAccount:${google_service_account.rag_backend.email}"],
  )
}
