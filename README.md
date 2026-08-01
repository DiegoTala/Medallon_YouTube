# YouTube DJ Analytics

Pipeline medallon serverless en GCP para analisis de sentimiento de comentarios en canales de DJs de YouTube.

## Arquitectura

| Capa | Descripcion |
|:---|:---|
| **Bronze** | JSON Lines inmutable en GCS (YouTube Data API v3 raw) |
| **Silver** | Validacion Pydantic + MERGE idempotente en BigQuery + Dead Letter Queue |
| **Gold** | Sentimiento (Vertex AI Gemini) + Embeddings + Vector Search |

## Stack

- **Orquestacion:** Cloud Scheduler -> Cloud Run Jobs
- **Lenguaje:** Python 3.12+
- **Validacion:** Pydantic v2
- **IaC:** Terraform
- **LLM:** Vertex AI (Gemini 1.5 Flash + text-embedding-004)
- **Presupuesto:** < $15 USD/mes

## Desarrollo local

```bash
# Instalar dependencias (requiere herramientas -- ver docs/SETUP.md)
uv sync
uv run pytest
```

## Infraestructura

```bash
terraform -chdir=infra fmt -check
terraform -chdir=infra validate
```

## Documentacion

- Especificacion completa: `docs/PRD.md`
- Setup y requisitos: `docs/SETUP.md`
