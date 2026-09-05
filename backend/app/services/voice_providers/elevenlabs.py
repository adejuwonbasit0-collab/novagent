from __future__ import annotations

import httpx

from app.core.config import settings
from app.services.voice_providers.base import BaseVoiceProvider, SynthesizeResult, TrainResult

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsVoiceProvider(BaseVoiceProvider):
    """
    Real voice-cloning provider using ElevenLabs' Instant Voice Cloning
    API. Implemented against their actual endpoint shapes (voices/add for
    training, text-to-speech/{voice_id} for synthesis with
    stability/similarity_boost/style voice_settings — the same three
    parameters TONE_PRESET_SETTINGS in models/voice.py maps tone presets
    onto).

    IMPORTANT — read this before trusting it blindly: this class has NOT
    been exercised against the real ElevenLabs API. api.elevenlabs.io
    is not reachable from the sandbox this was built in (only a small
    allowlist of package-registry domains is), so while the request/
    response shapes here match ElevenLabs' documented API as of this
    writing, that's from training knowledge, not a live-tested call —
    unlike literally everything else in this repository, which was run
    against a real service before being called done. Test this for real
    with your own ELEVENLABS_API_KEY before relying on it, and expect to
    fix small things (their API does change over time).

    Set VOICE_PROVIDER=elevenlabs and ELEVENLABS_API_KEY in .env to
    activate this in place of the mock provider — nothing else in the
    app needs to change.
    """

    def __init__(self):
        if not settings.ELEVENLABS_API_KEY:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured")
        self._headers = {"xi-api-key": settings.ELEVENLABS_API_KEY}

    async def train_voice(self, sample_paths: list[str], voice_name: str) -> TrainResult:
        try:
            files = []
            open_handles = []
            for path in sample_paths:
                f = open(path, "rb")
                open_handles.append(f)
                files.append(("files", (path.split("/")[-1], f, "audio/wav")))

            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        f"{ELEVENLABS_API_BASE}/voices/add",
                        headers=self._headers,
                        data={"name": voice_name},
                        files=files,
                    )
            finally:
                for f in open_handles:
                    f.close()

            if resp.status_code >= 400:
                return TrainResult(success=False, error=f"ElevenLabs error {resp.status_code}: {resp.text}")

            data = resp.json()
            return TrainResult(success=True, provider_voice_id=data["voice_id"])
        except Exception as e:
            return TrainResult(success=False, error=str(e))

    async def synthesize(
        self, text: str, provider_voice_id: str, stability: float, similarity: float, style: float
    ) -> SynthesizeResult:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{ELEVENLABS_API_BASE}/text-to-speech/{provider_voice_id}",
                    headers={**self._headers, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                    json={
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": stability,
                            "similarity_boost": similarity,
                            "style": style,
                            "use_speaker_boost": True,
                        },
                    },
                )

            if resp.status_code >= 400:
                return SynthesizeResult(success=False, error=f"ElevenLabs error {resp.status_code}: {resp.text}")

            return SynthesizeResult(success=True, audio_bytes=resp.content, content_type="audio/mpeg")
        except Exception as e:
            return SynthesizeResult(success=False, error=str(e))
