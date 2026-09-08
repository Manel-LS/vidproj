"""Selecting the depth estimator, and reporting honestly when there is none."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.infrastructure.depth.base import DepthProvider, NullDepthProvider
from app.infrastructure.depth.providers import OnnxDepthProvider

_PROVIDERS: dict[str, type[DepthProvider]] = {"onnx": OnnxDepthProvider}


@lru_cache
def get_depth_provider() -> DepthProvider:
    """The configured estimator, or the null one.

    Cached because the ONNX session is expensive to build and is reused across
    every scene of every render in the process.
    """
    factory = _PROVIDERS.get(settings.depth_provider)
    if factory is None:
        return NullDepthProvider()
    provider = factory()
    return provider if provider.is_available() else _explained(provider)


def _explained(provider: DepthProvider) -> DepthProvider:
    """Keep the configured provider even when unusable, so it can say why.

    Swapping in `NullDepthProvider` here would lose the difference between "no
    estimator was asked for" and "the one that was asked for is missing its model",
    which are two different things to fix.
    """
    return provider


def depth_status() -> dict[str, object]:
    provider = get_depth_provider()
    available = provider.is_available()
    message = ""
    if not available:
        message = (
            provider.unavailable_reason()
            if hasattr(provider, "unavailable_reason")
            else (
                "Depth-based parallax is unavailable because no depth model is configured. "
                "Scenes still animate with the standard camera moves."
            )
        )
    return {
        "available": available,
        "provider": provider.name,
        "display_name": provider.display_name,
        "message": message,
    }
