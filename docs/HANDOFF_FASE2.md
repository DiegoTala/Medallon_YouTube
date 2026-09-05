# Reporte de Handoff — Fase 2 (RAG Agent) · 2026-09-05

**Estado:** En progreso — Fase F (Despliegue y validación) casi completa.
**Bloqueante actual:** 1 bug de IAM en la herramienta `semantic_search`.
**Sesión:** Continuar desde este archivo. No re-ejecutar pasos ya completados.

---

## Resumen ejecutivo

El Cloud Run Service `rag-chat-service` está **desplegado y funcional**:
- IAP habilitado, acceso validado con las 3 identidades (diego, test01, test02) + rechazo de una 4ta ✅
- Pipeline de agentes ADK responde (HTTP 200) — Vertex AI configurado correctamente
- Firestore conectado (`rag-memory`), índices compuestos creados
- **PERO** la herramienta `semantic_search` falla con "acceso denegado a la base de datos" → bug de IAM identificado (falta `connectionUser` en la conexión Vertex para la SA de Fase 2)

---

## 1. BUG BLOQUEANTE — `semantic_search` 403 (el único bloqueante)

### Síntoma
Consulta real (`¿Qué opinan los usuarios sobre los drops de Fisher?`) → HTTP 200 pero la respuesta es:
> "El agente de búsqueda ha informado de un error: ... parece que hay un error de acceso denegado. No tengo los permisos necesarios para acceder a la base de datos."

### Causa raíz (verificada)
`semantic_search` ejecuta `ML.GENERATE_EMBEDDING` (modelo remoto `gold.embedding_model`) a través de la **conexión BigQuery ↔ Vertex AI** `vertex-ai-connection`.

La conexión solo tiene `roles/bigquery.connectionUser` para la SA de Fase 1:
```json
{"role": "roles/bigquery.connectionUser", "members": ["serviceAccount:yt-ingestion-job@medallon-youtube.iam.gserviceaccount.com"]}
```
**Falta `rag-backend-sa@medallon-youtube.iam.gserviceaccount.com`** → la SA de Fase 2 no puede usar `ML.GENERATE_EMBEDDING` ni el modelo remoto.

### Fix pendiente
1. Agregar `roles/bigquery.connectionUser` sobre `us-central1.vertex-ai-connection` para `serviceAccount:rag-backend-sa@medallon-youtube.iam.gserviceaccount.com`.
2. Declararlo en `infra/fase2/` (IAM de Fase 2 no toca recursos de Fase 1 → declarar como **data source** la conexión en `infra/fase2/main.tf` y el binding como `google_bigquery_connection_iam_member`, siguiendo el patrón de Fase 1 `infra/iam.tf`).
3. `terraform -chdir=infra/fase2 plan` + approval-gate + apply + registro en `infra/APPROVALS.md`.

> Nota histórica: Fase 1 tuvo exactamente este mismo gap (ver APPROVALS.md 2026-08-02T19:04:15). Se repite en Fase 2 porque la conexión es recurso compartido y Fase 2 no la posee.

### Verificación post-fix
```python
# tests/rag_evaluation/_test_tool.py ya existe — ejecutar:
wsl -d Ubuntu -- bash -c 'export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token 2>/dev/null) && cd /home/diegotala42/Medallon_YouTube && .venv/bin/python tests/rag_evaluation/_test_tool.py'
# Esperado: {"status": "success", "results": [...], "count": N}
```
Luego consulta real vía `run_eval.ask()` → debe devolver comentarios con citas.

---

## 2. DRIFT DE TERRAFORM — actualizar tfvars

- `infra/fase2/terraform.tfvars` dice `rag_image_tag = "7cae04b-fix3"`
- El servicio corre `7cae04b-fix4` (revisión `rag-chat-service-00006-j67`, desplegado vía `gcloud run deploy`)

**Acción:** actualizar `terraform.tfvars` a `7cae04b-fix4` y correr `terraform plan` para confirmar cero drift en la imagen.

---

## 3. PENDIENTE: registrar applies en `infra/APPROVALS.md`

Hoy se ejecutaron **5 applies** de `infra/fase2/` que NO están registrados. Cada uno con su plan y aprobación de Diego:

| # | Plan | Recursos | Aprobado por Diego |
|:--|:-----|:---------|:-------------------|
| 1 | `tfplan_indexes` | 3 índices Firestore + `iap_invoker` + `rag_access` (fix resource) | "Apruebo el plan!" |
| 2 | `tfplan_iap_fix` | `google_iap_web_cloud_run_service_iam_binding.rag_access` (resource correcto para Cloud Run) | (continuación del mismo) |
| 3 | `tfplan_eval_iam` | `diego_token_creator` + `rag_backend_invoker` | "Apruebo" |
| 4 | `tfplan_iap_sa` | SA en binding IAP + quitar invoker (conflicto detectado) | (continuación) |
| 5 | `tfplan_msg_index` | Reemplazo índice `messages` (DESC→ASC) + update Service | (continuación) |

Además: 4 builds/deploys (`fix1`…`fix4`), brand OAuth creado, `cloudresourcemanager.googleapis.com` + `compute.googleapis.com` habilitadas.

**Formato:** seguir plantilla del archivo. Raíz `infra/fase2/`, costo $0/mes, verbatim de aprobaciones arriba.

---

## 4. EVALUACIÓN (F.2) — lista para correr, bloqueada por el bug

- Runner: `tests/rag_evaluation/run_eval.py` (25 consultas, guarda JSON en `tests/rag_evaluation/results/`)
- Set de casos: `tests/rag_evaluation/test_cases.py` (15 doradas + 10 adversariales) ✅
- Autenticación automatizada: **JWT self-signed de `rag-backend-sa`** vía `gcloud iam service-accounts sign-jwt` con:
  - `aud` = **URL exacta con path**: `https://rag-chat-service-7od5boefba-uc.a.run.app/chat` (¡con `/chat`! El aud raíz o `/*` da 401 "Audience specified does not match requested endpoint")
- Precondiciones IAM ya aplicadas: `roles/iam.serviceAccountTokenCreator` (Diego→SA), `roles/iap.httpsResourceAccessor` (SA→IAP), SA en `ALLOWED_EMAILS` del código

**Después del fix del §1:** ejecutar `python tests/rag_evaluation/run_eval.py` y analizar métricas (citas 100%, rechazo adversarial 100%, exactitud numérica ≥90%).

---

## 5. Cambios de código ya hechos en esta sesión (en el commit local, sin push)

- `src/rag_agent/main.py`:
  - `firestore.Client(database="rag-memory")` (antes default → 404)
  - `GOLD_DATASET` default corregido: `"youtube_gold"` → `"gold"`
  - Pasa `GCP_REGION` a `build_agent_pipeline`
- `src/rag_agent/agents/orchestrator.py`: `Gemini(model=..., client_kwargs={"vertexai": True, "project": ..., "location": ...})` — **clave**: sin `vertexai=True` ADK usa la API de Gemini y falla con "No API key was provided"; con `project/location` pero sin `vertexai=True` falla con "Gemini API does not support project/location"
- `src/rag_agent/middleware/auth.py`: SA de evaluación agregada a `ALLOWED_EMAILS`
- `tests/test_rag_auth.py`: test actualizado a 4 emails
- `infra/fase2/firestore.tf`: 3 índices compuestos + fix `messages` (expires_at **ASCENDING** — el DESC que puse al inicio no lo aceptó Firestore)
- `infra/fase2/cloud_run.tf`: `ingress = "INGRESS_TRAFFIC_ALL"` + `iap_enabled = true` (el `INTERNAL_LOAD_BALANCER` original rompía IAP con 404)
- `infra/fase2/iap.tf`: resource correcto `google_iap_web_cloud_run_service_iam_binding` (el `google_iap_web_backend_service_iam_binding` es para LB y daba 404) + SA en members
- `infra/fase2/iam.tf`: `diego_token_creator`
- `Dockerfile.rag`: `COPY src/ ./src/` (antes solo `src/rag_agent/` → hatchling fallaba)
- Nuevo: `cloudbuild.rag.yaml`, `infra/fase2/terraform.tfvars`, `tests/rag_evaluation/run_eval.py`

**Tests:** 101/101 pasan (`--ignore=tests/test_rag_integration.py` — el de integración falla local por falta de ADC, normal).

---

## 6. Archivos temporales a limpiar (no commitear)

- `tests/rag_evaluation/_scan.py`
- `tests/rag_evaluation/_test_tool.py`
- `tests/rag_evaluation/_iam_check.py`
- Planes en `infra/fase2/`: `tfplan_indexes`, `tfplan_iap_fix`, `tfplan_eval_iam`, `tfplan_iap_sa`, `tfplan_msg_index` (y `tfplan_fase2` viejo)
- `/tmp/claim.json`, `/tmp/rag_signed.jwt`, `/tmp/rag_proxy.log` (en WSL)

---

## 7. Checklist Fase F actualizado

| Item | Estado |
|:-----|:-------|
| F.1 Build + push imagen | ✅ `7cae04b-fix4` |
| F.2 Set de evaluación | ⏳ bloqueado por bug §1 |
| F.3 Cotización + approval | ✅ |
| F.4 Deploy con IAP | ✅ revisión 00006 |
| F.5 Verificar 3 identidades | ✅ (Diego validó en navegador + rechazo 4ta) |
| F.6 Registrar en APPROVALS.md | ⏳ pendiente (3 applies + 4 deploys + brand OAuth) |
| F.7 Costo y latencia | ⏳ después de F.2 |

---

## 8. Notas de contexto para la próxima sesión

- **IAP programático con Google-managed OAuth client**: NO sirven ID tokens de gcloud ni `--audiences` con cuenta de usuario. La única vía viable es **JWT self-signed de SA** (`sign-jwt`) con `aud` = URL exacta + path.
- **`gcloud run services proxy` NO funciona con IAP** (devuelve "Invalid IAP credentials: empty token").
- **Índices Firestore**: el orden de `expires_at` importa y lo determina Firestore, no la intuición (sessions: DESC, messages: ASC, common_queries: DESC). Usar la URL que Firestore genera en el error "query requires an index".
- **La SA de evaluación consume su propia cuota** (30/día) — una corrida completa de evaluación usa 25.
- `rag-evaluation-suite` requiere omitir el caché; el endpoint `/chat` actualmente NO tiene forma de desactivarlo → si se agrega, documentar en el skill.
- El proxy de gcloud quedó instalado (`cloud-run-proxy` componente) — no molesta.
- La cuenta activa de gcloud es `diego@talamantes.com.mx`; `GOOGLE_OAUTH_ACCESS_TOKEN` se usa para Terraform (no hay ADC).
