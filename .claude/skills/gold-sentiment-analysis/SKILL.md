---
name: gold-sentiment-analysis
description: Cómo clasificar sentimiento de comentarios con ML.GENERATE_TEXT sobre el modelo remoto gemini-2.5-flash de Vertex AI, de forma incremental hacia gold_sentiment_analysis. Úsalo al escribir o modificar la clasificación de sentimiento de la capa Gold.
---

# gold-sentiment-analysis

## Alcance

Clasificar cada comentario de `silver_youtube_comments` como POSITIVO, NEGATIVO, NEUTRO o MIXTO usando el modelo remoto `gemini-2.5-flash` de Vertex AI vía `ML.GENERATE_TEXT`, procesando **solo comentarios nuevos** (nunca reprocesar todo el historial — es el principal control de costo de esta capa).

> **Nota (2026-08-02):** originalmente este skill y el PRD especificaban `gemini-1.5-flash`. Fue retirado de Vertex AI (verificado: `404 NOT_FOUND` al consultar el publisher model) — el `ENDPOINT` se actualizó a `gemini-2.5-flash` en `infra/bigquery.tf`, mismo tier de costo/latencia. El nombre del modelo remoto en BigQuery (`gold.gemini_flash_model`) no cambió, solo el endpoint de Vertex AI al que apunta.

## Prerrequisito de co-ubicación regional

El dataset de BigQuery y el modelo remoto de Vertex AI deben estar en `us-central1` — `ML.GENERATE_TEXT` falla si hay mismatch de región (PRD §3, nota de co-ubicación). El modelo remoto (`gemini_flash_model`) se crea vía [[terraform-provision]], no manualmente.

## MERGE incremental (nunca reprocesa lo ya clasificado)

```sql
MERGE INTO `proyecto.dataset.gold_sentiment_analysis` T
USING (
  SELECT
    comment_id,
    comment_text,
    ml_generate_text_result
  FROM
    ML.GENERATE_TEXT(
      MODEL `proyecto.dataset.gemini_flash_model`,
      (
        SELECT
          s.comment_id,
          s.comment_text,
          CONCAT(
            'Clasifica el sentimiento del siguiente comentario de un video/DJ set como POSITIVO, NEGATIVO, NEUTRO o MIXTO. ',
            'Responde ÚNICAMENTE con una de estas cuatro palabras.',
            '\n\nComentario: ',
            s.comment_text
          ) AS prompt
        FROM `proyecto.dataset.silver_youtube_comments` s
        LEFT JOIN `proyecto.dataset.gold_sentiment_analysis` g
          ON s.comment_id = g.comment_id
        WHERE g.comment_id IS NULL   -- clave del control de costo: solo lo nuevo
      ),
      STRUCT(0.2 AS temperature, 100 AS max_output_tokens)
    )
) S
ON T.comment_id = S.comment_id
WHEN NOT MATCHED THEN
  INSERT (comment_id, comment_text, sentiment_raw, sentiment_label, processed_at)
  VALUES (
    S.comment_id,
    S.comment_text,
    S.ml_generate_text_result,
    JSON_EXTRACT_SCALAR(S.ml_generate_text_result, '$.candidates[0].content.parts[0].text'),
    CURRENT_TIMESTAMP()
  );
```

## Por qué `s.comment_text` va en el SELECT de entrada a ML.GENERATE_TEXT

`ML.GENERATE_TEXT` solo pasa a la salida las columnas presentes en el `SELECT` de su subquery de entrada — no basta con usar `s.comment_text` dentro del `CONCAT` que arma el prompt, hay que seleccionarlo también como columna propia (junto a `comment_id`). Sin esto, el `MERGE` externo falla con `400 BadRequest: Unrecognized name: comment_text` porque esa columna nunca llegó a la salida de `ML.GENERATE_TEXT`. Bug real encontrado en el primer smoke test end-to-end (2026-08-02) — el snippet de arriba ya lo tiene corregido.

## Por qué el filtro `WHERE g.comment_id IS NULL` es crítico

Sin él, cada ejecución semanal volvería a llamar a Gemini para **todos** los comentarios históricos, no solo los ~125 nuevos por semana. Eso convierte un costo de ~$0.80-$1.20 USD/mes en un costo creciente sin techo — es la mitigación explícita del riesgo "Sobrecosto inesperado en Vertex AI" (PRD §6, matriz de riesgos). Nunca quitar este filtro, ni siquiera "para un reproceso puntual" sin pasar antes por [[approval-gate]] con una cotización explícita del volumen a reprocesar.

## Invariantes

- **`WHEN NOT MATCHED THEN INSERT` únicamente** — nunca `WHEN MATCHED THEN UPDATE`: un comentario ya clasificado no se re-clasifica (si el texto no cambia, no tiene sentido y cuesta dinero).
- **Parseo defensivo:** `JSON_EXTRACT_SCALAR` puede devolver NULL si Gemini no respondió con el formato esperado; el consumidor de `sentiment_label` debe tolerar NULL, no asumir que siempre hay una de las 4 etiquetas.
- **Temperature baja (0.2):** para mantener consistencia de clasificación entre ejecuciones — no subir la temperatura sin razón documentada.

## Relación con otros skills

- Consume `silver_youtube_comments` de [[silver-validation-comments]].
- El modelo remoto `gemini_flash_model` se provisiona vía [[terraform-provision]] bajo [[approval-gate]].
- El costo de este paso se estima con [[cost-guardrail]] antes de cualquier cambio (ej. subir `max_output_tokens`, cambiar de modelo).
