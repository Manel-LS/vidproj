"""OpenAI-compatible planner (OpenAI, Azure OpenAI, Together, Ollama, vLLM, ...).

Kept as a plain HTTP client so the deployment does not need a second SDK; any endpoint
that speaks `/chat/completions` with `response_format: json_schema` works. Point it at
a different host with `OPENAI_BASE_URL`.
"""
from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.llm.base import LLMPlanDraft, LLMProvider, LLMUnavailable, PlanBrief
from app.infrastructure.llm.prompt import SYSTEM_PROMPT, build_user_prompt

logger = get_logger(__name__)


def _strict_schema() -> dict:
    """JSON schema with the strictness these endpoints require."""
    schema = LLMPlanDraft.model_json_schema()

    def tighten(node: dict) -> None:
        if node.get("type") == "object":
            node["additionalProperties"] = False
            node.setdefault("required", sorted(node.get("properties", {}).keys()))
        for value in list(node.get("properties", {}).values()):
            if isinstance(value, dict):
                tighten(value)
        for key in ("items", "additionalProperties"):
            child = node.get(key)
            if isinstance(child, dict):
                tighten(child)
        for definition in (node.get("$defs") or {}).values():
            if isinstance(definition, dict):
                tighten(definition)

    tighten(schema)
    return schema


class OpenAICompatibleLLMProvider(LLMProvider):
    name = "openai_compatible"
    display_name = "OpenAI-compatible model"

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self._api_key = api_key or settings.openai_api_key
        self._base_url = (base_url or settings.openai_base_url).rstrip("/")
        self._model = model or settings.openai_model

    def is_available(self) -> bool:
        return bool(self._api_key and self._base_url)

    def generate_plan(self, brief: PlanBrief) -> LLMPlanDraft:
        if not self.is_available():
            raise LLMUnavailable("No OpenAI-compatible endpoint is configured.")

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(brief)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "video_plan", "strict": True, "schema": _strict_schema()},
            },
            "temperature": 0.7,
        }

        try:
            with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError as exc:
            logger.warning("LLM endpoint unreachable: %s", exc)
            raise LLMUnavailable("Could not reach the AI provider. Falling back to the built-in planner.") from exc

        if response.status_code >= 400:
            logger.warning("LLM endpoint error %s: %s", response.status_code, response.text[:400])
            raise LLMUnavailable(
                f"The AI provider returned an error ({response.status_code}). "
                "Falling back to the built-in planner."
            )

        try:
            content = response.json()["choices"][0]["message"]["content"]
            return LLMPlanDraft.model_validate(json.loads(content))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            logger.warning("LLM returned an invalid plan: %s", exc)
            raise LLMUnavailable(
                "The AI provider returned a plan that failed validation. "
                "Falling back to the built-in planner."
            ) from exc
