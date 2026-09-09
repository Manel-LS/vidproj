"""The deterministic video planner.

This is the fallback used whenever no LLM is configured — and the LLM path reuses it
for *structure*, asking the model only for copy. It is a real planner, not a stub: it
picks pacing from the style, animation variety from the image aspect ratios, transition
rhythm from the style, and text treatment from the measured brightness of the region
where the text will sit.

Pure domain code: given the same request it always yields the same plan.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.domain import copy as copy_tables
from app.domain import social
from app.domain.enums import (
    Language,
    Platform,
    AnimationType,
    GenerationMode,
    TextAnimation,
    TextBackground,
    TextPosition,
    TextRole,
    TransitionType,
    VideoFormat,
    VideoStyle,
)
from app.domain.insight import ImageInsight
from app.domain.language import scripts_match
from app.domain.plan import (
    MAX_TOTAL_SECONDS,
    MIN_SCENE_SECONDS,
    AudioPlan,
    PlanScene,
    TextOverlay,
    VideoPlan,
    VoiceOverPlan,
)
from app.domain.styles import STYLE_PRESETS, StylePreset
from app.domain.templates import VideoTemplate, render_slot_text


@dataclass
class PlanRequest:
    """Everything the planner needs. No database or file access involved."""

    images: list[ImageInsight]
    style: VideoStyle = VideoStyle.PRODUCT_SHOWCASE
    format: VideoFormat = VideoFormat.PORTRAIT_9_16
    fps: int = 30
    topic: str = ""
    description: str = ""
    cta: str = ""
    hook: str = ""
    target_duration: float | None = None
    template: VideoTemplate | None = None
    include_voiceover: bool = False
    language: Language = Language.ENGLISH
    mode: GenerationMode = GenerationMode.STANDARD
    #: Which network the post is for. The caption and the hashtags are written
    #: to that network's conventions, which differ enough to matter.
    platform: Platform = Platform.TIKTOK
    audio_media_id: str | None = None
    #: Optional per-scene copy supplied by an LLM: index -> list of lines.
    copy_lines: dict[int, list[str]] = field(default_factory=dict)
    generated_by: str = "heuristic"

    @property
    def preset(self) -> StylePreset:
        return STYLE_PRESETS[self.style]

    @property
    def subject(self) -> str:
        return (self.topic or self.description or "").strip()

    def seed(self) -> int:
        basis = f"{self.style}|{self.subject}|{len(self.images)}|{self.template.key if self.template else ''}"
        return int(hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8], 16)


# --------------------------------------------------------------------------------
# Copywriting helpers (deterministic; the LLM path overrides these with real copy)
# --------------------------------------------------------------------------------

_HOOKS: dict[VideoStyle, tuple[str, ...]] = {
    VideoStyle.PRODUCT_SHOWCASE: ("Meet {subject}", "This is {subject}", "{subject}, up close"),
    VideoStyle.TIKTOK_TREND: ("Wait for it...", "You need to see {subject}", "POV: you found {subject}"),
    VideoStyle.MINIMAL: ("{subject}", "Introducing {subject}", "Simply {subject}"),
    VideoStyle.LUXURY: ("{subject}", "The art of {subject}", "Crafted: {subject}"),
    VideoStyle.SALE: ("{subject} — now on sale", "Don't miss this", "Limited time: {subject}"),
    VideoStyle.STORYTELLING: ("It started with {subject}", "A short story about {subject}", "{subject}"),
    VideoStyle.REAL_ESTATE: ("Step inside {subject}", "Welcome to {subject}", "{subject} — a tour"),
    VideoStyle.FOOD: ("Hungry yet?", "{subject}, fresh today", "This is {subject}"),
    VideoStyle.EDUCATIONAL: ("{subject}: what to know", "3 things about {subject}", "{subject}, explained"),
    VideoStyle.CUSTOM: ("{subject}", "Discover {subject}", "About {subject}"),
}

_BEATS: dict[VideoStyle, tuple[str, ...]] = {
    VideoStyle.PRODUCT_SHOWCASE: ("Built to last", "Every detail considered", "Made for daily use", "Designed with care"),
    VideoStyle.TIKTOK_TREND: ("No way", "Look at this", "It gets better", "And it's this good"),
    VideoStyle.MINIMAL: ("Clean lines", "Quiet detail", "Considered form", "Nothing spare"),
    VideoStyle.LUXURY: ("Refined", "Timeless", "Uncompromising", "Made to be kept"),
    VideoStyle.SALE: ("Limited stock", "Today only", "While it lasts", "Best price yet"),
    VideoStyle.STORYTELLING: ("Then this happened", "The turning point", "What came next", "And finally"),
    VideoStyle.REAL_ESTATE: ("Light-filled living", "Open kitchen", "Room to breathe", "Move-in ready"),
    VideoStyle.FOOD: ("Fresh every morning", "Made to order", "Straight from the oven", "You can taste it"),
    VideoStyle.EDUCATIONAL: ("1. Start here", "2. Then this", "3. Remember this", "4. And that's it"),
    VideoStyle.CUSTOM: ("Detail one", "Detail two", "Detail three", "Detail four"),
}


def _titlecase_subject(subject: str) -> str:
    return subject[:1].upper() + subject[1:] if subject else "your product"


def default_hook(style: VideoStyle, subject: str, seed: int, language: Language = Language.ENGLISH) -> str:
    options = (
        copy_tables.hooks(language, style)
        if copy_tables.has_copy(language)
        else _HOOKS.get(style, _HOOKS[VideoStyle.CUSTOM])
    )
    template = options[seed % len(options)]
    return template.replace("{subject}", _titlecase_subject(subject)).strip()


#: Subject-bearing beats for English, matching `copy.subject_beats` for the rest.
_SUBJECT_BEATS: dict[VideoStyle, tuple[str, ...]] = {
    VideoStyle.PRODUCT_SHOWCASE: ("{subject}, up close", "Why {subject}"),
    VideoStyle.TIKTOK_TREND: ("{subject} 👀", "Wait — {subject}"),
    VideoStyle.MINIMAL: ("{subject}", "{subject}, simply"),
    VideoStyle.LUXURY: ("{subject}, in detail", "The making of {subject}"),
    VideoStyle.SALE: ("{subject} at this price", "{subject}, now"),
    VideoStyle.STORYTELLING: ("{subject}, continued", "And then {subject}"),
    VideoStyle.REAL_ESTATE: ("{subject}, room by room", "Inside {subject}"),
    VideoStyle.FOOD: ("{subject}, up close", "{subject}, straight out"),
    VideoStyle.EDUCATIONAL: ("{subject}, plainly", "Remember {subject}"),
    VideoStyle.CUSTOM: ("{subject}", "More on {subject}"),
}


def default_beat(
    style: VideoStyle,
    index: int,
    language: Language = Language.ENGLISH,
    subject: str = "",
) -> str:
    """One mid-video line.

    Two things this fixes. A six-scene video used to cycle four beats and repeat
    the first two, and none of them ever named what was being sold — six cards of
    "Built to last" over six pictures of a school bag. Naming the subject every
    other beat is what makes the copy read as being about *something*.

    The subject is only woven in when it is written in the same script as the
    copy: an Arabic line with a Latin brand dropped into it is read letter by
    letter by an Arabic voice, and the word timings that drive the subtitles go
    with it.
    """
    generic = (
        copy_tables.beats(language, style)
        if copy_tables.has_copy(language)
        else _BEATS.get(style, _BEATS[VideoStyle.CUSTOM])
    )
    subject = (subject or "").strip()
    named = (
        copy_tables.subject_beats(language, style)
        if copy_tables.has_copy(language)
        else _SUBJECT_BEATS.get(style, _SUBJECT_BEATS[VideoStyle.CUSTOM])
    )

    # Every other beat names the subject, starting with the second — the first
    # card follows the hook, which has already said what this is.
    if subject and named and index % 2 == 1 and scripts_match(subject, language):
        template = named[(index // 2) % len(named)]
        return template.replace("{subject}", _titlecase_subject(subject)).strip()
    # Counted over the generic beats actually emitted, not over the scene index:
    # indexing by the scene number skips every other entry, so a four-line table
    # repeated after two uses instead of four.
    return generic[(index // 2 if (subject and named) else index) % len(generic)]


def default_caption(
    style: VideoStyle, subject: str, cta: str, language: Language = Language.ENGLISH
) -> str:
    subject = _titlecase_subject(subject)
    if not cta:
        return subject
    # Lower-casing is an English habit; Arabic has no case and French sentence
    # copy reads wrong lower-cased mid-line.
    tail = cta.lower() if language is Language.ENGLISH else cta
    return f"{subject} — {tail} 👀"


def default_hashtags(
    style: VideoStyle, subject: str, language: Language = Language.ENGLISH
) -> list[str]:
    if copy_tables.has_copy(language):
        base = copy_tables.hashtags(language, style)
        words = [w for w in re.split(r"[^0-9A-Za-z؀-ۿ]+", subject) if len(w) > 2][:2]
        return [w.lower() for w in words] + base
    base = {
        VideoStyle.PRODUCT_SHOWCASE: ["product", "smallbusiness", "newin"],
        VideoStyle.TIKTOK_TREND: ["fyp", "foryou", "viral"],
        VideoStyle.MINIMAL: ["minimal", "design", "aesthetic"],
        VideoStyle.LUXURY: ["luxury", "craftsmanship", "timeless"],
        VideoStyle.SALE: ["sale", "discount", "deal"],
        VideoStyle.STORYTELLING: ["story", "behindthescenes", "brand"],
        VideoStyle.REAL_ESTATE: ["realestate", "hometour", "property"],
        VideoStyle.FOOD: ["food", "foodie", "yum"],
        VideoStyle.EDUCATIONAL: ["learn", "tips", "howto"],
        VideoStyle.CUSTOM: ["reels", "shorts", "video"],
    }[style]
    words = [w for w in re.split(r"[^0-9A-Za-z]+", subject) if len(w) > 2][:2]
    return [w.lower() for w in words] + base


def build_voiceover_script(plan_lines: list[str], hook: str, cta: str) -> str:
    parts = [hook] + [line for line in plan_lines if line] + [cta]
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        part = (part or "").strip()
        if part and part.lower() not in seen:
            seen.add(part.lower())
            ordered.append(part.rstrip(".") + ".")
    return " ".join(ordered)


# --------------------------------------------------------------------------------
# Planner
# --------------------------------------------------------------------------------


def _pick_animation(
    preset: StylePreset, insight: ImageInsight | None, index: int, seed: int
) -> AnimationType:
    options = list(preset.animations) or [AnimationType.KEN_BURNS]
    choice = options[(index + seed) % len(options)]
    if insight is None:
        return choice
    # A wide image cropped into a 9:16 frame has horizontal room to spare: prefer a
    # horizontal pan. A tall image has vertical room instead.
    if insight.landscape and choice in (AnimationType.PAN_UP, AnimationType.PAN_DOWN):
        return AnimationType.PAN_RIGHT if index % 2 == 0 else AnimationType.PAN_LEFT
    if not insight.landscape and choice in (AnimationType.PAN_LEFT, AnimationType.PAN_RIGHT):
        return AnimationType.PAN_DOWN if index % 2 == 0 else AnimationType.PAN_UP
    return choice


def _pick_transition(preset: StylePreset, index: int, seed: int) -> TransitionType:
    options = list(preset.transitions) or [TransitionType.FADE]
    return options[(index + seed) % len(options)]


def build_text_overlay(
    *,
    content: str,
    role: TextRole,
    preset: StylePreset,
    insight: ImageInsight | None,
    position: TextPosition,
    animation: TextAnimation,
) -> TextOverlay:
    typo = preset.typography
    size = {
        TextRole.TITLE: typo.title_size,
        TextRole.SUBTITLE: typo.subtitle_size,
        TextRole.CTA: typo.title_size,
        TextRole.CAPTION: typo.caption_size,
    }[role]

    color = typo.accent_color if role is TextRole.CTA else typo.color
    background = typo.background
    background_opacity = typo.background_opacity

    # Image-informed legibility: add or strengthen a scrim over bright/busy regions.
    if insight is not None and insight.needs_text_scrim(position.value):
        if background is TextBackground.NONE:
            background = TextBackground.GRADIENT if role is not TextRole.CTA else TextBackground.PILL
            background_opacity = 0.5
        else:
            background_opacity = min(1.0, background_opacity + 0.15)

    return TextOverlay(
        role=role,
        content=content,
        position=position,
        align=typo.align,
        animation=animation,
        font_family=typo.family,
        font_size=size,
        font_weight=800 if role in (TextRole.TITLE, TextRole.CTA) else 600,
        color=color,
        letter_spacing=typo.letter_spacing,
        uppercase=typo.uppercase,
        background=background,
        background_color=typo.background_color,
        background_opacity=background_opacity,
        shadow=typo.shadow,
        start=0.15,
        animation_duration=0.45,
    )


def build_plan(request: PlanRequest) -> VideoPlan:
    """Turn a PlanRequest into a fully-formed, validated VideoPlan."""
    if not request.images:
        raise ValueError("Please upload at least one image before generating a plan.")

    preset = request.preset
    seed = request.seed()
    subject = request.subject
    # The style preset's CTA is English; use the language table when there is one.
    cta_text = request.cta or (
        copy_tables.cta(request.language, request.style)
        if copy_tables.has_copy(request.language)
        else preset.default_cta
    )
    hook_text = request.hook or default_hook(request.style, subject, seed, request.language)

    slots = (
        request.template.expand(len(request.images))
        if request.template
        else _implicit_slots(len(request.images))
    )

    scenes: list[PlanScene] = []
    beat_lines: list[str] = []
    image_cursor = 0
    last_insight: ImageInsight | None = None

    for index, slot in enumerate(slots):
        insight: ImageInsight | None
        if slot.needs_image and image_cursor < len(request.images):
            insight = request.images[image_cursor]
            image_cursor += 1
        else:
            insight = last_insight or request.images[-1]
        last_insight = insight

        low, high = preset.scene_seconds
        base_duration = slot.duration if request.template else (low if index else high)
        duration = max(MIN_SCENE_SECONDS, round(base_duration, 2))

        animation = slot.animation or _pick_animation(preset, insight, index, seed)
        transition = (
            TransitionType.NONE
            if index == 0
            else (slot.transition or _pick_transition(preset, index, seed))
        )

        # Copy: LLM lines win, then the template's own text, then style defaults.
        llm_lines = request.copy_lines.get(index) or []
        role = slot.text_role or TextRole.SUBTITLE
        if llm_lines:
            content = llm_lines[0]
        elif slot.text_template:
            content = render_slot_text(
                slot.text_template, topic=_titlecase_subject(subject), index=index, cta=cta_text
            )
        elif slot.kind == "hook":
            content = hook_text
        elif slot.kind in ("cta", "outro"):
            content = cta_text
        else:
            content = default_beat(
                request.style, index - 1, request.language, subject=request.subject
            )

        texts: list[TextOverlay] = []
        if content:
            if slot.kind == "hook":
                role = TextRole.TITLE
            elif slot.kind in ("cta", "outro"):
                role = TextRole.CTA
            texts.append(
                build_text_overlay(
                    content=content,
                    role=role,
                    preset=preset,
                    insight=insight,
                    position=slot.text_position or preset.text_position,
                    animation=slot.text_animation or preset.text_animation,
                )
            )
            if slot.kind not in ("hook", "cta", "outro"):
                beat_lines.append(content)

        scenes.append(
            PlanScene(
                order=index,
                media_id=insight.media_id if insight else None,
                duration=duration,
                animation=animation,
                animation_intensity=preset.motion_intensity,
                focus_x=insight.focus_x if insight else 0.5,
                focus_y=insight.focus_y if insight else 0.5,
                transition=transition,
                transition_duration=0.0 if index == 0 else preset.transition_seconds,
                texts=texts,
                background_color="#000000",
                note=f"{slot.kind} scene · {animation.value.replace('_', ' ')}",
            )
        )

    # Written for the network rather than from one template: what a TikTok
    # caption does and what a Shorts description does are different jobs.
    caption, caption_tags = social.compose(
        platform=request.platform,
        language=request.language,
        style=request.style,
        subject=subject,
        hook=hook_text,
        cta=cta_text,
        description=request.description,
    )

    plan = VideoPlan(
        format=request.format,
        fps=request.fps,
        style=request.style,
        mode=request.mode,
        scenes=scenes,
        audio=AudioPlan(media_id=request.audio_media_id, volume=preset.music_volume),
        voiceover=VoiceOverPlan(
            enabled=request.include_voiceover,
            script=build_voiceover_script(beat_lines, hook_text, cta_text)
            if request.include_voiceover
            else "",
        ),
        hook=hook_text,
        cta=cta_text,
        caption=caption,
        hashtags=caption_tags,
        generated_by=request.generated_by,
        notes=preset.prompt_hint,
    )

    if request.target_duration:
        plan = fit_to_duration(plan, request.target_duration)
    return plan.normalised()


def _implicit_slots(image_count: int):
    """Slot list used when no template is selected: hook, beats, CTA."""
    from app.domain.templates import TemplateSlot

    slots = [TemplateSlot(kind="hook", text_role=TextRole.TITLE)]
    slots += [TemplateSlot(kind="content", text_role=TextRole.SUBTITLE) for _ in range(max(0, image_count - 1))]
    slots.append(TemplateSlot(kind="cta", needs_image=False, text_role=TextRole.CTA))
    return slots


def fit_to_duration(plan: VideoPlan, target_seconds: float) -> VideoPlan:
    """Scale every scene proportionally so the timeline lands on `target_seconds`.

    Transition overlaps are preserved as a fraction of scene length, so the pacing
    feel of the style survives the rescale.
    """
    target = max(MIN_SCENE_SECONDS * len(plan.scenes) * 0.5, min(target_seconds, MAX_TOTAL_SECONDS))
    current = plan.total_duration
    if current <= 0:
        return plan
    factor = target / current
    data = plan.model_dump(mode="python")
    for scene in data["scenes"]:
        scene["duration"] = round(max(MIN_SCENE_SECONDS, scene["duration"] * factor), 3)
        scene["transition_duration"] = round(scene["transition_duration"] * factor, 3)
        for text in scene["texts"]:
            text["start"] = round(min(text["start"] * factor, scene["duration"] * 0.5), 3)
            if text.get("duration") is not None:
                text["duration"] = round(min(text["duration"] * factor, scene["duration"] - text["start"]), 3)
    return VideoPlan.model_validate(data).normalised()
