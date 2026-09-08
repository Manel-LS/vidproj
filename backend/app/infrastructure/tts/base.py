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
class WordTiming:
    """When one spoken word starts, relative to the start of the audio.

    Seconds, not the provider's own unit: Edge reports 100-nanosecond ticks and
    another provider would report milliseconds, and a mixed unit reaching the
    renderer is the kind of mistake that shows up as subtitles drifting rather
    than as an error.
    """

    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return round(self.start + self.duration, 4)


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    content_type: str
    extension: str
    voice_id: str
    provider: str
    #: Per-word timings, when the provider reports them. Empty is a legitimate
    #: answer — not every provider does — and callers must degrade to
    #: sentence-level subtitles rather than inventing timings.
    words: tuple[WordTiming, ...] = ()


class VoiceUnavailable(RuntimeError):
    """The provider is not configured, or the request could not be served."""


class VoiceProvider(abc.ABC):
    name: str = "abstract"
    display_name: str = "Abstract"
    #: Whether `synthesize` fills `SynthesisResult.words`. Declared by the provider
    #: rather than inferred from an empty result, so the UI can tell "this provider
    #: cannot do word-level subtitles" apart from "this narration predates them".
    supports_word_timings: bool = False

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
