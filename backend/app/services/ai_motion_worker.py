"""AI Motion generation (requirement 12), run in the background.

Submits one scene's image to the configured image-to-video provider, polls until the
clip is ready, stores it, and points the scene at it. The renderer then uses that clip
instead of the local animation for that scene — everything else about the pipeline
(transitions, text, audio) is unchanged.
"""
from __future__ import annotations

import time

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import session_scope
from app.domain.enums import GenerationJobType, MediaKind
from app.domain.plan import ERROR_MAX_LENGTH
from app.infrastructure.i2v.base import (
    GenerationRequest,
    GenerationState,
    ImageToVideoUnavailable,
)
from app.infrastructure.i2v.factory import get_i2v_provider
from app.infrastructure.storage.factory import get_storage
from app.models import Media, Project, Scene
from app.services import generation_job_service as jobs, media_service

logger = get_logger(__name__)


def _update_spec(scene: Scene, **changes) -> dict:
    """Write changes to `scene.ai_motion` as a **new** dict, and return it.

    Mutating the dict the attribute already holds and reassigning it produces no
    UPDATE: SQLAlchemy compares old against new, they are the same object, and
    the attribute is reported unchanged. That silently lost the generated clip id
    on the success path — the provider was paid, the clip was stored, and the
    scene never learned about it. Every write goes through here so the mistake
    cannot come back.
    """
    spec = {**(scene.ai_motion or {}), **changes}
    scene.ai_motion = spec
    return spec


def _set_scene_error(session, scene: Scene, message: str, record=None) -> None:
    # Truncated at the source: a provider message longer than the field allows
    # would fail validation on the next read and take the project down with it.
    _update_spec(
        scene, enabled=True, error=message[:ERROR_MAX_LENGTH], generated_media_id=None
    )
    session.commit()
    jobs.fail(session, record, message)


def execute_ai_motion_job(project_id: str, user_id: str, scene_id: str) -> str:
    session = session_scope()
    record = None
    try:
        project = session.get(Project, project_id)
        if project is None or project.user_id != user_id:
            return "failed"
        scene = session.get(Scene, scene_id)
        if scene is None or scene.project_id != project.id:
            return "failed"

        record = jobs.open_job(
            session, project_id=project.id, user_id=user_id,
            type=GenerationJobType.VIDEO, scene_id=scene.id,
        )

        provider = get_i2v_provider()
        if not provider.is_available():
            _set_scene_error(
                session,
                scene,
                "AI Motion is unavailable because no video generation provider is configured.",
                record,
            )
            return "failed"

        if not scene.media_id:
            _set_scene_error(session, scene, "This scene has no image to animate.", record)
            return "failed"

        media = session.get(Media, scene.media_id)
        if media is None:
            _set_scene_error(session, scene, "The scene's image is missing.", record)
            return "failed"

        storage = get_storage()
        image_bytes = storage.read_bytes(media.storage_key)
        spec = dict(scene.ai_motion or {})

        try:
            job_reference = provider.generate_video_from_image(
                GenerationRequest(
                    image=image_bytes,
                    image_content_type=media.content_type,
                    prompt=str(spec.get("prompt") or "subtle cinematic camera movement"),
                    duration_seconds=scene.duration,
                    aspect_ratio=project.format,
                )
            )
        except ImageToVideoUnavailable as exc:
            _set_scene_error(session, scene, str(exc), record)
            return "failed"

        spec = _update_spec(
            scene, enabled=True, provider=provider.name, job_reference=job_reference, error=""
        )
        session.commit()
        jobs.start(session, record, provider=provider.name, stage="Generating motion")
        jobs.progress(session, record, 20, external_job_id=job_reference)

        deadline = time.monotonic() + settings.i2v_timeout_seconds
        while time.monotonic() < deadline:
            time.sleep(settings.i2v_poll_interval_seconds)
            status = provider.get_generation_status(job_reference)
            if status.state is GenerationState.COMPLETED:
                break
            if status.state is GenerationState.FAILED:
                _set_scene_error(
                    session,
                    scene,
                    status.error or "The video generation provider reported a failure.",
                    record,
                )
                return "failed"
        else:
            _set_scene_error(
                session,
                scene,
                "The AI Motion generation timed out. Try again with a shorter scene.",
                record,
            )
            return "failed"

        clip = provider.get_video_result(job_reference)
        clip_media = media_service.store_generated_file(
            session,
            project,
            data=clip.data,
            filename=f"ai-motion-{scene.id[:8]}.{clip.extension}",
            content_type=clip.content_type,
            kind=MediaKind.VIDEO,
            source="ai_motion",
        )

        _update_spec(scene, generated_media_id=clip_media.id, error="")
        session.commit()
        jobs.finish(session, record, result_media_id=clip_media.id, stage="Motion clip ready")
        return "completed"

    except Exception as exc:  # noqa: BLE001
        logger.exception("AI Motion generation failed for scene %s", scene_id)
        try:
            session.rollback()
            scene = session.get(Scene, scene_id)
            if scene is not None:
                _set_scene_error(
                    session, scene, f"AI Motion failed unexpectedly. ({type(exc).__name__})", record
                )
        except Exception:  # pragma: no cover
            logger.exception("Could not record the AI Motion failure")
        return "failed"
    finally:
        session.close()
