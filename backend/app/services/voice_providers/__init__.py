from app.core.config import settings
from app.services.voice_providers.base import BaseVoiceProvider
from app.services.voice_providers.mock import MockVoiceProvider


def get_voice_provider() -> BaseVoiceProvider:
    if settings.VOICE_PROVIDER == "elevenlabs":
        from app.services.voice_providers.elevenlabs import ElevenLabsVoiceProvider

        return ElevenLabsVoiceProvider()
    return MockVoiceProvider()
