---
name: gcloud-diagnostics
description: Comandos gcloud de SOLO LECTURA permitidos para verificar el estado real de recursos GCP (proyecto medallon-youtube) antes de planear o depurar. Nunca uses este skill para crear, modificar o borrar nada — eso es terraform-provision/terraform-decommission bajo approval-gate.
---

# gcloud-diagnostics

## Alcance

`gcloud` CLI se usa **exclusivamente** para diagnóstico e inspección de estado. La creación/modificación/eliminación de recursos es dominio exclusivo de Terraform ([[terraform-provision]] / [[terraform-decommission]]), gateado por [[approval-gate]]. Ningún comando de este skill muta estado ni genera costo relevante.

## Por qué gcloud no crea recursos en este proyecto

El PRD exige infraestructura como código declarativa (Terraform) para tener un state auditable y reproducible. Un `gcloud ... create` imperativo generaría drift respecto al state de Terraform y rompería la trazabilidad de [[approval-gate]]. Por eso el rol de gcloud aquí se limita a lectura.

## Comandos permitidos (lista no exhaustiva, todos de solo lectura)

```bash
# Estado general del proyecto
gcloud projects describe medallon-youtube

# Verificar APIs habilitadas
gcloud services list --enabled --project=medallon-youtube

# Inspeccionar el Cloud Run Job (config actual, última ejecución)
gcloud run jobs describe yt-ingestion-job --region=us-central1 --project=medallon-youtube
gcloud run jobs executions list --job=yt-ingestion-job --region=us-central1 --project=medallon-youtube

# Ver logs de la última ejecución (para depurar fallos)
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="yt-ingestion-job"' \
  --project=medallon-youtube --limit=100 --order=desc

# Verificar el Cloud Scheduler
gcloud scheduler jobs describe yt-weekly-trigger --location=us-central1 --project=medallon-youtube

# Verificar imágenes disponibles en Artifact Registry
gcloud artifacts docker images list us-central1-docker.pkg.dev/medallon-youtube/yt-pipeline

# Verificar secretos existentes (sin exponer el valor)
gcloud secrets list --project=medallon-youtube
gcloud secrets versions list youtube-api-key --project=medallon-youtube

# Verificar datasets/tablas de BigQuery (vía bq, también solo lectura)
bq ls --project_id=medallon-youtube
bq show medallon-youtube:silver.silver_youtube_comments
```

## Explícitamente prohibido en este skill

```bash
# NUNCA desde gcloud-diagnostics — usar terraform-provision bajo approval-gate:
gcloud run jobs create ...
gcloud run jobs update ...
gcloud run jobs deploy ...
gcloud services enable ...
gcloud secrets create ...
gcloud iam service-accounts create ...

# NUNCA desde gcloud-diagnostics — usar terraform-decommission bajo approval-gate:
gcloud run jobs delete ...
gcloud storage rm ...
bq rm ...
```

## Diagnóstico de Fase 2 (agente RAG) — también solo lectura

Recursos que Fase 1 no tiene. Mismas reglas: `describe`, `list`, `read`, nunca mutación.

```bash
# ¿El proyecto pertenece a una organización? — precondición de IAP, ver rag-iap-auth
gcloud projects describe medallon-youtube --format="value(parent.type,parent.id)"
gcloud organizations list

# PROJECT_NUMBER: necesario para el audience del JWT de IAP (es el número, no el ID)
gcloud projects describe medallon-youtube --format="value(projectNumber)"

# Cloud Run Service: estado, revisiones y reparto de tráfico
gcloud run services describe rag-chat-service --region=us-central1
gcloud run revisions list --service=rag-chat-service --region=us-central1

# IAP: quién tiene acceso realmente
gcloud run services get-iam-policy rag-chat-service --region=us-central1

# Firestore: base de datos y políticas TTL vigentes
gcloud firestore databases list
gcloud firestore fields list --database='(default)'

# Permisos efectivos de la service account del backend
gcloud projects get-iam-policy medallon-youtube \
  --flatten="bindings[].members" \
  --filter="bindings.members:rag-backend@medallon-youtube.iam.gserviceaccount.com"
bq show --format=prettyjson medallon-youtube:gold | grep -A20 access

# Logs del servicio (solo lectura)
gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=rag-chat-service' --limit=50
```

Las dos últimas consultas de IAM son el diagnóstico que respalda la meta de "0 accesos a tablas no autorizadas" del PRD Fase 2 §13: confirman que la cuenta del backend tiene lectura **solo** sobre el dataset `gold` y no a nivel de proyecto. Si `bq show` sobre `silver` o `bronze` la lista, hay un binding mal puesto — se corrige en [[rag-terraform-root]] bajo [[approval-gate]], nunca con `gcloud ... add-iam-policy-binding`.

Excepción parcial documentada: `deploy-release` sí ejecuta `gcloud run jobs update --image` (una mutación), pero lo hace como parte de su propio flujo gateado por [[approval-gate]] — no como parte de este skill de diagnóstico.

## Invariantes

- **Cero flags de mutación:** ningún comando en este skill lleva `create`, `update`, `delete`, `deploy`, `enable`, `add-iam-policy-binding`, etc.
- **No requiere aprobación previa** precisamente porque no muta nada — se puede correr en cualquier momento para informarse.

## Relación con otros skills

- Se usa para verificar estado antes de armar un plan en [[terraform-provision]], [[terraform-decommission]] o [[rag-terraform-root]].
- La verificación de organización es precondición obligatoria de [[rag-iap-auth]] antes de implementar autenticación.
- Complementa [[cost-guardrail]] cuando se necesita confirmar qué existe realmente antes de estimar un delta de costo.
