"""LLM provider selection.

`LLM_PROVIDER=auto` (the default) picks the first provider that has credentials, so a
deployment only needs to set an API key. With no key at all, planning still works —
the deterministic planner in `app.domain.planner` takes over and the API reports
`ai_available: false` so the UI can say so honestly.
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.infrastructure.llm.base import LLMProvider


@lru_cache
def get_llm_provider() -> LLMProvider | None:
    """The configured provider, or None when planning must fall back to heuristics."""
    choice = settings.llm_provider

    if choice in ("auto", "anthropic"):
        from app.infrastructure.llm.anthropic_provider import AnthropicLLMProvider

        provider = AnthropicLLMProvider()
        if provider.is_available():
            return provider
        if choice == "anthropic":
            return None

    if choice in ("auto", "openai_compatible"):
        from app.infrastructure.llm.openai_provider import OpenAICompatibleLLMProvider

        provider = OpenAICompatibleLLMProvider()
        if provider.is_available():
            return provider

    return None


def llm_status() -> dict[str, object]:
    provider = get_llm_provider()
    if provider is None:
        return {
            "available": False,
            "provider": None,
            "display_name": "Built-in planner",
            "message": (
                "AI planning is not configured. The built-in planner will structure your "
                "video instead — set ANTHROPIC_API_KEY to enable Claude."
            ),
        }
    return {
        "available": True,
        "provider": provider.name,
        "display_name": provider.display_name,
        "message": "",
    }
