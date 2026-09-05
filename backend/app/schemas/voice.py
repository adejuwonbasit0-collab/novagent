import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.voice import ProfileStatus, TonePreset, VoiceSampleStatus


class VoiceSampleOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    duration_seconds: float | None
    size_bytes: int
    status: VoiceSampleStatus
    created_at: datetime

    class Config:
        from_attributes = True


class VoiceProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    provider: str
    status: ProfileStatus
    failure_reason: str | None
    tone_preset: TonePreset
    custom_stability: float
    custom_similarity: float
    custom_style: float
    consent_given: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TrainVoiceRequest(BaseModel):
    voice_name: str = Field(default="My Voice", max_length=100)
    consent_given: bool  # must be explicitly true — spec section 12: "user gives consent"


class UpdateToneRequest(BaseModel):
    tone_preset: TonePreset
    custom_stability: float | None = Field(default=None, ge=0.0, le=1.0)
    custom_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    custom_style: float | None = Field(default=None, ge=0.0, le=1.0)


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    # Optional one-off override — doesn't change the saved profile setting,
    # just this synthesis call (e.g. "preview how 'energetic' would sound"
    # without committing to it).
    tone_preset_override: TonePreset | None = None
