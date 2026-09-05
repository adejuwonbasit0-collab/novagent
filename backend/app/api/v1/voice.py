from __future__ import annotations

import os
import uuid
import wave

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.voice import (
    TONE_PRESET_SETTINGS,
    ProfileStatus,
    TonePreset,
    VoiceProfile,
    VoiceSample,
    VoiceSampleStatus,
)
from app.schemas.voice import (
    SynthesizeRequest,
    TrainVoiceRequest,
    UpdateToneRequest,
    VoiceProfileOut,
    VoiceSampleOut,
)
from app.services.voice_providers import get_voice_provider

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


def _user_storage_dir(user_id: uuid.UUID) -> str:
    path = os.path.join(settings.VOICE_STORAGE_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def _probe_wav_duration(path: str) -> float | None:
    """Best-effort duration probe — only works for WAV files (stdlib
    `wave` module, no extra dependency). Other formats (mp3, m4a) return
    None rather than a wrong guess; a real deployment would add a proper
    audio-probing library (e.g. mutagen) for those."""
    try:
        with wave.open(path, "rb") as f:
            return f.getnframes() / f.getframerate()
    except Exception:
        return None


async def _get_or_create_profile(user: User, db: AsyncSession) -> VoiceProfile:
    result = await db.execute(select(VoiceProfile).where(VoiceProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = VoiceProfile(user_id=user.id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


@router.post("/samples", response_model=VoiceSampleOut, status_code=status.HTTP_201_CREATED)
async def upload_voice_sample(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    contents = await file.read()
    if len(contents) > settings.MAX_VOICE_SAMPLE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Sample exceeds {settings.MAX_VOICE_SAMPLE_BYTES} bytes",
        )
    if len(contents) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    sample_id = uuid.uuid4()
    ext = os.path.splitext(file.filename or "")[1] or ".wav"
    # Stored filename is the sample's own UUID, never the user-supplied
    # name — avoids any path-traversal or collision risk from filenames
    # we don't control.
    stored_filename = f"{sample_id}{ext}"
    dest_path = os.path.join(_user_storage_dir(current_user.id), stored_filename)

    with open(dest_path, "wb") as f:
        f.write(contents)

    duration = _probe_wav_duration(dest_path) if ext.lower() == ".wav" else None

    sample = VoiceSample(
        id=sample_id,
        user_id=current_user.id,
        file_path=os.path.join(str(current_user.id), stored_filename),
        original_filename=file.filename or "unnamed",
        duration_seconds=duration,
        size_bytes=len(contents),
    )
    db.add(sample)
    await db.commit()
    await db.refresh(sample)
    return sample


@router.get("/samples", response_model=list[VoiceSampleOut])
async def list_voice_samples(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VoiceSample).where(VoiceSample.user_id == current_user.id).order_by(VoiceSample.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/samples/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_sample(
    sample_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VoiceSample).where(VoiceSample.id == sample_id, VoiceSample.user_id == current_user.id)
    )
    sample = result.scalar_one_or_none()
    if sample is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found")

    full_path = os.path.join(settings.VOICE_STORAGE_DIR, sample.file_path)
    if os.path.exists(full_path):
        os.remove(full_path)

    await db.delete(sample)
    await db.commit()


@router.get("/profile", response_model=VoiceProfileOut)
async def get_voice_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_or_create_profile(current_user, db)


@router.post("/profile/train", response_model=VoiceProfileOut)
async def train_voice_profile(
    payload: TrainVoiceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Spec section 12's onboarding flow: consent -> samples -> train.
    Consent is checked here, not just implied by uploading — a user could
    upload samples well before deciding to actually train a voice from
    them, and training without consent=true is refused outright.
    """
    if not payload.consent_given:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voice training requires explicit consent (consent_given=true)",
        )

    result = await db.execute(
        select(VoiceSample).where(VoiceSample.user_id == current_user.id, VoiceSample.status == VoiceSampleStatus.UPLOADED)
    )
    samples = result.scalars().all()
    if not samples:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No voice samples to train from — upload at least one first")

    profile = await _get_or_create_profile(current_user, db)
    profile.status = ProfileStatus.TRAINING
    profile.name = payload.voice_name
    profile.consent_given = True
    await db.commit()

    sample_paths = [os.path.join(settings.VOICE_STORAGE_DIR, s.file_path) for s in samples]
    provider = get_voice_provider()
    result_ = await provider.train_voice(sample_paths, payload.voice_name)

    if result_.success:
        profile.status = ProfileStatus.READY
        profile.provider = settings.VOICE_PROVIDER
        profile.provider_voice_id = result_.provider_voice_id
        profile.failure_reason = None
        for s in samples:
            s.status = VoiceSampleStatus.USED
    else:
        profile.status = ProfileStatus.FAILED
        profile.failure_reason = result_.error

    await db.commit()
    await db.refresh(profile)
    return profile


@router.patch("/profile", response_model=VoiceProfileOut)
async def update_tone(
    payload: UpdateToneRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_or_create_profile(current_user, db)
    profile.tone_preset = payload.tone_preset
    if payload.tone_preset == TonePreset.CUSTOM:
        if payload.custom_stability is not None:
            profile.custom_stability = payload.custom_stability
        if payload.custom_similarity is not None:
            profile.custom_similarity = payload.custom_similarity
        if payload.custom_style is not None:
            profile.custom_style = payload.custom_style

    await db.commit()
    await db.refresh(profile)
    return profile


@router.post("/synthesize")
async def synthesize_speech(
    payload: SynthesizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_or_create_profile(current_user, db)

    if profile.status != ProfileStatus.READY or not profile.provider_voice_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No trained voice yet — upload samples and train a voice first",
        )

    tone = payload.tone_preset_override or profile.tone_preset
    if tone == TonePreset.CUSTOM:
        stability, similarity, style = profile.custom_stability, profile.custom_similarity, profile.custom_style
    else:
        stability, similarity, style = TONE_PRESET_SETTINGS[tone]

    provider = get_voice_provider()
    result = await provider.synthesize(payload.text, profile.provider_voice_id, stability, similarity, style)

    if not result.success or result.audio_bytes is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error or "Synthesis failed")

    return Response(content=result.audio_bytes, media_type=result.content_type)
