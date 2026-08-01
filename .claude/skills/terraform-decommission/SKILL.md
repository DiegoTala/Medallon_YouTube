---
name: terraform-decommission
description: Salvaguardas y flujo obligatorio para eliminar recursos GCP vía Terraform (terraform destroy, o remover un bloque de recurso seguido de apply). Úsalo SIEMPRE que la intención sea borrar/decomisionar infraestructura, nunca reutilices terraform-provision para esto.
---

# terraform-decommission

## Alcance

Cubre exclusivamente la **eliminación** de recursos GCP gestionados por Terraform: `terraform destroy` (completo o `-target` específico), o remover un bloque `resource` del `.tf` y correr `apply` (que Terraform interpreta como destroy de ese recurso). Es un skill separado de [[terraform-provision]] a propósito: crear y borrar tienen perfiles de riesgo distintos y el usuario pidió que no se mezclen.

## Por qué existe como skill separado

Un `apply` que crea un recurso es reversible (se puede volver a destruir). Un `destroy` sobre un dataset de BigQuery con datos de `silver`/`gold`, o sobre un bucket con el `raw` histórico, **no es reversible** — se pierde el dato salvo que exista backup. Esto exige un nivel de fricción deliberadamente mayor al de terraform-provision.

## Flujo obligatorio (más estricto que terraform-provision)

1. `terraform plan -destroy -out=tfplan` (o `-target=<recurso>` si es parcial) y leer el diff completo.
2. Identificar explícitamente si el recurso a borrar **contiene datos** (BigQuery dataset/tabla, bucket GCS no vacío). Si sí:
   - Confirmar con el usuario si existe o se necesita un respaldo (ej. `bq extract` a GCS, o exportar la tabla) **antes** de proponer el destroy.
   - Nunca asumir que "ya no se necesita" el dato — preguntar.
3. Invocar [[cost-guardrail]] para mostrar el ahorro esperado (delta negativo de costo).
4. Presentar al usuario, vía [[approval-gate]], un resumen que incluya explícitamente:
   - Qué se borra (nombre exacto del recurso).
   - Si contiene datos y si hay respaldo confirmado.
   - Que la acción es irreversible.
5. Esperar aprobación **verbatim y específica para el destroy** (una aprobación genérica de "aplica los cambios" dada para otro contexto no cuenta).
6. Ejecutar `terraform apply tfplan`.
7. Registrar en `infra/APPROVALS.md` con la etiqueta `[DESTROY]` al inicio del título de la entrada.

## Snippet de ejemplo: destroy dirigido a un recurso específico

```bash
# Nunca destroy completo del state salvo instrucción explícita del usuario.
terraform plan -destroy -target=google_storage_bucket.staging_temp -out=tfplan
# Revisar el plan, cotizar, obtener aprobación...
terraform apply tfplan
```

## Snippet de ejemplo: respaldo previo de una tabla BigQuery antes de borrarla

```bash
# Paso obligatorio si el recurso a decomisionar tiene datos y no hay backup previo confirmado.
bq extract --destination_format=NEWLINE_DELIMITED_JSON \
  proyecto:dataset.tabla_a_borrar \
  gs://medallon-youtube-backups/pre-destroy/tabla_a_borrar_$(date +%Y%m%d).json
```

## Invariantes

- **Nunca `terraform destroy` sin `-target` salvo instrucción explícita** de decomisionar el ambiente completo — el default es destruir el recurso puntual solicitado, no todo el state.
- **Nunca se ejecuta en el mismo turno de aprobación que un `terraform-provision`** — son dos ciclos de aprobación separados, aunque estén en la misma sesión de trabajo.
- **Datasets/tablas de BigQuery y buckets con datos:** requieren confirmación explícita de respaldo o de que el dato es descartable, antes de siquiera mostrar la cotización.
- Este skill jamás se autoinvoca; siempre requiere que el usuario (o una instrucción explícita derivada de él) pida decomisionar algo.

## Relación con otros skills

- Usa el mismo mecanismo de registro que [[approval-gate]], pero con el flujo más estricto arriba descrito.
- Se apoya en [[cost-guardrail]] para mostrar el ahorro.
- Nunca se usa para "limpiar" staging tables de BigQuery (`TRUNCATE`) — eso es parte normal del flujo idempotente de [[silver-validation-videos]]/[[silver-validation-comments]], no una decomisión de infraestructura.
