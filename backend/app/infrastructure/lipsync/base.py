"""LipSyncProvider abstraction: a silent clip plus a voice, out comes a speaking clip.

This is the last generative link, and the one that decides whether a video reads
as a character *talking* or merely as a character moving while a voice plays over
it. Nothing else in the pipeline can substitute for it.

The interface mirrors `ImageToVideoProvider` rather than `ImageProvider`: these
jobs take minutes, so submit / poll / fetch is the honest shape.

    generate_lipsync()  ->  a provider job id
    get_status()        ->  QUEUED / PROCESSING / COMPLETED / FAILED
    get_result()        ->  the finished clip's bytes
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import Enum


class LipSyncState(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class LipSyncRequest:
    video: bytes
    video_content_type: str
    #: The narration **for this clip only**. A scene handed the whole voice-over
    #: would lip-sync to words spoken in a different scene.
    audio: bytes
    audio_content_type: str
    #: Public URLs, when the provider fetches media itself instead of accepting
    #: an upload. Left empty when the storage backend cannot serve them.
    video_url: str = ""
    audio_url: str = ""


@dataclass(frozen=True)
class LipSyncStatus:
    job_id: str
    state: LipSyncState
    progress: int = 0
    error: str = ""
    result_url: str | None = None


@dataclass(frozen=True)
class GeneratedLipSync:
    data: bytes
    content_type: str
    extension: str
    provider: str


class LipSyncUnavailable(RuntimeError):
    """Raised when the provider cannot serve the request, with a user-safe message."""


class LipSyncProvider(abc.ABC):
    name: str = "abstract"
    display_name: str = "Abstract"
    #: Longest clip the provider will accept, in seconds. Scenes above this are
    #: refused up front rather than after the user has paid for a failed job.
    max_clip_seconds: float = 60.0
    #: True when the provider downloads the media from a URL rather than taking
    #: an upload — which only works if storage can serve public URLs.
    needs_public_urls: bool = False

    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @abc.abstractmethod
    def generate_lipsync(self, request: LipSyncRequest) -> str:
        """Submit the job and return the provider's job id."""

    @abc.abstractmethod
    def get_status(self, job_id: str) -> LipSyncStatus: ...

    @abc.abstractmethod
    def get_result(self, job_id: str) -> GeneratedLipSync:
        """Download the finished clip. Only valid once the status is COMPLETED."""


class NullLipSyncProvider(LipSyncProvider):
    name = "none"
    display_name = "Not configured"

    def is_available(self) -> bool:
        return False

    def _unavailable(self) -> LipSyncUnavailable:
        return LipSyncUnavailable(
            "Lip sync is unavailable because no lip-sync provider is configured. "
            "The clip will still play with the voice-over over it, without matching lips."
        )

    def generate_lipsync(self, request: LipSyncRequest) -> str:
        raise self._unavailable()

    def get_status(self, job_id: str) -> LipSyncStatus:
        raise self._unavailable()

    def get_result(self, job_id: str) -> GeneratedLipSync:
        raise self._unavailable()
