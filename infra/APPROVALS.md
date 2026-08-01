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
