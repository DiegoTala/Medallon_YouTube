# AGENTS.md

Arnés de desarrollo y mantenimiento de **YouTube DJ Analytics** — pipeline medallón serverless en GCP (ver `docs/PRD.md` para la especificación completa). Este archivo sigue el estándar abierto [agents.md](https://agents.md) para que cualquier agente de codificación (no solo Claude Code) pueda operar en este repo con las mismas reglas.

Este documento es deliberadamente **lean**: invariantes del sistema + tabla de qué guía usar. No dupliques el detalle operativo aquí — vive en `.claude/skills/<nombre>/SKILL.md`. Este estándar no tiene un mecanismo nativo de "skills"; los archivos `SKILL.md` referenciados abajo son simplemente Markdown plano y cualquier agente que pueda leer archivos del repo puede seguirlos igual que Claude Code.

## Invariantes del sistema (no negociables)

1. **Aprobación previa obligatoria.** Ningún `terraform apply`, `terraform destroy`, ni `gcloud` mutante se ejecuta sin plan + cotización de costo + aprobación explícita y verbatim del usuario en el chat, registrada después en `infra/APPROVALS.md`. Regla completa: `.claude/skills/approval-gate/SKILL.md`.
2. **Terraform es la única vía de mutación de infraestructura.** `gcloud` CLI se usa exclusivamente para diagnóstico de solo lectura. Nunca `gcloud ... create/update/delete/deploy` fuera del flujo de `deploy-release` (que también pasa por el gate de aprobación).
3. **Techo de presupuesto: $15.00 USD/mes.** Toda estimación de costo se compara explícitamente contra este techo (`.claude/skills/cost-guardrail/SKILL.md`).
4. **Idempotencia en Silver, incrementalidad en Gold.** Silver usa `MERGE` sobre clave natural. Gold nunca reprocesa comentarios ya clasificados/embebidos, por control de costo de Vertex AI.
5. **Ningún registro se descarta sin rastro.** Todo lo que falla validación va a `silver_dead_letter_queue`.
6. **Co-ubicación regional obligatoria:** BigQuery, Vertex AI y Cloud Run Jobs en `us-central1`.
7. **Esta versión del arnés no ejecuta nada real.** Los skills son guías para trabajo futuro.

## Comandos de referencia (una vez implementado el pipeline)

Ver `.claude/skills/deploy-release/SKILL.md` para el flujo completo. Tooling Python estándar del proyecto: **uv**.

```bash
uv sync --frozen          # instalar dependencias exactas del lockfile
uv run pytest             # correr pruebas (cuando existan)
terraform -chdir=infra fmt -check && terraform -chdir=infra validate   # validar IaC, solo lectura
```

## Qué guía usar

| Si vas a... | Usa la guía |
| :--- | :--- |
| Ejecutar o revisar cualquier `terraform apply`/`destroy`/`gcloud` mutante | `.claude/skills/approval-gate/SKILL.md` |
| Extraer metadatos de video de YouTube API v3 → GCS | `.claude/skills/bronze-ingestion-videos/SKILL.md` |
| Extraer comentarios/replies de YouTube API v3 → GCS | `.claude/skills/bronze-ingestion-comments/SKILL.md` |
| Validar videos (Pydantic) y aplicar MERGE a Silver | `.claude/skills/silver-validation-videos/SKILL.md` |
| Validar comentarios (Pydantic + FK) y aplicar MERGE a Silver | `.claude/skills/silver-validation-comments/SKILL.md` |
| Diseñar o consultar la dead-letter queue | `.claude/skills/silver-dead-letter-queue/SKILL.md` |
| Clasificar sentimiento con Gemini (`ML.GENERATE_TEXT`) | `.claude/skills/gold-sentiment-analysis/SKILL.md` |
| Generar embeddings (`ML.GENERATE_EMBEDDING`) | `.claude/skills/gold-embeddings-generation/SKILL.md` |
| Crear/mantener índice vectorial o hacer `VECTOR_SEARCH` | `.claude/skills/gold-vector-search/SKILL.md` |
| Crear o actualizar recursos GCP vía Terraform | `.claude/skills/terraform-provision/SKILL.md` |
| Eliminar recursos GCP vía Terraform | `.claude/skills/terraform-decommission/SKILL.md` |
| Verificar estado real de un recurso GCP (solo lectura) | `.claude/skills/gcloud-diagnostics/SKILL.md` |
| Estimar costo de un cambio propuesto vs. el techo de $15/mes | `.claude/skills/cost-guardrail/SKILL.md` |
| Build/push de imagen Docker y actualizar el Cloud Run Job | `.claude/skills/deploy-release/SKILL.md` |
| Actualizar `docs/PRD.md`, README u otra documentación | `.claude/skills/docs-maintenance/SKILL.md` |

## Referencias

- Especificación completa: `docs/PRD.md`
- Bitácora de aprobaciones de infraestructura: `infra/APPROVALS.md`
- Para Claude Code específicamente, ver `CLAUDE.md` (mismo contenido, mismos skills, formato equivalente).
