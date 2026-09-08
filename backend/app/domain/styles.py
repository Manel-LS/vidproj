"""Video style presets (requirement 5).

A style is a *creative policy*: how long scenes run, how much the camera moves, which
transitions read as on-brand, and how text is typeset. The planner consumes a preset
to produce a concrete VideoPlan; the user can override anything afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import (
    AnimationType,
    FontFamily,
    TextAlign,
    TextAnimation,
    TextBackground,
    TextPosition,
    TransitionType,
    VideoStyle,
)


@dataclass(frozen=True)
class TypographyPreset:
    family: FontFamily = FontFamily.SANS_BOLD
    title_size: int = 84
    subtitle_size: int = 56
    caption_size: int = 46
    color: str = "#FFFFFF"
    accent_color: str = "#FFD166"
    background: TextBackground = TextBackground.NONE
    background_color: str = "#000000"
    background_opacity: float = 0.45
    letter_spacing: float = 0.0
    uppercase: bool = False
    align: TextAlign = TextAlign.CENTER
    shadow: bool = True


@dataclass(frozen=True)
class StylePreset:
    style: VideoStyle
    name: str
    description: str
    tagline: str
    # Visual identity used for the style card in the UI (no binary assets needed).
    gradient: tuple[str, str] = ("#6366F1", "#EC4899")
    scene_seconds: tuple[float, float] = (2.4, 3.6)
    transition_seconds: float = 0.45
    motion_intensity: float = 1.0
    animations: tuple[AnimationType, ...] = (AnimationType.KEN_BURNS,)
    transitions: tuple[TransitionType, ...] = (TransitionType.FADE,)
    text_position: TextPosition = TextPosition.LOWER_THIRD
    text_animation: TextAnimation = TextAnimation.FADE
    typography: TypographyPreset = field(default_factory=TypographyPreset)
    music_volume: float = 0.7
    default_cta: str = "Shop now"
    prompt_hint: str = ""


STYLE_PRESETS: dict[VideoStyle, StylePreset] = {
    VideoStyle.PRODUCT_SHOWCASE: StylePreset(
        style=VideoStyle.PRODUCT_SHOWCASE,
        name="Product Showcase",
        description="Dynamic product presentation with confident camera moves.",
        tagline="Sell the detail",
        gradient=("#2563EB", "#06B6D4"),
        scene_seconds=(2.4, 3.2),
        transition_seconds=0.4,
        motion_intensity=1.1,
        animations=(
            AnimationType.ZOOM_IN,
            AnimationType.PAN_RIGHT,
            AnimationType.KEN_BURNS,
            AnimationType.ZOOM_OUT,
        ),
        transitions=(
            TransitionType.CROSS_DISSOLVE,
            TransitionType.SLIDE_LEFT,
            TransitionType.FADE,
        ),
        text_position=TextPosition.LOWER_THIRD,
        text_animation=TextAnimation.RISE,
        typography=TypographyPreset(
            title_size=88,
            subtitle_size=54,
            background=TextBackground.NONE,
            accent_color="#38BDF8",
        ),
        default_cta="Shop the collection",
        prompt_hint="Highlight materials, quality and one concrete benefit per scene.",
    ),
    VideoStyle.TIKTOK_TREND: StylePreset(
        style=VideoStyle.TIKTOK_TREND,
        name="TikTok Trend",
        description="Fast cuts, punchy zooms and high-energy pacing.",
        tagline="Stop the scroll",
        gradient=("#F43F5E", "#8B5CF6"),
        scene_seconds=(1.2, 2.0),
        transition_seconds=0.22,
        motion_intensity=1.6,
        animations=(
            AnimationType.DYNAMIC_ZOOM,
            AnimationType.ZOOM_IN,
            AnimationType.ROTATE_SLIGHT,
            AnimationType.PAN_LEFT,
        ),
        transitions=(
            TransitionType.ZOOM,
            TransitionType.SLIDE_LEFT,
            TransitionType.PUSH,
            TransitionType.BLUR,
        ),
        text_position=TextPosition.CENTER,
        text_animation=TextAnimation.POP,
        typography=TypographyPreset(
            title_size=100,
            subtitle_size=64,
            uppercase=True,
            letter_spacing=-1.0,
            background=TextBackground.PILL,
            background_color="#111111",
            background_opacity=0.55,
            accent_color="#FDE047",
        ),
        music_volume=0.85,
        default_cta="Get yours now",
        prompt_hint="Write like a creator: short, punchy, second-person, no corporate tone.",
    ),
    VideoStyle.MINIMAL: StylePreset(
        style=VideoStyle.MINIMAL,
        name="Minimal",
        description="Clean, quiet and elegant. Lets the image speak.",
        tagline="Less, but better",
        gradient=("#64748B", "#0F172A"),
        scene_seconds=(3.0, 4.0),
        transition_seconds=0.6,
        motion_intensity=0.6,
        animations=(
            AnimationType.SLOW_ZOOM,
            AnimationType.NONE,
            AnimationType.PAN_RIGHT,
        ),
        transitions=(TransitionType.FADE, TransitionType.CROSS_DISSOLVE),
        text_position=TextPosition.BOTTOM,
        text_animation=TextAnimation.FADE,
        typography=TypographyPreset(
            family=FontFamily.SANS,
            title_size=64,
            subtitle_size=44,
            caption_size=38,
            letter_spacing=2.0,
            shadow=False,
            accent_color="#E2E8F0",
        ),
        music_volume=0.55,
        default_cta="Discover",
        prompt_hint="One short line per scene. No exclamation marks.",
    ),
    VideoStyle.LUXURY: StylePreset(
        style=VideoStyle.LUXURY,
        name="Luxury",
        description="Slow, deliberate movement with elegant dissolves.",
        tagline="Quiet confidence",
        gradient=("#1C1917", "#B08D57"),
        scene_seconds=(3.4, 4.5),
        transition_seconds=0.8,
        motion_intensity=0.55,
        animations=(
            AnimationType.SLOW_ZOOM,
            AnimationType.KEN_BURNS,
            AnimationType.PAN_UP,
        ),
        transitions=(
            TransitionType.CROSS_DISSOLVE,
            TransitionType.FADE,
            TransitionType.BLUR,
        ),
        text_position=TextPosition.CENTER,
        text_animation=TextAnimation.FADE,
        typography=TypographyPreset(
            family=FontFamily.SERIF,
            title_size=72,
            subtitle_size=46,
            letter_spacing=6.0,
            uppercase=True,
            shadow=False,
            color="#F5F0E6",
            accent_color="#C8A96A",
        ),
        music_volume=0.5,
        default_cta="Explore the collection",
        prompt_hint="Evocative, restrained copy. Avoid discount language entirely.",
    ),
    VideoStyle.SALE: StylePreset(
        style=VideoStyle.SALE,
        name="Sale / Promotion",
        description="Bold typography and urgent, high-contrast motion.",
        tagline="Make them act",
        gradient=("#DC2626", "#F59E0B"),
        scene_seconds=(1.6, 2.4),
        transition_seconds=0.25,
        motion_intensity=1.4,
        animations=(
            AnimationType.DYNAMIC_ZOOM,
            AnimationType.ZOOM_IN,
            AnimationType.PAN_LEFT,
        ),
        transitions=(TransitionType.PUSH, TransitionType.ZOOM, TransitionType.WIPE),
        text_position=TextPosition.CENTER,
        text_animation=TextAnimation.POP,
        typography=TypographyPreset(
            title_size=108,
            subtitle_size=66,
            uppercase=True,
            background=TextBackground.BOX,
            background_color="#DC2626",
            background_opacity=0.92,
            color="#FFFFFF",
            accent_color="#FDE047",
        ),
        music_volume=0.85,
        default_cta="Shop the sale",
        prompt_hint="Lead with the offer. Include the discount and a deadline if given.",
    ),
    VideoStyle.STORYTELLING: StylePreset(
        style=VideoStyle.STORYTELLING,
        name="Storytelling",
        description="Images sequenced as a narrative with a beginning and an end.",
        tagline="Take them somewhere",
        gradient=("#0EA5E9", "#312E81"),
        scene_seconds=(2.8, 4.0),
        transition_seconds=0.6,
        motion_intensity=0.9,
        animations=(
            AnimationType.KEN_BURNS,
            AnimationType.PAN_RIGHT,
            AnimationType.SLOW_ZOOM,
            AnimationType.PARALLAX,
        ),
        transitions=(
            TransitionType.CROSS_DISSOLVE,
            TransitionType.FADE,
            TransitionType.SLIDE_LEFT,
        ),
        text_position=TextPosition.LOWER_THIRD,
        text_animation=TextAnimation.RISE,
        typography=TypographyPreset(
            family=FontFamily.SANS, title_size=70, subtitle_size=48
        ),
        music_volume=0.6,
        default_cta="Read the full story",
        prompt_hint="Each scene advances the story. Scene one sets a tension, the last resolves it.",
    ),
    VideoStyle.REAL_ESTATE: StylePreset(
        style=VideoStyle.REAL_ESTATE,
        name="Real Estate",
        description="Elegant property tour with steady architectural pans.",
        tagline="Walk them through",
        gradient=("#0F766E", "#134E4A"),
        scene_seconds=(2.8, 3.8),
        transition_seconds=0.55,
        motion_intensity=0.8,
        animations=(
            AnimationType.PAN_RIGHT,
            AnimationType.PAN_LEFT,
            AnimationType.SLOW_ZOOM,
            AnimationType.PAN_UP,
        ),
        transitions=(
            TransitionType.CROSS_DISSOLVE,
            TransitionType.SLIDE_LEFT,
            TransitionType.FADE,
        ),
        text_position=TextPosition.BOTTOM,
        text_animation=TextAnimation.SLIDE,
        typography=TypographyPreset(
            family=FontFamily.SANS,
            title_size=68,
            subtitle_size=44,
            background=TextBackground.GRADIENT,
            letter_spacing=1.0,
            accent_color="#5EEAD4",
        ),
        music_volume=0.55,
        default_cta="Book a viewing",
        prompt_hint="Name the room or feature, then one factual detail (size, light, finish).",
    ),
    VideoStyle.FOOD: StylePreset(
        style=VideoStyle.FOOD,
        name="Food",
        description="Fast, appetising close-ups with warm energy.",
        tagline="Make them hungry",
        gradient=("#EA580C", "#FACC15"),
        scene_seconds=(1.6, 2.6),
        transition_seconds=0.3,
        motion_intensity=1.3,
        animations=(
            AnimationType.ZOOM_IN,
            AnimationType.DYNAMIC_ZOOM,
            AnimationType.PAN_DOWN,
            AnimationType.KEN_BURNS,
        ),
        transitions=(
            TransitionType.ZOOM,
            TransitionType.CROSS_DISSOLVE,
            TransitionType.PUSH,
        ),
        text_position=TextPosition.LOWER_THIRD,
        text_animation=TextAnimation.POP,
        typography=TypographyPreset(
            title_size=92,
            subtitle_size=58,
            uppercase=True,
            background=TextBackground.PILL,
            background_color="#7C2D12",
            background_opacity=0.6,
            accent_color="#FDE68A",
        ),
        music_volume=0.8,
        default_cta="Order now",
        prompt_hint="Sensory words: crispy, melted, fresh. Mention price only if provided.",
    ),
    VideoStyle.EDUCATIONAL: StylePreset(
        style=VideoStyle.EDUCATIONAL,
        name="Educational",
        description="Images paired with clear, informative captions.",
        tagline="Teach in 30 seconds",
        gradient=("#4F46E5", "#22D3EE"),
        scene_seconds=(3.0, 4.2),
        transition_seconds=0.4,
        motion_intensity=0.7,
        animations=(
            AnimationType.SLOW_ZOOM,
            AnimationType.PAN_RIGHT,
            AnimationType.NONE,
        ),
        transitions=(
            TransitionType.SLIDE_LEFT,
            TransitionType.FADE,
            TransitionType.WIPE,
        ),
        text_position=TextPosition.UPPER_THIRD,
        text_animation=TextAnimation.TYPEWRITER,
        typography=TypographyPreset(
            family=FontFamily.SANS,
            title_size=66,
            subtitle_size=46,
            caption_size=40,
            background=TextBackground.BOX,
            background_color="#0F172A",
            background_opacity=0.72,
            accent_color="#67E8F9",
        ),
        music_volume=0.45,
        default_cta="Follow for more",
        prompt_hint="One fact per scene, numbered where it helps comprehension.",
    ),
    VideoStyle.CUSTOM: StylePreset(
        style=VideoStyle.CUSTOM,
        name="Custom",
        description="Start from neutral defaults and define your own look.",
        tagline="Your rules",
        gradient=("#334155", "#7C3AED"),
        scene_seconds=(2.5, 3.5),
        transition_seconds=0.45,
        motion_intensity=1.0,
        animations=(
            AnimationType.KEN_BURNS,
            AnimationType.ZOOM_IN,
            AnimationType.PAN_RIGHT,
        ),
        transitions=(TransitionType.FADE, TransitionType.CROSS_DISSOLVE),
        default_cta="Learn more",
        prompt_hint="Follow the user's description closely; it defines the tone.",
    ),
}


def get_style_preset(style: VideoStyle) -> StylePreset:
    return STYLE_PRESETS[style]
