"""App FastAPI de Fase 2 — punto de entrada del agente RAG.

Ver .claude/skills/rag-fastapi-service/SKILL.md.
Cadena de middleware (orden obligatorio):
  1. IAP -> 2. identidad -> 3. sanitización -> 4. rate limit ->
  5. cuota diaria -> 6. caché -> 7. historial -> 8. Router -> 9. persistencia

El healthcheck NO consulta BigQuery ni Vertex AI — un healthcheck que gasta
es un gasto recurrente por diseño.
"""

from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from google.cloud import firestore

from rag_agent.middleware.auth import authenticate
from rag_agent.middleware.cache import get_cached_response, store_response
from rag_agent.middleware.quota import check_daily_quota, check_rate_limit
from rag_agent.middleware.sanitize import sanitize

logger = logging.getLogger("rag_agent")

app = FastAPI(title="YouTube DJ Analytics — RAG Agent", version="0.1.0")

# Clientes a nivel de módulo (una vez por instancia, no por request).
# Ver rag-fastapi-service: "la inicialización pesada va a nivel de módulo,
# para que ocurra una vez por instancia y no por request."
db = firestore.Client()


@app.get("/health")
async def health() -> PlainTextResponse:
    """Healthcheck sin costo — no consulta BigQuery ni Vertex AI."""
    return PlainTextResponse("ok")


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

        # 6. Caché (placeholder — las versiones se implementan en Fase D)
        # cached = get_cached_response(db, query, {}, "es", "", "", "", user_id)
        # if cached:
        #     return JSONResponse(content={"response": cached["response"], "citations": cached["citations"], "cached": True})

        # 7-8. Agentes y herramientas (placeholder para Fase D)
        response_text = f"[placeholder] Consulta recibida: '{query}'. Agentes pendientes de implementar (Fase D)."
        citations: list = []

        # 9. Persistencia (placeholder para Fase E)
        # store_response(db, query, {}, "es", "", "", "", response_text, citations, user_id)

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
