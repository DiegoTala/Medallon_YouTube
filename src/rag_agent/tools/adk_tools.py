"""Wrappers de herramientas para ADK — funciones Python que el modelo puede llamar.

ADK convierte funciones Python en herramientas por inspección de la firma:
nombre, docstring, type hints y valores por defecto. El docstring ES la
descripción que ve el modelo — no es documentación interna.

Ver .claude/skills/rag-agent-topology/SKILL.md.
"""

from __future__ import annotations

from google.adk.tools import ToolContext
from google.cloud import bigquery, firestore

from rag_agent.memory.common_queries import get_common_queries as _get_common_queries
from rag_agent.memory.preferences import load_preferences as _load_preferences
from rag_agent.tools.semantic_search import semantic_search as _semantic_search
from rag_agent.tools.sentiment_analytics import sentiment_analytics as _sentiment_analytics
from rag_agent.tools.trend_detection import trend_detection as _trend_detection


def make_semantic_search_tool(client: bigquery.Client, project: str, dataset: str):
    """Crea una función tool de semantic_search con el client pre-configurado."""

    def semantic_search(
        query: str,
        top_k: int = 10,
        channel_name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sentiment_label: str | None = None,
    ) -> dict:
        """Busca comentarios de YouTube semánticamente similares a una consulta.

        Args:
            query (str): Lo que se quiere buscar, en lenguaje natural.
            top_k (int): Cuántos comentarios devolver. Máximo 20.
            channel_name (str | None): Limita la búsqueda a un canal de DJ.
            date_from (str | None): Fecha inicial ISO 8601 del comentario.
            date_to (str | None): Fecha final ISO 8601 del comentario.
            sentiment_label (str | None): Filtra por etiqueta de sentimiento.
        """
        return _semantic_search(
            client, project, dataset, query, top_k,
            channel_name, date_from, date_to, sentiment_label,
        )

    return semantic_search


def make_sentiment_analytics_tool(client: bigquery.Client, project: str, dataset: str):
    """Crea una función tool de sentiment_analytics con el client pre-configurado."""

    def sentiment_analytics(
        query_type: str,
        channel_name: str | None = None,
        video_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        channels: list[str] | None = None,
    ) -> dict:
        """Calcula métricas agregadas de sentimiento sobre los comentarios en Gold.

        Args:
            query_type (str): Una de: distribution_by_channel, distribution_by_period,
                compare_channels, evolution_over_time, summary_by_video.
            channel_name (str | None): Nombre exacto del canal de DJ. Para
                distribution_by_channel; opcional en distribution_by_period y
                evolution_over_time.
            video_id (str | None): ID del video, solo para summary_by_video.
            date_from (str | None): Fecha inicial ISO 8601. Omítela para cubrir
                todo el histórico disponible.
            date_to (str | None): Fecha final ISO 8601. Omítela para cubrir
                todo el histórico disponible.
            channels (list[str] | None): Lista de canales a comparar.
                OBLIGATORIA para compare_channels; ignorada en las demás.
        """
        return _sentiment_analytics(
            client, project, dataset, query_type,
            channel_name, video_id, date_from, date_to, channels,
        )

    return sentiment_analytics


def make_trend_detection_tool(client: bigquery.Client, project: str, dataset: str):
    """Crea una función tool de trend_detection con el client pre-configurado."""

    def trend_detection(
        current_from: str,
        current_to: str,
        baseline_from: str,
        baseline_to: str,
        metric: str,
        channel_name: str | None = None,
    ) -> dict:
        """Compara una métrica de sentimiento entre dos periodos de tiempo.

        Args:
            current_from (str): Inicio del periodo actual (ISO 8601).
            current_to (str): Fin del periodo actual (ISO 8601).
            baseline_from (str): Inicio del periodo base (ISO 8601).
            baseline_to (str): Fin del periodo base (ISO 8601).
            metric (str): Una de: positive_ratio, negative_ratio, comment_volume, avg_likes.
            channel_name (str | None): Limita la comparación a un canal de DJ.
        """
        return _trend_detection(
            client, project, dataset,
            current_from, current_to, baseline_from, baseline_to,
            metric, channel_name,
        )

    return trend_detection


# ── Memoria ───────────────────────────────────────────────────────────────
#
# El user_id NO se captura en el closure: el pipeline se construye una vez por
# instancia (rag-fastapi-service) y atiende a los tres usuarios. Viene de
# `tool_context.user_id`, que ADK toma del `user_id` con que se invoca el
# Runner — el mismo `sub` del JWT de IAP. Capturarlo al construir serviría la
# memoria de un usuario a otro.
#
# Ambas herramientas son de LECTURA. Escribir preferencias exige confirmación
# explícita previa (rag-memory-preferences) y ese flujo es otra pieza.


def make_common_queries_tool(db: firestore.Client):
    """Crea la tool de lectura de consultas frecuentes."""

    def get_my_common_queries(tool_context: ToolContext, limit: int = 10) -> dict:
        """Consulta qué le ha preguntado ESTE usuario al sistema más veces.

        Úsala cuando el usuario pregunte por sus propias consultas, sus temas
        recurrentes o su historial de uso ("¿qué suelo preguntar?").

        Args:
            limit (int): Cuántas consultas devolver. Máximo 20.
        """
        limit = min(max(limit, 1), 20)
        try:
            filas = _get_common_queries(db, tool_context.user_id, limit=limit)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        return {
            "status": "success",
            "count": len(filas),
            "results": [
                {
                    "consulta": f.get("normalized_query", ""),
                    "veces": f.get("count", 0),
                    "ultima_vez": str(f.get("last_used_at", "")),
                }
                for f in filas
            ],
        }

    return get_my_common_queries


def make_preferences_tool(db: firestore.Client):
    """Crea la tool de lectura de preferencias."""

    def get_my_preferences(tool_context: ToolContext) -> dict:
        """Consulta las preferencias guardadas de ESTE usuario.

        Úsala cuando el usuario pregunte qué preferencias tiene guardadas, o
        cuando necesites saber su idioma o canales favoritos para responder.
        """
        try:
            prefs = _load_preferences(db, tool_context.user_id)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        # updated_at es metadata interna, no una preferencia del usuario.
        prefs = {k: str(v) for k, v in prefs.items() if k != "updated_at"}
        return {"status": "success", "count": len(prefs), "preferences": prefs}

    return get_my_preferences
