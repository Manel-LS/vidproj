"""Image-to-video provider selection."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.infrastructure.i2v.base import ImageToVideoProvider, NullImageToVideoProvider


@lru_cache
def get_i2v_provider() -> ImageToVideoProvider:
    choice = settings.i2v_provider
    if choice == "none":
        return NullImageToVideoProvider()

    from app.infrastructure.i2v.providers import KlingProvider, LumaProvider, RunwayProvider

    provider = {
        "runway": RunwayProvider,
        "luma": LumaProvider,
        "kling": KlingProvider,
    }[choice]()
    return provider if provider.is_available() else NullImageToVideoProvider()


def i2v_status() -> dict[str, object]:
    provider = get_i2v_provider()
    available = provider.is_available()
    return {
        "available": available,
        "provider": provider.name,
        "display_name": provider.display_name,
        "supported_durations": list(provider.supported_durations),
        "supported_aspect_ratios": list(provider.supported_aspect_ratios),
        "message": ""
        if available
        else (
            "AI Motion is unavailable because no video generation provider is configured. "
            "Standard mode still animates your images locally."
        ),
    }
