"""Wrappers de herramientas para ADK — funciones Python que el modelo puede llamar.

ADK convierte funciones Python en herramientas por inspección de la firma:
nombre, docstring, type hints y valores por defecto. El docstring ES la
descripción que ve el modelo — no es documentación interna.

Ver .claude/skills/rag-agent-topology/SKILL.md.
"""

from __future__ import annotations

from google.cloud import bigquery

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
    ) -> dict:
        """Calcula métricas agregadas de sentimiento sobre los comentarios en Gold.

        Args:
            query_type (str): Una de: distribution_by_channel, distribution_by_period,
                compare_channels, evolution_over_time, summary_by_video.
            channel_name (str | None): Nombre exacto del canal de DJ.
            video_id (str | None): ID del video, solo para summary_by_video.
            date_from (str | None): Fecha inicial ISO 8601.
            date_to (str | None): Fecha final ISO 8601.
        """
        return _sentiment_analytics(
            client, project, dataset, query_type,
            channel_name, video_id, date_from, date_to,
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
