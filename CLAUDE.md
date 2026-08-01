# CLAUDE.md

Arnés de desarrollo y mantenimiento de **YouTube DJ Analytics** — pipeline medallón serverless en GCP (ver `docs/PRD.md` para la especificación completa). Este archivo es un orquestador **lean**: solo invariantes del sistema y la tabla de qué skill usar. El detalle operativo vive exclusivamente en `.claude/skills/<nombre>/SKILL.md` — no lo dupliques aquí.

## Invariantes del sistema (no negociables)

1. **Aprobación previa obligatoria.** Ningún `terraform apply`, `terraform destroy`, ni `gcloud` mutante se ejecuta sin plan + cotización de costo + aprobación explícita y verbatim del usuario en el chat, registrada después en `infra/APPROVALS.md`. Regla completa: `.claude/skills/approval-gate/SKILL.md`.
2. **Terraform es la única vía de mutación de infraestructura.** `gcloud` CLI se usa exclusivamente para diagnóstico de solo lectura (`describe`, `list`, `logs read`). Nunca `gcloud ... create/update/delete/deploy` fuera del flujo de `deploy-release` (que también pasa por el gate de aprobación).
3. **Techo de presupuesto: $15.00 USD/mes.** Toda estimación de costo se compara explícitamente contra este techo (`.claude/skills/cost-guardrail/SKILL.md`).
4. **Idempotencia en Silver, incrementalidad en Gold.** Silver usa `MERGE` sobre clave natural (reprocesar = 0 filas nuevas). Gold nunca reprocesa comentarios ya clasificados/embebidos (`LEFT JOIN ... WHERE IS NULL`), por control de costo de Vertex AI.
5. **Ningún registro se descarta sin rastro.** Todo lo que falla validación Pydantic o integridad referencial va a `silver_dead_letter_queue`, nunca se pierde silenciosamente.
6. **Co-ubicación regional obligatoria:** BigQuery, Vertex AI y Cloud Run Jobs en `us-central1` — `ML.GENERATE_TEXT`/`ML.GENERATE_EMBEDDING` fallan si hay mismatch de región.
7. **Esta sesión de arnés no ejecuta nada real.** Los skills son guías para trabajo futuro; no implican que la infraestructura ya exista o deba crearse por default.

## Qué skill usar

| Si vas a... | Usa el skill |
| :--- | :--- |
| Ejecutar o revisar cualquier `terraform apply`/`destroy`/`gcloud` mutante | [`approval-gate`](.claude/skills/approval-gate/SKILL.md) |
| Extraer metadatos de video de YouTube API v3 → GCS | [`bronze-ingestion-videos`](.claude/skills/bronze-ingestion-videos/SKILL.md) |
| Extraer comentarios/replies de YouTube API v3 → GCS | [`bronze-ingestion-comments`](.claude/skills/bronze-ingestion-comments/SKILL.md) |
| Validar videos (Pydantic) y aplicar MERGE a Silver | [`silver-validation-videos`](.claude/skills/silver-validation-videos/SKILL.md) |
| Validar comentarios (Pydantic + FK) y aplicar MERGE a Silver | [`silver-validation-comments`](.claude/skills/silver-validation-comments/SKILL.md) |
| Diseñar o consultar la dead-letter queue | [`silver-dead-letter-queue`](.claude/skills/silver-dead-letter-queue/SKILL.md) |
| Clasificar sentimiento con Gemini (`ML.GENERATE_TEXT`) | [`gold-sentiment-analysis`](.claude/skills/gold-sentiment-analysis/SKILL.md) |
| Generar embeddings (`ML.GENERATE_EMBEDDING`) | [`gold-embeddings-generation`](.claude/skills/gold-embeddings-generation/SKILL.md) |
| Crear/mantener índice vectorial o hacer `VECTOR_SEARCH` | [`gold-vector-search`](.claude/skills/gold-vector-search/SKILL.md) |
| Crear o actualizar recursos GCP vía Terraform | [`terraform-provision`](.claude/skills/terraform-provision/SKILL.md) |
| Eliminar recursos GCP vía Terraform | [`terraform-decommission`](.claude/skills/terraform-decommission/SKILL.md) |
| Verificar estado real de un recurso GCP (solo lectura) | [`gcloud-diagnostics`](.claude/skills/gcloud-diagnostics/SKILL.md) |
| Estimar costo de un cambio propuesto vs. el techo de $15/mes | [`cost-guardrail`](.claude/skills/cost-guardrail/SKILL.md) |
| Build/push de imagen Docker y actualizar el Cloud Run Job | [`deploy-release`](.claude/skills/deploy-release/SKILL.md) |
| Actualizar `docs/PRD.md`, README u otra documentación | [`docs-maintenance`](.claude/skills/docs-maintenance/SKILL.md) |

## Referencias

- Especificación completa: `docs/PRD.md`
- Bitácora de aprobaciones de infraestructura: `infra/APPROVALS.md`
- Para agentes no nativos de Claude Code (Cursor, Aider, Codex CLI, etc.), ver `AGENTS.md` — apunta a los mismos `.claude/skills/*/SKILL.md` como fuente única de verdad.
