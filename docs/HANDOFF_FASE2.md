# Handoff — Fase 2 (RAG Agent) · 2026-09-05

**Estado:** el agente está **desplegado, funcionando y probado a mano**. Revisión `rag-chat-service-00011-clx`, imagen `655492d`.
**Siguiente paso recomendado:** F.2, la evaluación de 25 preguntas. Es lo único que mide la calidad de forma sistemática en vez de por capturas sueltas.
**Sesión:** continuar desde aquí. No re-ejecutar lo que ya está hecho.

---

## 0. Estado real en GCP

Verificado con `gcloud` y `bq` al cierre de la sesión:

| | |
|:--|:--|
| Revisión activa | `rag-chat-service-00011-clx`, imagen `655492d`, `Ready: True` |
| URL | `https://rag-chat-service-7od5boefba-uc.a.run.app` |
| Corpus | **3,278 comentarios, 7 canales** (creció durante la sesión: el pipeline corrió) |
| IAP | 3 identidades humanas + la SA de evaluación |
| Cuota | Diego **sin tope**; el resto en 30/día; circuito agregado en 300/día |
| Tests | **219 pasan** (`--ignore=tests/test_rag_integration.py`) |
| `PROMPT_VERSION` | `2026-09-05.5` |
| Costo estimado | ~$3.19 – $6.69 / $20.00 (delta Fase 2: $1.34 – $4.84 / $5.00) |

**Cinco despliegues hoy**, todos registrados en `infra/APPROVALS.md` con plan, cotización y verificación:

| Revisión | Imagen | Qué entró |
|:--|:--|:--|
| `00007-874` | `65036a4` | IAM de la conexión Vertex + tope de bytes → `semantic_search` funciona |
| `00008-ggx` | `33c819c` | Bienvenida, cerrar sesión, citas como objetos |
| `00009-8mc` | `97f48bb` | Topología real, `max_output_tokens`, memoria conectada, cuota sin tope |
| `00010-s9k` | `5b43a82` | Síntesis recibe datos, umbral de relevancia, evidencia, caché |
| `00011-clx` | `655492d` | Validación numérica en código, regresión del umbral, logging |

---

## 1. LO PRIMERO PARA LA PRÓXIMA SESIÓN — el invariante que sigue sin cumplirse

**Las respuestas con datos no llevan cita.** El invariante 11 de `CLAUDE.md` no se cumple.

Verificado tras el último deploy: preguntar "¿Qué opinan de los drops de Martin Garrix?" devuelve **diez comentarios reales, transcritos textualmente y sin inventar nada** — pero sin el `[comment_id · "título" · canal · fecha]` que el formato exige. `citations` llega vacío a la UI y el panel "Fuentes" no muestra nada.

`validate_citations` **no lo atrapa por diseño**: verifica que ninguna cita sea inventada, no que existan citas. Una respuesta sin citas es legítima cuando no hay datos, y bloquear por ausencia degradaría precisamente esas.

**Regla candidata, ya acotada:** si `semantic_search` devolvió filas y la respuesta no cita ningún `comment_id`, es una violación → degradar.

**Medir antes de activar.** Hoy, dos veces, "arreglar" sin medir produjo el problema opuesto (ver §3). Correr primero la evaluación con la regla en modo observación —registrar cuántas respuestas la violarían— y activarla cuando se sepa el número.

---

## 2. Lo que se arregló hoy, y por qué importa cada cosa

### 2.1 Los dos bloqueantes de `semantic_search`

1. **IAM.** `ML.GENERATE_EMBEDDING` sale a Vertex por la conexión `vertex-ai-connection`, que tiene IAM propio: `dataViewer` sobre `gold` no alcanza. Faltaba `roles/bigquery.connectionUser` para `rag-backend-sa`. Mismo gap que tuvo Fase 1; se repite porque la conexión es compartida y Fase 2 la usa sin poseerla.
2. **Tope de bytes.** `VECTOR_SEARCH` exhaustivo (el corpus está por debajo de las 5,000 filas que exige un índice IVF) lee la columna `text_embedding` completa: **20,856,549 bytes** medidos. El tope de 10 MB rechazaba toda consulta semántica. Subido a **50 MB solo en esa herramienta**.

### 2.2 La topología estaba documentada pero no implementada

`orchestrator.py` importaba `ParallelAgent` y `SequentialAgent` y **no usaba ninguno**. El router tenía tres `AgentTool` sueltos y nada garantizaba que la síntesis corriera: podía responder él y saltarse citación y tope de tokens. Es la explicación de que el agente se sintiera "atontado" — no era el modelo, era el paso donde vivía la redacción.

Un diagrama no falla cuando el código deja de corresponderle. Por eso ahora hay `tests/test_rag_topology.py`.

### 2.3 La síntesis nunca recibía los datos

`SYNTHESIS_INSTRUCTION` nombraba `search_result` y `analytics_result` como **palabras sueltas**, sin las llaves que ADK necesita para sustituir estado. La síntesis redactaba a partir de la prosa del router, no de las filas.

Evidencia: las 20 respuestas en `response_cache` tenían `citations: []`. Los tres síntomas visibles —cero citas, nombres de agentes filtrándose al usuario, plantilla de formato emitida literal— salían de esa única causa.

> **Trampa relacionada:** `LlmAgent.canonical_instruction` devuelve `bypass_state_injection=True` cuando la instrucción es un callable. El helper `with_context` (que inyecta la fecha) convertía instrucciones en callables y **desactivaba la sustitución de llaves**. No rompía nada aún, pero habría hecho fallar este mismo arreglo en silencio. Ahora llama a `inject_session_state` explícitamente.

### 2.4 El agente pedía fechas en formato AAAA-MM-DD

Un LLM no tiene reloj: sin la fecha de hoy en el prompt, "el último mes" es irresoluble y preguntar era su única salida correcta. `rag_agent/agents/context.py` inyecta **por request** la fecha, los periodos relativos resueltos, la cobertura real de los datos y los nombres exactos de los canales.

Por request y no al construir el pipeline: una instancia de Cloud Run vive días, y una fecha horneada al arranque estaría mal al día siguiente — en silencio y de forma plausible.

Además, `analytics_agent` tenía escrito *"si el usuario no especifica canal o periodo, NO asumas — devuelve un error"*. Eso convierte cada pregunta natural en un formulario. La regla nueva: **una pregunta sin fechas no está incompleta, significa "sobre todo lo que haya"**.

### 2.5 Una de las cinco plantillas era inalcanzable

`compare_channels` filtra con `WHERE channel_name IN UNNEST(@channels)` y el wrapper de ADK **no exponía `channels`**. Siempre llegaba `[]`: `status: "success"`, `count: 0`, cero filas, sin fallar nunca. Era la plantilla que responde la pregunta de ejemplo de la propia bienvenida.

Hay un test que recorre las cinco plantillas buscando `@parametros` y exige que existan en el wrapper.

### 2.6 Umbral de relevancia — la mejor palanca de calidad con poco corpus

`VECTOR_SEARCH` **siempre** devuelve `top_k`, tenga o no que ver. Preguntar por un DJ ausente devolvía cinco comentarios de otro y el modelo tenía que rescatar una recuperación mala. Calibrado con seis consultas reales:

| Consulta | Naturaleza | Distancias |
| :--- | :--- | ---: |
| "el mejor set en vivo" | en corpus | 0.178 – 0.307 |
| "drops de Martin Garrix" | en corpus | 0.224 – 0.280 |
| "los sets de Tiesto" | DJ ausente | 0.379 – 0.411 |
| "recetas de cocina italiana" | fuera de dominio | 0.422 – 0.553 |
| "cómo declarar impuestos" | fuera de dominio | 0.509 – 0.575 |

Hueco limpio entre 0.31 y 0.38 → corte en **0.35** (`SEARCH_MAX_DISTANCE`).

**Con poco corpus, la mayoría de las malas respuestas no vienen de que el modelo alucine: vienen de entregarle basura y pedirle que la resuma.**

### 2.7 Evidencia, caché y aviso de MVP

- **`evidence_level` en `sentiment_analytics`**, con la escala compartida de `trend_detection` (30/100). **La marca la muestra más pequeña:** Martin Garrix (1,872) vs Zedd (6) da `insufficient` aunque un lado sea abundantísimo.
- **No se cachea lo que la evidencia no sostiene** (`insufficient`, `weak`, errores). La versión del corpus no cubre esto: una conclusión de seis comentarios era frágil desde el principio, y congelarla siete días la vuelve la respuesta permanente.
- **Aviso de cobertura en la bienvenida**, generado del corpus: cuánto hay, de qué sobra y de qué falta. El corte entre "bastante" y "poco" es el mismo `WEAK_BELOW` que usan las herramientas, para que bienvenida y respuestas nunca se contradigan.

### 2.8 Memoria conectada

`record_query()` se llamaba en cada consulta y `get_common_queries()` no la llamaba nadie; `preferences.py` estaba completo sin un solo importador. El agente respondía, con razón, que no podía recordar nada.

`memory_agent` nuevo, solo lectura. El `user_id` sale de `tool_context.user_id` **en tiempo de ejecución**: capturarlo en el closure al construir el pipeline habría servido la memoria de un usuario a otro. Verificado en uso real: contó repeticiones y agregó por DJ correctamente.

---

## 3. Dos lecciones que costaron un deploy cada una

**Un número concreto en un prompt es una sugerencia de qué escribir.** El modelo emitía el molde literal `(canal, periodo, n=X filas)`. Se "corrigió" con un ejemplo realista, `n=1869`. Entonces reportó **"ILLENIUM (n=1869)"** con ILLENIUM en 292 comentarios — y la respuesta salió convincente, con su advertencia sobre disparidad de muestras incluida. Pasó de escribir algo obviamente incompleto a escribir cifras falsas con aire de dato.

El prompt ahora usa marcadores sin rellenar, nombra los **dos errores opuestos**, y no contiene ninguna cifra de 3+ dígitos salvo el tope de tokens — con un test que lo verifica. Y lo que de verdad lo impide es `validate_numeric_claims`, no ninguna frase.

**Recortar una consulta empeora una búsqueda vectorial, no la enfoca.** El umbral de 0.35 rompió una pregunta que antes funcionaba, porque `search_agent` tenía instrucción de "extraer términos clave" y mandaba `"drops"` en lugar de la frase: 0.343–0.514 contra 0.224–0.292. Pensamiento de buscador por palabras aplicado a embeddings. La instrucción ahora exige la pregunta completa y **lleva la medición dentro**, para que no se revierta por intuición.

El patrón común: **arreglar sin medir produce el problema opuesto.** Aplica directo al pendiente de §1.

---

## 4. Guardrails de costo — leer antes de tocar

- **Diego sin tope diario** (`QUOTA_OVERRIDES="diego@talamantes.com.mx=0"`). El resto en 30.
- **Circuito agregado en 300/día** (`GLOBAL_DAILY_LIMIT`), evaluado **antes** que la cuota por usuario. Nunca se había implementado pese a estar en el skill; con una identidad sin tope es lo único que queda entre un bucle y la factura.
- Ambos en `cloud_run.tf`, **no en Firestore**: así aparecen en el `plan`, pasan por `approval-gate` y quedan en la bitácora.
- **Sin tope no es sin medición:** el contador sigue incrementando.
- Un override ilegible (`=muchas`) cae al límite normal, nunca a "sin tope".

**Lo que el circuito acota y lo que no:** un día completo contra el tope de 300 cuesta ~$0.50. Protege contra un día malo. **No** protege contra 300 diarias sostenidas un mes (~$15, rompe el techo). Es un cortacircuitos, no un presupuesto.

Estado al cierre: `_global:2026-09-05` en 17; una identidad en **28 de 30** (se reinicia mañana en hora de CDMX).

---

## 5. Evaluación (F.2) — pendiente, y es lo siguiente

- Runner: `tests/rag_evaluation/run_eval.py` (25 consultas → JSON en `results/`)
- Casos: `tests/rag_evaluation/test_cases.py` (15 doradas + 10 adversariales)
- Métricas objetivo: citas 100%, rechazo adversarial 100%, exactitud numérica ≥90%

**Dos cosas antes de correrla:**
1. La SA de evaluación consume su propia cuota de 30/día; una corrida usa 25. Cabe una corrida completa por día.
2. `rag-evaluation-suite` pide correr sin caché y `/chat` no tiene bandera de bypass. Con el caché versionado, la **primera** corrida del día sale limpia; una segunda del mismo día no.

**Predicción honesta:** la métrica de citas va a salir cerca de 0% por §1. No es un fallo de la evaluación, es el estado real.

---

## 6. Verificaciones que se pueden repetir

```bash
# Smoke check de semantic_search, impersonando la SA — como owner no prueba el IAM
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token \
    --impersonate-service-account=rag-backend-sa@medallon-youtube.iam.gserviceaccount.com)
.venv/bin/python tests/rag_evaluation/verify_semantic_search.py

# Aislamiento §8: gold debe dar 200; bronze, silver y la DLQ, 403
# (ver el bucle en la entrada 2026-09-05T14:30 de infra/APPROVALS.md)
```

---

## 7. Pendientes, en el orden sugerido

1. **Citas ausentes** (§1) — invariante del PRD sin cumplir. Medir, luego activar.
2. **F.2, la evaluación** (§5) — mide todo lo demás de forma sistemática.
3. **El historial reusa siempre la misma sesión.** `get_recent_sessions(..., limit=1)` toma la más reciente y nunca crea una nueva: conversaciones de temas distintos se contaminan entre sí en los últimos 6 mensajes que se inyectan al modelo.
4. **Escritura de preferencias** con el flujo de confirmación de `rag-memory-preferences`. Hoy la memoria es solo lectura.
5. **Métricas inventadas de raíz** (tipo "puntuación de sentimiento de 0.76" en una herramienta que solo devuelve distribuciones). Solo el prompt lo cubre; `validate_numeric_claims` no puede verlo.
6. **`ADK 2.8.0` deprecó `SequentialAgent` y `ParallelAgent`** en favor de `Workflow`. **No migrar todavía:** el aviso dice que *"Workflow cannot yet be used as an LlmAgent sub-agent"*, que es exactamente este caso.

---

## 8. Notas de entorno que siguen vigentes

- **No hay ADC.** Terraform y los scripts usan `GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)`. Un `terraform apply` sin esa variable falla con "could not find default credentials".
- **`gcloud builds submit` está bloqueado para el agente** por el clasificador de auto mode; lo ejecuta Diego con `!`. El `terraform apply` a veces también.
- **IAP programático:** solo funciona con **JWT self-signed de SA** (`gcloud iam service-accounts sign-jwt`) con `aud` = URL exacta **con path** (`.../chat`, `.../welcome`). El aud raíz da 401. `gcloud run services proxy` NO funciona con IAP.
- **Cerrar sesión** (`/?gcp-iap-mode=CLEAR_LOGIN_COOKIE`) borra la cookie de IAP pero **no** la sesión de Google: al volver puede reautenticar en silencio. Es correcto aunque parezca que no funcionó.
- **Índices Firestore:** el orden de `expires_at` lo determina Firestore según la consulta (`sessions` DESC, `messages` ASC, `common_queries` DESC). Usar la URL que Firestore devuelve en el error.
- **Gemini vía ADK:** `client_kwargs={"vertexai": True, "project": …, "location": …}`. Sin la bandera usa AI Studio y pide API key.
- **Modelos:** Fase 1 y Fase 2 usan el mismo `gemini-2.5-flash`, pero por caminos distintos (BigQuery vs Vertex directo) y declarados en lugares distintos (`infra/bigquery.tf` vs `orchestrator.py`). **Nada los mantiene sincronizados**: hoy coinciden por decisión, no por construcción.
- **Embeddings:** `text-embedding-004`, el mismo del corpus. Cambiarlo obliga a regenerar `gold_rag_corpus` completo **y a recalibrar el umbral de §2.6** — las distancias no son comparables entre modelos.
