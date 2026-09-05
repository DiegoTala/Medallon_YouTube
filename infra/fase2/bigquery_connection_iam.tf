# ── Acceso a la conexión BigQuery → Vertex AI (recurso de Fase 1) ──────────
#
# `semantic_search` embebe la consulta del usuario con ML.GENERATE_EMBEDDING
# sobre el modelo remoto `gold.embedding_model`. Ese modelo sale a Vertex AI a
# través de la conexión `vertex-ai-connection`, que es un recurso **con su
# propio IAM**, distinto del dataset: `roles/bigquery.dataViewer` sobre `gold`
# NO alcanza.
#
# Sin este binding, toda consulta de búsqueda semántica falla con:
#   403 Access Denied: ... User does not have bigquery.connections.use
#   permission for connection ...vertex-ai-connection
#
# Es exactamente el mismo gap que tuvo Fase 1 (ver infra/iam.tf y la entrada
# 2026-08-02T19:04:15 de infra/APPROVALS.md). Se repite aquí porque la conexión
# es un recurso compartido que Fase 2 usa pero no posee.
#
# La conexión NO se declara como `resource` ni se importa a este state: Fase 2
# solo crea el binding sobre ella. Se referencia por su id literal porque el
# provider no expone un data source para conexiones de BigQuery; el id vive en
# `infra/bigquery.tf` (google_bigquery_connection.vertex_ai) y se replica aquí
# como variable para que el acoplamiento sea explícito.
resource "google_bigquery_connection_iam_member" "rag_backend_connection_user" {
  project       = var.project_id
  location      = var.region
  connection_id = var.vertex_connection_id
  role          = "roles/bigquery.connectionUser"
  member        = "serviceAccount:${google_service_account.rag_backend.email}"
}
