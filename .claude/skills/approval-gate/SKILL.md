---
name: approval-gate
description: Regla no negociable de autorización previa para cualquier operación de infraestructura que mute recursos GCP reales (terraform apply, terraform destroy). Úsalo SIEMPRE antes de ejecutar terraform-provision, terraform-decommission o cualquier acción que cree, modifique o borre recursos facturables.
---

# approval-gate

## Regla (no negociable)

Ningún agente ejecuta `terraform apply`, `terraform destroy`, ni ningún comando `gcloud` que mute estado (crear, modificar, borrar, habilitar APIs de facturación) **sin antes**:

1. Mostrar el **plan** exacto de lo que se va a ejecutar (`terraform plan` completo, o el comando `gcloud` literal).
2. Mostrar una **cotización de costo** para el recurso/cambio, usando [[cost-guardrail]] y comparándola contra el techo de $15 USD/mes del PRD.
3. Esperar **aprobación explícita y verbatim** de Diego en el chat (ej. "apruebo", "adelante", "sí, aplica"). Un "ok" ambiguo o el silencio **no cuentan** como aprobación.
4. Solo entonces ejecutar, y **inmediatamente después** registrar la aprobación en `infra/APPROVALS.md`.

Esta regla aplica a **todo** cambio mutante, sin excepción por "cambio pequeño", "solo habilitar una API" o "ya lo habíamos aprobado antes de forma similar". Cada aplicación de Terraform requiere su propio ciclo plan → cotización → aprobación → registro.

No aplica a operaciones de solo lectura (`terraform plan`, `terraform show`, cualquier comando de [[gcloud-diagnostics]]) — esas se pueden ejecutar libremente para informar el plan y la cotización.

## Por qué existe

El presupuesto operativo máximo es $15 USD/mes (ver PRD §6). Un recurso mal configurado (ej. un índice vectorial IVF sobredimensionado, un Cloud Run Job sin límites de memoria, un dataset BigQuery en la región equivocada que obliga a duplicar datos) puede consumir ese margen sin que nadie lo note hasta la factura. La autorización previa es el único control real antes de que el gasto ocurra.

## Flujo estándar

```
1. Agente corre `terraform plan` (o `gcloud ... --dry-run` si existe)
2. Agente resume el plan en lenguaje claro: qué se crea/cambia/borra
3. Agente invoca cost-guardrail → obtiene estimación de costo incremental
4. Agente presenta al usuario:
   "Plan: <resumen>
    Costo estimado adicional: $X.XX USD/mes (nuevo total estimado: $Y.YY / techo $15.00)
    ¿Apruebas aplicar este cambio?"
5. Usuario responde explícitamente en el chat
6. Si aprueba → ejecutar → anexar entrada en infra/APPROVALS.md
7. Si no aprueba o pide cambios → no ejecutar, ajustar plan y repetir desde el paso 1
```

## Formato de entrada en infra/APPROVALS.md

Cada aprobación se anexa (nunca se sobreescribe el historial) con este formato:

```markdown
## 2026-07-31T22:10:00-06:00 — terraform-provision — bigquery-datasets

- **Recurso(s):** google_bigquery_dataset.bronze, google_bigquery_dataset.silver, google_bigquery_dataset.gold
- **Comando:** terraform apply -target=module.bigquery
- **Costo estimado incremental:** $0.00 USD/mes (sin storage aún)
- **Costo total estimado tras el cambio:** $0.00 / $15.00 USD
- **Aprobado por:** Diego (verbatim: "apruebo, adelante")
- **Ejecutado:** sí — sin errores
```

Ver plantilla completa en `infra/APPROVALS.md`.

## Relación con otros skills

- [[terraform-provision]] y [[terraform-decommission]] invocan este gate antes de cualquier `apply`/`destroy`.
- [[cost-guardrail]] provee la cotización que este gate exige mostrar.
- [[gcloud-diagnostics]] queda exento porque es estrictamente de solo lectura.
- [[deploy-release]] también pasa por este gate al actualizar la imagen de un Cloud Run Job, porque es una mutación de un recurso real.
