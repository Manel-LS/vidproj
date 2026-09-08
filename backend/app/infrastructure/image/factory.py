"""Image provider selection."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.infrastructure.image.base import ImageProvider, NullImageProvider

UNCONFIGURED_MESSAGE = (
    "Image generation is unavailable because no image provider is configured. "
    "Set IMAGE_PROVIDER and its API key, or upload your own images."
)


@lru_cache
def get_image_provider() -> ImageProvider:
    choice = settings.image_provider
    if choice == "none":
        return NullImageProvider()

    from app.infrastructure.image.providers import (
        GoogleImageProvider,
        OpenAIImageProvider,
        ReplicateImageProvider,
    )

    provider = {
        "openai": OpenAIImageProvider,
        "replicate": ReplicateImageProvider,
        "google": GoogleImageProvider,
    }[choice]()
    # A provider named but missing its key is the same as none, from the UI's
    # point of view: better to disable the button than to fail on click.
    return provider if provider.is_available() else NullImageProvider()


def image_status() -> dict[str, object]:
    provider = get_image_provider()
    available = provider.is_available()
    return {
        "available": available,
        "provider": provider.name,
        "display_name": provider.display_name,
        "supported_aspect_ratios": list(provider.supported_aspect_ratios),
        "supports_reference_image": provider.supports_reference_image,
        "message": "" if available else UNCONFIGURED_MESSAGE,
    }
