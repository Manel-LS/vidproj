"""Bridge between persistence (Scene rows) and the domain (`VideoPlan`).

This is the only module that knows both shapes. Everything upstream works with the
`VideoPlan`; everything downstream works with rows.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.domain.enums import (
    AnimationType,
    GenerationMode,
    TransitionType,
    VideoFormat,
    VideoStyle,
    VoiceOverStatus,
)
from app.domain.insight import ImageInsight
from app.domain.plan import (
    MAX_WORD_TIMINGS,
    AiMotionSpec,
    AudioPlan,
    PlanScene,
    SubtitleSpec,
    TextOverlay,
    VideoPlan,
    VoiceOverPlan,
    WordTimingEntry,
)
from app.domain.subtitles import SubtitleStyle
from app.infrastructure.imaging.analyzer import insight_from_media
from app.models import Media, Project, Scene


def scene_to_plan_scene(scene: Scene) -> PlanScene:
    return PlanScene(
        id=scene.id,
        order=scene.order_index,
        media_id=scene.media_id,
        duration=scene.duration,
        animation=AnimationType(scene.animation),
        animation_intensity=scene.animation_intensity,
        focus_x=scene.focus_x,
        focus_y=scene.focus_y,
        transition=TransitionType(scene.transition),
        transition_duration=scene.transition_duration,
        texts=[TextOverlay.model_validate(text) for text in (scene.texts or [])],
        background_color=scene.background_color,
        image_prompt=scene.image_prompt or "",
        ai_motion=AiMotionSpec.model_validate(scene.ai_motion) if scene.ai_motion else None,
        note=scene.note or "",
    )


def project_to_plan(project: Project) -> VideoPlan:
    """Assemble the renderable plan for a project from its rows."""
    if not project.scenes:
        raise ValidationError(
            "This project has no scenes yet. Upload at least one image to get started."
        )

    audio = project.audio_track
    voice = project.voice_over

    plan = VideoPlan(
        format=VideoFormat(project.format),
        fps=project.fps,
        style=VideoStyle(project.style),
        mode=GenerationMode(project.mode),
        scenes=[scene_to_plan_scene(scene) for scene in project.scenes],
        audio=AudioPlan(
            media_id=audio.media_id if audio else None,
            volume=audio.volume if audio else 0.7,
            fade_in=audio.fade_in if audio else 0.6,
            fade_out=audio.fade_out if audio else 1.0,
            start_offset=audio.start_offset if audio else 0.0,
            loop=audio.loop if audio else True,
        ),
        voiceover=VoiceOverPlan(
            enabled=bool(voice and voice.enabled),
            script=voice.script if voice else "",
            media_id=voice.media_id if voice else None,
            volume=voice.volume if voice else 1.0,
            duck_music_to=voice.duck_music_to if voice else 0.28,
            provider=voice.provider if voice else None,
            voice_id=voice.voice_id if voice else None,
            word_timings=[
                WordTimingEntry.model_validate(entry)
                for entry in (voice.word_timings or [])[:MAX_WORD_TIMINGS]
                if isinstance(entry, dict)
            ]
            if voice
            else [],
        ),
        subtitles=SubtitleSpec(style=SubtitleStyle(project.subtitle_style or "none")),
        hook=project.hook,
        cta=project.cta,
        caption=project.caption,
        hashtags=list(project.hashtags or []),
        generated_by=project.plan_generated_by,
        notes=project.plan_notes,
    )
    return plan.normalised()


def apply_plan_to_project(session: Session, project: Project, plan: VideoPlan) -> Project:
    """Replace the project's scenes and creative metadata with `plan`.

    Scene rows are rewritten wholesale — a plan is a complete description, and merging
    partial plans invites the two representations to drift apart.
    """
    plan = plan.normalised()

    project.format = plan.format.value
    project.fps = plan.fps
    project.style = plan.style.value
    project.mode = plan.mode.value
    project.hook = plan.hook
    project.cta = plan.cta
    project.caption = plan.caption
    project.hashtags = list(plan.hashtags)
    project.subtitle_style = plan.subtitles.style.value
    project.plan_generated_by = plan.generated_by
    project.plan_notes = plan.notes

    for existing in list(project.scenes):
        session.delete(existing)
    session.flush()

    project.scenes = [
        Scene(
            project_id=project.id,
            order_index=scene.order,
            media_id=scene.media_id,
            duration=scene.duration,
            animation=scene.animation.value,
            animation_intensity=scene.animation_intensity,
            focus_x=scene.focus_x,
            focus_y=scene.focus_y,
            transition=scene.transition.value,
            transition_duration=scene.transition_duration,
            texts=[text.model_dump(mode="json") for text in scene.texts],
            background_color=scene.background_color,
            image_prompt=scene.image_prompt,
            ai_motion=scene.ai_motion.model_dump(mode="json") if scene.ai_motion else None,
            note=scene.note,
        )
        for scene in plan.scenes
    ]

    if plan.audio is not None and project.audio_track is not None:
        # The media id is part of the plan and is ownership-checked by
        # `plan_service.apply_plan`. Leaving it out here meant a plan could name a
        # track, be accepted, and then render with the old one — the caller had no
        # way to tell the difference.
        project.audio_track.media_id = plan.audio.media_id
        project.audio_track.volume = plan.audio.volume
        project.audio_track.fade_in = plan.audio.fade_in
        project.audio_track.fade_out = plan.audio.fade_out
        project.audio_track.start_offset = plan.audio.start_offset
        project.audio_track.loop = plan.audio.loop

    if plan.voiceover is not None and project.voice_over is not None:
        voice = project.voice_over
        voice.enabled = plan.voiceover.enabled
        voice.volume = plan.voiceover.volume
        voice.duck_music_to = plan.voiceover.duck_music_to
        if plan.voiceover.script:
            voice.script = plan.voiceover.script
        if plan.voiceover.voice_id:
            voice.voice_id = plan.voiceover.voice_id
        if voice.media_id != plan.voiceover.media_id:
            voice.media_id = plan.voiceover.media_id
            # The status describes the audio that exists, so it has to follow the
            # media. A row left at "ready" with no media makes the editor offer a
            # download that 404s.
            voice.status = (
                VoiceOverStatus.READY.value
                if plan.voiceover.media_id
                else VoiceOverStatus.DRAFT.value
            )
            voice.error = ""
            if plan.voiceover.provider:
                voice.provider = plan.voiceover.provider

    project.duration_seconds = plan.total_duration
    session.flush()
    return project


def refresh_project_duration(project: Project) -> None:
    """Recompute the denormalised duration shown on the dashboard card."""
    try:
        project.duration_seconds = project_to_plan(project).total_duration
    except ValidationError:
        project.duration_seconds = 0.0


def media_insights(media_items: list[Media]) -> list[ImageInsight]:
    """Rebuild domain insights from stored media rows, in project order."""
    return [
        insight_from_media(item.id, item.width or 1080, item.height or 1920, item.analysis)
        for item in media_items
    ]
