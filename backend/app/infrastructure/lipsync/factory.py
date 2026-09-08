"""Lip-sync provider selection."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.infrastructure.lipsync.base import LipSyncProvider, NullLipSyncProvider

UNCONFIGURED_MESSAGE = (
    "Lip sync is unavailable because no lip-sync provider is configured. "
    "Set LIPSYNC_PROVIDER and its API key. Videos still render with the voice-over "
    "over the clip, without matching lips."
)


@lru_cache
def get_lipsync_provider() -> LipSyncProvider:
    choice = settings.lipsync_provider
    if choice == "none":
        return NullLipSyncProvider()

    from app.infrastructure.lipsync.providers import (
        HeyGenProvider,
        ReplicateLipSyncProvider,
        SyncLabsProvider,
    )

    provider = {
        "synclabs": SyncLabsProvider,
        "heygen": HeyGenProvider,
        "replicate": ReplicateLipSyncProvider,
    }[choice]()
    return provider if provider.is_available() else NullLipSyncProvider()


def lipsync_status() -> dict[str, object]:
    provider = get_lipsync_provider()
    available = provider.is_available()
    return {
        "available": available,
        "provider": provider.name,
        "display_name": provider.display_name,
        "max_clip_seconds": provider.max_clip_seconds,
        "needs_public_urls": provider.needs_public_urls,
        "message": "" if available else UNCONFIGURED_MESSAGE,
    }
