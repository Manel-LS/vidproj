"""VoiceProvider abstraction (requirement 11)."""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    description: str = ""
    language: str = "en"
    gender: str = ""


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    content_type: str
    extension: str
    voice_id: str
    provider: str


class VoiceUnavailable(RuntimeError):
    """The provider is not configured, or the request could not be served."""


class VoiceProvider(abc.ABC):
    name: str = "abstract"
    display_name: str = "Abstract"

    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @abc.abstractmethod
    def list_voices(self) -> list[Voice]:
        """Voices the user can pick from. May hit the network."""

    @abc.abstractmethod
    def synthesize(self, text: str, *, voice_id: str | None = None) -> SynthesisResult: ...


class NullVoiceProvider(VoiceProvider):
    """Used when no TTS provider is configured.

    It reports itself unavailable so the API can disable the feature in the UI with a
    clear message, instead of failing at the moment the user clicks Generate.
    """

    name = "none"
    display_name = "Not configured"

    def is_available(self) -> bool:
        return False

    def list_voices(self) -> list[Voice]:
        return []

    def synthesize(self, text: str, *, voice_id: str | None = None) -> SynthesisResult:
        raise VoiceUnavailable(
            "Voice-over is unavailable because no text-to-speech provider is configured. "
            "Set TTS_PROVIDER and the matching API key to enable it."
        )
