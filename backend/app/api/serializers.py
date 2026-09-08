"""Model -> DTO conversion.

Kept out of the routers so response shaping is testable on its own and consistent
across every endpoint that returns the same entity.
"""
from __future__ import annotations

from app.core.errors import ValidationError
from app.domain.language import is_rtl
from app.domain.enums import MediaKind, RenderStatus
from app.infrastructure.storage.factory import get_storage
from app.models import AudioTrack, Media, Project, RenderJob, Scene, VoiceOver
from app.schemas.media import AudioTrackResponse, MediaResponse
from app.schemas.project import (
    ProjectDetail,
    ProjectSummary,
    RenderJobResponse,
    SceneResponse,
    VoiceOverResponse,
)
from app.services.plan_assembler import project_to_plan


def serialize_media(media: Media | None) -> MediaResponse | None:
    if media is None:
        return None
    storage = get_storage()
    return MediaResponse(
        id=media.id,
        kind=MediaKind(media.kind),
        source=media.source,
        url=storage.get_url(media.storage_key),
        thumbnail_url=storage.get_url(media.thumbnail_key) if media.thumbnail_key else None,
        original_filename=media.original_filename,
        content_type=media.content_type,
        size_bytes=media.size_bytes,
        width=media.width,
        height=media.height,
        duration_seconds=media.duration_seconds,
        position=media.position,
        created_at=media.created_at,
        analysis=dict(media.analysis or {}),
    )


def serialize_scene(scene: Scene, *, start_time: float = 0.0) -> SceneResponse:
    # Built from an explicit dict rather than `from_attributes`: the nested `media`
    # field is a DTO, not the ORM relationship, and validating straight off the entity
    # would try (and fail) to coerce the entity into the DTO.
    return SceneResponse.model_validate(
        {
            "id": scene.id,
            "order_index": scene.order_index,
            "media_id": scene.media_id,
            "duration": scene.duration,
            "animation": scene.animation,
            "animation_intensity": scene.animation_intensity,
            "focus_x": scene.focus_x,
            "focus_y": scene.focus_y,
            "transition": scene.transition,
            "transition_duration": scene.transition_duration,
            "texts": list(scene.texts or []),
            "background_color": scene.background_color,
            "note": scene.note or "",
            "image_prompt": scene.image_prompt or "",
            "ai_motion": scene.ai_motion,
            "start_time": round(start_time, 3),
            "media": serialize_media(scene.media),
        }
    )


def serialize_audio(track: AudioTrack | None) -> AudioTrackResponse | None:
    if track is None:
        return None
    return AudioTrackResponse.model_validate(
        {
            "id": track.id,
            "media_id": track.media_id,
            "volume": track.volume,
            "fade_in": track.fade_in,
            "fade_out": track.fade_out,
            "start_offset": track.start_offset,
            "loop": track.loop,
            "library_track_key": track.library_track_key,
            "media": serialize_media(track.media),
        }
    )


def serialize_voice_over(voice: VoiceOver | None) -> VoiceOverResponse | None:
    if voice is None:
        return None
    return VoiceOverResponse.model_validate(
        {
            "id": voice.id,
            "enabled": voice.enabled,
            "script": voice.script,
            "status": voice.status,
            "provider": voice.provider,
            "voice_id": voice.voice_id,
            "volume": voice.volume,
            "duck_music_to": voice.duck_music_to,
            "error": voice.error,
            "media": serialize_media(voice.media),
        }
    )


def serialize_render_job(job: RenderJob | None) -> RenderJobResponse | None:
    if job is None:
        return None
    from app.services.render_service import status_message

    output_media = serialize_media(job.output_media)
    return RenderJobResponse.model_validate(
        {
            "id": job.id,
            "project_id": job.project_id,
            "status": job.status,
            "progress": job.progress,
            "stage": job.stage,
            "error": job.error,
            "message": status_message(job),
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "output_media": output_media.model_dump() if output_media else None,
            "download_url": output_media.url if output_media else None,
        }
    )


def _project_thumbnail_url(project: Project) -> str | None:
    from app.services.project_service import project_thumbnail_media

    media = project_thumbnail_media(project)
    if media is None:
        return None
    storage = get_storage()
    return storage.get_url(media.thumbnail_key or media.storage_key)


def serialize_project_summary(
    project: Project, *, latest_job: RenderJob | None = None
) -> ProjectSummary:
    summary = ProjectSummary.model_validate(project)
    summary.scene_count = len(project.scenes)
    summary.image_count = sum(1 for m in project.media if m.kind == MediaKind.IMAGE.value)
    summary.thumbnail_url = _project_thumbnail_url(project)
    if latest_job is not None:
        summary.render_status = RenderStatus(latest_job.status)
        summary.render_progress = latest_job.progress
        if latest_job.output_media is not None:
            summary.download_url = get_storage().get_url(latest_job.output_media.storage_key)
    return summary


def serialize_project_detail(
    project: Project, *, latest_job: RenderJob | None = None
) -> ProjectDetail:
    detail = ProjectDetail.model_validate(
        {
            **serialize_project_summary(project, latest_job=latest_job).model_dump(),
            "topic": project.topic,
            "fps": project.fps,
            "template_key": project.template_key,
            "language": project.language,
            "rtl": is_rtl(project.language),
            "character_id": project.character_id,
            "character_description": (
                project.character.description if project.character is not None else ""
            ),
            "target_duration": project.target_duration,
            "hook": project.hook,
            "cta": project.cta,
            "caption": project.caption,
            "hashtags": list(project.hashtags or []),
            "plan_generated_by": project.plan_generated_by,
            "plan_notes": project.plan_notes,
            "scenes": [],
            "media": [],
        }
    )

    start_times: list[float] = []
    try:
        plan = project_to_plan(project)
        start_times = plan.scene_start_times()
        detail.total_duration = plan.total_duration
    except ValidationError:
        detail.total_duration = 0.0

    ordered_scenes = sorted(project.scenes, key=lambda s: s.order_index)
    detail.scenes = [
        serialize_scene(scene, start_time=start_times[index] if index < len(start_times) else 0.0)
        for index, scene in enumerate(ordered_scenes)
    ]
    detail.media = [
        serialize_media(media)
        for media in sorted(project.media, key=lambda m: (m.kind, m.position, m.created_at))
        if media.source != "render" or media.kind == MediaKind.VIDEO
    ]
    detail.audio = serialize_audio(project.audio_track)
    detail.voice_over = serialize_voice_over(project.voice_over)
    return detail
