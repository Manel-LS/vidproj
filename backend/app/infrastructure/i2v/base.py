"""ImageToVideoProvider abstraction (requirement 12).

These APIs are genuinely different from one another — different auth, different
polling shapes, different result payloads — so the interface is deliberately the
lowest common denominator that all of them can honour:

    generate_video_from_image()  ->  a provider job id
    get_generation_status()      ->  QUEUED / PROCESSING / COMPLETED / FAILED + progress
    get_video_result()           ->  the finished clip's bytes

Nothing above this package knows which provider is in use, and when none is configured
`NullImageToVideoProvider` reports AI Motion mode as unavailable so the UI disables it.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import Enum


class GenerationState(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class GenerationRequest:
    image: bytes
    image_content_type: str
    prompt: str = ""
    duration_seconds: float = 5.0
    aspect_ratio: str = "9:16"
    seed: int | None = None


@dataclass(frozen=True)
class GenerationStatus:
    job_id: str
    state: GenerationState
    progress: int = 0
    error: str = ""
    #: Populated once the provider has a downloadable asset.
    video_url: str | None = None


@dataclass(frozen=True)
class GeneratedVideo:
    data: bytes
    content_type: str
    extension: str
    provider: str


class ImageToVideoUnavailable(RuntimeError):
    pass


class ImageToVideoProvider(abc.ABC):
    name: str = "abstract"
    display_name: str = "Abstract"
    #: Clip lengths the provider actually supports, for the UI to offer.
    supported_durations: tuple[float, ...] = (5.0,)
    supported_aspect_ratios: tuple[str, ...] = ("9:16",)

    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @abc.abstractmethod
    def generate_video_from_image(self, request: GenerationRequest) -> str:
        """Submit a generation and return the provider's job id."""

    @abc.abstractmethod
    def get_generation_status(self, job_id: str) -> GenerationStatus: ...

    @abc.abstractmethod
    def get_video_result(self, job_id: str) -> GeneratedVideo:
        """Download the finished clip. Only valid once the status is COMPLETED."""


class NullImageToVideoProvider(ImageToVideoProvider):
    name = "none"
    display_name = "Not configured"

    def is_available(self) -> bool:
        return False

    def _unavailable(self):
        return ImageToVideoUnavailable(
            "AI Motion is unavailable because no video generation provider is configured. "
            "Standard mode still animates your images locally."
        )

    def generate_video_from_image(self, request: GenerationRequest) -> str:
        raise self._unavailable()

    def get_generation_status(self, job_id: str) -> GenerationStatus:
        raise self._unavailable()

    def get_video_result(self, job_id: str) -> GeneratedVideo:
        raise self._unavailable()
