"""App FastAPI de Fase 2 — punto de entrada del agente RAG.

Ver .claude/skills/rag-fastapi-service/SKILL.md.
Cadena de middleware (orden obligatorio):
  1. IAP -> 2. identidad -> 3. sanitización -> 4. rate limit ->
  5. cuota diaria -> 6. caché -> 7. historial -> 8. Router ->
  8b. validación de citas -> 9. persistencia

La validación de citas (8b) corre contra los resultados reales de las
herramientas, no contra metadata que el modelo controle: ver
rag-synthesis-citations. Una respuesta con citas sin evidencia se degrada y
no se cachea.

El healthcheck NO consulta BigQuery ni Vertex AI — un healthcheck que gasta
es un gasto recurrente por diseño.
"""

from __future__ import annotations

import logging
import os
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.cloud import bigquery, firestore
from google.genai import types

from rag_agent.agents.orchestrator import MODEL, build_agent_pipeline
from rag_agent.middleware.auth import authenticate_identity, display_name
from rag_agent.middleware.cache import get_cached_response, store_response
from rag_agent.middleware.citations import (
    MENSAJE_DEGRADADO,
    MENSAJE_NUMEROS,
    collect_tool_payloads,
    es_cacheable,
    render_inline_citations,
    tools_used,
    validate_citations,
    validate_numeric_claims,
)
from rag_agent.middleware.quota import (
    DAILY_QUOTA,
    check_daily_quota,
    check_global_circuit,
    check_rate_limit,
    get_quota_remaining,
    quota_limit_for,
)
from rag_agent.middleware.sanitize import sanitize
from rag_agent.catalog import get_available_channels
from rag_agent.tools.evidence import WEAK_BELOW
from rag_agent.memory.common_queries import record_query
from rag_agent.memory.session import create_session, get_recent_sessions, load_session_messages, save_message
from rag_agent.versions import PROMPT_VERSION, get_corpus_version

# Sin esto, ningún logger del proyecto emite: los diagnósticos que se
# escribieron para calibrar el umbral de relevancia y para registrar citas
# inventadas nunca llegaron a Cloud Logging. Un log que no se escribe es peor
# que no tenerlo, porque uno cree que lo tiene.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("rag_agent")

app = FastAPI(title="YouTube DJ Analytics — RAG Agent", version="0.1.0")

# Static files (UI)
app.mount("/static", StaticFiles(directory="src/rag_agent/static"), name="static")

# Clientes a nivel de módulo (una vez por instancia, no por request).
# Ver rag-fastapi-service: "la inicialización pesada va a nivel de módulo,
# para que ocurra una vez por instancia y no por request."
db = firestore.Client(database="rag-memory")
bq_client = bigquery.Client(project=os.environ.get("GCP_PROJECT", "medallon-youtube"))

# Configuración
GCP_PROJECT = os.environ.get("GCP_PROJECT", "medallon-youtube")
GOLD_DATASET = os.environ.get("GOLD_DATASET", "gold")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")

# Pipeline de agentes ADK (se construye una vez por instancia)
root_agent = build_agent_pipeline(bq_client, GCP_PROJECT, GOLD_DATASET, GCP_REGION, db=db)
session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name="rag_agent",
    session_service=session_service,
)


@app.get("/health")
async def health() -> PlainTextResponse:
    """Healthcheck sin costo — no consulta BigQuery ni Vertex AI."""
    return PlainTextResponse("ok")


# Lo que el agente sabe hacer, uno por herramienta. Vive aquí y no en el HTML
# para que la UI no pueda prometer una capacidad que el backend no tiene.
CAPACIDADES = [
    {
        "titulo": "Buscar qué dice la gente",
        "ejemplo": "¿Qué opinan de los drops de Martin Garrix?",
    },
    {
        "titulo": "Analizar sentimiento",
        "ejemplo": "¿Cómo es el sentimiento de ILLENIUM comparado con Alesso?",
    },
    {
        "titulo": "Detectar tendencias",
        "ejemplo": "¿Cambió la reacción a Avicii en agosto contra julio?",
    },
]

DESCRIPCION = (
    "Soy un agente de análisis de comentarios de YouTube. Trabajo sobre los "
    "comentarios que el público deja en los canales de estos DJs: los busco, "
    "los analizo y te respondo solo con lo que dicen, citando siempre de dónde "
    "salió cada cosa. No opino ni relleno con conocimiento general — si no hay "
    "datos, te lo digo."
)

# Umbral para decir "tengo poco de este canal". Es el mismo con el que las
# herramientas marcan la evidencia como débil, así que el aviso de la
# bienvenida y las advertencias de las respuestas dicen lo mismo.
POCOS_COMENTARIOS = WEAK_BELOW


def _aviso_de_cobertura(canales: list[dict]) -> str:
    """Aviso honesto de MVP: cuánto hay, de qué sobra y de qué falta.

    Que el usuario sepa el sesgo ANTES de preguntar cambia cómo lee cualquier
    comparación. Sin esto, "Zedd es 100% positivo" y "Martin Garrix es 82%
    positivo" se leen como cifras equivalentes, y una está calculada sobre
    seis comentarios.
    """
    if not canales:
        return (
            "Soy un MVP y ahora mismo no tengo comentarios cargados, así que "
            "no voy a poder responder gran cosa todavía."
        )

    total = sum(c["n_comments"] for c in canales)
    desde = min(c["desde"] for c in canales)
    hasta = max(c["hasta"] for c in canales)

    abundantes = [c for c in canales if c["n_comments"] >= POCOS_COMENTARIOS]
    escasos = [c for c in canales if c["n_comments"] < POCOS_COMENTARIOS]

    partes = [
        f"Ojo, soy un MVP: mi base de conocimiento todavía es chica — "
        f"{total:,} comentarios de {len(canales)} canales, publicados entre el "
        f"{desde} y el {hasta}."
    ]
    if abundantes:
        partes.append(
            "Donde tengo bastante material: "
            + ", ".join(f"{c['channel_name']} ({c['n_comments']})" for c in abundantes)
            + "."
        )
    if escasos:
        partes.append(
            "Donde tengo poco, y por eso cualquier conclusión ahí es frágil: "
            + ", ".join(f"{c['channel_name']} ({c['n_comments']})" for c in escasos)
            + "."
        )
    partes.append(
        "Cuando una respuesta se apoye en pocos datos te lo voy a decir, en "
        "vez de presentarla como si fuera sólida."
    )
    return " ".join(partes)


@app.get("/welcome")
async def welcome(request: Request) -> JSONResponse:
    """Datos de la pantalla de bienvenida.

    NO consume cuota diaria: no invoca al Router ni a Vertex AI. Gastar una de
    las 30 consultas del día por cargar la página sería cobrarle al usuario por
    leer el menú. La cuota se lee con get_quota_remaining(), que no incrementa.
    """
    sub, email = authenticate_identity(request)

    canales = get_available_channels(bq_client, GCP_PROJECT, GOLD_DATASET)
    limite = quota_limit_for(email)
    restantes = get_quota_remaining(db, sub, limite)

    return JSONResponse(content={
        "nombre": display_name(email),
        "descripcion": DESCRIPCION,
        "aviso_cobertura": _aviso_de_cobertura(canales),
        "capacidades": CAPACIDADES,
        # Solo los canales CON comentarios: los 10 configurados en Fase 1 no
        # son los que se pueden responder.
        "djs": [c["channel_name"] for c in canales],
        # limite None -> sin tope; la UI lo muestra como ilimitado.
        "cuota": {"restantes": restantes, "limite": limite},
    })


@app.get("/", response_class=HTMLResponse)
async def root():
    """Sirve la UI del chat."""
    with open("src/rag_agent/static/index.html") as f:
        return HTMLResponse(content=f.read())


@app.post("/chat")
async def chat(request: Request) -> JSONResponse:
    """Endpoint principal del agente RAG.

    Cadena completa: auth -> sanitize -> rate limit -> quota -> cache -> agent.
    """
    try:
        # 1-2. IAP + identidad
        user_id, email = authenticate_identity(request)

        # Parsear body
        body = await request.json()
        raw_query = body.get("query", "")
        if not raw_query or not raw_query.strip():
            return JSONResponse(
                status_code=400,
                content={"error": "La consulta no puede estar vacía."},
            )

        # 3. Sanitización
        query = sanitize(raw_query)
        if not query:
            return JSONResponse(
                status_code=400,
                content={"error": "La consulta no tiene contenido válido después de sanitizar."},
            )

        # 4. Rate limit
        if not check_rate_limit(db, user_id):
            return JSONResponse(
                status_code=429,
                content={"error": "Límite de 5 consultas por minuto. Intenta en unos segundos."},
            )

        # 5a. Circuito de protección agregado — ANTES de la cuota por usuario.
        # Con una identidad sin tope, esto es lo único que detiene un bucle.
        if not check_global_circuit(db):
            return JSONResponse(
                status_code=503,
                content={"error": (
                    "El servicio alcanzó su límite agregado de consultas del "
                    "día y se detuvo por protección de costo. Vuelve mañana."
                )},
            )

        # 5b. Cuota diaria del usuario (puede tener excepción, ver quota_limit_for)
        limite = quota_limit_for(email)
        allowed, remaining = check_daily_quota(db, user_id, limite)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": f"Agotaste las {limite} consultas diarias. Vuelve mañana."},
            )

        # 6. Caché — la clave se versiona por corpus, prompt y modelo
        # (rag-response-cache). Sin versión de corpus no se usa el caché: es
        # preferible pagar la consulta que servir números viejos sobre datos
        # nuevos sin ninguna señal.
        corpus_version = get_corpus_version(bq_client, GCP_PROJECT, GOLD_DATASET)
        cache_enabled = corpus_version is not None

        cached = (
            get_cached_response(
                db, query, {}, "es",
                corpus_version, PROMPT_VERSION, MODEL, user_id,
            )
            if cache_enabled
            else None
        )
        if cached:
            # Registrar consulta frecuente (hit de caché igual cuenta)
            record_query(db, user_id, query, {}, "es")
            return JSONResponse(content={
                "response": cached["response"],
                "citations": cached["citations"],
                "cached": True,
                "quota_remaining": remaining,
            })

        # 7. Historial — obtener o crear sesión
        sessions = get_recent_sessions(db, user_id, limit=1)
        if sessions:
            session_id = sessions[0]["id"]
            history = load_session_messages(db, user_id, session_id)
        else:
            session_id = create_session(db, user_id)
            history = []

        # Construir contexto de historial para el agente
        history_context = ""
        if history:
            recent = history[-6:]  # últimos 3 intercambios
            history_context = "\n".join(
                f"{m['role']}: {m['content']}" for m in recent
            )

        # 8. Agentes y herramientas — ejecutar pipeline ADK
        full_query = query
        if history_context:
            full_query = f"Contexto de conversación reciente:\n{history_context}\n\nConsulta actual: {query}"

        # Crear sesión ADK y ejecutar
        adk_session = await session_service.create_session(
            app_name="rag_agent",
            user_id=user_id,
        )
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=full_query)],
        )

        response_text = ""
        # Resultados REALES de las herramientas — la evidencia contra la que se
        # validan las citas. No se derivan del texto del modelo ni de metadata
        # que el modelo controle. Ver rag-synthesis-citations.
        tool_payloads: list[tuple[str, dict]] = []

        async for event in runner.run_async(
            user_id=user_id,
            session_id=adk_session.id,
            new_message=user_message,
        ):
            tool_payloads.extend(collect_tool_payloads(event))
            if event.is_final_response():
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text

        # Validar que la respuesta no esté vacía
        if not response_text:
            response_text = "No pude generar una respuesta. Por favor, intenta reformular tu pregunta."

        # 8b. Validación de citas EN CÓDIGO contra los resultados de las tools.
        # Una cita que no corresponde a ningún comment_id devuelto es una
        # alucinación: la respuesta se degrada, no se envía y no se cachea.
        citas_ok, citations, citas_inventadas = validate_citations(
            response_text, tool_payloads
        )
        herramientas = tools_used(tool_payloads)

        # Las cifras se validan igual que los comment_id: contra los resultados
        # reales. El modelo llegó a reportar "ILLENIUM (n=1869)" copiando el
        # número del ejemplo del prompt, con ILLENIUM en 292. Una respuesta
        # convincente y falsa es peor que una evasiva.
        numeros_ok, numeros_inventados = validate_numeric_claims(
            response_text, tool_payloads
        )

        if not citas_ok or not numeros_ok:
            motivo = MENSAJE_DEGRADADO if not citas_ok else MENSAJE_NUMEROS
            logger.error(
                "Respuesta degradada — citas inventadas: %s | cifras sin respaldo: %s",
                citas_inventadas, numeros_inventados,
            )
            save_message(db, user_id, session_id, "user", query)
            save_message(
                db, user_id, session_id, "assistant", motivo,
                tools_used=herramientas, citations=[],
            )
            record_query(db, user_id, query, {}, "es")
            return JSONResponse(content={
                "response": motivo,
                "citations": [],
                "quota_remaining": remaining,
                "cached": False,
                "degraded": True,
            })

        # 8c. El formato de la cita lo arma el código, no el modelo. La síntesis
        # escribe [comment_id]; aquí se expande al formato completo con la
        # metadata REAL de la fila (título, canal, fecha, URL). Ver
        # rag-synthesis-citations.
        display_text = render_inline_citations(response_text, tool_payloads)

        # 9. Persistencia
        # Guardar mensaje del usuario
        save_message(db, user_id, session_id, "user", query)

        # Guardar respuesta del agente
        save_message(
            db, user_id, session_id, "assistant", display_text,
            tools_used=herramientas, citations=citations,
        )

        # Guardar en caché: solo si sabemos contra qué versión del corpus, y
        # solo si la evidencia sostiene la respuesta. Una conclusión basada en
        # 6 comentarios no debe volverse la respuesta permanente a esa pregunta.
        if cache_enabled and es_cacheable(tool_payloads):
            store_response(
                db, query, {}, "es",
                corpus_version, PROMPT_VERSION, MODEL,
                display_text, citations, user_id,
            )

        # Registrar consulta frecuente
        record_query(db, user_id, query, {}, "es")

        return JSONResponse(content={
            "response": display_text,
            "citations": citations,
            "quota_remaining": remaining,
            "cached": False,
        })

    except HTTPException:
        raise
    except Exception:
        logger.error("Error procesando consulta:\n%s", traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"error": "Error interno. Intenta más tarde."},
        )
