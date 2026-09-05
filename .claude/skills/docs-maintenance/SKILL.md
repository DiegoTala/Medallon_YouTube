---
name: docs-maintenance
description: Cómo mantener docs/PRD.md, docs/PRD_Fase2.md, README.md y el resto de la documentación del proyecto sincronizados cuando cambia la arquitectura, el costo real observado o el alcance. Úsalo después de cualquier cambio de infraestructura, esquema o skill que haga que la documentación existente quede desactualizada.
---

# docs-maintenance

## Alcance

Hay **dos PRD independientes**: `docs/PRD.md` (pipeline medallón, Fase 1) y `docs/PRD_Fase2.md` (agente RAG conversacional, Fase 2). Cada uno es la especificación de su fase — ninguno es un changelog, y **no se fusionan**: un cambio en el agente no edita el PRD de Fase 1, y viceversa. Lo único que ambos comparten es el techo de costo, cuya fuente de verdad es [[cost-guardrail]]. Este skill define cuándo y cómo actualizar la documentación para que siga reflejando la realidad del sistema, sin convertir el PRD en un documento que cambia constantemente de forma descontrolada.

## Qué se actualiza y cuándo

| Evento | Documento a actualizar | Qué cambiar |
| :--- | :--- | :--- |
| Cambia un esquema Pydantic o DDL de una tabla | `docs/PRD.md` §4/§5 | Reflejar el nuevo contrato de datos exacto. |
| Cambia el costo real observado de forma sostenida | `docs/PRD.md` §6 | Actualizar la tabla de costo estimado, sin borrar los valores originales de diseño (agregar nota de "costo real observado desde <fecha>"). |
| Se agrega/quita un skill del arnés | `CLAUDE.md` y `AGENTS.md` (tabla de skills) | Mantener la tabla de "cuándo usar qué skill" en sync con `.claude/skills/`. |
| Se aprueba y ejecuta un cambio de infraestructura | `infra/APPROVALS.md` | Ya cubierto por [[approval-gate]] — este skill no duplica ese registro. |
| Cambia el alcance del proyecto (ej. más de 5 canales) | `docs/PRD.md` §1/§2 | Requiere confirmación explícita del usuario antes de editar — el alcance no se autoactualiza. |
| Cambia el contrato de `gold_rag_corpus` | `docs/PRD_Fase2.md` §8 **y** `docs/PRD.md` | Es la frontera entre fases: un cambio de esquema afecta a quien lo escribe y a quien lo lee. Ver [[gold-rag-corpus]]. |
| Se activa la ruta de contingencia de autenticación | `docs/PRD_Fase2.md` §11 | Obligatorio **antes** de implementarla — es un cambio de arquitectura. Ver [[rag-iap-auth]]. |
| Cambia una cuota, un límite o el techo de costo | `docs/PRD_Fase2.md` §12/§15 y [[cost-guardrail]] | El techo vive en `cost-guardrail`; el PRD registra la autorización y su fecha. |
| Se ejecuta el set de evaluación antes de un release | `docs/` (reporte de la corrida) | Resultados de las 15 doradas y las 10 adversariales. Ver [[rag-evaluation-suite]]. |

## Qué NO se hace desde este skill

- No se reescribe el PRD para "mejorar la redacción" sin que haya un cambio funcional real que documentar.
- No se borra historial de decisiones de diseño — los cambios se anotan como adiciones/actualizaciones fechadas, no como reemplazos silenciosos.
- No se documenta aquí el registro de aprobaciones de infraestructura — eso vive exclusivamente en `infra/APPROVALS.md` vía [[approval-gate]].

## Snippet de ejemplo: nota de actualización con fecha, sin borrar el original

```markdown
### Presupuesto Operativo Estimado (Máximo $15.00 USD / Mes)

<!-- Estimación de diseño original, PRD v1 -->
* **Costo Total Estimado (diseño):** ~$1.40 - $1.80 USD / mes.

<!-- docs-maintenance: actualización con costo real observado -->
> **Actualización (2026-09-01):** costo real observado en las primeras 4 semanas
> de operación: $1.62 USD/mes promedio, consistente con la estimación de diseño.
> Ver `infra/APPROVALS.md` para el detalle de cambios de infraestructura aplicados.
```

## Invariantes

- **El PRD nunca se edita para justificar un cambio ya hecho sin aprobación** — si un cambio de infraestructura no pasó por [[approval-gate]], documentarlo aquí no lo legitima; hay que señalar la inconsistencia, no ocultarla.
- **Cambios de alcance requieren confirmación explícita del usuario**, igual que cualquier otra decisión de producto — este skill no decide alcance por su cuenta.
- **CLAUDE.md/AGENTS.md se mantienen lean:** al agregar/quitar un skill, solo se toca la fila correspondiente de la tabla, nunca se infla el orquestador con detalle operativo (eso vive en el `SKILL.md` respectivo).

## Relación con otros skills

- Se dispara después de cambios hechos por cualquiera de los otros 31 skills que alteren esquema, costo o alcance.
- El techo de costo no se documenta aquí: su fuente de verdad es [[cost-guardrail]].
- Nunca reemplaza el registro de [[approval-gate]] en `infra/APPROVALS.md`; es documentación complementaria, no redundante.
