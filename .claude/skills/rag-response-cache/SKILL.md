---
name: rag-response-cache
description: Caché exacto de respuestas en Firestore — clave compuesta versionada por corpus, prompt y modelo, e invalidación automática al cambiar cualquiera. Úsalo al escribir o modificar el caché, su clave o su invalidación.
---

# rag-response-cache

## Alcance

Caché **exacto** (no semántico — el semántico está fuera de alcance, PRD §17) de respuestas ya generadas, en Firestore. Ahorra llamadas a Gemini y a BigQuery en consultas repetidas, que es la partida más grande del presupuesto de Fase 2 (§15).

## La clave lo es todo

La clave compuesta del PRD §10 tiene seis componentes, y **cada uno está por una razón de corrección, no de eficiencia**:

| Componente | Qué previene omitirlo |
| :--- | :--- |
| Consulta normalizada | — (es la consulta) |
| Filtros | servir la respuesta de un canal para la pregunta de otro |
| Idioma | responder en inglés a quien preguntó en español |
| **Versión de `gold_rag_corpus`** | servir números viejos sobre datos nuevos, sin ninguna señal |
| **Versión del prompt** | servir respuestas redactadas con reglas de citación derogadas |
| **Modelo** | mezclar salidas de modelos distintos como si fueran equivalentes |

```python
def cache_key(normalized_query, filters, language,
              corpus_version, prompt_version, model, user_id=None):
    payload = json.dumps({
        "q": normalized_query, "f": filters, "l": language,
        "corpus": corpus_version, "prompt": prompt_version, "model": model,
        "u": user_id,          # None cuando la respuesta NO es personalizada
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

La normalización de la consulta es **la misma función** que usa [[rag-memory-common-queries]]. Una sola implementación, importada por ambos.

## Invalidación: por clave, no por borrado

No hay job de limpieza ni invalidación explícita. Al cambiar la versión del corpus o del prompt, la clave cambia y las entradas viejas simplemente dejan de encontrarse; su TTL las retira después. Esto hace la invalidación **imposible de olvidar** — pero solo si las versiones se leen de verdad:

- **Versión del corpus:** `MAX(updated_at)` de [[gold-rag-corpus]], leído por el servicio y cacheado unos minutos, no hardcodeado.
- **Versión del prompt:** una constante que se sube **a mano** al tocar cualquier instrucción de agente. Este es el punto frágil de todo el mecanismo: si alguien edita el prompt de [[rag-synthesis-citations]] y no sube la versión, el sistema sirve respuestas con las reglas viejas y no hay error que lo delate. Cualquier cambio de prompt y esa constante van en el mismo commit.

## Respuestas personalizadas

Si en la generación intervino una preferencia de [[rag-memory-preferences]], el `user_id` entra en la clave y la entrada **no se comparte** (PRD §10). Cuando no intervino ninguna, `user_id` va en `None` y la entrada sirve a los tres usuarios.

La regla operativa: ante la duda de si una preferencia influyó, se particiona por usuario. El costo de un fallo de caché es unos centavos; el de servirle a un usuario una respuesta moldeada por las preferencias de otro es una fuga de información entre cuentas.

## Documento y TTL

```
response_cache/{cache_key}
  response: str
  citations: list
  created_at: timestamp
  expires_at: timestamp     <- created_at + 7 días
  hit_count: int
```

El TTL de 7 días es un piso de higiene: la clave ya invalida por versión, pero sin `expires_at` las entradas huérfanas de versiones viejas se acumularían para siempre. Se declara en [[rag-terraform-root]] junto con las otras políticas.

## Qué no se cachea

- Respuestas rechazadas por [[rag-security-guardrails]] — el rechazo es barato y cachearlo sirve texto hostil desde Firestore.
- Errores de herramienta. Un `status: "error"` transitorio de BigQuery no debe volverse la respuesta permanente a esa pregunta.
- Respuestas con `evidence_level: "insufficient"` de [[rag-tool-trend-detection]] cuando el corpus está creciendo: la siguiente corrida del pipeline puede cambiar la conclusión. La versión del corpus ya lo cubre, pero conviene tenerlo presente.

## Invariantes

- **Los seis componentes de la clave, siempre.** Quitar uno es servir respuestas incorrectas en silencio.
- **La versión del prompt sube en el mismo commit que el prompt.**
- **La versión del corpus se lee del corpus**, nunca se hardcodea.
- **Personalizada ⇒ particionada por `user_id`.**
- **Un hit de caché igual cuenta** para la cuota diaria de [[rag-quota-limits]] y para el registro de [[rag-memory-common-queries]].
- **Caché exacto, no semántico.** Aproximar la coincidencia es cambiar la respuesta a la pregunta.

## Relación con otros skills

- Versión del corpus: [[gold-rag-corpus]].
- Versión del prompt: [[rag-synthesis-citations]] y [[rag-agent-topology]].
- Normalización compartida: [[rag-memory-common-queries]].
- Particionado por preferencias: [[rag-memory-preferences]].
- TTL aprovisionado en [[rag-terraform-root]]; su lugar en la cadena de middleware, en [[rag-fastapi-service]].
