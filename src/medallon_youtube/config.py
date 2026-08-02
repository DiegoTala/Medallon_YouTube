"""Configuración del pipeline leída de variables de entorno.

Nunca hardcodea project_id, nombre de bucket ni canales — todo se inyecta como
env var (Cloud Run Job + Terraform), consistente con las invariantes de
bronze-ingestion-videos y terraform-provision.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from medallon_youtube.bronze.videos import load_channel_ids


@dataclass(frozen=True)
class PipelineConfig:
    project_id: str
    bronze_bucket: str
    channel_ids: list[str]

    @property
    def staging_videos_table(self) -> str:
        return f"{self.project_id}.silver.staging_youtube_videos"

    @property
    def silver_videos_table(self) -> str:
        return f"{self.project_id}.silver.silver_youtube_videos"

    @property
    def staging_comments_table(self) -> str:
        return f"{self.project_id}.silver.staging_youtube_comments"

    @property
    def silver_comments_table(self) -> str:
        return f"{self.project_id}.silver.silver_youtube_comments"

    @property
    def dead_letter_table(self) -> str:
        return f"{self.project_id}.silver.silver_dead_letter_queue"

    @property
    def gold_sentiment_table(self) -> str:
        return f"{self.project_id}.gold.gold_sentiment_analysis"

    @property
    def gold_embeddings_table(self) -> str:
        return f"{self.project_id}.gold.gold_youtube_embeddings"

    @property
    def gemini_model(self) -> str:
        return f"{self.project_id}.gold.gemini_flash_model"

    @property
    def embedding_model(self) -> str:
        return f"{self.project_id}.gold.embedding_model"


def load_config() -> PipelineConfig:
    project_id = os.environ.get("PROJECT_ID", "medallon-youtube")
    bronze_bucket = os.environ.get("BRONZE_BUCKET", f"{project_id}-yt-bronze")
    return PipelineConfig(project_id=project_id, bronze_bucket=bronze_bucket, channel_ids=load_channel_ids())
