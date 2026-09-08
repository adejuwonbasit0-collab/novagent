import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    source_filename: str | None
    status: str
    error: str | None
    char_count: int
    chunk_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class KnowledgeTextCreate(BaseModel):
    """For pasting text directly rather than uploading a file."""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=500_000)
