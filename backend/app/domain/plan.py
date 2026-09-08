"""The VideoPlan — the single contract shared by the AI planner, the editor UI and
the render engine (requirement 19).

An LLM never touches ffmpeg. It emits JSON that must parse into `VideoPlan`; anything
that does not validate is rejected with an actionable message. `VideoPlan.normalised()`
then repairs the survivable problems (overlong transitions, text running past the end
of its scene) so the renderer always receives a self-consistent plan.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import (
    AnimationType,
    FontFamily,
    GenerationMode,
    TextAlign,
    TextAnimation,
    TextBackground,
    TextPosition,
    TextRole,
    TransitionType,
    VideoFormat,
    VideoStyle,
)

PLAN_VERSION = 1

MIN_SCENE_SECONDS = 0.4
MAX_SCENE_SECONDS = 30.0
MAX_SCENES = 40
MAX_TOTAL_SECONDS = 180.0
MAX_TEXT_LENGTH = 280
#: Provider error messages are echoed to the editor; bounded so a talkative
#: provider cannot make a scene unstorable.
ERROR_MAX_LENGTH = 500
#: Image prompts carry subject, clothing, environment, lighting, camera and a
#: consistency clause. 400 (the `note` limit) truncated them mid-sentence.
IMAGE_PROMPT_MAX_LENGTH = 1200

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _validate_hex(value: str) -> str:
    if not _HEX_RE.match(value):
        raise ValueError(f"'{value}' is not a valid hex colour (expected #RGB, #RRGGBB or #RRGGBBAA)")
    return value.upper()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TextOverlay(StrictModel):
    """A single text layer inside a scene (requirement 9)."""

    id: str = ""
    role: TextRole = TextRole.TITLE
    content: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    position: TextPosition = TextPosition.LOWER_THIRD
    align: TextAlign = TextAlign.CENTER
    animation: TextAnimation = TextAnimation.FADE
    font_family: FontFamily = FontFamily.SANS_BOLD
    font_size: int = Field(default=72, ge=16, le=220)
    font_weight: int = Field(default=700, ge=100, le=900)
    color: str = "#FFFFFF"
    letter_spacing: float = Field(default=0.0, ge=-10.0, le=40.0)
    line_height: float = Field(default=1.16, ge=0.8, le=2.5)
    uppercase: bool = False
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    background: TextBackground = TextBackground.NONE
    background_color: str = "#000000"
    background_opacity: float = Field(default=0.45, ge=0.0, le=1.0)
    shadow: bool = True
    max_width_pct: float = Field(default=0.84, ge=0.2, le=1.0)
    #: Fine positional nudge as a fraction of frame height, applied to `position`.
    offset_y_pct: float = Field(default=0.0, ge=-0.5, le=0.5)
    offset_x_pct: float = Field(default=0.0, ge=-0.5, le=0.5)
    #: Timing relative to the start of the owning scene.
    start: float = Field(default=0.0, ge=0.0, le=MAX_SCENE_SECONDS)
    duration: float | None = Field(default=None, ge=0.1, le=MAX_SCENE_SECONDS)
    animation_duration: float = Field(default=0.5, ge=0.05, le=3.0)

    @field_validator("color", "background_color")
    @classmethod
    def _check_colour(cls, value: str) -> str:
        return _validate_hex(value)

    @field_validator("content")
    @classmethod
    def _clean_content(cls, value: str) -> str:
        # Normalise newlines; strip control characters that would break rasterisation.
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        value = "".join(ch for ch in value if ch == "\n" or ch >= " ")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Text content cannot be empty.")
        return cleaned

    def resolved_duration(self, scene_duration: float) -> float:
        end = scene_duration if self.duration is None else min(self.start + self.duration, scene_duration)
        return max(0.0, end - self.start)

    @property
    def display_text(self) -> str:
        return self.content.upper() if self.uppercase else self.content


class AiMotionSpec(StrictModel):
    """Per-scene settings for AI Motion mode (requirement 12)."""

    enabled: bool = False
    prompt: str = Field(default="", max_length=800)
    #: Populated by the provider once generation succeeds; the renderer then uses the
    #: generated clip instead of the still-image animation for this scene.
    generated_media_id: str | None = None
    provider: str | None = None
    job_reference: str | None = None
    #: The clip before lip sync. Kept so lip sync can be redone — or undone —
    #: without paying to generate the motion again. Once lip sync succeeds,
    #: `generated_media_id` points at the speaking clip and this at the silent one.
    silent_media_id: str | None = None
    lipsync_provider: str | None = None
    lipsync_job_reference: str | None = None
    #: Why the last generation failed, surfaced to the editor. The worker writes
    #: this on every attempt, so the model has to accept it: a strict model that
    #: rejected it made the whole project unreadable after any AI Motion run.
    error: str = Field(default="", max_length=ERROR_MAX_LENGTH)


class PlanScene(StrictModel):
    id: str = ""
    order: int = Field(ge=0, le=MAX_SCENES)
    media_id: str | None = None
    duration: float = Field(default=3.0, ge=MIN_SCENE_SECONDS, le=MAX_SCENE_SECONDS)
    animation: AnimationType = AnimationType.KEN_BURNS
    animation_intensity: float = Field(default=1.0, ge=0.3, le=2.0)
    #: Focal point in normalised image coordinates, from image analysis.
    focus_x: float = Field(default=0.5, ge=0.0, le=1.0)
    focus_y: float = Field(default=0.5, ge=0.0, le=1.0)
    #: Transition *into* this scene (ignored for the first scene).
    transition: TransitionType = TransitionType.FADE
    transition_duration: float = Field(default=0.4, ge=0.0, le=3.0)
    texts: list[TextOverlay] = Field(default_factory=list, max_length=4)
    background_color: str = "#000000"
    #: What to ask the image provider for. Kept on the scene, not derived at
    #: generation time, so regenerating an image reproduces the same shot.
    image_prompt: str = Field(default="", max_length=IMAGE_PROMPT_MAX_LENGTH)
    ai_motion: AiMotionSpec | None = None
    #: Free-form note from the planner explaining the creative choice, shown in the UI.
    note: str = Field(default="", max_length=400)

    @field_validator("background_color")
    @classmethod
    def _check_colour(cls, value: str) -> str:
        return _validate_hex(value)

    @property
    def focus(self) -> tuple[float, float]:
        return (self.focus_x, self.focus_y)


class AudioPlan(StrictModel):
    media_id: str | None = None
    volume: float = Field(default=0.7, ge=0.0, le=1.5)
    fade_in: float = Field(default=0.6, ge=0.0, le=10.0)
    fade_out: float = Field(default=1.0, ge=0.0, le=10.0)
    #: Offset into the source track where playback starts.
    start_offset: float = Field(default=0.0, ge=0.0, le=3600.0)
    loop: bool = True


class VoiceOverPlan(StrictModel):
    enabled: bool = False
    script: str = Field(default="", max_length=4000)
    media_id: str | None = None
    volume: float = Field(default=1.0, ge=0.0, le=1.5)
    #: Music is attenuated by this factor while the voice-over plays.
    duck_music_to: float = Field(default=0.28, ge=0.0, le=1.0)
    provider: str | None = None
    voice_id: str | None = None


class VideoPlan(StrictModel):
    """The complete, renderable description of a video."""

    version: int = PLAN_VERSION
    format: VideoFormat = VideoFormat.PORTRAIT_9_16
    fps: int = Field(default=30, ge=15, le=60)
    style: VideoStyle = VideoStyle.PRODUCT_SHOWCASE
    mode: GenerationMode = GenerationMode.STANDARD
    scenes: list[PlanScene] = Field(min_length=1, max_length=MAX_SCENES)
    audio: AudioPlan | None = None
    voiceover: VoiceOverPlan | None = None
    hook: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    cta: str = Field(default="", max_length=MAX_TEXT_LENGTH)
    caption: str = Field(default="", max_length=2200)
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    #: Which planner produced this plan: "heuristic", "anthropic", "manual", ...
    generated_by: str = "manual"
    notes: str = Field(default="", max_length=2000)

    @field_validator("hashtags")
    @classmethod
    def _clean_hashtags(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for tag in values:
            tag = tag.strip().lstrip("#")
            # `\w` is Unicode-aware, so Arabic, accented Latin and other scripts
            # survive. The old ASCII-only class silently reduced #قصص_الأنبياء to
            # "_" — every Arabic project in the database had lost its hashtags,
            # and nothing reported it.
            tag = re.sub(r"[^\w]", "", tag, flags=re.UNICODE)[:40]
            if tag and tag.lower() not in {c.lower() for c in cleaned}:
                cleaned.append(tag)
        return cleaned

    @model_validator(mode="after")
    def _check_total_duration(self) -> "VideoPlan":
        if self.total_duration > MAX_TOTAL_SECONDS:
            raise ValueError(
                f"The plan is {self.total_duration:.1f}s long; the maximum is "
                f"{MAX_TOTAL_SECONDS:.0f}s. Shorten or remove some scenes."
            )
        return self

    # ---- Derived values ----------------------------------------------------

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.format.dimensions

    @property
    def total_duration(self) -> float:
        """Wall-clock length. Cross-fades overlap, so they shorten the timeline."""
        total = sum(scene.duration for scene in self.scenes)
        for previous, scene in zip(self.scenes, self.scenes[1:]):
            if scene.transition is not TransitionType.NONE:
                total -= min(
                    scene.transition_duration,
                    previous.duration * 0.9,
                    scene.duration * 0.9,
                )
        return round(max(total, MIN_SCENE_SECONDS), 3)

    def scene_start_times(self) -> list[float]:
        """Absolute start time of each scene on the final timeline."""
        starts: list[float] = []
        cursor = 0.0
        for index, scene in enumerate(self.scenes):
            if index == 0:
                starts.append(0.0)
                cursor = scene.duration
                continue
            overlap = self.effective_transition_duration(index)
            start = cursor - overlap
            starts.append(round(start, 4))
            cursor = start + scene.duration
        return starts

    def effective_transition_duration(self, index: int) -> float:
        """Transition length into `scenes[index]`, clamped to what the pair allows."""
        if index <= 0 or index >= len(self.scenes):
            return 0.0
        scene = self.scenes[index]
        if scene.transition is TransitionType.NONE:
            return 0.0
        previous = self.scenes[index - 1]
        return round(
            max(
                0.0,
                min(
                    scene.transition_duration,
                    previous.duration * 0.9,
                    scene.duration * 0.9,
                ),
            ),
            4,
        )

    def media_ids(self) -> list[str]:
        """Every media file the renderer must have on disk to produce this plan.

        The AI Motion clips belong here too: the renderer looks a scene's generated
        clip up in the paths it was handed, so omitting them made it fall back to
        the still image without a word — the generated motion was simply discarded.
        """
        ids = [s.media_id for s in self.scenes if s.media_id]
        ids += [
            s.ai_motion.generated_media_id
            for s in self.scenes
            if s.ai_motion and s.ai_motion.generated_media_id
        ]
        if self.audio and self.audio.media_id:
            ids.append(self.audio.media_id)
        if self.voiceover and self.voiceover.media_id:
            ids.append(self.voiceover.media_id)
        return ids

    # ---- Repair ------------------------------------------------------------

    def normalised(self) -> "VideoPlan":
        """Return a copy with orders resequenced, ids filled and timings clamped."""
        data = self.model_dump(mode="python")
        scenes = sorted(data["scenes"], key=lambda s: s["order"])
        for index, scene in enumerate(scenes):
            scene["order"] = index
            scene["id"] = scene.get("id") or f"scene-{index + 1}"
            if index == 0:
                scene["transition"] = TransitionType.NONE.value
                scene["transition_duration"] = 0.0
            duration = float(scene["duration"])
            for text_index, text in enumerate(scene.get("texts") or []):
                text["id"] = text.get("id") or f"{scene['id']}-text-{text_index + 1}"
                text["start"] = min(float(text["start"]), max(0.0, duration - 0.1))
                remaining = duration - text["start"]
                if text.get("duration") is None:
                    text["duration"] = round(remaining, 3)
                else:
                    text["duration"] = round(min(float(text["duration"]), remaining), 3)
                text["animation_duration"] = round(
                    min(float(text["animation_duration"]), max(0.05, text["duration"] * 0.6)), 3
                )
        data["scenes"] = scenes
        plan = VideoPlan.model_validate(data)
        # Clamp transitions against final neighbour durations.
        for index in range(1, len(plan.scenes)):
            plan.scenes[index].transition_duration = plan.effective_transition_duration(index)
        return plan


def validate_plan(raw: Any) -> VideoPlan:
    """Parse untrusted JSON (from an LLM or an API client) into a VideoPlan.

    Raises `pydantic.ValidationError`; callers translate that into an AppError.
    """
    if isinstance(raw, VideoPlan):
        return raw.normalised()
    return VideoPlan.model_validate(raw).normalised()


def plan_schema_json() -> dict[str, Any]:
    return VideoPlan.model_json_schema()


def summarise_plan(plan: VideoPlan) -> dict[str, Any]:
    return {
        "scenes": len(plan.scenes),
        "duration": plan.total_duration,
        "format": plan.format.value,
        "style": plan.style.value,
        "has_audio": bool(plan.audio and plan.audio.media_id),
        "has_voiceover": bool(plan.voiceover and plan.voiceover.enabled),
        "generated_by": plan.generated_by,
    }


def iter_text_overlays(plan: VideoPlan) -> Iterable[tuple[PlanScene, TextOverlay]]:
    for scene in plan.scenes:
        for text in scene.texts:
            yield scene, text
