from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class YouTubeVideoSchema(BaseModel):
    video_id: str = Field(..., min_length=5, description="ID unico del video de YT")
    channel_name: str = Field(..., min_length=1, description="Nombre del canal propietario")
    title: str = Field(..., min_length=1, description="Titulo del video")
    description: str = Field(..., description="Descripcion del video")
    published_at: datetime = Field(..., description="Fecha de publicacion en ISO 8601")
    default_language: Optional[str] = Field(None, description="Idioma predeterminado del video")
    duration: str = Field(..., description="Duracion en formato ISO 8601 (PT#H#M#S)")
    view_count: int = Field(ge=0, description="Numero de vistas")
    like_count: int = Field(ge=0, description="Numero de me gusta")

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El titulo no puede estar vacio")
        return v


class YouTubeCommentSchema(BaseModel):
    comment_id: str = Field(..., min_length=5, description="ID unico del comentario de YT")
    video_id: str = Field(..., min_length=5, description="ID del video asociado")
    author: str = Field(..., min_length=1, description="Nombre del autor del comentario")
    comment_text: str = Field(..., min_length=1, description="Contenido en texto del comentario")
    like_count: int = Field(ge=0, description="Numero de likes debe ser mayor o igual a cero")
    published_at: datetime = Field(..., description="Fecha de publicacion valida en ISO 8601")

    @field_validator("comment_text")
    @classmethod
    def text_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El comentario no puede contener unicamente espacios en blanco")
        return v
