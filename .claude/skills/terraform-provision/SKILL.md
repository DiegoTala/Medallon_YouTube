---
name: terraform-provision
description: Convenciones para crear o actualizar recursos GCP declarativamente con Terraform (Cloud Scheduler, Cloud Run Jobs, Artifact Registry, BigQuery, GCS, Secret Manager, IAM). Úsalo al escribir o modificar cualquier archivo .tf que aprovisione o actualice un recurso. SIEMPRE pasa por approval-gate antes de aplicar.
---

# terraform-provision

## Alcance

Toda creación o actualización de recursos GCP reales se declara en Terraform.

> **Dos raíces de Terraform (desde 2026-09-04).** `infra/` es el pipeline medallón de Fase 1 (state `terraform/state`); `infra/fase2/` es el agente RAG de Fase 2 (state `terraform/fase2`, mismo bucket). Están aisladas a propósito: un `destroy` solo alcanza lo que está en su propio state. **Todo comando lleva `-chdir` explícito** — `terraform -chdir=infra plan` o `terraform -chdir=infra/fase2 plan` — y la entrada en `infra/APPROVALS.md` dice cuál se aplicó. Las convenciones de este skill valen para ambas; lo específico de Fase 2 está en [[rag-terraform-root]].

Este skill cubre el "crear/actualizar". Para borrar recursos ver [[terraform-decommission]] (skill separado, con salvaguardas adicionales).

## Regla de oro

**Nunca `terraform apply` sin pasar antes por [[approval-gate]].** `terraform plan` sí se puede correr libremente — es de solo lectura.

## Inventario de recursos (PRD §6, "Despliegue de Infraestructura con Terraform")

| Recurso | Módulo sugerido | Notas |
| :--- | :--- | :--- |
| Cloud Scheduler | `modules/scheduler` | Cron semanal, destino HTTP al Cloud Run Job. |
| Cloud Run Job | `modules/cloud_run_job` | Variables de entorno (sin secrets en texto plano), límites de recursos, `--max-retries=3 --task-timeout=30m`. |
| Artifact Registry | `modules/artifact_registry` | Repositorio Docker para la imagen del contenedor. |
| BigQuery | `modules/bigquery` | Datasets `bronze`/`silver`/`gold`, tablas, modelos remotos de Vertex AI. Región `us-central1` obligatoria (co-ubicación con Vertex AI). |
| Cloud Storage | `modules/gcs` | Buckets con lifecycle rule de borrado automático >90 días. |
| Secret Manager | `modules/secrets` | API Key de YouTube, montada como env var en Cloud Run Job. |
| IAM | `modules/iam` | Service account de mínimo privilegio para el Job. |

## Backend de state

State remoto en un bucket GCS con versionado habilitado (para colaboración/auditoría, PRD §6):

```hcl
terraform {
  backend "gcs" {
    bucket = "medallon-youtube-tfstate"
    prefix = "terraform/state"
  }
}
```

## Snippet de ejemplo: Cloud Run Job con secret montado

```hcl
resource "google_cloud_run_v2_job" "yt_ingestion" {
  name     = "yt-ingestion-job"
  location = "us-central1"

  template {
    template {
      containers {
        image = "us-central1-docker.pkg.dev/${var.project_id}/yt-pipeline/ingestion:${var.image_tag}"

        env {
          name = "YOUTUBE_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.youtube_api_key.secret_id
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
      timeout     = "1800s"  # 30m, coincide con --task-timeout del PRD
    }
  }
}
```

## Snippet de ejemplo: lifecycle rule de GCS (borrado >90 días)

```hcl
resource "google_storage_bucket" "bronze" {
  name     = "${var.project_id}-yt-bronze"
  location = "US"  # multirregional, según PRD §3

  lifecycle_rule {
    condition { age = 90 }
    action { type = "Delete" }
  }
}
```

## Flujo obligatorio antes de aplicar

1. `terraform -chdir=<raíz> fmt` + `terraform -chdir=<raíz> validate`.
2. `terraform -chdir=<raíz> plan -out=tfplan` y leer el diff completo (no solo el resumen). Confirmar que la raíz es la correcta **antes** de leer el plan: un plan que propone crear recursos que ya existen suele significar que se está en la raíz equivocada.
3. Invocar [[cost-guardrail]] para cotizar el delta.
4. Presentar plan + cotización al usuario vía [[approval-gate]] y esperar aprobación verbatim.
5. Solo entonces `terraform -chdir=<raíz> apply tfplan`.
6. Registrar en `infra/APPROVALS.md`.

## Invariantes

- **Principio de mínimo privilegio** en todo `google_project_iam_member`/`google_service_account_iam_member` — nunca `roles/owner` ni `roles/editor` para el service account del Job.
- **Ningún secreto en texto plano** en archivos `.tf` ni en `terraform.tfvars` versionado — siempre vía Secret Manager o variables marcadas `sensitive = true`.
- **Región `us-central1`** para BigQuery, Vertex AI y Cloud Run — nunca desviarse sin justificación explícita, por la restricción de co-ubicación del PRD §3.

## Relación con otros skills

- Gateado siempre por [[approval-gate]].
- Cotizado siempre por [[cost-guardrail]] antes de aplicar.
- Complementario a [[terraform-decommission]] (nunca se mezclan create/destroy en el mismo plan sin dejarlo explícito en la revisión).
- El repositorio de Artifact Registry que este skill crea es consumido por [[deploy-release]] y por [[rag-deploy-service]] para publicar imágenes.
- Para la raíz de Fase 2, sus `data` sources y su service account de mínimo privilegio: [[rag-terraform-root]].
