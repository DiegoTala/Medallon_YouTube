# YouTube DJ Analytics — Sistema Agéntico RAG

**Reporte Ejecutivo de Arquitectura y Evidencia de Verificación**

**Autor:** Diego Talamantes Sánchez  
**Repositorio:** [github.com/DiegoTala/Medallon_YouTube](https://github.com/DiegoTala/Medallon_YouTube)  
**Fecha:** 5 de septiembre de 2026  
**Proyecto GCP:** `medallon-youtube`  
**Alcance:** Fase 2, construida sobre la base de datos de la Fase 1

---

## 1. Resumen ejecutivo

La Fase 2 convierte el pipeline analítico de YouTube DJ Analytics en una aplicación web conversacional. El sistema permite consultar qué opinan los usuarios sobre los DJs monitorizados, analizar sentimiento y comparar tendencias, siempre sobre datos recuperados desde la plataforma.

La Fase 1 fue el prerrequisito técnico y de calidad de la Fase 2. Su pipeline medallón extrae los datos de YouTube, los valida, elimina duplicados mediante operaciones idempotentes y genera sentimiento y embeddings. Al final de ese proceso, la tabla `gold_rag_corpus` funciona como la **Knowledge Base (KB)** del sistema agéntico: una frontera de datos curada, estructurada y vectorizada que la aplicación puede consultar sin acceder a Bronze, Silver ni a la dead-letter queue.

La solución está desplegada en GCP con FastAPI sobre Cloud Run, Google ADK para la coordinación de agentes, Gemini mediante Vertex AI, BigQuery Vector Search para recuperación semántica, Firestore para memoria y caché, e IAP para autenticación.

### 1.1 Estado operativo

| Elemento | Estado |
|:---|:---|
| Servicio | Cloud Run Service desplegado y listo |
| Revisión activa documentada | `rag-chat-service-00011-clx` |
| Corpus RAG | 3,278 comentarios de 7 canales, según el handoff operativo |
| Autenticación | IAP nativo de Cloud Run |
| Modelo generativo | Gemini 2.5 Flash vía Vertex AI |
| Embeddings | `text-embedding-004`, 768 dimensiones |
| Memoria | Firestore con TTL y aislamiento por identidad |
| Región | `us-central1` |
| Costo estimado total | ~$3.19–$6.69 USD/mes, dentro del techo de $20.00 |

## 2. La Fase 1 como base de la Fase 2

La arquitectura no trata a la aplicación conversacional como un sistema aislado. La Fase 2 consume el resultado gobernado de la Fase 1.

```mermaid
flowchart LR
    Y[YouTube Data API v3] --> B[Bronze<br/>GCS JSONL inmutable]
    B --> S[Silver<br/>Pydantic + MERGE idempotente]
    S --> G[Gold<br/>sentimiento + embeddings]
    G --> K[gold_rag_corpus<br/>Knowledge Base del agente]
    K --> R[Fase 2<br/>Sistema agéntico RAG]
    R --> U[Usuario autenticado]
```

### 2.1 Qué aporta la Fase 1

- **Bronze:** conserva la extracción cruda de videos y comentarios en GCS como JSON Lines inmutable.
- **Silver:** valida los contratos con Pydantic, aplica `MERGE` sobre las claves naturales y envía errores a `silver_dead_letter_queue`.
- **Gold:** calcula sentimiento con Gemini, genera embeddings con `text-embedding-004` y habilita la búsqueda vectorial.
- **`gold_rag_corpus`:** denormaliza la información necesaria para que los agentes consulten texto, sentimiento, video, canal, fecha, URL y embedding desde una sola fuente de lectura.

La consecuencia importante es que el modelo no recibe datos crudos directamente desde YouTube. Recibe resultados estructurados de herramientas que consultan la KB Gold.

## 3. Razonamiento de diseño

### 3.1 RAG propio sobre BigQuery

Se eligió un RAG implementado sobre BigQuery Vector Search en lugar de Vertex AI RAG Engine. Esta decisión evita un servicio administrado con costo fijo adicional y aprovecha que la Fase 1 ya produce embeddings en BigQuery.

El flujo es:

1. El usuario formula una pregunta en lenguaje natural.
2. El agente de búsqueda conserva la pregunta completa y la envía a `semantic_search`.
3. La herramienta genera el embedding de la consulta con el mismo modelo del corpus.
4. `VECTOR_SEARCH` recupera los comentarios más cercanos por distancia coseno.
5. Un umbral de relevancia descarta resultados que sean vecinos matemáticos pero no evidencia útil.
6. La síntesis recibe únicamente los resultados estructurados y redacta una respuesta con citas.

El umbral calibrado de relevancia es `0.35`. Con un corpus pequeño, devolver siempre `top_k` resultados produciría evidencia irrelevante para preguntas sobre DJs ausentes o temas fuera del dominio. El umbral convierte esa incertidumbre en una respuesta explícita de ausencia de datos.

### 3.2 Catálogo cerrado en lugar de SQL libre

Las consultas analíticas no se generan dinámicamente. `sentiment_analytics` utiliza cinco plantillas SQL parametrizadas y `trend_detection` compara periodos mediante un contrato controlado. Los parámetros tienen tipos y validaciones estrictas.

Esto evita que el texto del usuario se convierta en SQL, incluso si se sanitiza. El sistema tampoco expone herramientas para leer Bronze, Silver o la DLQ.

### 3.3 Agentes especializados

Google ADK permite separar responsabilidades sin permitir que un especialista se salte los controles de la aplicación. La coordinación utiliza `AgentTool`, no transferencia directa de control.

```mermaid
flowchart TD
    R[Router agent<br/>único punto conversacional] --> S[Search agent]
    R --> A[Analytics agent]
    R --> M[Memory agent]
    R --> H[Hybrid pipeline]
    H --> P[ParallelAgent]
    P --> S2[Search]
    P --> A2[Analytics]
    P --> Y[SequentialAgent]
    S2 --> Y
    A2 --> Y
    Y --> T[Synthesis agent]
    S --> V[semantic_search]
    A --> SA[sentiment_analytics]
    A --> TD[trend_detection]
    M --> MQ[common_queries / preferences]
    T --> C[Validación de citas y cifras]
```

- **Router:** clasifica la intención y selecciona la capacidad adecuada.
- **Search agent:** ejecuta recuperación semántica sobre `gold_rag_corpus`.
- **Analytics agent:** ejecuta las plantillas de sentimiento y tendencias.
- **Memory agent:** consulta historial agregado y preferencias, sin inventar información.
- **Synthesis agent:** redacta con los resultados de las herramientas; no tiene herramientas propias.
- **Validación en código:** revisa citas y afirmaciones numéricas antes de responder.

La síntesis ocurre después de las ramas de búsqueda y analítica. En preguntas híbridas, las ramas se ejecutan en paralelo y la redacción se ejecuta secuencialmente después de que ambas hayan terminado.

## 4. Software y arquitectura desplegada

| Capa | Software o servicio | Responsabilidad |
|:---|:---|:---|
| API | FastAPI + Uvicorn | Endpoint `/chat`, bienvenida, healthcheck y UI |
| Agentes | Google ADK 2.x | Router, especialistas, memoria y síntesis |
| Modelo | Gemini 2.5 Flash vía Vertex AI | Interpretación, coordinación y redacción |
| Recuperación | BigQuery `VECTOR_SEARCH` | Búsqueda semántica sobre embeddings |
| Analítica | BigQuery + SQL parametrizado | Sentimiento, comparaciones y tendencias |
| KB | `gold_rag_corpus` | Única fuente de datos para Fase 2 |
| Memoria | Firestore Native `rag-memory` | Sesiones, preferencias, consultas frecuentes y caché |
| Identidad | IAP nativo de Cloud Run | Autenticación Google y protección del servicio |
| Infraestructura | Terraform | Provisionamiento declarativo y estados aislados |
| Ejecución | Cloud Run Service | Servicio web con scale-to-zero |
| Imagen | Artifact Registry | Almacenamiento de la imagen del agente |

Todos los componentes de datos y cómputo analítico se mantienen co-ubicados en `us-central1` para evitar incompatibilidades de región entre BigQuery y Vertex AI.

## 5. Memoria y personalización

La memoria se implementa como una capa explícita sobre Firestore, independiente del servicio de sesiones nativo de ADK. Esto permite controlar qué se guarda, cuánto tiempo permanece y cómo se aísla por usuario.

```mermaid
flowchart LR
    I[Identidad IAP: sub] --> U[users/{user_id}]
    U --> S[sessions/{session_id}]
    S --> MSG[messages/{message_id}<br/>TTL 7 días]
    U --> P[Preferencias<br/>sin TTL]
    U --> Q[common_queries<br/>TTL 180 días]
    U --> C[response_cache<br/>TTL 7 días]
```

- **Memoria de sesión:** guarda mensajes, herramientas utilizadas, citas y referencia del snapshot Gold. Los mensajes expiran después de 7 días.
- **Preferencias:** solo se guardan después de una instrucción explícita y confirmación del usuario. No tienen TTL automático.
- **Consultas frecuentes:** almacenan hash, parámetros y contador, no la respuesta completa, con TTL de 180 días.
- **Caché:** usa una clave versionada por consulta, parámetros, idioma, corpus, prompt y modelo. No cachea conclusiones con evidencia insuficiente o débil.
- **Aislamiento:** el identificador estable es el `sub` de la identidad autenticada, no el correo electrónico. Así, historial, cuotas y caché no se mezclan entre usuarios.

El usuario puede preguntar por sus consultas repetidas y el sistema puede reportar conteos reales. La memoria no se utiliza para fabricar hechos sobre los comentarios.

## 6. Autenticación y control de acceso

La aplicación utiliza IAP nativo de Cloud Run, sin Load Balancer adicional. El servicio no permite acceso anónimo.

```mermaid
flowchart LR
    U[Usuario Google] --> I[IAP]
    I -->|JWT firmado| CR[Cloud Run]
    CR --> V[FastAPI verifica JWT]
    V --> AL[Allowlist de identidades]
    AL --> APP[Aplicación RAG]
```

El backend verifica el header firmado `x-goog-iap-jwt-assertion` con:

- Audiencia del servicio Cloud Run.
- Certificados públicos de IAP.
- Correo incluido en el token.
- Allowlist de identidades autorizadas.

Los headers `x-goog-authenticated-user-*` no se consideran suficientes porque no constituyen por sí mismos una prueba criptográfica de identidad.

La identidad de evaluación automatizada tiene un binding separado. Las cuentas humanas autorizadas son las del dominio `talamantes.com.mx`; no se usan contraseñas propias de la aplicación.

## 7. Guardrails de seguridad, calidad y costo

### 7.1 Seguridad de entrada

Antes de que la consulta llegue al prompt:

- Se normaliza Unicode con NFKC.
- Se eliminan caracteres de control e invisibles.
- Se normalizan espacios conservando saltos de línea.
- Se limita la consulta a 500 caracteres.

La sanitización acota la forma de la entrada, pero no la convierte en confiable. Las instrucciones del usuario y el contenido de comentarios recuperados se tratan como datos, no como órdenes del sistema.

### 7.2 Dominio cerrado y aislamiento de datos

El sistema solo responde preguntas sobre comentarios de los canales DJ disponibles. No responde conocimiento general sobre geografía, restaurantes, precios, infraestructura o temas ajenos.

La cuenta de servicio del backend tiene acceso de lectura únicamente al dataset Gold necesario para la aplicación. Bronze, Silver y la DLQ permanecen fuera del perímetro de lectura de Fase 2, con IAM a nivel de dataset.

### 7.3 Citas y evidencia

El modelo solo elige qué comentario citar. El formato final de la cita lo construye el código a partir de la fila real devuelta por la herramienta:

```text
[comment_id · "título del video" · canal · fecha · URL]
```

La aplicación compara los identificadores citados contra los `comment_id` recuperados. Una cita inventada degrada la respuesta y evita su almacenamiento en caché. Las cifras de tamaño de muestra (`n=`) también se comparan contra los resultados reales.

Las herramientas informan niveles de evidencia `insufficient`, `weak` o `solid`. Una muestra pequeña no se presenta con la misma confianza que una muestra amplia y las respuestas con evidencia débil no se convierten en respuestas persistentes de caché.

### 7.4 Límites operativos

- Rate limit: 5 consultas por minuto por usuario.
- Cuota normal: 30 consultas diarias por usuario.
- Circuito agregado: 300 consultas diarias para todo el servicio.
- Tope de generación: 3,000 tokens.
- Límite general de bytes de BigQuery: 10 MB.
- Límite específico de búsqueda semántica: 50 MB, debido al tamaño actual del corpus y la lectura exhaustiva de embeddings.
- Healthcheck sin llamadas a BigQuery ni Vertex AI.

Los contadores se registran aunque una identidad tenga una excepción de cuota. Sin tope de usuario no significa sin medición ni sin circuito global.

## 8. Fase F del plan: despliegue y validación

La Fase F corresponde a la puesta en producción y a la evaluación del sistema completo. Se realizaron el build y push de la imagen, la aprobación del despliegue, el despliegue del Cloud Run Service y verificaciones manuales con el servicio activo.

El conjunto de evaluación está definido en `tests/rag_evaluation/`:

- 15 preguntas doradas: búsqueda semántica, analítica de sentimiento y tendencias.
- 10 preguntas adversariales: fuera de dominio, inyección de prompt y acceso a datos no autorizados.
- Métricas objetivo: citas completas, rechazo adversarial y exactitud numérica.

La evidencia disponible muestra respuestas correctas de recuperación semántica, avisos de evidencia insuficiente y rechazos de solicitudes adversariales. También se mantiene una observación importante: la evaluación registrada muestra que algunas respuestas analíticas todavía llegan sin citas visibles, por lo que la cobertura total de citas debe seguir tratándose como pendiente de endurecimiento, aunque las citas inventadas sí se validan en código.

## 9. Evidencias de funcionamiento

### 9.1 Respuesta con recuperación semántica y citas

La siguiente evidencia corresponde a una consulta real sobre problemas de audio. La respuesta recupera comentarios concretos, incluye metadata de video y muestra el panel de fuentes.

![Respuesta de búsqueda semántica con citas](../../tests/rag_evaluation/results/evidencia_20260905/search-03.png)

### 9.2 Advertencia de evidencia insuficiente

El sistema puede responder con el canal que presenta el porcentaje observado más alto y, al mismo tiempo, advertir que la muestra no permite una comparación sólida.

![Analítica con evidencia insuficiente](../../tests/rag_evaluation/results/evidencia_20260905/analytics-03.png)

### 9.3 Rechazo de inyección de prompt

Ante una instrucción para ignorar las reglas y acceder a `silver_dead_letter_queue`, el agente mantiene el dominio cerrado y no revela infraestructura ni datos fuera de Gold.

![Rechazo de inyección de prompt](../../tests/rag_evaluation/results/evidencia_20260905/sec-inject-01.png)

### 9.4 Nota sobre las imágenes

Estas imágenes **no son capturas de la interfaz gráfica de la aplicación**. Son reconstrucciones visuales generadas con **Pillow** a partir de las respuestas reales devueltas por la API del sistema agéntico. Se incluyen como material de evidencia legible y reproducible, no como sustituto de una captura de pantalla de la UI.

## 10. Conclusiones

- La Fase 1 proporcionó la base de datos confiable, incremental y vectorizada que la Fase 2 utiliza como KB.
- `gold_rag_corpus` establece la frontera entre el pipeline de datos y el sistema agéntico.
- La Fase 2 combina recuperación semántica, analítica parametrizada y síntesis controlada mediante Google ADK.
- Firestore aporta memoria con aislamiento por usuario, TTL, caché versionado y registro de consultas frecuentes.
- IAP y la verificación de JWT evitan depender de headers no firmados para autenticar usuarios.
- Los guardrails limitan dominio, datos accesibles, costo, volumen de salida, inyección y citas sin evidencia.
- El sistema se encuentra desplegado y operativo, pero la cobertura completa de citas en respuestas con datos debe continuar validándose antes de declarar la evaluación de calidad como finalizada.

## 11. Acceso a la aplicación

**URL de la aplicación:** [https://rag-chat-service-7od5boefba-uc.a.run.app](https://rag-chat-service-7od5boefba-uc.a.run.app)

### Usuarios de prueba

Las identidades se autentican mediante Google e IAP. Las contraseñas no son administradas por la aplicación y se agregarán posteriormente a este documento si se requiere una referencia operativa.

| Usuario | Contraseña |
|:---|:---|
| `medallon.rag.test01@talamantes.com.mx` | **[pass goes here]** |
| `medallon.rag.test02@talamantes.com.mx` | **[pass goes here]** |

**Repositorio:** [github.com/DiegoTala/Medallon_YouTube](https://github.com/DiegoTala/Medallon_YouTube)

## Referencias

- [`docs/PRD_Fase2.md`](../PRD_Fase2.md)
- [`docs/PLAN_FASE2.md`](../PLAN_FASE2.md)
- [`docs/HANDOFF_FASE2.md`](../HANDOFF_FASE2.md)
- [`infra/APPROVALS.md`](../../infra/APPROVALS.md)
- [`tests/rag_evaluation/`](../../tests/rag_evaluation/)
