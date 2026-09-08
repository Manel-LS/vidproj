"""Voice provider selection."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.infrastructure.tts.base import NullVoiceProvider, VoiceProvider


@lru_cache
def get_voice_provider() -> VoiceProvider:
    if settings.tts_provider == "edge":
        from app.infrastructure.tts.providers import EdgeVoiceProvider

        provider = EdgeVoiceProvider()
        return provider if provider.is_available() else NullVoiceProvider()

    if settings.tts_provider == "elevenlabs":
        from app.infrastructure.tts.providers import ElevenLabsVoiceProvider

        provider = ElevenLabsVoiceProvider()
        return provider if provider.is_available() else NullVoiceProvider()

    if settings.tts_provider == "openai":
        from app.infrastructure.tts.providers import OpenAITTSVoiceProvider

        provider = OpenAITTSVoiceProvider()
        return provider if provider.is_available() else NullVoiceProvider()

    return NullVoiceProvider()


def voice_status() -> dict[str, object]:
    provider = get_voice_provider()
    available = provider.is_available()
    return {
        "available": available,
        "provider": provider.name,
        "display_name": provider.display_name,
        "message": ""
        if available
        else (
            "Voice-over is unavailable because no text-to-speech provider is configured. "
            "Set TTS_PROVIDER and the matching API key to enable it."
        ),
    }
