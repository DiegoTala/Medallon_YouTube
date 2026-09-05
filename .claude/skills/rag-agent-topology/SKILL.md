---
name: rag-agent-topology
description: Topología multiagente de Fase 2 con Google ADK — qué agente puede llamar a qué, por qué se usa AgentTool y no delegación por transferencia, y cómo se ejecutan Search y Analytics en paralelo. Úsalo al crear o modificar cualquier agente, o al cambiar cómo se coordinan entre sí.
---

# rag-agent-topology

## Alcance

El contrato de responsabilidades entre los cuatro agentes del PRD Fase 2 §6. Este skill define **quién puede llamar a quién y quién habla con el usuario**. La sustancia de cada herramienta vive en su propio skill; aquí solo está la coordinación.

## Topología

```
usuario
   |
root_router_agent          <- ÚNICO agente que le habla al usuario
   |
   +-- AgentTool(search_agent)      -> semantic_search
   +-- AgentTool(analytics_agent)   -> sentiment_analytics, trend_detection
   +-- AgentTool(synthesis_agent)   -> redacta la respuesta final con citas
```

| Agente | Puede llamar | NUNCA puede |
| :--- | :--- | :--- |
| `root_router_agent` | los tres agentes especializados | consultar BigQuery directamente |
| `search_agent` | `semantic_search` | `sentiment_analytics`, `trend_detection`, hablar con el usuario |
| `analytics_agent` | `sentiment_analytics`, `trend_detection` | `semantic_search`, hablar con el usuario |
| `synthesis_agent` | ninguna herramienta de datos | **tocar BigQuery bajo cualquier forma** |

## Decisión: `AgentTool`, no `sub_agents`

ADK ofrece dos formas de composición y **no son intercambiables aquí**:

- `sub_agents=[...]` → **transferencia**: el control pasa al especialista, que a partir de ahí le habla al usuario directamente.
- `AgentTool(agent=...)` → **llamada**: el coordinador invoca al especialista, recibe un resultado estructurado y **conserva el control**.

Fase 2 usa `AgentTool` en los tres casos. La razón no es estilística: el PRD §6 exige que el Synthesis Agent trabaje *solo con resultados estructurados entregados por los agentes especializados*, y §12 exige que toda respuesta al usuario pase por validación de citas y por el tope de 3.000 tokens. Con transferencia, un especialista puede responderle al usuario sin pasar por ninguno de esos controles.

> **Nota (verificada 2026-09-04, [guía de multi-agentes de ADK](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)):** Google documenta un modo de falla real del patrón de transferencia — el LLM hijo puede no emitir nunca el `transfer_to_agent()` de vuelta al padre, y el usuario queda atrapado conversando con el especialista. En este sistema eso significaría un usuario recibiendo datos de BigQuery sin citas y sin límite de tokens: exactamente los dos invariantes que [[rag-synthesis-citations]] y [[rag-quota-limits]] existen para proteger. `AgentTool` no tiene ese modo de falla porque el control siempre regresa.

## Ejecución en paralelo (preguntas híbridas)

El PRD §6 permite que el Router ejecute Search y Analytics en paralelo. En ADK eso es `ParallelAgent` seguido de la síntesis dentro de un `SequentialAgent`:

```python
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

hybrid_fanout = ParallelAgent(
    name="hybrid_fanout",
    sub_agents=[search_agent, analytics_agent],
)

hybrid_pipeline = SequentialAgent(
    name="hybrid_pipeline",
    sub_agents=[hybrid_fanout, synthesis_agent],
)
```

Cada especialista escribe su resultado en el estado de sesión vía `output_key`, y la síntesis lo lee por nombre desde su `instruction`:

```python
search_agent = LlmAgent(name="search_agent", model=MODEL,
                        tools=[semantic_search], output_key="search_result")
analytics_agent = LlmAgent(name="analytics_agent", model=MODEL,
                           tools=[sentiment_analytics, trend_detection],
                           output_key="analytics_result")
```

> **Nota (verificada 2026-09-04, [ParallelAgent en la doc de ADK](https://adk.dev/agents/workflow-agents/parallel-agents/)):** las ramas de un `ParallelAgent` **no comparten estado ni historial durante la ejecución**. Esto no es una limitación a sortear — es justamente lo que hace que Search y Analytics no puedan contaminarse entre sí, y que la síntesis reciba dos resultados independientes. No intentes coordinarlos durante la ejecución; el punto de encuentro es el `output_key` que leen después.

El `SequentialAgent` es lo que garantiza que la síntesis corra **después** de que ambas ramas terminaron. Sin él, la síntesis leería `output_key` vacíos.

## Herramientas como funciones Python

ADK convierte funciones Python en herramientas por inspección de la firma: nombre, docstring, type hints y valores por defecto. Ver la forma exacta en cada skill de tool.

> **Nota (verificada 2026-09-04, [function tools en ADK](https://adk.dev/tools-custom/function-tools/)):** el docstring **es** la descripción que ve el modelo — no es documentación interna, es parte del prompt. Un docstring vago produce un tool mal invocado. El tipo de retorno preferido es `dict`, e incluir una clave `status` (`"success"` / `"error"`) es la convención documentada; un retorno que no sea `dict` se envuelve automáticamente en `{"result": ...}`.

## Contexto situacional: el modelo no tiene reloj ni catálogo

Las instrucciones de `root_router_agent`, `search_agent` y `analytics_agent` se
componen en tiempo de ejecución con un bloque que trae la **fecha de hoy**, los
periodos relativos ya resueltos y los **nombres exactos de los canales con
datos** (`rag_agent/agents/context.py`).

Sin ese bloque el agente no está siendo rígido, está siendo correcto: "el último
mes" es literalmente irresoluble sin saber qué día es, así que pedía fechas en
`AAAA-MM-DD`. Lo mismo con los canales — sin la lista no puede saber si "Garrix"
existe ni cuál es su grafía exacta para el filtro.

**Se calcula por request, no al construir el pipeline.** ADK acepta `instruction`
como callable, y aquí eso importa: una instancia de Cloud Run vive horas o días,
así que una fecha horneada al arranque estaría equivocada al día siguiente —
silenciosamente y de forma plausible, que es el peor tipo de error.

La síntesis **no** recibe este bloque: no elige filtros ni resuelve fechas, y su
prompt ya es el más largo del sistema.

La degradación es parcial y en ese orden: si BigQuery falla, se pierde el
catálogo de canales pero **se conserva la fecha**. Perder los canales hace que el
agente pregunte por el DJ; perder la fecha lo devolvería a pedir `AAAA-MM-DD`.

## Pedir aclaración es el último recurso, no el primero

Una instrucción del tipo *"si el usuario no especifica canal o periodo, NO
asumas — devuelve un error indicando qué parámetros faltan"* convierte cada
pregunta natural en un formulario. Estuvo en `analytics_agent` y producía
exactamente eso.

La regla correcta: **una pregunta sin fechas no está incompleta, significa "sobre
todo lo que haya"**. Los filtros de las tres herramientas son opcionales por
diseño. Solo se pide aclaración cuando el dato falta de verdad y no se puede
deducir — un video sin `video_id`, un DJ que no está en el catálogo — y cuando se
pide, se pide en lenguaje natural, nunca en un formato de fecha.

## Invariantes

- **La fecha y el catálogo se inyectan por request**, nunca al construir el pipeline.
- **Una pregunta sin filtros no es ambigua.** Aclarar es el último recurso, y jamás pidiendo `AAAA-MM-DD`.

- **Un solo agente le habla al usuario:** `root_router_agent`. Todo lo demás devuelve datos estructurados.
- **`synthesis_agent` sin acceso a datos:** no recibe herramientas de BigQuery, ni credenciales, ni tablas. Solo texto y estructuras que le pasan los otros. Ver [[rag-synthesis-citations]].
- **`AgentTool`, nunca transferencia** para los tres especialistas, por la razón documentada arriba.
- **Cambiar la topología cambia la clave de caché:** la versión del prompt es parte de la clave de [[rag-response-cache]]. Modificar instrucciones de agentes sin subir esa versión sirve respuestas viejas en silencio.
- **La versión de ADK se fija en el lockfile.** ADK cambia rápido; los snippets de este arnés están verificados contra la 2.8.0 (2026-09-05). Al subir de versión, revalidar los snippets de este skill antes de asumir que siguen siendo correctos.

> **Nota (verificada 2026-09-05 contra ADK 2.8.0 instalada):** `SequentialAgent` y `ParallelAgent` emiten `DeprecationWarning` — ADK los está reemplazando por `Workflow`. **No migrar todavía:** el aviso dice literalmente que *"Workflow cannot yet be used as an LlmAgent sub-agent"*, y aquí el pipeline híbrido se expone como `AgentTool` del router, que es exactamente ese caso. Los dos siguen siendo la construcción correcta hoy. Revisar cuando `Workflow` soporte ese uso.

- **La topología se verifica en tests, no solo en el diagrama.** `tests/test_rag_topology.py` afirma que el pipeline híbrido es un `SequentialAgent` cuyo primer hijo es un `ParallelAgent`. Esto existe porque la topología estuvo documentada aquí y en el docstring de `orchestrator.py` durante días **sin estar implementada**: se importaban `ParallelAgent` y `SequentialAgent` y no se usaba ninguno. Un diagrama no falla cuando el código deja de corresponderle; un test sí.

## Relación con otros skills

- Las tres herramientas: [[rag-tool-semantic-search]], [[rag-tool-sentiment-analytics]], [[rag-tool-trend-detection]].
- La redacción final y sus reglas: [[rag-synthesis-citations]].
- Los límites que el Router aplica antes de invocar a nadie: [[rag-quota-limits]] y [[rag-security-guardrails]].
- Dónde se monta todo esto: [[rag-fastapi-service]].
