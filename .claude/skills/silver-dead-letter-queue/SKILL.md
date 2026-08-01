---
name: silver-dead-letter-queue
description: Esquema y semántica de la tabla silver_dead_letter_queue donde aterrizan los registros de video/comentario que fallan validación Pydantic o integridad referencial. Úsalo al escribir código que rechaza registros, o al diagnosticar por qué faltan datos en silver/gold.
---

# silver-dead-letter-queue

## Alcance

Tabla compartida donde [[silver-validation-videos]] y [[silver-validation-comments]] insertan **todo** registro que no pasa validación — nunca se descarta un registro sin dejar rastro. El pipeline nunca se detiene por un registro inválido individual (matriz de riesgos del PRD: "Fallo en esquema de origen" → impacto Bajo, mitigado exactamente por este mecanismo).

## Esquema (PRD §4.2)

| Columna | Tipo | Descripción |
| :--- | :--- | :--- |
| `error_timestamp` | TIMESTAMP | Momento en que se detectó el error de validación. |
| `comment_id` | STRING | ID del comentario fallido (NULL si no está disponible, ej. error en un video). |
| `video_id` | STRING | ID del video asociado (NULL si no está disponible). |
| `raw_payload` | JSON | Registro original completo en formato JSON. |
| `validation_error` | STRING | Mensaje de error detallado de Pydantic. |
| `error_field` | STRING | Campo específico que falló la validación. |
| `batch_execution_id` | STRING | Identificador de la ejecución del batch para trazabilidad. |

## DDL

```sql
CREATE TABLE IF NOT EXISTS `proyecto.dataset.silver_dead_letter_queue` (
  error_timestamp    TIMESTAMP  NOT NULL,
  comment_id         STRING,
  video_id           STRING,
  raw_payload        JSON       NOT NULL,
  validation_error   STRING     NOT NULL,
  error_field        STRING,
  batch_execution_id STRING     NOT NULL
)
PARTITION BY DATE(error_timestamp);
```

## Carga

Inserción directa (load job o `INSERT` batch), **sin MERGE** — cada rechazo es un evento inmutable, no hay "actualización" de un registro rechazado. Si el mismo registro se vuelve a rechazar en una re-ejecución, se inserta una nueva fila (no se deduplica): eso es intencional, permite ver cuántas veces un dato malo reapareció.

```python
from google.cloud import bigquery

def insert_dead_letters(client: bigquery.Client, table_id: str, rows: list[dict]) -> None:
    if not rows:
        return
    errors = client.insert_rows_json(table_id, rows)
    if errors:
        raise RuntimeError(f"Fallo insertando en dead-letter queue: {errors}")
```

## Consulta de diagnóstico típica

```sql
-- Top motivos de rechazo del último batch semanal
SELECT
  error_field,
  COUNT(*) AS total_rechazos,
  ARRAY_AGG(validation_error LIMIT 3) AS ejemplos
FROM `proyecto.dataset.silver_dead_letter_queue`
WHERE batch_execution_id = @ultimo_batch_id
GROUP BY error_field
ORDER BY total_rechazos DESC;
```

## Invariantes

- **No hay reintentos automáticos** de un registro en dead-letter dentro del mismo batch; se corrige el origen (o el schema) y se re-ingiere en la siguiente ventana semanal.
- **No bloquea el pipeline:** un lote con 500 registros válidos y 3 rechazados completa su MERGE con los 500; los 3 quedan documentados aquí.
- **`raw_payload` siempre completo:** nunca se trunca ni se redacta el JSON original, para permitir inspección forense.

## Relación con otros skills

- Receptor único de rechazos de [[silver-validation-videos]] y [[silver-validation-comments]].
- Consultada por [[docs-maintenance]] al documentar salud del pipeline; útil también en auditorías manuales de [[cost-guardrail]] si un volumen alto de rechazos indica un problema de origen que infla costos de reprocesamiento.
