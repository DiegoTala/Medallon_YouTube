---
name: cost-guardrail
description: Metodología de estimación estática de costo (sin llamar a la Billing API real) para cualquier cambio propuesto en infraestructura o volumen de procesamiento, comparado contra el techo vigente del proyecto. Este skill es la ÚNICA fuente de verdad del techo. Úsalo SIEMPRE que approval-gate lo requiera, o antes de proponer cualquier cambio con impacto de costo.
---

# cost-guardrail

## Alcance

Producir una estimación **estática** (basada en el pricing público de GCP y los supuestos de volumen del PRD, no en la Billing API en tiempo real) de cuánto agrega o resta un cambio propuesto, y compararla contra el **techo vigente** definido abajo. Esta estimación es el insumo obligatorio que [[approval-gate]] exige mostrar antes de cualquier `apply`/`destroy`.

## Techo vigente (fuente de verdad del proyecto)

| Techo | Valor | Origen |
| :--- | ---: | :--- |
| Sub-techo Fase 1 (pipeline) | $15.00 USD/mes | `docs/PRD.md` §6 |
| Delta máximo Fase 2 (agente RAG) | $5.00 USD/mes | `docs/PRD_Fase2.md` §3 |
| **Techo total del proyecto** | **$20.00 USD/mes** | `docs/PRD_Fase2.md` §15 — autorizado por Diego, 2026-09-04 |

Toda cotización se compara contra el **techo total de $20.00**, y si el cambio es de Fase 2 se compara **además** contra el delta de $5.00. Un cambio de Fase 2 que quepa en los $20 totales pero rompa su propio delta de $5 se marca igual: el PRD Fase 2 §3 fija ese delta como objetivo, no como consecuencia.

Ningún otro skill hardcodea un techo. [[approval-gate]] pide la cotización a este skill precisamente para que el número viva en un solo lugar.

## Línea base (PRD §6 y PRD Fase 2 §15)

| Componente | Costo estimado/mes |
| :--- | :--- |
| Cloud Scheduler | $0.00 (nivel gratuito) |
| Cloud Run Jobs | ~$0.15 |
| Cloud Storage (GCS) | ~$0.03 |
| BigQuery (storage + queries) | ~$0.40 |
| Vertex AI (Gemini + Embeddings) | ~$0.80 – $1.20 |
| **Subtotal Fase 1** | **~$1.40 – $1.80** |
| Cloud Run Service (scale-to-zero) | $0.00 – $1.00 |
| Gemini (agente, 30 consultas/día/usuario) | $0.50 – $2.00 |
| Embeddings de consultas | $0.02 – $0.20 |
| BigQuery (consultas del agente) | $0.10 – $0.50 |
| Firestore (memoria y caché) | $0.00 – $0.10 |
| Logging y artefactos | $0.05 – $0.30 |
| **Subtotal Fase 2** | **~$1.00 – $4.50** |
| **Total estimado** | **~$2.40 – $6.30 / $20.00 techo** |

Esta tabla es el punto de partida: cualquier estimación nueva se presenta como "línea base + delta del cambio propuesto", no recalculada desde cero cada vez, salvo que haya evidencia (vía [[gcloud-diagnostics]] o facturación real observada) de que la línea base cambió.

## Costos que no son de GCP pero sí son del proyecto

No todo lo que consume el techo aparece en la factura de Google Cloud. El caso vigente:

- **Identidades de usuario.** Las tres cuentas de Fase 2 viven en `talamantes.com.mx` y se crean como **Cloud Identity Free** ($0, 50 licencias gratuitas por omisión). Pero si el dominio tiene activo el aprovisionamiento automático de licencias, un usuario nuevo recibe una licencia de **Google Workspace de pago** — y dos de esas exceden por sí solas el techo de $20/mes del proyecto completo. Verificar antes de crear cualquier identidad; detalle en [[rag-iap-auth]].

La regla general: si un cambio agrega **usuarios, licencias o suscripciones**, cotízalo aunque no sea un recurso de Terraform. El techo es del proyecto, no del proveedor.

## Metodología de estimación por componente

- **Cloud Run Jobs:** `costo ≈ (vCPU-segundos × precio_vCPU) + (GiB-segundos × precio_memoria)`. Con duración < 3 min/semana y recursos mínimos (1 vCPU, 512Mi), el costo es marginal — recalcular solo si cambian los límites de recursos o la frecuencia.
- **GCS:** `costo ≈ GB_almacenados × precio_clase_almacenamiento + operaciones`. Con <20MB/mes de JSON y regla de borrado a 90 días, el crecimiento es acotado — recalcular si cambia el volumen de canales/comentarios o se elimina la lifecycle rule.
- **BigQuery:** `costo ≈ GB_procesados_por_query × $6.25/TB (on-demand)` + storage activo (~$0.02/GB/mes tras 90 días). El filtro incremental de Gold (`WHERE ... IS NULL`) es lo que mantiene los GB procesados bajos — cualquier cambio que amplíe el `WHERE` a un rango histórico completo dispara este costo.
- **Vertex AI (Gemini):** `costo ≈ num_comentarios_nuevos × (tokens_prompt + tokens_respuesta) × precio_por_1K_tokens`. Con ~125 comentarios/semana y `max_output_tokens=100`, el volumen es el driver principal — escala linealmente con el número de comentarios nuevos, no con el histórico.
- **Vertex AI (Embeddings):** análogo, `costo ≈ num_comentarios_nuevos × precio_por_1K_tokens_embedding`.

## Snippet de ejemplo: calculadora de estimación incremental (Python, para uso interno del agente, no para producción)

```python
PRECIOS_REFERENCIA_USD = {
    "bq_query_per_tb": 6.25,
    "gemini_flash_per_1k_input_tokens": 0.000075,
    "gemini_flash_per_1k_output_tokens": 0.0003,
    "embedding_per_1k_tokens": 0.000025,
}

def estimar_delta_gold(nuevos_comentarios: int, tokens_prompt_promedio: int = 60) -> float:
    tokens_input = nuevos_comentarios * tokens_prompt_promedio
    tokens_output = nuevos_comentarios * 4  # 1 palabra de las 4 etiquetas ~= 1-2 tokens, margen a 4
    costo_sentiment = (
        (tokens_input / 1000) * PRECIOS_REFERENCIA_USD["gemini_flash_per_1k_input_tokens"]
        + (tokens_output / 1000) * PRECIOS_REFERENCIA_USD["gemini_flash_per_1k_output_tokens"]
    )
    costo_embeddings = (tokens_input / 1000) * PRECIOS_REFERENCIA_USD["embedding_per_1k_tokens"]
    return round(costo_sentiment + costo_embeddings, 4)
```

## Formato de salida obligatorio para approval-gate

```
Costo base actual estimado: $X.XX USD/mes
Delta estimado del cambio propuesto: +$Y.YY USD/mes (o -$Y.YY si es una decomisión)
Costo total estimado tras el cambio: $Z.ZZ / $20.00 USD (techo vigente)
Margen restante: $(20.00 - Z.ZZ) USD (~W% del techo)
[Si el cambio es de Fase 2] Delta acumulado Fase 2: $D.DD / $5.00 USD
```

Si `Z.ZZ` se acerca a $20.00 (ej. >70% del techo) o lo supera, o si el delta acumulado de Fase 2 supera $5.00, se marca explícitamente como **ALERTA** en el mensaje a [[approval-gate]] — no basta con mostrar el número, hay que señalarlo.

## Invariantes

- **Estimación estática, no Billing API real:** este skill no llama a ninguna API de facturación; es una calculadora basada en pricing público y supuestos del PRD. Si se necesita costo real observado, eso es un diagnóstico vía [[gcloud-diagnostics]]/consola de Billing, no responsabilidad de este skill.
- **Siempre relativo al techo vigente de $20 USD/mes** (y al delta de $5 si es Fase 2), nunca un número aislado sin contexto de cuánto margen queda.
- **Cualquier estimación que supere el techo se marca como bloqueante** — [[approval-gate]] no debe presentar eso como una aprobación de rutina.

## Relación con otros skills

- Invocado por [[approval-gate]] antes de cualquier `apply`/`destroy`.
- Usado por [[terraform-provision]] y [[terraform-decommission]] para cotizar sus cambios.
- Puede apoyarse en [[gcloud-diagnostics]] para verificar volúmenes reales (ej. cantidad actual de comentarios en `silver_youtube_comments`) antes de proyectar un delta.
