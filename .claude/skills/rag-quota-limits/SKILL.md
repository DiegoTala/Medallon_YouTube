---
name: rag-quota-limits
description: Guardrails económicos de Fase 2 — cuota de 30 consultas diarias, rate limit de 5/min, tope de 3.000 tokens, maximum_bytes_billed (10 MB general, 50 MB en semantic_search) y circuito de protección por consumo. Úsalo al escribir o modificar cuotas, límites o cualquier llamada a BigQuery o Vertex AI desde el agente.
---

# rag-quota-limits

## Alcance

Los cinco límites cuantitativos del PRD Fase 2 §12 que mantienen el delta mensual por debajo de $5 USD. Cada uno se aplica **en código**, en un punto definido de la cadena, no en un prompt.

## Los cinco límites y dónde se aplican

| Límite | Valor | Dónde se aplica |
| :--- | :--- | :--- |
| Cuota diaria | 30 consultas/usuario | middleware, antes de invocar al Router |
| Rate limit | 5 consultas/min/usuario (configurable) | middleware, antes de la cuota |
| Tokens de respuesta | 3.000 máximo | configuración del modelo **y** verificación previa al envío |
| Bytes facturados | 10 MB por consulta BigQuery (50 MB en `semantic_search`, ver excepción abajo) | `QueryJobConfig` de **cada** herramienta |
| Resultados recuperados | 20 máximo | dentro de [[rag-tool-semantic-search]] |

El orden en el middleware importa: rate limit antes que cuota. Un cliente en bucle debe frenarse por minuto sin consumir las 30 consultas del día de un usuario legítimo en treinta segundos.

## `maximum_bytes_billed`: el único que falla en la dirección correcta

```python
job_config = bigquery.QueryJobConfig(
    maximum_bytes_billed=10 * 1024 * 1024,   # 10 MB
    query_parameters=[...],
)
```

Si la consulta excediera el tope, BigQuery **la rechaza sin cobrar**, en vez de ejecutarla y facturar. Es el único límite del sistema que protege el presupuesto aunque todo lo demás falle, y por eso va en cada llamada sin excepción: una sola herramienta sin él anula la garantía.

Se configura por job, no por proyecto, así que **una herramienta nueva no lo hereda**. Al escribir una herramienta que consulte BigQuery, el `QueryJobConfig` con este campo es parte del contrato mínimo.

Que una consulta lo exceda es, casi siempre, la señal de que le falta un filtro — no un incidente de infraestructura. Ver el `WHERE` externo de [[rag-tool-trend-detection]] como ejemplo de la corrección esperada.

### La única excepción: `semantic_search` a 50 MB

Hay un caso donde ningún filtro ayuda. `VECTOR_SEARCH` en modo exhaustivo tiene que leer la columna `text_embedding` **entera** para calcular distancias; un `WHERE` sobre `channel_name` o fechas se aplica *después* del escaneo, no antes. El corpus de 3,261 filas × 768 dimensiones pesa ~20 MB, medido el 2026-09-05 con `bq query --dry_run`: **20,856,549 bytes**.

Con el tope de 10 MB, BigQuery rechazaba *toda* consulta semántica —el guardrail no estaba protegiendo el presupuesto, estaba apagando la única herramienta de recuperación del sistema. Se elevó a **50 MB solo en [[rag-tool-semantic-search]]**; las otras dos herramientas escanean ~80 KB y se quedan en 10 MB.

| | escaneo real medido | tope |
| :--- | ---: | ---: |
| `semantic_search` | ~20.9 MB | 50 MB |
| `sentiment_analytics` | ~79 KB | 10 MB |
| `trend_detection` | ~58 KB | 10 MB |

Peor caso a 50 MB: 90 consultas/día × 30 días × 50 MB = 132 GB/mes ≈ **$0.83 USD/mes**, dentro de la partida "BigQuery (consultas del agente)" que [[cost-guardrail]] ya presupuesta en $0.10–$0.50 con el escaneo real de 20 MB (~$0.34/mes).

**Cuándo revisar el valor:** cuando el corpus pase de 5,000 filas y el índice vectorial IVF sea creable ([[gold-vector-search]]), el escaneo deja de ser exhaustivo y el tope debe volver a bajar. Mientras tanto, subirlo de nuevo por un fallo de bytes es señal de que el corpus creció — recalcular con `--dry_run`, no elegir un número más grande.

## Cuota y rate limit en Firestore

Ambos contadores viven bajo el usuario, con `expires_at` propio:

```
users/{user_id}/quota/{YYYY-MM-DD}     count, expires_at (+2 días)
users/{user_id}/rate/{YYYY-MM-DDTHH:MM} count, expires_at (+1 hora)
```

Se incrementan con `firestore.Increment(1)` de forma atómica. Leer-luego-escribir permite que dos requests concurrentes vean el mismo valor y ambos pasen el límite.

El día de la cuota se calcula en una zona horaria fija y declarada (la del usuario, `America/Mexico_City`), no en UTC ni en la del servidor. Sin eso, la cuota se reinicia a las 6 de la tarde y nadie entiende por qué.

**Un hit de [[rag-response-cache]] también cuenta.** El límite de 30 es de uso, no solo de costo: es lo que acota el gasto *y* el abuso.

Al agotarse, la respuesta es un mensaje claro con el momento de reinicio — no un error genérico ni un 500.

## Excepciones por identidad

La cuota de 30 admite excepciones por usuario, configuradas en la variable de entorno `QUOTA_OVERRIDES` del Cloud Run Service (`infra/fase2/cloud_run.tf`), con formato `correo=limite`. Un límite de **0 significa sin tope**.

**Van en Terraform y no en Firestore a propósito.** Un override guardado en Firestore sería mutable desde la consola sin dejar rastro; en `cloud_run.tf` aparece en el `terraform plan`, pasa por [[approval-gate]] y queda en `infra/APPROVALS.md`. Un guardrail de presupuesto que se puede cambiar sin auditoría no es un guardrail.

Dos reglas que hacen que la excepción no sea un agujero:

- **Sin tope no es sin medición.** El contador de Firestore se incrementa igual. Es la única forma de saber cuánto está costando la excepción.
- **Un override mal escrito cae al límite normal**, nunca a "sin tope". `QUOTA_OVERRIDES="diego@…=muchas"` da 30, no infinito. La dirección del fallo importa.

## Circuito de protección por consumo

Además de los límites por usuario, un tope agregado: si el conteo de consultas del día sumando a todos los usuarios supera `GLOBAL_DAILY_LIMIT` (por defecto 300), el servicio responde 503 y deja de invocar a Vertex AI.

Existe para el escenario que los límites por usuario no cubren: un bug en el propio servicio que reintenta en bucle con identidad válida. Los usuarios son de confianza; el código no necesariamente.

**Con una identidad sin tope, este circuito es el único límite que queda entre un bucle y la factura**, y por eso se evalúa *antes* que la cuota por usuario. Cuando se concede un override, revisar este número es parte del mismo cambio, no un pendiente.

Lo que acota y lo que no: un día completo contra el tope de 300 cuesta del orden de **$0.50 USD** (~$0.0017 por consulta: cuatro o cinco llamadas a Gemini Flash más ~21 MB de `VECTOR_SEARCH`). Eso protege contra un día malo. **No** protege contra 300 consultas diarias sostenidas un mes — eso serían ~$15 y rompería el techo. El circuito es un cortacircuitos, no un presupuesto: si el consumo real se acerca al tope de forma habitual, la respuesta correcta es recotizar con [[cost-guardrail]], no subir el número.

## Cotización, no adivinanza

Cualquier cambio a estos valores se cotiza con [[cost-guardrail]] contra el techo vigente **antes** de aplicarse. Subir la cuota de 30 a 100 es triplicar la partida de Gemini, que es la mayor del §15. No es un ajuste de configuración.

## Invariantes

- **Los cinco límites en código**, nunca solo en el prompt. El modelo no es un mecanismo de control.
- **`maximum_bytes_billed` en cada `QueryJobConfig`**, sin excepción.
- **Contadores atómicos** con `Increment`.
- **Zona horaria fija y declarada** para el día de la cuota.
- **El caché no exime de cuota.**
- **Subir cualquier límite pasa por [[cost-guardrail]]** y, si toca infraestructura, por [[approval-gate]].
- **Las excepciones de cuota viven en Terraform**, nunca en Firestore, y se registran en `APPROVALS.md`.
- **Un override ilegible cae al límite normal**, jamás a sin tope.
- **Sin tope sigue contando**: la medición no es opcional aunque el bloqueo lo sea.
- **El agotamiento de cuota es una respuesta, no un error.**

## Relación con otros skills

- Su lugar en la cadena de middleware: [[rag-fastapi-service]].
- El tope de 20 resultados se aplica en [[rag-tool-semantic-search]]; el de bytes, también en [[rag-tool-sentiment-analytics]] y [[rag-tool-trend-detection]].
- El tope de tokens lo aplica [[rag-synthesis-citations]].
- Los guardrails de seguridad (dominio, inyección, SQL) son [[rag-security-guardrails]].
- Identidad para contar por usuario: [[rag-iap-auth]].
- Cotización contra el techo: [[cost-guardrail]].
