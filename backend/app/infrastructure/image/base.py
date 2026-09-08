"""ImageProvider abstraction: a prompt in, a still image out.

This is the first link of the generation chain. Until it existed, a scene could
only ever hold an image the user had uploaded, so nothing downstream — AI Motion,
lip sync — could start from a description.

Unlike `ImageToVideoProvider`, the interface is **synchronous**: one call returns
the finished bytes. Some providers (Replicate, Imagen long jobs) really are
asynchronous, and those adapters poll inside `generate()` behind their own
deadline. That asymmetry is deliberate. Image generation takes seconds where a
video takes minutes, so a job/poll protocol at this layer would cost every caller
a state machine to save a handful of seconds. What must never happen is blocking
an HTTP request: callers run this from the job queue, not from a route.

When nothing is configured, `NullImageProvider` reports the feature unavailable
so the UI can disable it instead of failing on click.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass

#: Pixel sizes per aspect ratio. Providers snap to their own nearest supported
#: size; these are the targets the rest of the app reasons about.
ASPECT_SIZES: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
}


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    aspect_ratio: str = "9:16"
    #: A previous image of the same character, for providers that can keep a
    #: subject consistent across generations. Ignored by those that cannot —
    #: `supports_reference_image` says which.
    reference_image: bytes | None = None
    reference_content_type: str = ""
    negative_prompt: str = ""
    seed: int | None = None


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    content_type: str
    extension: str
    provider: str
    #: Some providers rewrite the prompt before generating and return what they
    #: actually used. Worth keeping: it explains a surprising result.
    revised_prompt: str = ""


class ImageUnavailable(RuntimeError):
    """Raised when the provider cannot serve the request, with a user-safe message."""


class ImageProvider(abc.ABC):
    name: str = "abstract"
    display_name: str = "Abstract"
    supported_aspect_ratios: tuple[str, ...] = ("9:16", "1:1", "16:9")
    #: Whether `ImageRequest.reference_image` is honoured rather than dropped.
    supports_reference_image: bool = False

    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @abc.abstractmethod
    def generate(self, request: ImageRequest) -> GeneratedImage:
        """Produce one image. Blocks until it is ready or raises `ImageUnavailable`."""

    def resolve_size(self, aspect_ratio: str) -> tuple[int, int]:
        return ASPECT_SIZES.get(aspect_ratio, ASPECT_SIZES["9:16"])


class NullImageProvider(ImageProvider):
    name = "none"
    display_name = "Not configured"
    supported_aspect_ratios = ()

    def is_available(self) -> bool:
        return False

    def generate(self, request: ImageRequest) -> GeneratedImage:
        raise ImageUnavailable(
            "Image generation is unavailable because no image provider is configured. "
            "You can still upload your own images."
        )
