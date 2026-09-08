"""Read-only catalogue endpoints: styles, templates, formats, capabilities.

The frontend renders style cards, template cards and feature toggles straight from
these, so adding a style or a provider never requires a frontend change.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import rate_limit
from app.core.config import settings
from app.domain.enums import (
    AnimationType,
    FontFamily,
    Platform,
    TextAnimation,
    TextBackground,
    TextPosition,
    TextRole,
    TransitionType,
    VideoFormat,
    VideoStyle,
)
from app.domain.plan import plan_schema_json
from app.domain.styles import STYLE_PRESETS
from app.domain.subtitles import SUBTITLE_PRESETS, SubtitleStyle
from app.infrastructure.i2v.factory import i2v_status
from app.domain.language import language_support
from app.infrastructure.depth.factory import depth_status
from app.infrastructure.image.factory import image_status
from app.infrastructure.lipsync.factory import lipsync_status
from app.infrastructure.imaging.fonts import font_report
from app.infrastructure.jobs.factory import queue_status
from app.infrastructure.llm.factory import llm_status
from app.infrastructure.render.engine import FFmpegRenderEngine
from app.infrastructure.render.ffmpeg import ffmpeg_version, supported_xfade_transitions
from app.infrastructure.storage.factory import get_storage
from app.infrastructure.tts.factory import get_voice_provider, voice_status
from app.services import template_service

router = APIRouter(tags=["catalog"], dependencies=[Depends(rate_limit)])


@router.get("/styles", summary="Video style presets")
def list_styles() -> list[dict]:
    payload = []
    for style, preset in STYLE_PRESETS.items():
        payload.append(
            {
                "key": style.value,
                "name": preset.name,
                "description": preset.description,
                "tagline": preset.tagline,
                "gradient": list(preset.gradient),
                "scene_seconds": list(preset.scene_seconds),
                "transition_seconds": preset.transition_seconds,
                "motion_intensity": preset.motion_intensity,
                "animations": [a.value for a in preset.animations],
                "transitions": [t.value for t in preset.transitions],
                "text_position": preset.text_position.value,
                "text_animation": preset.text_animation.value,
                "default_cta": preset.default_cta,
                "typography": {
                    "family": preset.typography.family.value,
                    "title_size": preset.typography.title_size,
                    "subtitle_size": preset.typography.subtitle_size,
                    "caption_size": preset.typography.caption_size,
                    "color": preset.typography.color,
                    "accent_color": preset.typography.accent_color,
                    "background": preset.typography.background.value,
                    "background_color": preset.typography.background_color,
                    "background_opacity": preset.typography.background_opacity,
                    "letter_spacing": preset.typography.letter_spacing,
                    "uppercase": preset.typography.uppercase,
                    "align": preset.typography.align.value,
                    "shadow": preset.typography.shadow,
                },
            }
        )
    return payload


@router.get("/templates", summary="Video templates")
def list_templates(category: str = Query(default="", max_length=64)) -> dict:
    return {
        "categories": template_service.list_categories(),
        "items": template_service.list_templates(category),
    }


@router.get("/formats", summary="Supported output formats and platforms")
def list_formats() -> dict:
    return {
        "formats": [
            {
                "key": fmt.value,
                "width": fmt.dimensions[0],
                "height": fmt.dimensions[1],
                "label": {
                    VideoFormat.PORTRAIT_9_16: "Vertical 9:16",
                    VideoFormat.SQUARE_1_1: "Square 1:1",
                    VideoFormat.LANDSCAPE_16_9: "Landscape 16:9",
                    VideoFormat.VERTICAL_4_5: "Portrait 4:5",
                }[fmt],
                "default": fmt is VideoFormat.PORTRAIT_9_16,
            }
            for fmt in VideoFormat
        ],
        "platforms": [
            {
                "key": platform.value,
                "label": {
                    Platform.TIKTOK: "TikTok",
                    Platform.REELS: "Instagram Reels",
                    Platform.SHORTS: "YouTube Shorts",
                    Platform.STORY: "Instagram Story",
                }[platform],
                "default_format": platform.default_format.value,
                "max_seconds": platform.max_recommended_seconds,
            }
            for platform in Platform
        ],
    }


@router.get("/options", summary="Every enum the editor offers")
def list_options() -> dict:
    return {
        "animations": [a.value for a in AnimationType],
        "transitions": [t.value for t in TransitionType],
        "text_positions": [p.value for p in TextPosition],
        "text_animations": [a.value for a in TextAnimation],
        "text_roles": [r.value for r in TextRole],
        "text_backgrounds": [b.value for b in TextBackground],
        "font_families": [f.value for f in FontFamily],
        "styles": [s.value for s in VideoStyle],
        # Presets rather than bare keys: the editor needs a name and a sentence to
        # put next to each option, and duplicating those in the client would let
        # them drift from what the renderer actually draws.
        "subtitle_styles": [
            {
                "key": SubtitleStyle.NONE.value,
                "name": "No subtitles",
                "description": "The video carries no burned-in text.",
            }
        ]
        + [
            {"key": preset.key.value, "name": preset.name, "description": preset.description}
            for preset in SUBTITLE_PRESETS.values()
        ],
    }


@router.get("/plan-schema", summary="JSON schema for a video plan")
def plan_schema() -> dict:
    """Published so clients can validate a plan before submitting it."""
    return plan_schema_json()


@router.get("/capabilities", summary="What this deployment can actually do")
def capabilities() -> dict:
    """The live provider matrix.

    The UI reads this to decide which features to enable, so an unconfigured provider
    shows as unavailable up front rather than failing when the user clicks the button.
    """
    engine = FFmpegRenderEngine()
    ffmpeg_ok = engine.is_available()
    voice = get_voice_provider()

    return {
        "render": {
            "available": ffmpeg_ok,
            "engine": engine.name,
            "version": ffmpeg_version() if ffmpeg_ok else "",
            "fps": settings.render_fps,
            "transitions": sorted(supported_xfade_transitions())[:80],
            "message": ""
            if ffmpeg_ok
            else "Rendering is unavailable because FFmpeg was not found on the server.",
        },
        "ai_planner": llm_status(),
        "voiceover": {
            **voice_status(),
            "voices": [v.__dict__ for v in voice.list_voices()],
            # Per language, and honest: a provider with no ar-TN voice is not
            # reported as supporting derja just because it has some Arabic.
            "languages": language_support(voice.list_voices()),
        },
        "image": image_status(),
        "depth": depth_status(),
        "ai_motion": i2v_status(),
        "lipsync": lipsync_status(),
        "queue": queue_status(),
        "storage": {"provider": get_storage().name},
        "fonts": font_report(),
        "limits": {
            "max_image_bytes": settings.max_image_bytes,
            "max_audio_bytes": settings.max_audio_bytes,
            "max_images_per_project": settings.max_images_per_project,
            "allowed_image_types": settings.allowed_image_mimes,
            "allowed_audio_types": settings.allowed_audio_mimes,
        },
    }
