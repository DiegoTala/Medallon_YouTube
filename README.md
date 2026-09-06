# YouTube DJ Analytics

Plataforma serverless en GCP para analizar comentarios de canales de DJs de YouTube.

El proyecto tiene dos fases: la Fase 1 construye el pipeline de datos y la Fase 2 usa la Gold layer como Knowledge Base de un sistema agéntico RAG.

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
- **LLM:** Vertex AI (Gemini 2.5 Flash + text-embedding-004)
- **Presupuesto Fase 1:** < $15 USD/mes

## Fase 2: Sistema agéntico RAG

Aplicación web conversacional sobre `gold_rag_corpus`, la tabla Gold que funciona como Knowledge Base del agente.

- **RAG:** BigQuery Vector Search y consultas analíticas parametrizadas
- **Agentes:** Google ADK con búsqueda, analítica, tendencias, memoria y síntesis
- **Memoria:** Firestore para sesiones, preferencias, consultas frecuentes y caché
- **Autenticación:** IAP nativo de Cloud Run
- **Guardrails:** dominio cerrado, acceso solo a Gold, validación de citas, cuotas y límites de costo
- **Aplicación:** [rag-chat-service-7od5boefba-uc.a.run.app](https://rag-chat-service-7od5boefba-uc.a.run.app)
- **Reporte ejecutivo:** [`docs/Evidencias Fase 2/REPORTE-EJECUTIVO-FASE2-2026-09-05.md`](docs/Evidencias%20Fase%202/REPORTE-EJECUTIVO-FASE2-2026-09-05.md)

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
- Especificacion Fase 2: `docs/PRD_Fase2.md`
- Setup y requisitos: `docs/SETUP.md`
