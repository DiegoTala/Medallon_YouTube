---
name: rag-terraform-root
description: Raíz Terraform aislada de Fase 2 en infra/fase2/ — state propio, recursos de Fase 1 solo por data source, service account de mínimo privilegio, Firestore con políticas TTL e IAP. Úsalo al escribir o modificar cualquier .tf de Fase 2.
---

# rag-terraform-root

## Alcance

La infraestructura de Fase 2 vive en **`infra/fase2/`**, una raíz de Terraform separada de `infra/` (Fase 1). Este skill cubre qué va ahí, qué no, y por qué el aislamiento es un control de seguridad y no una preferencia de organización.

Las convenciones generales de Terraform (formato, flujo de plan, mínimo privilegio, región) siguen siendo las de [[terraform-provision]]; este skill solo agrega lo específico de Fase 2.

## Aislamiento de state

Mismo bucket de state, prefijo distinto:

```hcl
# infra/fase2/main.tf
terraform {
  required_version = ">= 1.9"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 7.42" }
  }
  backend "gcs" {
    bucket = "medallon-youtube-tfstate"
    prefix = "terraform/fase2"        # <- Fase 1 usa "terraform/state"
  }
}
```

**Por qué importa:** `terraform destroy` solo puede destruir lo que está en su state. Con esta separación, un destroy de Fase 2 es incapaz de tocar el pipeline productivo — no por disciplina del operador, sino porque esos recursos no existen en su state. Es la misma lógica de defensa en capas de [[rag-security-guardrails]]: el control más fuerte es el que no depende de que alguien recuerde aplicarlo.

Consecuencia operativa: **todo comando lleva `-chdir` explícito.** Un `terraform apply` sin `-chdir` corre sobre el directorio actual, y ese es exactamente el descuido que el aislamiento existe para contener.

```bash
terraform -chdir=infra/fase2 plan -out=tfplan
terraform -chdir=infra/fase2 apply tfplan
```

## Recursos de Fase 1: `data`, nunca `resource`

Fase 2 necesita referirse al dataset Gold, pero **no lo posee**. Se lee, no se declara:

```hcl
data "google_bigquery_dataset" "gold" {
  dataset_id = "gold"
  project    = var.project_id
}
```

Declararlo como `resource` lo pondría bajo el state de Fase 2, y un destroy de Fase 2 borraría el dataset Gold del pipeline. Es el error más caro posible en este archivo. La regla es mecánica: **si el recurso ya existe en `infra/`, en `infra/fase2/` es un `data`.**

`gold_rag_corpus` es de Fase 1 y se declara en `infra/bigquery.tf` — ver [[gold-rag-corpus]].

## Service account de mínimo privilegio

La cuenta del backend (PRD §14) es donde el invariante "cero acceso a Bronze, Silver y DLQ" se vuelve real:

| Permiso | Alcance | Para qué |
| :--- | :--- | :--- |
| `roles/bigquery.dataViewer` | **solo el dataset `gold`** | leer el corpus |
| `roles/bigquery.jobUser` | proyecto | ejecutar consultas |
| `roles/datastore.user` | proyecto | Firestore |
| `roles/aiplatform.user` | proyecto | Gemini y embeddings |

```hcl
resource "google_bigquery_dataset_iam_member" "backend_gold_reader" {
  dataset_id = data.google_bigquery_dataset.gold.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.rag_backend.email}"
}
```

**A nivel de dataset, nunca a nivel de proyecto.** Un `google_project_iam_member` con `roles/bigquery.dataViewer` concede lectura sobre Bronze, Silver **y** la dead-letter queue de un plumazo, y la meta del PRD §13 de "0 accesos a tablas no autorizadas" pasaría a depender de que ningún prompt falle nunca. Sin permisos administrativos, sin `roles/editor`, sin escritura sobre Gold.

Diego recibe por separado roles de **solo lectura** sobre Firestore, Logging y Monitoring (PRD §14) para administrar desde la consola.

## Firestore y sus políticas TTL

Base de datos en modo nativo, en `us-central1`. Las tres políticas TTL son recursos, no configuración manual:

```hcl
resource "google_firestore_field" "messages_ttl" {
  project    = var.project_id
  database   = google_firestore_database.rag.name
  collection = "messages"          # collection group
  field      = "expires_at"
  ttl_config {}                    # bloque vacío = TTL habilitado
}
```

Una por cada *collection group* con retención: `messages` (7 días, [[rag-memory-session]]), `common_queries` (180 días, [[rag-memory-common-queries]]) y `response_cache` (7 días, [[rag-response-cache]]). **No** lleva TTL el documento raíz `users/{user_id}` — ahí viven las preferencias, que no expiran ([[rag-memory-preferences]]).

> **Nota (verificada 2026-09-04, [google_firestore_field](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/firestore_field) y [TTL de Firestore](https://docs.cloud.google.com/firestore/native/docs/ttl)):** `ttl_config {}` va vacío — no toma parámetros; la presencia del bloque es lo que habilita la política. Quitarlo en una edición posterior **deshabilita el TTL**, no lo deja como estaba. Y la política solo marca el campo: si la aplicación no escribe `expires_at`, no se borra nada. La retención es mitad Terraform, mitad código.

## Cloud Run Service e IAP

El servicio se declara con IAP habilitado y sin acceso público, y el acceso se concede con `roles/iap.httpsResourceAccessor` a las tres identidades del PRD §2.

**El brand OAuth externo no es Terraform.** Es un paso manual en consola, obligatorio para las dos cuentas `@gmail.com` — ver [[rag-iap-auth]]. Aun así se registra en `infra/APPROVALS.md`, porque cambia quién puede entrar al sistema.

## Flujo de aplicación

Idéntico al de [[terraform-provision]] — `fmt`, `validate`, `plan`, cotización con [[cost-guardrail]], aprobación verbatim vía [[approval-gate]], `apply`, registro en `infra/APPROVALS.md` — **con `-chdir=infra/fase2` en cada comando** y anotando en la entrada de aprobación cuál de las dos raíces se aplicó.

## Invariantes

- **Dos raíces, dos states.** `infra/` es Fase 1; `infra/fase2/` es Fase 2.
- **`-chdir` explícito siempre.**
- **Recursos de Fase 1 se referencian con `data`, jamás con `resource`.**
- **Lectura de BigQuery a nivel de dataset**, nunca de proyecto.
- **Sin escritura sobre Gold** para la cuenta del backend.
- **Una política TTL por collection group con retención**, y ninguna sobre `users/{user_id}`.
- **`us-central1`** para todo, por la co-ubicación regional del proyecto.
- **El brand OAuth se registra en APPROVALS.md** aunque sea manual.

## Relación con otros skills

- Hereda convenciones de [[terraform-provision]]; para borrar, [[terraform-decommission]] con la misma disciplina de `-chdir`.
- Gateado por [[approval-gate]], cotizado por [[cost-guardrail]].
- Materializa las barreras de [[rag-security-guardrails]] y la identidad de [[rag-iap-auth]].
- Aprovisiona el TTL que consumen [[rag-memory-session]], [[rag-memory-common-queries]] y [[rag-response-cache]].
- El servicio que declara se despliega con [[rag-deploy-service]].
