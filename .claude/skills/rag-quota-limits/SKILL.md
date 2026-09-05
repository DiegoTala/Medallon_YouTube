---
name: rag-quota-limits
description: Guardrails económicos de Fase 2 — cuota de 30 consultas diarias, rate limit de 5/min, tope de 3.000 tokens, maximum_bytes_billed de 10 MB y circuito de protección por consumo. Úsalo al escribir o modificar cuotas, límites o cualquier llamada a BigQuery o Vertex AI desde el agente.
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
| Bytes facturados | 10 MB por consulta BigQuery | `QueryJobConfig` de **cada** herramienta |
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

Que una consulta lo exceda no es un incidente de infraestructura: es la señal de que le falta un filtro. Ver el `WHERE` externo de [[rag-tool-trend-detection]] como ejemplo de la corrección esperada.

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

## Circuito de protección por consumo

Además de los límites por usuario, un tope agregado: si el conteo de consultas del día en todos los usuarios supera un umbral configurado (por defecto `3 usuarios × 30 = 90`, con margen), el servicio deja de invocar a Vertex AI y responde en modo degradado.

Existe para el escenario que los límites por usuario no cubren: un bug en el propio servicio que reintenta en bucle con identidad válida. Los tres usuarios son de confianza; el código no necesariamente.

## Cotización, no adivinanza

Cualquier cambio a estos valores se cotiza con [[cost-guardrail]] contra el techo vigente **antes** de aplicarse. Subir la cuota de 30 a 100 es triplicar la partida de Gemini, que es la mayor del §15. No es un ajuste de configuración.

## Invariantes

- **Los cinco límites en código**, nunca solo en el prompt. El modelo no es un mecanismo de control.
- **`maximum_bytes_billed` en cada `QueryJobConfig`**, sin excepción.
- **Contadores atómicos** con `Increment`.
- **Zona horaria fija y declarada** para el día de la cuota.
- **El caché no exime de cuota.**
- **Subir cualquier límite pasa por [[cost-guardrail]]** y, si toca infraestructura, por [[approval-gate]].
- **El agotamiento de cuota es una respuesta, no un error.**

## Relación con otros skills

- Su lugar en la cadena de middleware: [[rag-fastapi-service]].
- El tope de 20 resultados se aplica en [[rag-tool-semantic-search]]; el de bytes, también en [[rag-tool-sentiment-analytics]] y [[rag-tool-trend-detection]].
- El tope de tokens lo aplica [[rag-synthesis-citations]].
- Los guardrails de seguridad (dominio, inyección, SQL) son [[rag-security-guardrails]].
- Identidad para contar por usuario: [[rag-iap-auth]].
- Cotización contra el techo: [[cost-guardrail]].
