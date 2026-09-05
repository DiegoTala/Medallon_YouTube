---
name: rag-tool-trend-detection
description: Contrato de la herramienta trend_detection — comparación entre dos periodos sobre gold_rag_corpus, con nivel de evidencia obligatorio y ejecución solo bajo demanda explícita. Úsalo al escribir o modificar esta herramienta.
---

# rag-tool-trend-detection

## Alcance

Comparar una métrica entre un **periodo actual** y un **periodo base** sobre [[gold-rag-corpus]] (PRD Fase 2 §7), y devolver el cambio con una calificación honesta de cuánta evidencia lo respalda.

## Contrato

| Entrada | Tipo | Regla |
| :--- | :--- | :--- |
| `current_from` / `current_to` | `str` | ISO 8601, obligatorios |
| `baseline_from` / `baseline_to` | `str` | ISO 8601, obligatorios |
| `channel_name` | `str \| None` | debe existir en el corpus |
| `metric` | `str` | catálogo cerrado: `positive_ratio`, `negative_ratio`, `comment_volume`, `avg_likes` |

Salida (`dict` con `status`): `absolute_change`, `percent_change`, `direction` (`up` / `down` / `flat`), `evidence_level`, `periods` (los cuatro límites, ecoados), `n_current`, `n_baseline` y las citas a los datos.

## Solo bajo demanda explícita

El PRD §7 lo dice y §4 lo refuerza poniendo alertas proactivas y digests fuera de alcance: **las tendencias se calculan únicamente cuando el usuario las pide**. Ningún callback, ningún cron, ningún "ya que estamos" del Router al responder otra cosa. Cada corrida no solicitada es costo de Vertex AI y de BigQuery que nadie pidió, y el PRD §15 dimensionó el presupuesto sobre 30 consultas diarias solicitadas.

## Nivel de evidencia (no es decorativo)

Con ~3,239 comentarios repartidos en 10 canales, una ventana de dos semanas para un canal puede tener 12 comentarios. Un salto de "20% positivo" a "40% positivo" sobre esa base **no es una tendencia**, y presentarlo como tal es exactamente la falla que el PRD §13 mide con "0 respuestas que inventen datos".

Regla mínima, aplicada en código y devuelta siempre:

| `evidence_level` | Condición | Qué debe hacer la síntesis |
| :--- | :--- | :--- |
| `insufficient` | `n_current < 30` o `n_baseline < 30` | reportar el cambio **y** advertir que la muestra no lo sostiene |
| `weak` | ambos ≥ 30, alguno < 100 | reportar con la reserva explícita |
| `solid` | ambos ≥ 100 | reportar normalmente |

Los umbrales son un piso pragmático para el volumen actual, no una prueba estadística. Si el corpus crece un orden de magnitud, revísalos — pero **nunca los quites**: la herramienta jamás devuelve un cambio sin decir sobre cuántas filas se calculó.

`percent_change` con `n_baseline = 0` es división por cero: se devuelve `direction: "flat"`, `evidence_level: "insufficient"` y `percent_change: None`, nunca un infinito ni un 100% inventado.

## Forma de la consulta

Un solo escaneo con agregación condicional, no dos consultas — mitad de bytes facturados y ambos periodos garantizadamente sobre la misma versión del corpus:

```sql
SELECT
  COUNTIF(comment_published_at BETWEEN @current_from  AND @current_to)  AS n_current,
  COUNTIF(comment_published_at BETWEEN @baseline_from AND @baseline_to) AS n_baseline,
  AVG(IF(comment_published_at BETWEEN @current_from AND @current_to,
         IF(sentiment_label = 'positivo', 1.0, 0.0), NULL))            AS current_metric,
  AVG(IF(comment_published_at BETWEEN @baseline_from AND @baseline_to,
         IF(sentiment_label = 'positivo', 1.0, 0.0), NULL))            AS baseline_metric
FROM `proyecto.gold.gold_rag_corpus`
WHERE (@channel_name IS NULL OR channel_name = @channel_name)
  AND comment_published_at BETWEEN @baseline_from AND @current_to;
```

El `WHERE` externo acota el escaneo al rango total; sin él se escanea el corpus completo aunque los periodos sean de una semana.

## Invariantes

- **Nunca proactiva.** Solo se invoca cuando el usuario pide una comparación temporal.
- **`evidence_level` siempre presente** en la salida, y siempre calculado sobre los `n` reales.
- **`metric` de catálogo cerrado**, igual que las plantillas de [[rag-tool-sentiment-analytics]]. Sin métricas ad hoc.
- **Los periodos se devuelven ecoados** en la respuesta: el usuario debe poder ver contra qué se comparó sin confiar en la redacción del modelo.
- **Parámetros tipados, cero interpolación**, y `maximum_bytes_billed` presente — ver [[rag-quota-limits]].
- **Solapamiento permitido pero reportado:** si los dos periodos se traslapan, la herramienta lo señala en la salida en vez de rechazar o de callarlo.

## Relación con otros skills

- Lee exclusivamente de [[gold-rag-corpus]].
- La invoca `analytics_agent` junto a [[rag-tool-sentiment-analytics]] — ver [[rag-agent-topology]].
- `evidence_level` es de lectura obligatoria para [[rag-synthesis-citations]]: una tendencia `insufficient` no puede redactarse como hallazgo.
- Sus cinco preguntas de tendencia viven en [[rag-evaluation-suite]].
