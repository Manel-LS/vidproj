"""Claude-backed video planner.

Uses the official Anthropic SDK with structured outputs, so the response is validated
against `LLMPlanDraft` by the SDK before it ever reaches our code.

Configure with `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`) in the backend
environment. The key is read server-side only and is never sent to the browser.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.llm.base import LLMPlanDraft, LLMProvider, LLMUnavailable, PlanBrief
from app.infrastructure.llm.prompt import SYSTEM_PROMPT, build_user_prompt

logger = get_logger(__name__)


class AnthropicLLMProvider(LLMProvider):
    name = "anthropic"
    display_name = "Claude"

    def __init__(self, api_key: str = "", model: str = ""):
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or settings.anthropic_model
        self._client = None

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic  # noqa: PLC0415  (optional dependency)
            except ImportError as exc:  # pragma: no cover
                raise LLMUnavailable(
                    "The anthropic package is not installed. Run `pip install anthropic`."
                ) from exc
            self._client = anthropic.Anthropic(
                api_key=self._api_key,
                timeout=float(settings.llm_timeout_seconds),
                max_retries=2,
            )
        return self._client

    def generate_plan(self, brief: PlanBrief) -> LLMPlanDraft:
        if not self.is_available():
            raise LLMUnavailable("No Anthropic API key is configured.")

        import anthropic  # noqa: PLC0415

        client = self._get_client()
        try:
            response = client.messages.parse(
                model=self._model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(brief)}],
                output_format=LLMPlanDraft,
            )
        except anthropic.APIStatusError as exc:
            logger.warning("Anthropic API error %s: %s", exc.status_code, exc.message)
            raise LLMUnavailable(
                f"Claude returned an error ({exc.status_code}). Falling back to the built-in planner."
            ) from exc
        except anthropic.APIConnectionError as exc:
            logger.warning("Anthropic connection error: %s", exc)
            raise LLMUnavailable("Could not reach Claude. Falling back to the built-in planner.") from exc

        if response.stop_reason == "refusal":
            raise LLMUnavailable(
                "Claude declined to plan this video. Adjust the description and try again."
            )

        draft = response.parsed_output
        if draft is None:
            raise LLMUnavailable("Claude returned an unusable plan. Falling back to the built-in planner.")
        return draft
