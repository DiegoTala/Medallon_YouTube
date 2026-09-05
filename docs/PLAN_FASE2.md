# Plan de Trabajo — Fase 2: Sistema Agéntico RAG con Memoria

**Fecha de creación:** 2026-09-04
**Última actualización:** 2026-09-05
**Estado:** En progreso — Fases A-D completas, E en curso
**Especificación:** `docs/PRD_Fase2.md`
**Tests:** 91/91 pasan

## Estado del proyecto al inicio de Fase 2

| Componente | Estado |
|:---|:---|
| Pipeline Fase 1 | Operativo (3,239 comentarios, 44 videos, 10 canales DJ) |
| `gold_rag_corpus` | NO existe — falta crear tabla y paso MERGE |
| `infra/fase2/` | NO existe — falta infraestructura Terraform |
| `src/rag_agent/` | NO existe — falta código del agente |
| Skills | 32 skills documentados en `.claude/skills/` |
| Identidades de prueba | Ya creadas (`medallon.rag.test01@`, `medallon.rag.test02@talamantes.com.mx`) |

## Fases del plan

### FASE A — `gold_rag_corpus` en el pipeline de Fase 1
> Skill: `gold-rag-corpus` · Afecta infraestructura de Fase 1 · Requiere approval-gate

- [x] A.1 — Agregar tabla `gold_rag_corpus` en `infra/bigquery.tf` (esquema PRD §8: 14 campos)
- [x] A.2 — Crear módulo `src/medallon_youtube/gold/rag_corpus.py` con MERGE incremental sobre `comment_id`
- [x] A.3 — Integrar `run_rag_corpus_merge()` en `main.py` después de embeddings
- [x] A.4 — Tests unitarios para el MERGE (2 tests nuevos, 43/43 total pasan)
- [x] A.5 — `terraform plan + apply` — tabla creada, registrado en `infra/APPROVALS.md`
- [x] A.6 — Job ejecutado: corpus materializado con **3,261 filas** (7 canales, 768 dims)

### FASE B — Infraestructura Terraform de Fase 2
> Skill: `rag-terraform-root` · Nueva raíz `infra/fase2/` · Requiere approval-gate

- [x] B.1 — Crear `infra/fase2/main.tf` — backend GCS prefix `terraform/fase2`, provider
- [x] B.2 — Crear `infra/fase2/variables.tf` — project_id, region, service name, allowed emails
- [x] B.3 — Crear `infra/fase2/iam.tf` — SA `rag-backend-sa` mínimo privilegio (dataViewer solo gold, jobUser, datastore.user, aiplatform.user)
- [x] B.4 — Crear `infra/fase2/firestore.tf` — database nativo us-central1, 3 políticas TTL (messages 7d, common_queries 180d, response_cache 7d)
- [x] B.5 — Crear `infra/fase2/cloud_run.tf` — Cloud Run Service con IAP, scale-to-zero, no-allow-unauthenticated, sin env vars
- [ ] B.6 — Crear `infra/fase2/iap.tf` — 3 bindings roles/iap.httpsResourceAccessor — **diferido a Fase F** (falta imagen válida + propagación API IAP)
- [x] B.7 — Crear `infra/fase2/outputs.tf`
- [x] B.8 — terraform fmt + validate + cotización cost-guardrail + approval-gate
- [x] B.9 — terraform apply (14/16 recursos) → registrado en infra/APPROVALS.md

### FASE C — Código del agente: estructura base y middleware
> Skills: `rag-fastapi-service`, `rag-iap-auth`, `rag-security-guardrails`, `rag-quota-limits`

- [x] C.1 — Agregar dependencias a pyproject.toml: google-adk, google-cloud-firestore, fastapi, uvicorn, google-auth
- [x] C.2 — Crear estructura src/rag_agent/ (main.py, middleware/, agents/, tools/, memory/, utils/, static/)
- [x] C.3 — Implementar src/rag_agent/main.py — app FastAPI, healthcheck, error handling, endpoint /chat con placeholder
- [x] C.4 — Implementar middleware/auth.py — verificación JWT IAP (x-goog-iap-jwt-assertion, audience Cloud Run, allowlist 3 emails)
- [x] C.5 — Implementar middleware/sanitize.py — normalización NFKC, eliminación controles, preservación newlines, truncado 500 chars
- [x] C.6 — Implementar middleware/quota.py — rate limit 5/min, cuota 30/día, contadores atómicos Firestore, TZ America/Mexico_City
- [x] C.7 — Implementar middleware/cache.py — caché exacto con clave 6 componentes, TTL 7d, hit count
- [x] C.8 — Tests unitarios (29 tests nuevos: 8 sanitize, 3 auth, 8 utils, 6 quota, 4 cache) — 72/72 total pasan

### FASE D — Código del agente: herramientas y agentes ADK
> Skills: `rag-agent-topology`, `rag-tool-semantic-search`, `rag-tool-sentiment-analytics`, `rag-tool-trend-detection`, `rag-synthesis-citations`

- [x] D.1 — Implementar tools/semantic_search.py — VECTOR_SEARCH, top_k ≤ 20, maximum_bytes_billed 10MB, parámetros tipados
- [x] D.2 — Implementar tools/sentiment_analytics.py — 5 plantillas SQL cerradas, validación estricta de parámetros
- [x] D.3 — Implementar tools/trend_detection.py — comparación dual-periodo, evidence_level (insufficient/weak/solid)
- [x] D.4 — Implementar agents/router.py — clasificación de intención, coordinación AgentTool
- [x] D.5 — Implementar agents/search.py — search_agent con output_key="search_result"
- [x] D.6 — Implementar agents/analytics.py — analytics_agent con output_key="analytics_result"
- [x] D.7 — Implementar agents/synthesis.py — synthesis_agent (tools=[]), validación citas, tope 3000 tokens
- [x] D.8 — Implementar orquestación ADK: build_agent_pipeline() con AgentTool (no transferencia)
- [x] D.9 — Tests unitarios (19 tests: 13 tools + 6 agents) — 91/91 total pasan

### FASE E — Memoria, UI y evaluación
> Skills: `rag-memory-session`, `rag-memory-preferences`, `rag-memory-common-queries`, `rag-evaluation-suite`

- [x] E.1 — Implementar memory/session.py — CRUD Firestore TTL 7d, subcolección messages (creado en Fase C)
- [x] E.2 — Implementar memory/preferences.py — instrucción explícita + confirmación, sin TTL (creado en Fase C)
- [x] E.3 — Implementar memory/common_queries.py — hash + contador, TTL 180d (creado en Fase C)
- [x] E.4 — Implementar utils/normalize.py — normalización compartida (creado en Fase C)
- [ ] E.5 — Implementar UI HTML/CSS/JS en static/
- [ ] E.6 — Crear Dockerfile.rag (separado del pipeline)
- [ ] E.7 — Crear set 15 preguntas doradas + 10 adversariales en tests/rag_evaluation/
- [ ] E.8 — Integración completa: cadena middleware → agentes → herramientas → respuesta
- [ ] E.9 — Tests de integración end-to-end

### FASE F — Despliegue y validación
> Skills: `rag-deploy-service`, `rag-evaluation-suite`, `rag-iap-auth`

- [ ] F.1 — Build + push imagen Docker a Artifact Registry
- [ ] F.2 — Ejecutar set de evaluación contra datos reales
- [ ] F.3 — Cotización + approval-gate para despliegue Cloud Run Service
- [ ] F.4 — Deploy del servicio con IAP habilitado
- [ ] F.5 — Verificar acceso con las 3 identidades reales
- [ ] F.6 — Registrar en infra/APPROVALS.md
- [ ] F.7 — Medir costo real y latencia

## Presupuesto

```
Costo base actual (Fase 1):    ~$1.85 USD/mes
Delta estimado Fase 2:         ~$1.00 - $4.50 USD/mes
Costo total estimado:          ~$2.85 - $6.35 USD/mes
Techo vigente:                 $20.00 USD/mes
Margen:                        ~$13.65 - $17.15 USD
```

## Riesgos principales

| Riesgo | Mitigación |
|:---|:---|
| `gold_rag_corpus` no existe → agentes sin datos | Fase A es prerequisito de todo lo demás |
| ADK 2.6.0 puede tener breaking changes | Pinned en lockfile, snippets verificados |
| IAP nativo sobre Cloud Run sin LB | Ya verificado en rag-iap-auth |
| Costo de Gemini al escalar | maximum_bytes_billed + circuit breaker + cuota |

## Referencias

- Especificación: `docs/PRD_Fase2.md`
- Bitácora de aprobaciones: `infra/APPROVALS.md`
- Skills: `.claude/skills/rag-*/SKILL.md`
- AGENTS.md: invariantes y tabla de qué guía usar
