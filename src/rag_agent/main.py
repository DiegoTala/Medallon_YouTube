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
from rag_agent.middleware.auth import authenticate
from rag_agent.middleware.cache import get_cached_response, store_response
from rag_agent.middleware.citations import (
    MENSAJE_DEGRADADO,
    collect_tool_payloads,
    tools_used,
    validate_citations,
)
from rag_agent.middleware.quota import check_daily_quota, check_rate_limit
from rag_agent.middleware.sanitize import sanitize
from rag_agent.memory.common_queries import record_query
from rag_agent.memory.session import create_session, get_recent_sessions, load_session_messages, save_message
from rag_agent.versions import PROMPT_VERSION, get_corpus_version

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
root_agent = build_agent_pipeline(bq_client, GCP_PROJECT, GOLD_DATASET, GCP_REGION)
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
        user_id = authenticate(request)

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

        # 5. Cuota diaria
        allowed, remaining = check_daily_quota(db, user_id)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": "Agotaste las 30 consultas diarias. Vuelve mañana."},
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

        if not citas_ok:
            logger.error(
                "Respuesta degradada por citas sin evidencia: %s", citas_inventadas
            )
            save_message(db, user_id, session_id, "user", query)
            save_message(
                db, user_id, session_id, "assistant", MENSAJE_DEGRADADO,
                tools_used=herramientas, citations=[],
            )
            record_query(db, user_id, query, {}, "es")
            return JSONResponse(content={
                "response": MENSAJE_DEGRADADO,
                "citations": [],
                "quota_remaining": remaining,
                "cached": False,
                "degraded": True,
            })

        # 9. Persistencia
        # Guardar mensaje del usuario
        save_message(db, user_id, session_id, "user", query)

        # Guardar respuesta del agente
        save_message(
            db, user_id, session_id, "assistant", response_text,
            tools_used=herramientas, citations=citations,
        )

        # Guardar en caché (solo si sabemos contra qué versión del corpus)
        if cache_enabled:
            store_response(
                db, query, {}, "es",
                corpus_version, PROMPT_VERSION, MODEL,
                response_text, citations, user_id,
            )

        # Registrar consulta frecuente
        record_query(db, user_id, query, {}, "es")

        return JSONResponse(content={
            "response": response_text,
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
