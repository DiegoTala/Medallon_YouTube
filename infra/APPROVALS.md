# Bitácora de Aprobaciones de Infraestructura

Registro append-only de toda aprobación de cambios de infraestructura real (GCP), conforme a la regla no negociable definida en [`.claude/skills/approval-gate/SKILL.md`](../.claude/skills/approval-gate/SKILL.md).

**Regla:** ninguna entrada se agrega retroactivamente para "justificar" un cambio ya ejecutado sin aprobación previa. Si eso ocurre, se documenta como incidente, no como aprobación.

**No editar ni borrar entradas existentes** — solo se anexan nuevas al final del archivo.

---

<!--
Plantilla de entrada. Copiar y completar por cada apply/destroy aprobado.
Para decomisiones (terraform-decommission), prefijar el título con [DESTROY].

## <timestamp ISO 8601> — <skill: terraform-provision | terraform-decommission | deploy-release> — <nombre corto del cambio>

- **Recurso(s):** <lista de recursos afectados>
- **Comando:** <comando exacto ejecutado>
- **Costo estimado incremental:** <+/-$X.XX USD/mes>
- **Costo total estimado tras el cambio:** <$Y.YY / $15.00 USD>
- **¿Contiene datos / requirió backup?:** <sí/no, detalle si aplica — obligatorio para DESTROY>
- **Aprobado por:** Diego (verbatim: "<texto exacto de la aprobación>")
- **Ejecutado:** <sí/no — resultado, errores si los hubo>
-->

## 2026-08-02T16:59:30-06:00 — terraform-provision — bootstrap-tfstate-bucket

- **Recurso(s):** google_storage_bucket.tfstate (medallon-youtube-tfstate)
- **Comando:** terraform apply -target=google_storage_bucket.tfstate "tfplan" (backend local temporal, luego `terraform init -migrate-state -force-copy` para migrar al backend "gcs" recién creado)
- **Costo estimado incremental:** $0.00 USD/mes (bucket vacío, Standard Storage us-central1; un state file de Terraform pesa KB, no GB)
- **Costo total estimado tras el cambio:** $0.00 / $15.00 USD
- **¿Contiene datos / requirió backup?:** No — creación, no destrucción; no aplica backup.
- **Aprobado por:** Diego (verbatim: "Aprobado!")
- **Ejecutado:** sí — sin errores. `google_storage_bucket.tfstate` creado (1 added, 0 changed, 0 destroyed). State migrado exitosamente a `gs://medallon-youtube-tfstate/terraform/state/default.tfstate` (verificado con `gcloud storage ls`, solo lectura). Backend "gcs" descomentado en `infra/main.tf`.
