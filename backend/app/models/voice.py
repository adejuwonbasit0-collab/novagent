from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum as SAEnum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class VoiceSampleStatus(str, enum.Enum):
    UPLOADED = "uploaded"       # stored, not yet used in a training run
    USED = "used"                # incorporated into the current trained profile


class VoiceSample(UUIDPKMixin, TimestampMixin, Base):
    """A short audio recording of the user's own voice, used to train
    VoiceProfile.provider_voice_id. Spec section 12's onboarding flow
    ('user records multiple voice samples') — this is the storage side of
    that; the actual cloning/training happens in a VoiceProvider."""

    __tablename__ = "voice_samples"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    file_path: Mapped[str] = mapped_column(String(500), nullable=False)  # relative to VOICE_STORAGE_DIR
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[VoiceSampleStatus] = mapped_column(
        SAEnum(VoiceSampleStatus, name="voice_sample_status"), default=VoiceSampleStatus.UPLOADED
    )


class ProfileStatus(str, enum.Enum):
    UNTRAINED = "untrained"
    TRAINING = "training"
    READY = "ready"
    FAILED = "failed"


class TonePreset(str, enum.Enum):
    """Maps to ElevenLabs-shaped voice_settings (stability/similarity/style)
    so the same tone selection works whether the active provider is the
    mock or a real cloning provider — see app/services/voice_providers/."""

    WARM = "warm"
    PROFESSIONAL = "professional"
    ENERGETIC = "energetic"
    CALM = "calm"
    CUSTOM = "custom"


# (stability, similarity_boost, style) per preset — higher stability = more
# consistent/less expressive; higher style = more exaggerated delivery.
# These are starting points a real provider integration should let a user
# fine-tune, not hardcoded truth about how someone's voice should sound.
TONE_PRESET_SETTINGS: dict[TonePreset, tuple[float, float, float]] = {
    TonePreset.WARM: (0.65, 0.80, 0.35),
    TonePreset.PROFESSIONAL: (0.85, 0.75, 0.10),
    TonePreset.ENERGETIC: (0.40, 0.70, 0.65),
    TonePreset.CALM: (0.80, 0.80, 0.15),
}


class VoiceProfile(UUIDPKMixin, TimestampMixin, Base):
    """One trained voice per user (spec section 12/15 — assistant voice
    config). Tone is adjustable independently of training: the same
    trained voice can speak 'warm' or 'energetic' without retraining."""

    __tablename__ = "voice_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    name: Mapped[str] = mapped_column(String(100), default="My Voice")
    provider: Mapped[str] = mapped_column(String(50), default="mock")  # "mock" | "elevenlabs"
    provider_voice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[ProfileStatus] = mapped_column(
        SAEnum(ProfileStatus, name="voice_profile_status"), default=ProfileStatus.UNTRAINED
    )
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    tone_preset: Mapped[TonePreset] = mapped_column(SAEnum(TonePreset, name="tone_preset"), default=TonePreset.WARM)
    # Only meaningful when tone_preset == CUSTOM; otherwise derived from
    # TONE_PRESET_SETTINGS at synthesis time.
    custom_stability: Mapped[float] = mapped_column(Float, default=0.65)
    custom_similarity: Mapped[float] = mapped_column(Float, default=0.80)
    custom_style: Mapped[float] = mapped_column(Float, default=0.35)

    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
