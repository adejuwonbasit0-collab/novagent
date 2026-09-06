from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.speaker_profile import EMBEDDING_DIM, SpeakerProfileStatus

MIN_ENROLLMENT_SAMPLES = 3  # spec section 9: "multiple samples," not one


class EnrollSpeakerRequest(BaseModel):
    """
    Each entry is one enrollment utterance's embedding vector, already
    computed on-device (see desktop-agent/core/speaker_embedding.py) — raw
    audio never leaves the machine for this feature. The backend only
    averages and stores the resulting template.
    """

    embeddings: list[list[float]] = Field(min_length=MIN_ENROLLMENT_SAMPLES)

    @field_validator("embeddings")
    @classmethod
    def _check_dims(cls, v: list[list[float]]) -> list[list[float]]:
        for vec in v:
            if len(vec) != EMBEDDING_DIM:
                raise ValueError(f"Each embedding must have exactly {EMBEDDING_DIM} dimensions")
        return v


class SpeakerProfileOut(BaseModel):
    """Status-only view — never includes the embedding itself. Used by the
    dashboard's Voice/Permissions pages."""

    id: uuid.UUID
    status: SpeakerProfileStatus
    sample_count: int
    threshold: float
    enabled: bool
    updated_at: datetime

    class Config:
        from_attributes = True


class SpeakerTemplateOut(BaseModel):
    """The actual template — only returned to the authenticated
    user/device that owns it, so the desktop agent can cache it locally
    and verify wake events completely offline afterward."""

    status: SpeakerProfileStatus
    embedding: list[float] | None
    threshold: float
    enabled: bool


class UpdateSpeakerSettingsRequest(BaseModel):
    enabled: bool | None = None
    threshold: float | None = Field(default=None, ge=0.3, le=0.95)
