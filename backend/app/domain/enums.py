"""Domain vocabulary. Pure enums — no framework imports."""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class VideoFormat(StrEnum):
    """Target canvas. `PORTRAIT_9_16` is the product default (1080x1920)."""

    PORTRAIT_9_16 = "9:16"
    SQUARE_1_1 = "1:1"
    LANDSCAPE_16_9 = "16:9"
    VERTICAL_4_5 = "4:5"

    @property
    def dimensions(self) -> tuple[int, int]:
        return FORMAT_DIMENSIONS[self]


FORMAT_DIMENSIONS: dict[VideoFormat, tuple[int, int]] = {
    VideoFormat.PORTRAIT_9_16: (1080, 1920),
    VideoFormat.SQUARE_1_1: (1080, 1080),
    VideoFormat.LANDSCAPE_16_9: (1920, 1080),
    VideoFormat.VERTICAL_4_5: (1080, 1350),
}


class Platform(StrEnum):
    TIKTOK = "tiktok"
    REELS = "instagram_reels"
    SHORTS = "youtube_shorts"
    STORY = "instagram_story"

    @property
    def default_format(self) -> VideoFormat:
        return VideoFormat.PORTRAIT_9_16

    @property
    def max_recommended_seconds(self) -> int:
        return {
            Platform.TIKTOK: 60,
            Platform.REELS: 90,
            Platform.SHORTS: 60,
            Platform.STORY: 15,
        }[self]


class VideoStyle(StrEnum):
    PRODUCT_SHOWCASE = "product_showcase"
    TIKTOK_TREND = "tiktok_trend"
    MINIMAL = "minimal"
    LUXURY = "luxury"
    SALE = "sale"
    STORYTELLING = "storytelling"
    REAL_ESTATE = "real_estate"
    FOOD = "food"
    EDUCATIONAL = "educational"
    CUSTOM = "custom"


class AnimationType(StrEnum):
    NONE = "none"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    SLOW_ZOOM = "slow_zoom"
    DYNAMIC_ZOOM = "dynamic_zoom"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    PAN_UP = "pan_up"
    PAN_DOWN = "pan_down"
    KEN_BURNS = "ken_burns"
    ROTATE_SLIGHT = "rotate_slight"
    PARALLAX = "parallax"


class TransitionType(StrEnum):
    NONE = "none"
    FADE = "fade"
    CROSS_DISSOLVE = "cross_dissolve"
    SLIDE_LEFT = "slide_left"
    SLIDE_RIGHT = "slide_right"
    ZOOM = "zoom"
    BLUR = "blur"
    PUSH = "push"
    WIPE = "wipe"


class TextRole(StrEnum):
    TITLE = "title"
    SUBTITLE = "subtitle"
    CTA = "cta"
    CAPTION = "caption"


class TextPosition(StrEnum):
    TOP = "top"
    UPPER_THIRD = "upper_third"
    CENTER = "center"
    LOWER_THIRD = "lower_third"
    BOTTOM = "bottom"


class TextAlign(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class TextAnimation(StrEnum):
    NONE = "none"
    FADE = "fade"
    SLIDE = "slide"
    POP = "pop"
    TYPEWRITER = "typewriter"
    ZOOM = "zoom"
    RISE = "rise"


class TextBackground(StrEnum):
    NONE = "none"
    BOX = "box"
    PILL = "pill"
    GRADIENT = "gradient"


class FontFamily(StrEnum):
    SANS_BOLD = "sans_bold"
    SANS = "sans"
    SERIF = "serif"
    CONDENSED = "condensed"
    MONO = "mono"


class GenerationMode(StrEnum):
    """Requirement 12: two generation modes."""

    STANDARD = "standard"   # local ffmpeg animation pipeline; always available
    AI_MOTION = "ai_motion"  # external image-to-video provider


class RenderStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaKind(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class VoiceOverStatus(StrEnum):
    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class CharacterKind(StrEnum):
    """What the character is, which changes how a prompt should describe it."""

    BABY = "baby"
    CHILD = "child"
    TEEN = "teen"
    ADULT = "adult"
    ELDER = "elder"
    FICTIONAL = "fictional"
    ANIMAL = "animal"


class Language(StrEnum):
    """Languages the product commits to.

    Tunisian derja is separate from Modern Standard Arabic: the register, the
    vocabulary and the voice tags all differ, and collapsing them produces a news
    bulletin where a conversation was wanted.
    """

    TUNISIAN = "tn"
    ARABIC = "ar"
    FRENCH = "fr"
    ENGLISH = "en"


class GenerationJobType(StrEnum):
    """Every kind of work the pipeline queues.

    One vocabulary, so the dashboard can show a project's whole progress instead
    of the four separate, differently-shaped states it used to read.
    """

    STORY = "story"
    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"
    LIPSYNC = "lipsync"
    RENDER = "render"
