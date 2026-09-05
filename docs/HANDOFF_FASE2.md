# Reporte de Handoff — Fase 2 (RAG Agent) · 2026-09-05 (actualizado)

**Estado:** Fase F. Los dos bloqueantes de `semantic_search` están **arreglados, aplicados y verificados en GCP**.
**Pendiente:** F.2 (evaluación de 25 preguntas), en espera — Diego prueba el servicio a mano primero.
**Sesión:** continuar desde este archivo. No re-ejecutar pasos ya completados.

---

## 0. LO PRIMERO — qué está desplegado

Verificado con `gcloud` después del apply del 2026-09-05T14:30:

| | Estado real en GCP |
|:--|:--|
| Revisión activa | `rag-chat-service-00007-874`, imagen `65036a4`, `Ready: True` |
| `roles/bigquery.connectionUser` sobre `vertex-ai-connection` | `yt-ingestion-job` **y** `rag-backend-sa` ✅ |
| Env vars del Service | `GCP_PROJECT`, `GCP_REGION`, `GOLD_DATASET` declaradas ✅ |
| `semantic_search` | funciona — verificado impersonando a `rag-backend-sa` ✅ |
| Aislamiento §8 (Bronze/Silver/DLQ) | 403 con la identidad del backend; `gold` 200 ✅ |

El apply fue `1 added, 1 changed, 0 destroyed`. Registro completo en `infra/APPROVALS.md`, entrada `2026-09-05T14:30:00-06:00`.

**Commits:** `65036a4` (los fixes) y `60f212f` (bitácora, tfvars, limpieza). Sin push todavía.

## 1. Los dos bloqueantes de `semantic_search` (causa raíz, ambos verificados)

El handoff anterior documentaba solo el primero. El segundo habría hecho fallar la herramienta igual después de arreglar el IAM, con otro mensaje de error.

### 1.1 IAM — falta `connectionUser` (403)

`ML.GENERATE_EMBEDDING` sale a Vertex AI por la conexión `vertex-ai-connection`, que es un recurso **con su propio IAM**, distinto del dataset: `roles/bigquery.dataViewer` sobre `gold` no alcanza.

Política real leída con la API:
```
roles/bigquery.connectionUser → serviceAccount:yt-ingestion-job@medallon-youtube…
```
Falta `rag-backend-sa@medallon-youtube.iam.gserviceaccount.com`.

**Fix:** `infra/fase2/bigquery_connection_iam.tf`. La conexión se referencia por su id (`var.vertex_connection_id`), nunca como `resource` — es de Fase 1 y un destroy de Fase 2 no debe poder alcanzarla. El provider no expone data source para conexiones de BigQuery, así que el acoplamiento es explícito vía variable.

> Es el mismo gap que tuvo Fase 1 (`infra/iam.tf`, APPROVALS 2026-08-02T19:04:15). Se repite porque la conexión es compartida y Fase 2 la usa sin poseerla.

### 1.2 `maximum_bytes_billed` — 10 MB rechazaba toda búsqueda semántica

`gold_rag_corpus` pesa 21,026,121 bytes y **no hay índice vectorial** (3,261 filas < las 5,000 que exige BigQuery), así que `VECTOR_SEARCH` corre exhaustivo y lee la columna `text_embedding` completa.

Medido con `bq query --dry_run` el 2026-09-05:

| Herramienta | Escaneo real | Tope |
|:--|--:|--:|
| `semantic_search` | **20,856,549 B (19.9 MB)** | 50 MB ✅ |
| `sentiment_analytics` | 79,152 B | 10 MB |
| `trend_detection` | 57,713 B | 10 MB |

Ningún `WHERE` lo arregla: los filtros se aplican **después** de `VECTOR_SEARCH`, no antes.

**Fix:** 50 MB solo en `semantic_search` (~2.4× el corpus, ~9 meses de margen al ritmo de +125 comentarios/semana). Documentado en `rag-quota-limits` y `rag-tool-semantic-search` con el criterio de reversión: cuando el corpus pase de 5,000 filas y el índice IVF sea creable, el escaneo baja y el tope debe volver a bajar.

**Cotización aprobada:** +$0.34 USD/mes (peor caso real), tope duro del guardrail $0.83/mes. Total ~$3.19–$6.69 / $20.00.

---

## 2. Tres invariantes que el código no sostenía (arreglados en `65036a4`)

### 2.1 Las citas nunca se llenaban — invariante 11 de CLAUDE.md

`main.py` las leía de `event.custom_metadata`, que ADK no puebla. `citations` siempre iba `[]` y **no existía ninguna validación**. La evaluación habría reportado 0% de citas aunque el agente respondiera bien.

**Fix:** `src/rag_agent/middleware/citations.py`. Se capturan los `function_response` reales de las herramientas durante el loop de eventos y se verifica **en código** que todo `comment_id` citado exista en esos resultados. Una cita sin evidencia degrada la respuesta (no se envía, no se cachea) y se registra en el log.

Decisión de diseño: una respuesta **sin** citas es válida — admitir ausencia de evidencia es la conducta correcta según `rag-synthesis-citations`. Lo que se bloquea es citar algo que no existe. Que falten citas donde debería haberlas es calidad, y eso lo mide `rag-evaluation-suite`.

### 2.2 La clave del caché iba sin versionar

`get_cached_response(db, query, {}, "es", "", "", "", user_id)` — tres `""` en los componentes de corpus, prompt y modelo. Todas las respuestas colapsaban en la misma clave, sin invalidación posible.

**Fix:** `src/rag_agent/versions.py`.
- `corpus_version` = `MAX(updated_at)` de `gold_rag_corpus`, memoizada 5 min (no se hardcodea: es lo que hace que un run del pipeline invalide el caché solo).
- `PROMPT_VERSION` = constante `"2026-09-05.1"`, **sube a mano en el mismo commit que toque cualquier prompt**. Es el punto frágil del mecanismo.
- Si la versión del corpus no se puede leer, devuelve `None` y el servicio **se salta el caché**, en vez de sustituir un valor fijo que serviría respuestas viejas sobre datos nuevos.

### 2.3 El Cloud Run Service no declaraba ninguna env var

Funcionaba solo porque los defaults de `main.py` coinciden con producción. **Fix:** `GCP_PROJECT`, `GOLD_DATASET` y `GCP_REGION` declaradas en `cloud_run.tf`.

---

## 3. Bitácora de aprobaciones — al día

`infra/APPROVALS.md` tiene ahora seis entradas de **registro diferido** para los 5 applies y los 4 build/deploy del 2026-09-05 que se ejecutaron con aprobación de Diego pero sin registrar. Reconstruidas desde los planes guardados y el estado real. El retraso queda anotado en las entradas como desviación de `approval-gate` paso 4.

Falta registrar el apply de `tfplan_conn_iam` cuando se ejecute.

---

## 4. Estado de los tests

**126 pasan** (`--ignore=tests/test_rag_integration.py`; el de integración falla local por falta de ADC, es lo normal). Eran 101.

Nuevos: `tests/test_rag_citations.py` (14) y `tests/test_rag_versions.py` (10), más uno de contraste de topes de bytes por herramienta.

Corregido de paso: `tests/test_rag_tools.py` importaba `MAX_BYTES_BILLED` de `semantic_search` y lo asertaba contra el `job_config` de `sentiment_analytics`. Pasaba solo porque los tres valores coincidían.

---

## 5. Verificación después del apply

**Ya ejecutada, en verde.** Se corre así — impersonando a la SA, que es lo único que prueba el fix de IAM (como owner la consulta pasa aunque el binding no exista):

```bash
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token \
    --impersonate-service-account=rag-backend-sa@medallon-youtube.iam.gserviceaccount.com)
.venv/bin/python tests/rag_evaluation/verify_semantic_search.py
```

Smoke check de los dos bloqueantes a la vez: si falta el IAM da 403, si el tope de bytes está mal da "Query exceeded limit for bytes billed". Resultado obtenido: 5 comentarios con `comment_id`, distancia y canal (Martin Garrix, ILLENIUM, Swedish House Mafia).

Falta lo que Diego va a probar a mano: una consulta real por `/chat`, para ver que las citas ahora llegan pobladas y que la validación en código no degrada respuestas legítimas.

---

## 6. Evaluación (F.2) — EN ESPERA por decisión de Diego

Diego pidió probar el servicio a mano antes de correr la evaluación. **No ejecutar `run_eval.py` sin su visto bueno.**

- Runner: `tests/rag_evaluation/run_eval.py` (25 consultas → JSON en `tests/rag_evaluation/results/`)
- Casos: `tests/rag_evaluation/test_cases.py` (15 doradas + 10 adversariales)
- Métricas objetivo: citas 100%, rechazo adversarial 100%, exactitud numérica ≥90%

**Dos cosas a resolver antes de correrla:**
1. La SA de evaluación consume su propia cuota de 30/día; una corrida usa 25. Solo cabe una corrida completa por día.
2. `rag-evaluation-suite` pide correr sin caché, y `/chat` no tiene bandera para desactivarlo. Con el caché ya versionado de verdad, la **primera** corrida del día es toda miss y sale limpia; una segunda del mismo día ya no. Si se quiere una bandera de bypass, hay que agregarla y documentarla en el skill.

---

## 7. Checklist Fase F

| Item | Estado |
|:-----|:-------|
| F.1 Build + push imagen | ✅ `65036a4` |
| F.2 Set de evaluación | ⏸️ en espera — Diego prueba a mano primero |
| F.3 Cotización + approval | ✅ |
| F.4 Deploy con IAP | ✅ revisión `00007-874` con `65036a4` |
| F.5 Verificar 3 identidades | ✅ Diego validó en navegador + rechazo de una 4ta |
| F.6 Registrar en APPROVALS.md | ✅ al día |
| F.7 Costo y latencia | ⏳ después de F.2 |

---

## 8. Notas de contexto que siguen vigentes

- **IAP programático con cliente OAuth administrado por Google:** no sirven ID tokens de gcloud ni `--audiences` con cuenta de usuario. La única vía es **JWT self-signed de SA** (`gcloud iam service-accounts sign-jwt`) con `aud` = URL exacta **con path**: `https://rag-chat-service-7od5boefba-uc.a.run.app/chat`. El aud raíz o `/*` da 401 "Audience specified does not match requested endpoint".
- **`gcloud run services proxy` NO funciona con IAP** ("Invalid IAP credentials: empty token").
- **Índices Firestore:** el orden de `expires_at` lo determina Firestore según la consulta, no la simetría entre índices (`sessions` DESC, `messages` ASC, `common_queries` DESC). La fuente correcta es siempre la URL que Firestore devuelve en el error "query requires an index".
- **Gemini vía ADK:** `client_kwargs={"vertexai": True, "project": …, "location": …}`. Sin `vertexai=True` usa AI Studio y pide API key; con project/location pero sin la bandera, falla con "Gemini API does not support project/location".
- **No hay ADC en el entorno.** Terraform y los scripts usan `GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)`. Cuenta activa: `diego@talamantes.com.mx`.
- **`gcloud builds submit` y otros comandos mutantes están bloqueados para el agente** por el clasificador de auto mode. Los ejecuta Diego con el prefijo `!` en el chat.
- El proxy de gcloud quedó instalado (componente `cloud-run-proxy`) — no molesta.

---

## 9. Limpieza — hecha

- Borrados: `tests/rag_evaluation/_scan.py`, `_iam_check.py` (diagnósticos de un solo uso, obsoletos tras el fix).
- `_test_tool.py` → `tests/rag_evaluation/verify_semantic_search.py` (§5).
- Borrados los planes viejos de `infra/fase2/`: `tfplan_fase2`, `tfplan_indexes`, `tfplan_iap_fix`, `tfplan_eval_iam`, `tfplan_iap_sa`, `tfplan_msg_index`. Queda solo `tfplan_conn_iam`, que es el pendiente de aplicar.
- Temporales en WSL (`/tmp/claim.json`, `/tmp/rag_signed.jwt`, `/tmp/rag_proxy.log`): sin tocar, se pueden borrar cuando quieras.
