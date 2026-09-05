---
name: rag-memory-common-queries
description: Registro de consultas frecuentes por usuario en Firestore — hash de consulta, contador y TTL de 180 días, sin almacenar respuestas completas. Úsalo al escribir o modificar este registro.
---

# rag-memory-common-queries

## Alcance

Telemetría de uso por usuario en `users/{user_id}/common_queries/{query_hash}`, con retención de **180 días** (PRD Fase 2 §9). Responde "¿qué le pregunta este usuario al sistema una y otra vez?".

No es memoria conversacional (eso es [[rag-memory-session]]), no es preferencia (eso es [[rag-memory-preferences]]) y **no es caché** (eso es [[rag-response-cache]]). Confundirla con caché es el error a evitar: aquí no se guardan respuestas.

## Documento

```
users/{user_id}/common_queries/{query_hash}
  normalized_query: str
  query_hash: str          <- el propio id del documento
  count: int
  last_used_at: timestamp
  filters: dict            <- canal, rango de fechas, sentimiento
  language: str
  expires_at: timestamp    <- last_used_at + 180 días
```

`query_hash` como id del documento hace que el registro sea un `set` con contador: la misma consulta normalizada incrementa en vez de duplicar.

## Normalización y hash

La misma función de normalización que usa [[rag-response-cache]] — si divergen, el sistema cuenta como distintas dos consultas que sí comparten caché, y las estadísticas dejan de explicar el gasto:

```python
import hashlib, json, unicodedata

def normalize_query(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    return " ".join(text.split())

def query_hash(normalized: str, filters: dict, language: str) -> str:
    payload = json.dumps(
        {"q": normalized, "f": filters, "l": language},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

Diferencia con la clave de caché: aquí **no** entran la versión de Gold, la versión del prompt ni el modelo. Una consulta sigue siendo la misma consulta aunque el corpus cambie; una respuesta cacheada, no.

## Escritura

Se registra al **atender** una consulta, incluida la que se sirvió desde caché — si no, las consultas más repetidas quedan sistemáticamente subcontadas, que son justo las que interesan.

Se hace con `Increment` de Firestore, no leyendo y reescribiendo:

```python
doc_ref.set({
    "normalized_query": normalized,
    "count": firestore.Increment(1),
    "last_used_at": now,
    "expires_at": now + timedelta(days=180),
    "filters": filters,
    "language": language,
}, merge=True)
```

`expires_at` se recalcula en cada uso: los 180 días corren desde el **último** uso, no desde el primero. Una consulta viva no debe expirar.

**No se registran consultas rechazadas** por [[rag-security-guardrails]]. Guardar el texto de intentos fuera de dominio o de inyección crea un depósito de texto hostil dentro de los datos del usuario, sin ningún beneficio.

## Invariantes

- **Nunca se almacenan respuestas completas** (PRD §9). Solo la consulta, sus filtros y el contador.
- **TTL de 180 días desde el último uso**, con `expires_at` en toda escritura.
- **Misma normalización que [[rag-response-cache]]**, en una sola función compartida.
- **Aislado por usuario** bajo `users/{user_id}`, con el `user_id` del JWT de [[rag-iap-auth]].
- **No alimenta preferencias.** Una consulta repetida no autoriza a inferir un gusto — ver la regla de [[rag-memory-preferences]].
- **No se registra lo rechazado.**

## Relación con otros skills

- Comparte normalización con [[rag-response-cache]].
- Comparte base de datos y política TTL con [[rag-memory-session]] — ambas se declaran en [[rag-terraform-root]].
- Identidad: [[rag-iap-auth]].
- El filtro que decide qué no se registra: [[rag-security-guardrails]].
