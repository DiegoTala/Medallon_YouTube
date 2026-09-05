---
name: rag-fastapi-service
description: Estructura del servicio FastAPI de Fase 2 y el orden obligatorio de la cadena de middleware (IAP, identidad, sanitización, rate limit, cuota, caché, agente). Úsalo al crear o modificar el servicio, sus endpoints, su middleware o la UI.
---

# rag-fastapi-service

## Alcance

El Cloud Run Service que hospeda la UI de chat, la cadena de middleware y el runtime de ADK (PRD Fase 2 §5). Es donde todos los demás skills de Fase 2 se ensamblan en un orden que importa.

## La cadena, en orden

```
request
  1. IAP            -> verificación del JWT firmado        [rag-iap-auth]
  2. identidad      -> claims.sub como user_id interno     [rag-iap-auth]
  3. sanitización   -> normaliza, quita controles, trunca  [rag-security-guardrails]
  4. rate limit     -> 5/min por usuario                   [rag-quota-limits]
  5. cuota diaria   -> 30/día por usuario                  [rag-quota-limits]
  6. caché          -> hit? responde y sale                [rag-response-cache]
  7. historial      -> carga sesión de Firestore           [rag-memory-session]
  8. Router         -> agentes y herramientas              [rag-agent-topology]
  9. persistencia   -> mensajes, caché, consulta frecuente
```

El orden no es preferencia. Cada paso protege a los siguientes:

- **Identidad antes que todo lo demás**, porque los pasos 4, 5, 6 y 7 son por usuario. Sin `user_id` verificado, la cuota es un contador global y el historial es de cualquiera.
- **Sanitización antes del rate limit**, para que la clave de límite se calcule sobre texto normalizado.
- **Rate limit antes de cuota**, para que un bucle no queme las 30 consultas del día en segundos.
- **Caché antes del historial y del agente**, que es donde está el ahorro. Pero el hit **igual** incrementa cuota (paso 5, ya ejecutado) y se registra en [[rag-memory-common-queries]] al salir.
- **Persistencia al final**, después de que la respuesta pasó la validación de citas de [[rag-synthesis-citations]]. Una respuesta rechazada no se cachea ni se guarda como historial.

Un `try/except` de nivel superior envuelve el manejador: los errores no propagan al usuario como stack trace, y se registran completos en Cloud Logging. Es la misma lección que ya costó una entrada en `infra/APPROVALS.md` en Fase 1 — un pipeline sin manejo de errores en el orquestador murió sin dejar un solo log útil.

## Montaje de ADK sobre FastAPI

> **Nota (verificada 2026-09-04, [issue #51 de adk-python](https://github.com/google/adk-python/issues/51)):** `get_fast_api_app(web=True)` deja **inalcanzables** los endpoints personalizados definidos después — devuelven 404 o 405 sin explicación. Con `web=False` funcionan normalmente. Fase 2 tiene UI propia y middleware propio, así que si se usa `get_fast_api_app`, va con `web=False`. La UI de desarrollo de ADK no es la interfaz del PRD §4.

La alternativa, más alineada con la cadena de arriba, es crear la app FastAPI normalmente e invocar el `Runner` de ADK desde el manejador. Da control total del orden del middleware, que es justo lo que este skill exige. Ver [[rag-agent-topology]] para la construcción de los agentes.

## Estructura sugerida

```
src/rag_agent/
  main.py            # app FastAPI, montaje, manejador de errores
  middleware/        # auth, sanitize, ratelimit, quota, cache
  agents/            # router, search, analytics, synthesis
  tools/             # semantic_search, sentiment_analytics, trend_detection
  memory/            # session, preferences, common_queries
  static/            # UI: HTML/CSS/JS
```

Paquete separado de `src/medallon_youtube/`, que es el pipeline de Fase 1. **No se importan módulos entre ambos**: comparten datos a través de [[gold-rag-corpus]], no a través de código. Un import cruzado ataría el despliegue del servicio al del Job y volvería negociable una frontera que no lo es.

## Salud y scale-to-zero

Un endpoint de salud sin autenticación, que **no** consulta BigQuery ni Vertex AI — un healthcheck que gasta es un gasto recurrente por diseño.

El servicio escala a cero (PRD §15). Consecuencias reales: la primera consulta tras inactividad paga arranque en frío, así que la inicialización pesada (clientes de BigQuery y Firestore) va a nivel de módulo, para que ocurra una vez por instancia y no por request. Nada de estado en memoria entre requests: la instancia que atendió el turno anterior puede ya no existir. Todo estado vive en Firestore.

## UI

HTML/CSS/JS servidos como estáticos desde el mismo servicio (PRD §5) — sin bundler ni framework, para no agregar superficie de build a un proyecto con techo de $20. La UI **no** habla con BigQuery ni con Vertex AI: solo con el endpoint de chat de este servicio.

## Invariantes

- **El orden de la cadena no se altera** sin revisar qué protege cada paso.
- **`user_id` verificado antes de cualquier paso por usuario.**
- **Un hit de caché igual cuenta para la cuota.**
- **Nada se persiste antes de validar citas.**
- **`web=False`** si se usa `get_fast_api_app`.
- **Sin imports cruzados** con `src/medallon_youtube/`.
- **Healthcheck sin costo** y sin autenticación.
- **Sin estado en memoria entre requests.**
- **Errores registrados completos, nunca devueltos crudos.**

## Relación con otros skills

- Ensambla [[rag-iap-auth]], [[rag-security-guardrails]], [[rag-quota-limits]], [[rag-response-cache]], [[rag-memory-session]], [[rag-memory-preferences]], [[rag-memory-common-queries]] y [[rag-agent-topology]].
- Se empaqueta y despliega con [[rag-deploy-service]].
- Su infraestructura se declara en [[rag-terraform-root]].
