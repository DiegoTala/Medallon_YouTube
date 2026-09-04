# Brainstorming — Sistema agéntico conversacional (RAG sobre Gold layer)

> **Estado:** fase de brainstorming. Este documento NO es especificación aprobada ni
> implica ningún cambio de infraestructura. Sirve para discutir el diseño antes de
> comprometerse con nada.
>
> Fecha: 2026-09-03 (expandido: 2026-09-03)

## Objetivo

Llevar **YouTube DJ Analytics** al siguiente nivel: diseñar un sistema agéntico
conversacional sobre un framework (preferentemente de Google) para implementar un
**RAG con memoria y autenticación simple**, usando la **Gold layer como base de
conocimiento**.

---

## 0. La tesis de valor

El pipeline actual ya responde **"¿qué pasó?"** (datos). El agente debe responder
**"¿qué hago con esto?"** (decisiones). Ese salto de datos → decisiones es donde
vive el valor real.

---

## 1. La restricción que manda: el techo de $15/mes

Antes de diseñar nada, esto define casi todas las decisiones:

- **Vertex AI Vector Search (endpoint dedicado) = ~$700-800/mes.** Queda descartado
  por completo. La recuperación semántica **se queda en BigQuery `VECTOR_SEARCH`**
  sobre el índice IVF que ya existe en `gold_youtube_embeddings`. Cero infraestructura
  nueva, cero costo fijo.
- **Vertex AI RAG Engine** (el servicio "managed RAG") usa Spanner como backend de
  indexado → costo fijo mensual. También descartado. El RAG propio ya lo dan las
  capas medallón; no hace falta que Google lo re-implemente.
- **Agent Engine** (runtime gestionado para ADK) cobra por vCPU/memoria-hora del
  runtime. Para una demo de bajo volumen probablemente entra, pero **Cloud Run
  Service con scale-to-zero es más barato y encaja con el patrón actual** (ya se
  usan Cloud Run Jobs + Terraform).

**Conclusión:** el "framework de Google" que conviene es **ADK (Agent Development
Kit)** como librería, desplegado en **Cloud Run**, no el stack managed de Agent
Builder.

---

## 2. Propuesta de valor — Casos de uso

### 2.1 Para DJs / Managers de DJs

| Caso de uso | Pregunta que el agente responde | Valor |
|:---|:---|:---|
| **Monitor de reacción en vivo** | "¿Cómo reaccionó la gente cuando estrené este ID en Tomorrowland?" | Feedback inmediato post-set sin encuestas |
| **Benchmark competitivo** | "¿De qué se queja la gente de los sets de Martin Garrix vs los míos?" | Inteligencia competitiva sin contratar analistas |
| **Descubrimiento de oportunidades** | "¿Qué temas piden más que yo nunca he tocado?" | Detección de demanda no cubierta |
| **Gestión de crisis** | "¿Hay algún sentimiento negativo inusual esta semana?" | Alerta temprana de PR |
| **Content planning** | "¿Qué videos míos tienen mejor engagement y por qué?" | Decidir qué contenido producir |

### 2.2 Para Promoters / Festivales

| Caso de uso | Pregunta | Valor |
|:---|:---|:---|
| **Booking intelligence** | "¿Qué DJs tienen mejor sentimiento en comentarios de sets similares al que quiero?" | Data-driven booking |
| **Post-evento análisis** | "¿Qué dijo la gente del lineup del festival X?" | Mejorar siguiente edición |

### 2.3 Modelo de negocio potencial (si escalara)

- **SaaS freemium:** 5 queries/mes gratis, $9.99/mes ilimitado
- **API para integraciones:** Bots de Discord/Telegram que consultan el agente
- **Reportes automáticos:** Digest semanal por email generado por el agente

---

## 3. Arquitectura propuesta

```
                         ┌─────────────────────────────────────────────┐
                         │            Cloud Run Service                │
                         │         (ADK Agent + FastAPI)               │
                         │                                             │
  Usuario ──→ IAP ──→   │  ┌─────────┐   ┌──────────┐   ┌─────────┐ │
                         │  │ Router  │──→│  Agent   │──→│ Tools   │ │
                         │  │ (auth)  │   │ (Gemini) │   │ (3-5)   │ │
                         │  └─────────┘   └────┬─────┘   └────┬────┘ │
                         │                     │              │      │
                         │              ┌──────┴──────┐       │      │
                         │              │   Memory    │       │      │
                         │              │  (Firestore)│       │      │
                         │              └─────────────┘       │      │
                         └────────────────────────────────────┼──────┘
                                                              │
                         ┌────────────────────────────────────┼──────┐
                         │            BigQuery                 │      │
                         │  ┌──────────┐ ┌──────────┐ ┌──────┴───┐  │
                         │  │gold_     │ │gold_     │ │silver_   │  │
                         │  │rag_corpus│ │sentiment │ │videos    │  │
                         │  │(embeddings+metadata)│ │          │  │
                         │  └──────────┘ └──────────┘ └──────────┘  │
                         └───────────────────────────────────────────┘
```

El agente es un **orquestador que decide qué herramienta usar**; ahí está lo
"agéntico":

- Pregunta semántica ("¿de qué se queja la gente del audio en los sets de X?") →
  `semantic_search`
- Pregunta analítica ("dame el desglose de sentimiento del canal X en agosto") →
  `sentiment_analytics` (query parametrizada, **no** text-to-SQL libre al inicio)
- Pregunta híbrida → el agente encadena ambas y Gemini sintetiza

---

## 4. Herramientas del agente (Tools)

### Tool 1: `semantic_search` (ya existe la lógica)

- RAG puro: embed la query del usuario → VECTOR_SEARCH en BigQuery
- Pre-filtros opcionales: `channel_name`, `date_range`, `sentiment_label`
- Devuelve top-k comentarios con metadata (video, canal, sentimiento, fecha)
- **Guardrail:** `maximum_bytes_billed=10MB`, `top_k <= 20`

### Tool 2: `sentiment_analytics` (nuevo)

- Queries parametrizadas sobre `gold_sentiment_analysis` JOIN `silver_youtube_videos`
- Ejemplos: distribución de sentimiento por canal, tendencia temporal, comparación entre canales
- **No es text-to-SQL** — son templates con parámetros validados
- **Guardrail:** solo queries pre-aprobadas, sin acceso a tablas raw

### Tool 3: `video_context` (nuevo)

- Dado un `video_id`, devuelve metadata completa + top 5 comentarios más positivos y más negativos
- Útil para preguntas como "¿qué opinan de este track específico?"
- También: lista de videos recientes de un canal con stats

### Tool 4: `trend_detection` (nuevo, fase 2)

- Compara distribución de sentimiento entre dos períodos
- Detecta cambios significativos (ej: "esta semana hubo 3x más negatividad que el promedio")
- Usa BigQuery con window functions

### Tool 5: `recommendation` (nuevo, fase 3)

- "Dado este comentario, ¿qué otros comentarios/videos son similares?"
- Combina VECTOR_SEARCH con filtros de sentimiento
- Útil para explorar temas relacionados

---

## 5. Preparar la Gold layer para RAG

Los "documentos" hoy son comentarios sueltos (texto corto, ideal para embeddings,
no requieren chunking). Conviene enriquecerlos en tres niveles:

### a) Vista denormalizada `gold_rag_corpus` (inmediato)

Una unidad de recuperación con metadata rica para filtrar:

```sql
-- gold_rag_corpus: vista denormalizada
SELECT
    c.comment_id,
    c.comment_text,
    e.text_embedding,
    s.sentiment_label,
    v.video_id,
    v.title AS video_title,
    v.channel_name,
    v.published_at AS video_published_at,
    c.published_at AS comment_published_at,
    c.like_count
FROM silver_youtube_comments c
JOIN silver_youtube_videos v ON c.video_id = v.video_id
JOIN gold_sentiment_analysis s ON c.comment_id = s.comment_id
JOIN gold_youtube_embeddings e ON c.comment_id = e.comment_id
```

Así el `VECTOR_SEARCH` puede pre-filtrar por canal/fecha/idioma antes de rankear.

### b) Documentos sintéticos de nivel superior (fase posterior, opcional)

- **Video digest:** Resumen generado por Gemini del sentimiento general + top temas de un video
- **Channel digest:** Resumen mensual por canal con tendencias
- **Theme clusters:** Agrupar comentarios por tema (audio quality, track selection, crowd energy) usando embeddings + clustering

Generados incrementalmente con la misma disciplina Gold
(`LEFT JOIN ... WHERE NULL`). Mejoran el recall en preguntas de "panorama general",
donde recuperar 10 comentarios sueltos se queda corto.

### c) Multi-modal (visión futura)

- Embeddings de thumbnails de videos (si se quiere buscar por estética visual)
- Transcripciones de sets (si se extraen con Speech-to-Text)

### d) Multilingüe

`text-embedding-004` maneja varios idiomas razonablemente; guardar `lang` en
metadata para que el agente pueda responder "solo comentarios en español".

---

## 6. Memoria

Tres niveles:

| Nivel | Qué guarda | Opción recomendada |
|:---|:---|:---|
| **Corto plazo (sesión)** | Historial del hilo actual | `DatabaseSessionService` de ADK sobre Firestore |
| **Largo plazo** | Preferencias del usuario ("me interesa el canal X", "siempre en español"), consultas frecuentes | **Firestore DIY** (casi gratis a esta escala) |
| **Semántica (avanzado)** | Embeddings de queries previas para cache y detección de consultas similares | Firestore + VECTOR_SEARCH (fase posterior) |

### Esquema de Firestore

```
firestore/
├── users/{user_id}
│   ├── preferences: {
│   │     "favorite_channels": ["Martin Garrix", "Avicii"],
│   │     "language": "es",
│   │     "interests": ["track IDs", "crowd reactions"]
│   │   }
│   └── sessions/{session_id}
│       ├── created_at
│       ├── last_active
│       └── messages: [
│             {"role": "user", "content": "..."},
│             {"role": "agent", "content": "...", "tools_used": [...]}
│           ]
```

### Memoria semántica (avanzado, fase posterior)

- Embeddings de las queries del usuario para detectar consultas similares
- Cache semántica: si un usuario pregunta algo similar a otra query previa, reutilizar respuesta
- Reduce costo de Gemini y latencia para queries repetidas

### Sobre Memory Bank

Memory Bank es elegante (usa Gemini para extraer hechos del historial de forma
asíncrona) pero: está en preview, añade llamadas a Gemini por sesión, y ata más al
stack managed. Para empezar, **Firestore con un esquema simple de
`user_preferences` + `conversation_summaries`** es suficiente y trivial de versionar
en Terraform. Se puede migrar a Memory Bank después si la extracción automática de
preferencias vale la pena.

---

## 7. Autenticación simple

### Implementación con IAP (recomendado para uso interno)

```
Usuario → IAP (Google Identity) → Cloud Run Service
                │
                ├── JWT token en header X-Goog-IAP-JWT-Assertion
                │
                └── FastAPI middleware:
                    ├── Valida JWT
                    ├── Extrae user_id (sub claim)
                    ├── Crea/recupera sesión de Firestore
                    └── Pasa al agente
```

**Ventajas de IAP:**
- Cero código de auth — Google maneja login, MFA, etc.
- Se configura 100% en Terraform
- Perfecto para uso interno/equipo
- Gratis

Según audiencia (pendiente de confirmar):

- **Solo yo / equipo interno:** Cloud Run + **IAP (Identity-Aware Proxy)**. Cero
  código de auth, identidad Google, se configura por Terraform. La opción más simple.
- **UI web para usuarios no-Google:** **Firebase Authentication** (email/password o
  Google sign-in), tier gratuito muy amplio, se verifica el ID token en un middleware
  de FastAPI.
- **Solo API / demo rápida:** API key en Secret Manager + middleware. Lo más básico,
  menos seguro.

Recomendación: **IAP** si es interno; **Firebase Auth** si habrá usuarios externos.

---

## 8. Guardrails del agente (críticos por costo y seguridad)

### Económicos

- Service account de BigQuery **solo lectura**, con allowlist de tablas (`gold_*`,
  `silver_youtube_videos`).
- `maximum_bytes_billed` en cada query (las tablas Gold son de MBs; cualquier query
  que escanee GBs es un bug).
- Límite de filas devueltas por herramienta (p.ej. top 20).
- Rate limiting: 20 queries/minuto por usuario.
- Token budget: máximo 4000 tokens de output por respuesta.
- Cache de respuestas frecuentes (reduce llamadas a Gemini).

### De seguridad

- Sin text-to-SQL libre en v1 — herramientas con queries parametrizadas. El
  text-to-SQL abierto se añade después con más validación.
- Sin acceso a `silver_dead_letter_queue` (datos sensibles de debugging).
- Sanitización de inputs del usuario.

### De calidad

- **Citas obligatorias:** cada respuesta cita `comment_id` / link al video. Es un
  proyecto de analítica; la trazabilidad es el punto.
- Confidence scoring: si el agente no encuentra info relevante, lo dice explícitamente.
- Set de evaluación: 15-20 preguntas doradas con respuestas esperadas, usando el
  framework de eval de ADK.

---

## 9. Costo estimado (orden de magnitud, volumen bajo)

| Componente | Costo/mes |
| :--- | :--- |
| Cloud Run Service (scale-to-zero, uso esporádico) | ~$0-1 |
| BigQuery `VECTOR_SEARCH` + queries analíticas (tablas pequeñas) | < $0.50 |
| Gemini 2.5 Flash (generación por turno, ~cientos de turnos/mes) | ~$0.50-2 |
| `text-embedding-004` para embeber la query del usuario | centavos |
| Firestore (memoria, escala mínima) | ~$0 (tier gratuito) |
| IAP | gratis |
| **Total incremental** | **~$2-4/mes** |

Entra holgado en el techo. El único riesgo real es dejar un endpoint de Vector
Search encendido o un bug de query sin `maximum_bytes_billed`.

---

## 10. Roadmap incremental

| Fase | Qué se hace | Valor inmediato | Costo incremental |
|:---|:---|:---|:---|
| **Fase 0** | Vista `gold_rag_corpus` + SA read-only + guardrails de bytes | Base para todo | ~$0 |
| **Fase 1** | Agente ADK con 1 tool (`semantic_search`), local con `adk web` | Validar calidad de RAG | ~$0 |
| **Fase 2** | + `sentiment_analytics` + memoria de sesión (Firestore) | El agente ya es útil | ~$1-2/mes |
| **Fase 3** | Deploy a Cloud Run + IAP + Terraform | Accesible para el equipo | ~$1-2/mes |
| **Fase 4** | + `video_context` + `trend_detection` + memoria largo plazo | Inteligencia proactiva | ~$1/mes |
| **Fase 5** | + Multi-agente + feedback loop + eval set | Calidad de producción | ~$1/mes |
| **Fase 6** | + Documentos sintéticos (digests) + semantic cache + `recommendation` | Escalabilidad | ~$1/mes |

**Costo total estimado al final: ~$5-8/mes** (dentro del techo de $15)

### Detalle por fase

- **Fase 0** — Vista `gold_rag_corpus`, service account read-only, guardrails de
  bytes. (Terraform → approval-gate)
- **Fase 1** — Agente ADK de un solo tool (`semantic_search`), corriendo local con
  `adk web`. Sin memoria, sin auth. Validar calidad de recuperación.
- **Fase 2** — Segundo tool (`sentiment_analytics` parametrizado) + memoria de
  sesión en Firestore.
- **Fase 3** — Deploy a Cloud Run detrás de IAP, todo en Terraform. Nueva skill
  `agent-conversational-rag` + actualizar `docs/PRD.md`.
- **Fase 4** — Tercer y cuarto tool (`video_context`, `trend_detection`) + memoria
  de largo plazo (preferencias de usuario).
- **Fase 5** — Arquitectura multi-agente (Router → Search Agent, Analytics Agent,
  Summary Agent) + feedback loop (👍/👎 en Firestore) + eval set de 20 preguntas
  doradas.
- **Fase 6** — Documentos sintéticos (video digests, channel digests), semantic
  cache para reducir costo de Gemini, tool `recommendation`.

---

## 11. Técnicas avanzadas (diferenciadores)

### 11.1 Multi-Agent Architecture (ADK)

En vez de un solo agente, usar el patrón de multi-agente de ADK:

```
Root Agent (Router)
├── Search Agent (RAG specialist)
│   └── Tools: semantic_search, video_context
├── Analytics Agent (SQL specialist)
│   └── Tools: sentiment_analytics, trend_detection
└── Summary Agent (Synthesis specialist)
    └── Tools: none (solo genera texto con contexto de los otros)
```

**Ventaja:** cada agente tiene un system prompt especializado, mejores resultados.

### 11.2 Proactive Intelligence (Agent Callbacks)

El agente no solo responde — también proactivamente:

- **Post-pipeline callback:** Después de cada ejecución semanal del pipeline, el
  agente genera un "digest inteligente" y lo guarda en Firestore.
- **Alertas automáticas:** Si el sentimiento de un canal cambia >20% vs semana
  anterior, notificar.
- **Sugerencias no pedidas:** "Noté que los comentarios sobre audio quality
  aumentaron 40% este mes en tu canal."

### 11.3 Conversational Analytics Dashboard

El agente como frontend de un dashboard:

```
Usuario: "Dame un resumen de esta semana"
Agente: [ejecuta sentiment_analytics + trend_detection]
        "Esta semana: 347 nuevos comentarios.
         Sentimiento: 85% positivo (↑3% vs semana pasada).
         Tema trending: 'track IDs' apareció en 23% de comentarios.
         Top comentario: 'This set gave me chills...' (142 likes)
         [link al video]"
```

### 11.4 Semantic Caching

```
Query del usuario → Embedding → Buscar en cache semántico
    ├── Si similitud > 0.95 → Devolver respuesta cacheada
    └── Si no → Ejecutar RAG normal → Guardar en cache
```

Reduce costo de Gemini y latencia para queries repetidas/similares.

### 11.5 Feedback Loop (RLHF-lite)

```
Respuesta del agente → Usuario marca: 👍/👎
    ↓
Firestore: feedback/{response_id}
    ├── user_query
    ├── agent_response
    ├── tools_used
    ├── rating
    └── feedback_text (opcional)
    ↓
Periódicamente: fine-tune del system prompt basado en feedback
```

---

## 12. Stack final propuesto

```
Frontend:     Chat UI simple (HTML/JS o Streamlit) → Cloud Run
Auth:         IAP (Identity-Aware Proxy)
Backend:      Cloud Run Service (FastAPI + ADK Agent)
LLM:          Gemini 2.5 Flash (via Vertex AI)
Embeddings:   text-embedding-004 (para queries del usuario)
RAG:          BigQuery VECTOR_SEARCH (gold_rag_corpus)
Memory:       Firestore (sessions + preferences)
IaC:          Terraform (nuevos recursos: Cloud Run Service, IAP, Firestore, IAM)
Monitoring:   Cloud Logging + feedback en Firestore
```

---

## 13. Decisiones abiertas (para afinar el diseño)

### Tabla de decisiones

| Decisión | Opción A | Opción B | Recomendación |
|:---|:---|:---|:---|
| **Runtime** | Cloud Run Service | Agent Engine | Cloud Run (más barato, consistente con stack) |
| **Memoria** | Firestore DIY | Memory Bank (preview) | Firestore (estable, versionable en TF) |
| **Auth** | IAP (interno) | Firebase Auth (externo) | IAP primero, migrar si hay usuarios externos |
| **Multi-agente** | Agente único | Multi-agente ADK | Agente primero, multi-agente en fase 5 |
| **Text-to-SQL** | Templates parametrizados | SQL libre con validación | Templates (seguro, predecible) |
| **Cache** | Sin cache | Semantic cache | Sin cache primero, cache en fase 6 |

### Preguntas pendientes

1. **Audiencia:** ¿solo yo, un equipo interno, o usuarios externos? (define auth y
   algo del costo)
2. **Volumen esperado** de consultas/mes, aunque sea a ojo (define el sizing de
   Gemini).
3. **Runtime:** ¿Cloud Run (más barato, encaja con el patrón) o Agent Engine (más
   managed, algo más caro)?
4. **Memoria:** ¿Firestore DIY para empezar, o ir directo a Memory Bank aunque esté
   en preview?
5. **Tipo de preguntas** previstas: más semánticas ("qué dice la gente de..."), más
   analíticas ("dame números de..."), o ambas por igual.
6. **Frontend:** ¿Chat UI vanilla, Streamlit, o solo API? (afecta complejidad y UX)
7. **Feedback loop:** ¿implementar desde el inicio o en fase posterior?

---

## Referencias

### ADK y Agent Builder
- [Memory - Agent Development Kit (ADK)](https://google.github.io/adk-docs/sessions/memory/)
- [Quickstart with Agent Development Kit | Vertex AI Agent Builder](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/quickstart-adk)
- [Remember this: Agent state and memory with ADK | Google Cloud Blog](https://cloud.google.com/blog/topics/developers-practitioners/remember-this-agent-state-and-memory-with-adk)
- [adk-vertex-ai-rag-engine (GitHub)](https://github.com/arjunprabhulal/adk-vertex-ai-rag-engine)
- [ADK Multi-Agent Systems](https://google.github.io/adk-docs/agents/multi-agents.html)

### Memory y RAG
- [Vertex AI Memory Bank in public preview | Google Cloud Blog](https://cloud.google.com/blog/products/ai-machine-learning/vertex-ai-memory-bank-in-public-preview)
- [BigQuery VECTOR_SEARCH documentation](https://cloud.google.com/bigquery/docs/vector-search-intro)
- [text-embedding-004 model card](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/text-embeddings)

### Pricing
- [Vertex AI Pricing: The Complete 2026 Guide](https://www.nops.io/blog/vertex-ai-pricing/)
- [Google Vertex AI Pricing: Complete Enterprise Guide (2026)](https://www.cloudzero.com/blog/google-vertex-ai-pricing/)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Firestore pricing](https://cloud.google.com/firestore/pricing)

### Autenticación
- [Identity-Aware Proxy documentation](https://cloud.google.com/iap/docs/concepts-overview)
- [Firebase Authentication](https://firebase.google.com/docs/auth)

### Evaluación y calidad
- [ADK Evaluation Framework](https://google.github.io/adk-docs/evaluate/)
- [RAG evaluation best practices](https://cloud.google.com/vertex-ai/generative-ai/docs/evaluation/rag-evaluation)
