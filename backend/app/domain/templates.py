"""Reusable video templates (requirement 18).

A template is a *scene blueprint*: an ordered list of slots that get filled with the
user's images. Exactly one slot may be marked `repeat`, which absorbs the images left
over after the fixed slots have been served. Text is expressed as a small format string
with `{topic}`, `{index}` and `{cta}` placeholders — no arbitrary code, ever.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from app.domain.enums import (
    AnimationType,
    TextAnimation,
    TextPosition,
    TextRole,
    TransitionType,
    VideoFormat,
    VideoStyle,
)
from app.domain.styles import STYLE_PRESETS, StylePreset

SlotKind = Literal["hook", "content", "feature", "cta", "before", "after", "outro"]


@dataclass(frozen=True)
class TemplateSlot:
    kind: SlotKind = "content"
    duration: float = 3.0
    animation: AnimationType | None = None
    transition: TransitionType | None = None
    text_role: TextRole | None = TextRole.TITLE
    text_template: str = ""
    text_position: TextPosition | None = None
    text_animation: TextAnimation | None = None
    #: When true this slot expands to cover every remaining image.
    repeat: bool = False
    #: A slot may render without consuming an image (uses the previous image instead).
    needs_image: bool = True


@dataclass(frozen=True)
class VideoTemplate:
    key: str
    name: str
    description: str
    category: str
    style: VideoStyle
    slots: tuple[TemplateSlot, ...]
    format: VideoFormat = VideoFormat.PORTRAIT_9_16
    min_images: int = 1
    max_images: int = 20
    recommended_duration: float = 15.0
    default_cta: str = ""

    @property
    def preset(self) -> StylePreset:
        return STYLE_PRESETS[self.style]

    @property
    def gradient(self) -> tuple[str, str]:
        return self.preset.gradient

    def expand(self, image_count: int) -> list[TemplateSlot]:
        """Materialise the slot list for a concrete number of images."""
        fixed = [s for s in self.slots if not s.repeat]
        repeats = [s for s in self.slots if s.repeat]
        fixed_image_slots = sum(1 for s in fixed if s.needs_image)
        remaining = max(0, image_count - fixed_image_slots)

        expanded: list[TemplateSlot] = []
        repeat_expanded = False
        for slot in self.slots:
            if not slot.repeat:
                expanded.append(slot)
                continue
            # Only the first repeating slot absorbs the leftover images; any further
            # repeating slot degrades to a single occurrence.
            count = remaining if not repeat_expanded else min(1, remaining)
            repeat_expanded = True
            for _ in range(count):
                expanded.append(replace(slot, repeat=False))
        if not expanded:
            expanded = [TemplateSlot()]

        # Never emit more image-consuming slots than we have images.
        usable: list[TemplateSlot] = []
        used = 0
        for slot in expanded:
            if slot.needs_image:
                if used >= image_count:
                    continue
                used += 1
            usable.append(slot)
        return usable or [TemplateSlot()]


def _t(**kwargs) -> TemplateSlot:
    return TemplateSlot(**kwargs)


BUILTIN_TEMPLATES: tuple[VideoTemplate, ...] = (
    VideoTemplate(
        key="product_tiktok",
        name="Product TikTok",
        description="Hook, three quick product beats, hard CTA. The default for e-commerce.",
        category="E-commerce",
        style=VideoStyle.TIKTOK_TREND,
        recommended_duration=15.0,
        min_images=2,
        default_cta="Get yours now",
        slots=(
            _t(kind="hook", duration=2.0, animation=AnimationType.DYNAMIC_ZOOM,
               text_role=TextRole.TITLE, text_template="{topic}?",
               text_position=TextPosition.CENTER, text_animation=TextAnimation.POP),
            _t(kind="content", duration=1.8, repeat=True, transition=TransitionType.ZOOM,
               text_role=TextRole.SUBTITLE, text_template=""),
            _t(kind="cta", duration=2.2, needs_image=False, transition=TransitionType.PUSH,
               animation=AnimationType.ZOOM_IN, text_role=TextRole.CTA, text_template="{cta}",
               text_position=TextPosition.CENTER, text_animation=TextAnimation.POP),
        ),
    ),
    VideoTemplate(
        key="product_promotion",
        name="Product Promotion",
        description="Calm product presentation with a benefit line under each shot.",
        category="E-commerce",
        style=VideoStyle.PRODUCT_SHOWCASE,
        recommended_duration=18.0,
        default_cta="Shop the collection",
        slots=(
            _t(kind="hook", duration=2.6, animation=AnimationType.ZOOM_IN,
               text_template="{topic}", text_position=TextPosition.CENTER,
               text_animation=TextAnimation.RISE),
            _t(kind="content", duration=2.8, repeat=True,
               text_role=TextRole.SUBTITLE, text_position=TextPosition.LOWER_THIRD),
            _t(kind="cta", duration=2.6, needs_image=False, text_role=TextRole.CTA,
               text_template="{cta}", text_position=TextPosition.CENTER),
        ),
    ),
    VideoTemplate(
        key="new_collection",
        name="New Collection",
        description="Announce a drop: title card, gallery, closing CTA.",
        category="Fashion",
        style=VideoStyle.MINIMAL,
        recommended_duration=20.0,
        default_cta="See the collection",
        slots=(
            _t(kind="hook", duration=3.0, animation=AnimationType.SLOW_ZOOM,
               text_template="{topic}", text_position=TextPosition.CENTER,
               text_animation=TextAnimation.FADE),
            _t(kind="content", duration=3.0, repeat=True, text_role=TextRole.CAPTION,
               text_position=TextPosition.BOTTOM),
            _t(kind="outro", duration=3.0, needs_image=False, text_role=TextRole.CTA,
               text_template="{cta}", text_position=TextPosition.CENTER),
        ),
    ),
    VideoTemplate(
        key="flash_sale",
        name="Sale",
        description="Urgent, high-contrast promotion built around one offer.",
        category="Promotion",
        style=VideoStyle.SALE,
        recommended_duration=12.0,
        default_cta="Shop the sale",
        slots=(
            _t(kind="hook", duration=1.8, animation=AnimationType.DYNAMIC_ZOOM,
               text_template="{topic}", text_position=TextPosition.CENTER,
               text_animation=TextAnimation.POP),
            _t(kind="content", duration=1.6, repeat=True, transition=TransitionType.PUSH,
               text_role=TextRole.SUBTITLE),
            _t(kind="cta", duration=2.0, needs_image=False, text_role=TextRole.CTA,
               text_template="{cta}", text_position=TextPosition.CENTER,
               text_animation=TextAnimation.POP),
        ),
    ),
    VideoTemplate(
        key="restaurant_promo",
        name="Restaurant Promotion",
        description="Appetising close-ups, warm pacing, ordering CTA.",
        category="Food",
        style=VideoStyle.FOOD,
        recommended_duration=15.0,
        default_cta="Order now",
        slots=(
            _t(kind="hook", duration=2.0, animation=AnimationType.ZOOM_IN,
               text_template="{topic}", text_position=TextPosition.CENTER,
               text_animation=TextAnimation.POP),
            _t(kind="content", duration=2.0, repeat=True, text_role=TextRole.SUBTITLE,
               text_position=TextPosition.LOWER_THIRD),
            _t(kind="cta", duration=2.2, needs_image=False, text_role=TextRole.CTA,
               text_template="{cta}", text_position=TextPosition.CENTER),
        ),
    ),
    VideoTemplate(
        key="real_estate_tour",
        name="Real Estate",
        description="Room-by-room walkthrough with steady pans and factual captions.",
        category="Property",
        style=VideoStyle.REAL_ESTATE,
        recommended_duration=25.0,
        default_cta="Book a viewing",
        slots=(
            _t(kind="hook", duration=3.2, animation=AnimationType.SLOW_ZOOM,
               text_template="{topic}", text_position=TextPosition.BOTTOM,
               text_animation=TextAnimation.SLIDE),
            _t(kind="content", duration=3.0, repeat=True, text_role=TextRole.CAPTION,
               text_position=TextPosition.BOTTOM),
            _t(kind="cta", duration=3.0, needs_image=False, text_role=TextRole.CTA,
               text_template="{cta}", text_position=TextPosition.CENTER),
        ),
    ),
    VideoTemplate(
        key="before_after",
        name="Before / After",
        description="Two-shot comparison with a reveal transition.",
        category="Transformation",
        style=VideoStyle.STORYTELLING,
        recommended_duration=10.0,
        min_images=2,
        max_images=8,
        default_cta="See how it works",
        slots=(
            _t(kind="before", duration=2.6, animation=AnimationType.SLOW_ZOOM,
               text_role=TextRole.TITLE, text_template="Before",
               text_position=TextPosition.UPPER_THIRD, text_animation=TextAnimation.FADE),
            _t(kind="after", duration=3.0, animation=AnimationType.ZOOM_IN,
               transition=TransitionType.WIPE, text_role=TextRole.TITLE,
               text_template="After", text_position=TextPosition.UPPER_THIRD,
               text_animation=TextAnimation.POP),
            _t(kind="content", duration=2.4, repeat=True, text_role=TextRole.SUBTITLE),
            _t(kind="cta", duration=2.4, needs_image=False, text_role=TextRole.CTA,
               text_template="{cta}", text_position=TextPosition.CENTER),
        ),
    ),
    VideoTemplate(
        key="educational_tips",
        name="Educational",
        description="Numbered facts typed on screen over each image.",
        category="Education",
        style=VideoStyle.EDUCATIONAL,
        recommended_duration=25.0,
        default_cta="Follow for more",
        slots=(
            _t(kind="hook", duration=3.0, animation=AnimationType.SLOW_ZOOM,
               text_template="{topic}", text_position=TextPosition.UPPER_THIRD,
               text_animation=TextAnimation.TYPEWRITER),
            _t(kind="content", duration=3.4, repeat=True, text_role=TextRole.SUBTITLE,
               text_position=TextPosition.UPPER_THIRD,
               text_animation=TextAnimation.TYPEWRITER),
            _t(kind="cta", duration=2.8, needs_image=False, text_role=TextRole.CTA,
               text_template="{cta}", text_position=TextPosition.CENTER),
        ),
    ),
    VideoTemplate(
        key="storytelling",
        name="Storytelling",
        description="A narrative arc across your images, ending on a resolution.",
        category="Brand",
        style=VideoStyle.STORYTELLING,
        recommended_duration=22.0,
        default_cta="Read the full story",
        slots=(
            _t(kind="hook", duration=3.4, animation=AnimationType.KEN_BURNS,
               text_template="{topic}", text_position=TextPosition.LOWER_THIRD,
               text_animation=TextAnimation.RISE),
            _t(kind="content", duration=3.2, repeat=True, text_role=TextRole.SUBTITLE),
            _t(kind="outro", duration=3.0, needs_image=False, text_role=TextRole.CTA,
               text_template="{cta}", text_position=TextPosition.CENTER),
        ),
    ),
    VideoTemplate(
        key="luxury_reveal",
        name="Luxury Reveal",
        description="Slow dissolves and restrained serif typography.",
        category="Brand",
        style=VideoStyle.LUXURY,
        recommended_duration=20.0,
        default_cta="Explore the collection",
        slots=(
            _t(kind="hook", duration=3.6, animation=AnimationType.SLOW_ZOOM,
               text_template="{topic}", text_position=TextPosition.CENTER),
            _t(kind="content", duration=3.6, repeat=True, text_role=TextRole.SUBTITLE,
               text_position=TextPosition.CENTER),
            _t(kind="outro", duration=3.4, needs_image=False, text_role=TextRole.CTA,
               text_template="{cta}", text_position=TextPosition.CENTER),
        ),
    ),
)

TEMPLATES_BY_KEY: dict[str, VideoTemplate] = {t.key: t for t in BUILTIN_TEMPLATES}


def get_template(key: str) -> VideoTemplate | None:
    return TEMPLATES_BY_KEY.get(key)


def render_slot_text(template_text: str, *, topic: str, index: int, cta: str) -> str:
    """Fill a slot's placeholders. Unknown placeholders are left untouched."""
    if not template_text:
        return ""
    out = template_text
    for key, value in (("{topic}", topic), ("{index}", str(index)), ("{cta}", cta)):
        out = out.replace(key, value)
    return out.strip()
