from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum as SAEnum, Float, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

# Embedding dimensionality produced by desktop-agent/core/speaker_embedding.py
# (13 MFCC coefficients x mean+std = 26). Kept here too so the backend can
# sanity-check incoming vectors without importing agent code.
EMBEDDING_DIM = 26

# Cosine-similarity cutoff. Calibrated against synthetic same-speaker vs
# different-speaker test signals during development (same-speaker takes
# clustered ~0.999, distinctly-different synthetic voices ~0.86-0.90) —
# NOT against real human recordings, since none were available to tune
# against here. Treat 0.90 as a conservative starting point, not a
# validated production value: it should be re-checked against real
# enrollment/verification attempts and adjusted per user via
# PATCH /api/v1/speaker/profile (exposed for exactly this reason) before
# this gate is trusted for anything sensitive.
DEFAULT_MATCH_THRESHOLD = 0.90  # cosine similarity — see SECURITY note in api/v1/speaker.py


class SpeakerProfileStatus(str, enum.Enum):
    UNTRAINED = "untrained"
    READY = "ready"


class SpeakerProfile(UUIDPKMixin, TimestampMixin, Base):
    """
    Voice *authentication* (spec section 8/9) — deliberately a separate
    model from VoiceProfile (models/voice.py), which is a text-to-speech
    voice clone (Nova speaking back in the user's voice). Those are
    unrelated features that happened to share the word "voice"; this one
    exists so "Hey Nova" from an unenrolled speaker can be rejected.

    Only ever stores a numeric embedding vector, never raw audio — the
    audio a sample is derived from is discarded immediately after the
    agent computes its embedding (see desktop-agent/core/speaker_embedding.py).
    """

    __tablename__ = "speaker_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    status: Mapped[SpeakerProfileStatus] = mapped_column(
        SAEnum(SpeakerProfileStatus, name="speaker_profile_status"), default=SpeakerProfileStatus.UNTRAINED
    )
    # L2-normalized, EMBEDDING_DIM-length float vector — the average of
    # every enrollment sample's own L2-normalized embedding, re-normalized.
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)

    # Cosine-similarity cutoff for a match. Configurable per user (Voice
    # page: "retrain", implicitly also threshold) rather than hardcoded —
    # a lower threshold trades false-rejections for false-accepts.
    threshold: Mapped[float] = mapped_column(Float, default=DEFAULT_MATCH_THRESHOLD)

    # Spec section 9: "user should be able to disable voice verification."
    # When False, the desktop agent skips the gate entirely and treats
    # every wake event as authenticated — same as having no profile, but
    # explicit and reversible without losing the trained embedding.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
