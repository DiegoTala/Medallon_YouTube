"""Aplana el JSON crudo de la YouTube Data API (tal cual lo persiste Bronze) al
shape plano que esperan YouTubeVideoSchema / YouTubeCommentSchema en Silver.

Bronze nunca transforma (invariante de bronze-ingestion-videos/comments): guarda
la respuesta de la API sin tocar. Pero esa respuesta cruda (`item["id"]`,
`item["snippet"]["channelTitle"]`, etc.) no tiene el shape plano
(`video_id`, `channel_name`, ...) que validate_video_batch/validate_comment_batch
esperan — este módulo es el puente explícito entre ambas capas.
"""

from __future__ import annotations

from typing import Any


def flatten_video(raw: dict[str, Any]) -> dict[str, Any]:
    snippet = raw.get("snippet", {})
    content_details = raw.get("contentDetails", {})
    statistics = raw.get("statistics", {})
    return {
        "video_id": raw.get("id"),
        "channel_name": snippet.get("channelTitle"),
        "title": snippet.get("title"),
        "description": snippet.get("description", ""),
        "published_at": snippet.get("publishedAt"),
        "default_language": snippet.get("defaultLanguage"),
        "duration": content_details.get("duration"),
        "view_count": int(statistics.get("viewCount", 0)),
        "like_count": int(statistics.get("likeCount", 0)),
    }


def _flatten_comment(comment_item: dict[str, Any], video_id: str) -> dict[str, Any]:
    snippet = comment_item.get("snippet", {})
    return {
        "comment_id": comment_item.get("id"),
        "video_id": video_id,
        "author": snippet.get("authorDisplayName"),
        "comment_text": snippet.get("textOriginal"),
        "like_count": snippet.get("likeCount", 0),
        "published_at": snippet.get("publishedAt"),
    }


def flatten_comment_thread(bronze_line: dict[str, Any]) -> list[dict[str, Any]]:
    """Un bronze_line = {"video_id": ..., "thread": <commentThreads().list() item>}.

    Expande el comentario de nivel superior y sus respuestas de primer nivel
    (PRD §2) en filas planas independientes — cada una es un comentario propio
    con su propio comment_id.
    """
    video_id = bronze_line["video_id"]
    thread = bronze_line["thread"]
    top_level = thread.get("snippet", {}).get("topLevelComment", {})

    flat = [_flatten_comment(top_level, video_id)]
    for reply in thread.get("replies", {}).get("comments", []):
        flat.append(_flatten_comment(reply, video_id))
    return flat
