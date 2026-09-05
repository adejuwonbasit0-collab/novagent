from __future__ import annotations

import io
import uuid
import wave

from app.services.voice_providers.base import BaseVoiceProvider, SynthesizeResult, TrainResult


class MockVoiceProvider(BaseVoiceProvider):
    """
    Default provider — requires no API key, no external network, and is
    what every automated test in this repo runs against. It does NOT
    perform real voice cloning: train_voice() just validates that sample
    files exist and mints a fake voice ID; synthesize() returns a real,
    valid (if silent) WAV file so every downstream consumer — the HTTP
    response's content-type, a client trying to actually play the audio,
    duration-based UI — is exercised against genuine audio bytes rather
    than an empty placeholder.

    This exists so the entire voice-training pipeline (upload -> train ->
    tone settings -> synthesize -> playback) is provably correct
    end-to-end without needing network access this environment doesn't
    have. Swapping to a real cloning provider is a one-line settings
    change (VOICE_PROVIDER=elevenlabs) — nothing else in the app changes.
    """

    async def train_voice(self, sample_paths: list[str], voice_name: str) -> TrainResult:
        import os

        if not sample_paths:
            return TrainResult(success=False, error="No voice samples provided")

        missing = [p for p in sample_paths if not os.path.exists(p)]
        if missing:
            return TrainResult(success=False, error=f"{len(missing)} sample file(s) not found on disk")

        return TrainResult(success=True, provider_voice_id=f"mock-voice-{uuid.uuid4().hex[:12]}")

    async def synthesize(
        self, text: str, provider_voice_id: str, stability: float, similarity: float, style: float
    ) -> SynthesizeResult:
        if not provider_voice_id.startswith("mock-voice-"):
            return SynthesizeResult(success=False, error="Unknown voice ID for mock provider")

        # Duration scales roughly with text length (a real TTS engine's
        # output would too) so a UI showing "estimated duration" has
        # something non-trivial to render even against mock audio.
        duration_seconds = max(0.5, min(len(text) / 15, 30.0))
        sample_rate = 16000
        n_frames = int(duration_seconds * sample_rate)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit PCM
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"\x00\x00" * n_frames)  # silence — this is a mock, not real TTS

        return SynthesizeResult(success=True, audio_bytes=buffer.getvalue(), content_type="audio/wav")
