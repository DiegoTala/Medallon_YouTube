# PRD Fase 2: Sistema Agéntico RAG con Memoria

**Proyecto:** YouTube DJ Analytics  
**Fase:** 2  
**Proyecto GCP:** `medallon-youtube`  
**Región:** `us-central1`  
**Fecha:** 2026-09-04  
**Estado:** Especificación independiente de `docs/PRD.md`

## 1. Resumen

Construir una aplicación web conversacional que permita consultar la Gold layer de YouTube DJ Analytics mediante un sistema multiagente basado en Google ADK.

La aplicación utilizará:

- Google ADK para la arquitectura multiagente.
- Gemini en Vertex AI para razonamiento y síntesis.
- BigQuery y `gold_rag_corpus` como base RAG.
- Firestore para memoria corta y larga.
- Cloud Run para el backend y frontend.
- IAP nativo de Cloud Run para autenticación.
- Python y FastAPI como tecnología principal.

La primera versión permitirá realizar búsquedas semánticas, consultar analítica de sentimiento y detectar tendencias bajo demanda.

## 2. Usuarios y acceso

| Usuario | Identidad | Rol |
|---|---|---|
| Principal | `diego@talamantes.com.mx` | Administrador |
| Prueba 1 | `medallon.rag.test01@gmail.com` | Analista |
| Prueba 2 | `medallon.rag.test02@gmail.com` | Analista |

Las dos cuentas Gmail deben crearse manualmente. IAP utilizará las cuentas Google existentes; no habrá usuarios ni contraseñas propias de la aplicación.

Las contraseñas:

- Serán administradas exclusivamente por Google.
- No se almacenarán en el PRD, repositorio, Secret Manager ni Firestore.
- Se concederá acceso mediante una allowlist de IAP.

Todos los usuarios tendrán acceso equivalente a los datos Gold. Diego ejercerá funciones administrativas directamente sobre Cloud Console (Logging, Monitoring, BigQuery, Firestore) mediante un rol IAM elevado, sin una UI administrativa dedicada dentro de la aplicación.

## 3. Objetivos

- Permitir consultas conversacionales sobre datos Gold.
- Implementar una arquitectura multiagente especializada.
- Proporcionar respuestas trazables con citas.
- Mantener el costo incremental por debajo de `$5 USD/mes`.
- Mantener el costo total del proyecto por debajo de `$20 USD/mes`.
- Incorporar memoria de sesión y preferencias explícitas.
- Impedir consultas fuera del dominio YouTube DJ Analytics.
- Evaluar la calidad mediante 15 preguntas doradas y un set de seguridad de 10 preguntas.

## 4. Alcance funcional

### Incluido

- Interfaz web de chat.
- Búsqueda semántica de comentarios.
- Analítica de sentimiento por canal, video y periodo.
- Detección de cambios entre dos periodos.
- Respuestas en español o en el idioma de la consulta.
- Citas a `comment_id`, video y canal.
- Memoria de sesión de siete días.
- Preferencias explícitas por usuario.
- Registro de consultas frecuentes durante 180 días.
- Caché exacto de respuestas.
- Cuota de 30 consultas diarias por usuario.
- Evaluación automática y manual.

### Fuera de alcance

- Alertas proactivas.
- Digests automáticos.
- Clustering temático.
- Recomendaciones.
- Transcripciones o análisis multimodal.
- Usuarios externos no autorizados.
- Text-to-SQL libre.
- Acceso a Bronze, Silver o Dead Letter Queue.
- Vertex AI Vector Search administrado.
- Agent Engine.
- Vertex AI RAG Engine.
- Load Balancer.
- Panel administrativo independiente.

## 5. Arquitectura general

```text
Usuario
   |
   v
IAP nativo de Cloud Run
   |
   v
Cloud Run Service
FastAPI + UI HTML/CSS/JS
   |
   +--> Middleware de identidad y cuotas
   +--> Memoria y caché en Firestore
   +--> Root Router Agent
              |
              +--> Search Agent
              |       +--> semantic_search
              |
              +--> Analytics Agent
              |       +--> sentiment_analytics
              |       +--> trend_detection
              |
              +--> Synthesis Agent
                      +--> Respuesta con citas
   |
   +--> Vertex AI Gemini
   +--> Vertex AI Embeddings
   +--> BigQuery gold_rag_corpus
```

## 6. Arquitectura multiagente

| Agente | Responsabilidad |
|---|---|
| `root_router_agent` | Clasificar la intención y coordinar agentes |
| `search_agent` | Recuperación semántica sobre comentarios |
| `analytics_agent` | Consultas de sentimiento y tendencias |
| `synthesis_agent` | Integrar resultados, generar respuesta y validar citas |

El Router podrá ejecutar Search y Analytics en paralelo para preguntas híbridas.

El Synthesis Agent no tendrá acceso directo a BigQuery. Solo podrá trabajar con resultados estructurados entregados por los agentes especializados.

## 7. Herramientas

### `semantic_search`

Entradas:

- Consulta textual.
- Canal opcional.
- Rango de fechas opcional.
- Etiqueta de sentimiento opcional.
- `top_k`, limitado a 20.

Salidas:

- Texto del comentario.
- `comment_id`.
- Video y canal.
- Fecha.
- Sentimiento.
- Likes.
- URL del video.
- Distancia de similitud.

### `sentiment_analytics`

Consultas permitidas:

- Distribución de sentimiento por canal.
- Distribución por periodo.
- Comparación entre canales.
- Evolución temporal.
- Resumen por video.

No generará SQL libre. Utilizará plantillas parametrizadas y validación estricta de parámetros.

### `trend_detection`

Entradas:

- Periodo actual.
- Periodo base.
- Canal opcional.
- Métrica permitida.

Salidas:

- Cambio absoluto.
- Cambio porcentual.
- Dirección de la tendencia.
- Nivel de evidencia.
- Periodos comparados.
- Citas a los datos Gold.

Las tendencias se calcularán únicamente cuando el usuario las solicite.

## 8. Gold layer para RAG

Se creará una tabla Gold materializada denominada:

```text
gold_rag_corpus
```

La tabla será construida incrementalmente por el pipeline Gold y será la única fuente de datos usada por los agentes.

### Esquema propuesto

| Campo | Tipo |
|---|---|
| `comment_id` | STRING |
| `comment_text` | STRING |
| `text_embedding` | ARRAY<FLOAT64> |
| `sentiment_label` | STRING |
| `video_id` | STRING |
| `video_title` | STRING |
| `channel_name` | STRING |
| `video_published_at` | TIMESTAMP |
| `comment_published_at` | TIMESTAMP |
| `like_count` | INT64 |
| `language` | STRING |
| `video_url` | STRING |
| `gold_snapshot_id` | STRING |
| `updated_at` | TIMESTAMP |

La tabla reutilizará los embeddings y el análisis de sentimiento existentes. No se generarán embeddings nuevamente para registros ya procesados.

La tabla se actualizará mediante `MERGE` sobre `comment_id` como clave natural: inserta comentarios nuevos ya clasificados/embebidos y actualiza únicamente los campos de metadatos de video/canal cuando cambien, sin reprocesar sentimiento ni embeddings existentes.

Se podrá crear un índice IVF cuando el volumen cumpla el mínimo de BigQuery. Mientras tanto, `VECTOR_SEARCH` utilizará búsqueda exhaustiva.

## 9. Memoria en Firestore

Nota de diseño: Google ADK provee un modelo propio de sesiones y memoria pensado para integrarse con Agent Engine. Dado que Agent Engine está fuera de alcance por costo, la memoria de corto y largo plazo se implementará como una capa custom sobre Firestore, externa al runtime de sesiones de ADK. Esta es una decisión de integración deliberada, no el camino por defecto del framework: los agentes deberán leer y escribir explícitamente contra Firestore en lugar de depender del servicio de sesiones nativo de ADK.

### Memoria corta

Retención: **7 días**.

```text
users/{user_id}/sessions/{session_id}
users/{user_id}/sessions/{session_id}/messages/{message_id}
```

Cada mensaje almacenará:

- Rol.
- Contenido.
- Timestamp.
- Herramientas utilizadas.
- Citas.
- Versión de Gold consultada.

Se utilizarán subcolecciones para evitar superar el límite de tamaño de un documento Firestore.

### Preferencias

Solo se guardarán cuando el usuario lo solicite explícitamente.

Ejemplos:

- Idioma preferido.
- Canales favoritos.
- Temas de interés.
- Preferencias de formato.

```text
users/{user_id}
```

El agente deberá confirmar la intención antes de persistir una preferencia.

### Consultas frecuentes

Se almacenará por usuario:

- Consulta normalizada.
- Hash de consulta.
- Contador.
- Último uso.
- Filtros.
- Idioma.
- Fecha de expiración.

Retención: **180 días**.

```text
users/{user_id}/common_queries/{query_hash}
```

No se almacenarán respuestas completas como memoria permanente.

## 10. Caché

Se implementará un caché exacto en Firestore.

La clave incluirá:

- Consulta normalizada.
- Filtros.
- Idioma.
- Versión de `gold_rag_corpus`.
- Versión del prompt.
- Modelo utilizado.

Las respuestas personalizadas por preferencias de usuario no se compartirán entre usuarios.

El caché se invalidará cuando cambie la versión de Gold o el prompt del agente.

## 11. Autenticación con IAP

Se utilizará IAP nativo de Cloud Run, sin Load Balancer.

Flujo:

```text
Usuario
  -> Login Google
  -> IAP
  -> Cloud Run
  -> Middleware FastAPI
  -> Agente
```

Requisitos:

- Cloud Run con IAP habilitado.
- OAuth configurado como aplicación externa.
- Allowlist de las tres cuentas.
- Verificación del JWT de IAP en FastAPI.
- Mapeo de identidad Google a usuario interno.
- Rechazo de cualquier identidad no autorizada.

El acceso a la aplicación no dependerá únicamente de headers no verificados. El backend validará la identidad recibida por IAP.

Riesgo técnico a validar antes del MVP: confirmar disponibilidad de IAP nativo sobre Cloud Run (sin Load Balancer) en `us-central1` para el tipo de servicio a desplegar. Si no está disponible, esta sección requiere revisión antes de continuar, dado que el Load Balancer está fuera de alcance.

## 12. Guardrails

| Guardrail | Regla |
|---|---|
| Dominio | Solo preguntas relacionadas con Gold de YouTube DJ Analytics |
| Cuota diaria | 30 consultas por usuario |
| Rate limit | 5 consultas por minuto por usuario (configurable) |
| Tokens | Máximo 3.000 tokens por respuesta |
| BigQuery | `maximum_bytes_billed` de 10 MB por consulta |
| Recuperación | Máximo 20 resultados |
| SQL | Solo plantillas parametrizadas |
| Datos | Sin acceso a Bronze, Silver ni DLQ |
| Input | Normalización, límite de longitud y eliminación de controles |
| Prompt injection | El contenido recuperado se trata como dato no confiable |
| Citas | Toda respuesta basada en datos debe incluir fuentes |
| Respuestas vacías | El agente debe admitir cuando no existe evidencia |
| Caché | Solo respuestas exactas y versionadas |
| Costo | Alertas y circuito de protección por consumo |

Las consultas fuera de alcance recibirán una respuesta controlada indicando que el sistema solo analiza los datos Gold disponibles.

## 13. Evaluación

Se creará un set de **15 preguntas doradas**.

Distribución sugerida:

- 5 preguntas de búsqueda semántica.
- 5 preguntas de analítica de sentimiento.
- 5 preguntas de tendencias.

Adicionalmente, un set de seguridad independiente de 10 preguntas adversariales (fuera de dominio, intentos de prompt injection, solicitudes de acceso a Bronze/Silver/DLQ) sobre el cual se mide la métrica de rechazo al 100%.

Cada pregunta tendrá:

- Consulta.
- Intención esperada.
- Herramienta esperada.
- Datos relevantes.
- Respuesta esperada.
- Citas requeridas.
- Criterios de rechazo.

Métricas objetivo:

- 100% de respuestas con citas cuando existan datos.
- 90% o más de exactitud numérica en analítica.
- 80% o más de recuperación relevante en `Recall@K`.
- 100% de rechazo de consultas fuera de dominio en el set de seguridad.
- 0 accesos a tablas no autorizadas.
- 0 respuestas que inventen datos cuando no existe evidencia.

La evaluación se ejecutará antes de cada release.

## 14. Infraestructura GCP

Recursos principales:

- Cloud Run Service.
- Artifact Registry.
- Firestore en modo nativo.
- BigQuery Gold.
- Vertex AI Gemini.
- Vertex AI Embeddings.
- IAP.
- Cloud Logging.
- Cloud Monitoring.
- IAM.
- Terraform.
- Políticas TTL de Firestore (7 días sesión, 180 días consultas frecuentes).

La cuenta de servicio del backend tendrá:

- Lectura únicamente sobre el dataset Gold.
- Permiso para ejecutar consultas BigQuery.
- Acceso controlado a Firestore.
- Acceso a Vertex AI.
- Sin permisos sobre Silver, Bronze o DLQ.
- Sin permisos administrativos sobre infraestructura.

Diego contará con un rol IAM adicional de solo lectura sobre Firestore, Cloud Logging y Cloud Monitoring del proyecto, usado para ejercer sus funciones administrativas directamente desde Cloud Console.

## 15. Presupuesto

Estimación estática para el máximo de 30 consultas diarias por usuario:

| Componente | Delta mensual estimado |
|---|---:|
| Cloud Run Service scale-to-zero | `$0.00 - $1.00` |
| Gemini | `$0.50 - $2.00` |
| Embeddings de consultas | `$0.02 - $0.20` |
| BigQuery | `$0.10 - $0.50` |
| Firestore | `$0.00 - $0.10` |
| Logging y artefactos | `$0.05 - $0.30` |
| **Incremento estimado** | **`$1.00 - $4.50`** |

Comparación:

```text
Costo base actual estimado: $1.40 - $1.80/mes
Delta estimado Fase 2:      $1.00 - $4.50/mes
Costo total estimado:       $2.40 - $6.30/mes
Techo original:             $15.00/mes
Techo aprobado Fase 2:      $20.00/mes
```

Autorización del techo Fase 2: Diego (usuario principal), 2026-09-04.

No se utilizarán:

- Vertex AI Vector Search dedicado.
- Agent Engine.
- Vertex AI RAG Engine.
- Load Balancer.
- Recursos con costo fijo elevado.

## 16. Criterios de aceptación

- Los tres usuarios pueden autenticarse mediante Google e IAP.
- Usuarios no autorizados no pueden acceder al servicio.
- Diego aparece como administrador funcional.
- Los tres usuarios pueden hacer consultas sobre Gold.
- Las búsquedas semánticas retornan comentarios relevantes y citas.
- La analítica de sentimiento utiliza únicamente plantillas permitidas.
- La detección de tendencias funciona bajo demanda.
- La memoria de sesión expira después de siete días.
- Las preferencias solo se guardan mediante instrucción explícita.
- Las consultas frecuentes expiran después de 180 días.
- Ningún usuario supera 30 consultas diarias.
- Ninguna respuesta supera 3.000 tokens.
- Ninguna consulta BigQuery supera 10 MB facturados.
- Las consultas fuera de dominio son rechazadas.
- El set de 15 preguntas doradas y el set de seguridad de 10 preguntas se ejecutan como regresión.
- El costo incremental esperado permanece debajo de `$5/mes`.

## 17. Roadmap

### MVP técnico

- Validar disponibilidad de IAP nativo de Cloud Run en us-central1 (spike técnico).
- Configurar políticas TTL de Firestore para memoria de sesión y consultas frecuentes.
- Crear `gold_rag_corpus`.
- Implementar servicio FastAPI.
- Integrar Google ADK.
- Implementar Router, Search, Analytics y Synthesis Agents.
- Implementar las tres herramientas aprobadas.
- Crear memoria en Firestore.
- Implementar cuotas, caché y sanitización.
- Crear interfaz web.
- Habilitar IAP.
- Registrar las tres identidades.

### Validación

- Crear las 15 preguntas doradas y el set de seguridad de 10 preguntas.
- Ejecutar pruebas funcionales.
- Ejecutar pruebas de seguridad.
- Ejecutar pruebas de cuota y tokens.
- Medir costos y latencia.
- Validar citas y respuestas fuera de dominio.

### Futuras versiones

- Alertas proactivas.
- Digests semanales.
- Clustering temático.
- Feedback de usuarios.
- Recomendaciones.
- Caché semántico.
- Nuevos roles y usuarios externos.

## 18. Restricción operativa

La creación o modificación de recursos GCP se realizará únicamente mediante Terraform y requerirá:

- Plan de Terraform.
- Estimación de costo.
- Aprobación explícita previa.
- Registro de la aprobación en `infra/APPROVALS.md`.

Las cuentas Gmail de prueba deberán crearse manualmente antes de configurar la allowlist de IAP.
