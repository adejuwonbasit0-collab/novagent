from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TrainResult:
    success: bool
    provider_voice_id: str | None = None
    error: str | None = None


@dataclass
class SynthesizeResult:
    success: bool
    audio_bytes: bytes | None = None
    content_type: str = "audio/wav"
    error: str | None = None


class BaseVoiceProvider(ABC):
    """
    Every voice provider — real or mock — implements this same surface, so
    swapping which one is active (via settings.VOICE_PROVIDER) never
    touches the API routes or the database models. This is what makes the
    mock provider (voice_providers/mock.py) a genuine, fully-testable
    stand-in rather than a dead-end stub: everything downstream of this
    interface — upload handling, training-status transitions, tone
    settings, the synthesize endpoint's response shape — is exercised
    identically regardless of which implementation is behind it.
    """

    @abstractmethod
    async def train_voice(self, sample_paths: list[str], voice_name: str) -> TrainResult:
        """Takes local file paths to the user's uploaded voice samples and
        produces a provider-specific voice ID that later synthesize() calls
        reference. Real cloning providers (ElevenLabs, etc.) upload the
        audio and return their own voice ID; see the docstring on
        ElevenLabsVoiceProvider for exactly what that involves."""
        raise NotImplementedError

    @abstractmethod
    async def synthesize(
        self, text: str, provider_voice_id: str, stability: float, similarity: float, style: float
    ) -> SynthesizeResult:
        """Generates speech audio for `text` using the trained voice,
        modulated by the tone parameters (see models/voice.py's
        TONE_PRESET_SETTINGS for what these mean)."""
        raise NotImplementedError
