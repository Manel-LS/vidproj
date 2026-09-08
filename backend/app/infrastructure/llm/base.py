"""LLMProvider abstraction and the schema the model is allowed to emit.

The model never returns a full `VideoPlan`. It returns a deliberately small draft —
creative decisions only — which `mapper.draft_to_plan` merges with the style preset
and the real media ids. That keeps three properties:

  * a malformed or hostile model response cannot inject anything into the renderer;
  * every field is constrained to a domain enum, so it validates or it is rejected;
  * when the model is unavailable the deterministic planner produces the same shape.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    AnimationType,
    TextAnimation,
    TextPosition,
    TransitionType,
    VideoStyle,
)
from app.domain.insight import ImageInsight

#: Literal unions mirror the enums so the JSON schema constrains the model directly.
AnimationName = Literal[
    "none", "zoom_in", "zoom_out", "slow_zoom", "dynamic_zoom",
    "pan_left", "pan_right", "pan_up", "pan_down", "ken_burns",
    "rotate_slight", "parallax",
]
TransitionName = Literal[
    "none", "fade", "cross_dissolve", "slide_left", "slide_right",
    "zoom", "blur", "push", "wipe",
]
TextPositionName = Literal["top", "upper_third", "center", "lower_third", "bottom"]
TextAnimationName = Literal["none", "fade", "slide", "pop", "typewriter", "zoom", "rise"]
SceneRoleName = Literal["hook", "content", "cta"]


class LLMSceneDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_index: int = Field(
        description="0-based index into the supplied image list, or -1 for a card with no image."
    )
    role: SceneRoleName = "content"
    duration_seconds: float = Field(ge=0.6, le=12.0)
    text: str = Field(default="", max_length=140, description="On-screen text. May be empty.")
    text_position: TextPositionName = "lower_third"
    text_animation: TextAnimationName = "fade"
    animation: AnimationName = "ken_burns"
    transition: TransitionName = "fade"
    reason: str = Field(default="", max_length=160, description="Why this choice fits the brief.")


class LLMPlanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: str = Field(default="", max_length=140)
    cta: str = Field(default="", max_length=80)
    caption: str = Field(default="", max_length=400, description="Social caption for the post.")
    hashtags: list[str] = Field(default_factory=list, max_length=12)
    voiceover_script: str = Field(default="", max_length=1200)
    scenes: list[LLMSceneDraft] = Field(min_length=1, max_length=30)

    # -- enum coercion helpers ------------------------------------------------

    @staticmethod
    def to_animation(value: str) -> AnimationType:
        return AnimationType(value)

    @staticmethod
    def to_transition(value: str) -> TransitionType:
        return TransitionType(value)

    @staticmethod
    def to_text_position(value: str) -> TextPosition:
        return TextPosition(value)

    @staticmethod
    def to_text_animation(value: str) -> TextAnimation:
        return TextAnimation(value)


@dataclass
class PlanBrief:
    """Everything the model is told. Assembled by the service, never by a router."""

    style: VideoStyle
    images: list[ImageInsight]
    topic: str = ""
    description: str = ""
    #: The free-text instruction from the "Create with AI" box.
    instruction: str = ""
    target_duration: float = 15.0
    platform: str = "tiktok"
    cta: str = ""
    include_voiceover: bool = False
    language: str = "the same language as the description"
    style_hint: str = ""
    extra_context: dict[str, str] = field(default_factory=dict)

    @property
    def image_count(self) -> int:
        return len(self.images)


class LLMUnavailable(RuntimeError):
    """Raised by a provider that is configured but cannot serve the request."""


class LLMProvider(abc.ABC):
    name: str = "abstract"
    #: Shown in the UI so the user knows what produced their plan.
    display_name: str = "Abstract"

    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @abc.abstractmethod
    def generate_plan(self, brief: PlanBrief) -> LLMPlanDraft:
        """Return a validated draft, or raise LLMUnavailable."""
