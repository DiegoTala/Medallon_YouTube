---
name: rag-memory-session
description: Memoria corta de conversación en Firestore — estructura users/{user_id}/sessions/{session_id}/messages/{message_id}, qué guarda cada mensaje y TTL de 7 días. Úsalo al escribir o modificar la persistencia del historial de conversación.
---

# rag-memory-session

## Alcance

El historial de la conversación, con retención de **7 días** (PRD Fase 2 §9). Es la memoria que permite decir "¿y en el otro canal?" sin repetir el contexto.

## Por qué es custom sobre Firestore y no el session service de ADK

ADK trae su propio modelo de sesiones, pensado para integrarse con Agent Engine. **Agent Engine está fuera de alcance por costo** (PRD §4 y §15), así que la memoria se implementa como capa propia sobre Firestore, externa al runtime de sesiones de ADK. El PRD §9 lo marca como decisión deliberada de integración, no como el camino por defecto del framework.

Consecuencia práctica que hay que tener presente al escribir código: **los agentes no obtienen el historial gratis**. El servicio lo lee de Firestore y lo inyecta explícitamente antes de invocar al Router, y escribe el turno nuevo después. Si alguien asume el comportamiento nativo de ADK, la conversación pierde memoria sin lanzar ningún error.

## Estructura

```
users/{user_id}/sessions/{session_id}
users/{user_id}/sessions/{session_id}/messages/{message_id}
```

Los mensajes van en **subcolección**, no en un array dentro del documento de sesión. Firestore topa un documento en 1 MiB; una conversación larga con citas y resultados de herramientas lo alcanza, y el fallo llega como error de escritura a mitad de una conversación en curso.

Cada mensaje guarda (PRD §9): `role`, `content`, `timestamp`, `tools_used`, `citations`, `gold_snapshot_id` (la versión de Gold consultada) y `expires_at`.

`gold_snapshot_id` en el mensaje no es redundante con [[rag-response-cache]]: sirve para explicar después por qué una misma pregunta dio números distintos en dos días — el corpus cambió entre ambas.

## TTL: el campo manda

Firestore borra por **política TTL sobre un campo**, no por antigüedad automática. Cada mensaje y cada sesión escriben su propio `expires_at`:

```python
from datetime import datetime, timedelta, timezone

expires_at = datetime.now(timezone.utc) + timedelta(days=7)
```

> **Nota (verificada 2026-09-04, [TTL de Firestore](https://docs.cloud.google.com/firestore/native/docs/ttl)):** la política se declara sobre un *collection group* y un campo; el borrado ocurre **típicamente dentro de las 24 horas** posteriores al vencimiento, no en el instante exacto. Dos consecuencias: (1) no asumas que un documento vencido ya no existe — filtra por `expires_at > now` al leer, no confíes solo en el TTL; (2) los borrados por TTL **cuentan como borrados de documento** para efectos de costo, así que el volumen de mensajes es un driver de costo real, aunque marginal a esta escala ([[cost-guardrail]]).

Un documento sin `expires_at` **nunca se borra**. Escribir un mensaje sin ese campo es crear datos de usuario permanentes en un sistema que prometió 7 días.

La política se declara en Terraform, no a mano — ver [[rag-terraform-root]].

## Invariantes

- **Subcolección `messages`**, nunca un array embebido.
- **`expires_at` en toda escritura**, en el mensaje y en la sesión.
- **7 días exactos**, valor del PRD §16. Cambiarlo es un cambio de alcance, no de configuración.
- **Aislamiento por usuario:** toda ruta arranca en `users/{user_id}`, y el `user_id` sale del JWT verificado de [[rag-iap-auth]] — nunca de un header, un parámetro de query ni el cuerpo del request.
- **Al leer se filtra por `expires_at > now`**, porque el borrado real puede tardar hasta 24 h.
- **El historial no es fuente de verdad de datos:** un número mencionado en un mensaje viejo no se recita como dato actual; se vuelve a consultar. El corpus pudo cambiar.

## Relación con otros skills

- El `user_id` viene de [[rag-iap-auth]].
- La política TTL se aprovisiona en [[rag-terraform-root]].
- Comparte base de datos con [[rag-memory-preferences]] y [[rag-memory-common-queries]], con retenciones distintas.
- El servicio que inyecta y persiste el historial es [[rag-fastapi-service]].
- `gold_snapshot_id` se define en [[gold-rag-corpus]].
