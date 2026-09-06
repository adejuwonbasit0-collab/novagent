from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_actor
from app.models.device import Device
from app.models.speaker_profile import EMBEDDING_DIM, SpeakerProfile, SpeakerProfileStatus
from app.models.user import User
from app.schemas.speaker import (
    EnrollSpeakerRequest,
    SpeakerProfileOut,
    SpeakerTemplateOut,
    UpdateSpeakerSettingsRequest,
)

router = APIRouter(prefix="/api/v1/speaker", tags=["speaker-verification"])

# SECURITY NOTE (be honest with anyone reading this before they trust it):
# This backs a lightweight MFCC-statistics speaker embedding (see
# desktop-agent/core/speaker_embedding.py), not a deep neural speaker
# embedding (e.g. ECAPA-TDNN/resemblyzer). It meaningfully distinguishes
# different speakers' voices and is real, working, on-device verification
# — but it has neither the accuracy of a production biometric model nor
# any real liveness/anti-spoofing (a played-back recording of the
# enrolled user could pass). Treat it as a genuine but first-generation
# gate: fine for "is this even roughly the right person," not sufficient
# on its own for anything you'd want a bank-grade guarantee on. The
# BaseVoiceProvider-style pluggable pattern here means a stronger model
# can replace the embedding function later without touching this API or
# the desktop-agent wiring around it.


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-9:
        return vec
    return [x / norm for x in vec]


async def _get_or_create_profile(user: User, db: AsyncSession) -> SpeakerProfile:
    result = await db.execute(select(SpeakerProfile).where(SpeakerProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = SpeakerProfile(user_id=user.id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


@router.get("/profile", response_model=SpeakerProfileOut)
async def get_speaker_profile(
    actor: tuple[User, Device | None] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    user, _device = actor
    return await _get_or_create_profile(user, db)


@router.get("/template", response_model=SpeakerTemplateOut)
async def get_speaker_template(
    actor: tuple[User, Device | None] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the actual embedding vector so a connected device can cache it
    locally (see desktop-agent/core/speaker_verification.py) and verify
    wake events with zero network round-trip afterward — required for
    offline operation (spec section 38) and for latency (verification
    happens against the exact same audio buffer the wake word was heard
    in, so there's no extra recording step before Nova can respond).
    """
    user, _device = actor
    profile = await _get_or_create_profile(user, db)
    return SpeakerTemplateOut(
        status=profile.status, embedding=profile.embedding, threshold=profile.threshold, enabled=profile.enabled
    )


@router.post("/enroll", response_model=SpeakerProfileOut, status_code=status.HTTP_201_CREATED)
async def enroll_speaker(
    payload: EnrollSpeakerRequest,
    actor: tuple[User, Device | None] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    """
    Averages every submitted sample's own L2-normalized embedding, then
    re-normalizes the result — standard practice for centroid-based
    speaker templates, and robust to one noisier sample skewing the whole
    profile more than a simple unweighted vector average would be.
    Re-enrolling (e.g. "retrain" on the Voice page) fully replaces the
    previous template rather than blending into it, so a bad first
    attempt can't permanently drag the profile off-center.
    """
    user, _device = actor

    normalized = [_l2_normalize(vec) for vec in payload.embeddings]
    centroid = [sum(v[i] for v in normalized) / len(normalized) for i in range(EMBEDDING_DIM)]
    centroid = _l2_normalize(centroid)

    profile = await _get_or_create_profile(user, db)
    profile.embedding = centroid
    profile.sample_count = len(payload.embeddings)
    profile.status = SpeakerProfileStatus.READY
    profile.enabled = True
    await db.commit()
    await db.refresh(profile)
    return profile


@router.patch("/profile", response_model=SpeakerProfileOut)
async def update_speaker_settings(
    payload: UpdateSpeakerSettingsRequest,
    actor: tuple[User, Device | None] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    user, _device = actor
    profile = await _get_or_create_profile(user, db)
    if payload.enabled is not None:
        profile.enabled = payload.enabled
    if payload.threshold is not None:
        profile.threshold = payload.threshold
    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/profile", response_model=SpeakerProfileOut)
async def reset_speaker_profile(
    actor: tuple[User, Device | None] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    """Spec section 9: "reset voice profile." Clears the template but
    keeps the row (and the enabled/threshold prefs) rather than deleting
    it outright, so re-enrollment doesn't need to recreate settings."""
    user, _device = actor
    profile = await _get_or_create_profile(user, db)

    if profile.status != SpeakerProfileStatus.READY:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No trained profile to reset")

    profile.embedding = None
    profile.sample_count = 0
    profile.status = SpeakerProfileStatus.UNTRAINED
    await db.commit()
    await db.refresh(profile)
    return profile
