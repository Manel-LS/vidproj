"""Generate a scene's still image from its prompt (background job).

Generation takes seconds to a minute, so it never runs inside a request. The job
does four things and commits once at the end of each, so a crash leaves the scene
in a state the UI can explain rather than half-written.

The generated image goes through the same `add_image` path as an upload —
optimisation, thumbnail, analysis, dimensions — because everything downstream
(focus point, Ken Burns, the renderer) reads those fields. Storing the raw bytes
would produce a scene the planner cannot reason about.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.base import session_scope
from app.domain.plan import ERROR_MAX_LENGTH
from app.infrastructure.image.base import ImageRequest, ImageUnavailable
from app.infrastructure.image.factory import get_image_provider
from app.infrastructure.storage.factory import get_storage
from app.models import Media, Project, Scene
from app.domain.enums import GenerationJobType
from app.services import character_service, generation_job_service as jobs, media_service

logger = get_logger(__name__)


def _set_scene_error(session, scene: Scene, message: str, record=None) -> None:
    """Record a failure where the editor can show it.

    Reuses the `ai_motion` spec's error slot: it is the scene's one place for
    "the last generation for this scene went wrong", and the UI already renders it.
    """
    scene.ai_motion = {
        **(scene.ai_motion or {}),
        "error": message[:ERROR_MAX_LENGTH],
    }
    session.commit()
    jobs.fail(session, record, message)


def execute_image_job(project_id: str, user_id: str, scene_id: str) -> str:
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
            type=GenerationJobType.IMAGE, scene_id=scene.id,
        )

        provider = get_image_provider()
        if not provider.is_available():
            from app.infrastructure.image.factory import UNCONFIGURED_MESSAGE

            _set_scene_error(session, scene, UNCONFIGURED_MESSAGE, record)
            return "failed"

        prompt = (scene.image_prompt or "").strip()
        if not prompt:
            _set_scene_error(session, scene, "This scene has no image prompt yet.", record)
            return "failed"

        # The character clause goes in front, verbatim and identical for every
        # scene. That repetition is the whole mechanism: rebuilding a description
        # per scene, however carefully, drifts into a different person.
        jobs.start(session, record, provider=provider.name, stage="Generating image")

        prefix = character_service.prompt_prefix(project)
        if prefix and prefix not in prompt:
            prompt = f"{prefix}. {prompt}"

        # A reference image keeps the character recognisable between scenes, but
        # only providers that accept one can use it — passing it blindly would
        # make the others fail on an unexpected field.
        reference: bytes | None = None
        reference_type = ""
        if provider.supports_reference_image:
            reference, reference_type = _reference_for(session, project, scene)

        try:
            generated = provider.generate(
                ImageRequest(
                    prompt=prompt,
                    aspect_ratio=project.format,
                    reference_image=reference,
                    reference_content_type=reference_type,
                )
            )
        except ImageUnavailable as exc:
            _set_scene_error(session, scene, str(exc), record)
            return "failed"

        previous_media_id = scene.media_id
        media = media_service.add_image(
            session,
            project,
            media_service.UploadPayload(
                filename=f"ai-image-{scene.id[:8]}.{generated.extension}",
                content_type=generated.content_type,
                data=generated.data,
            ),
            source="ai_image",
        )
        scene.media_id = media.id
        scene.ai_motion = {**(scene.ai_motion or {}), "error": ""}
        session.commit()

        # Only now that the new image is committed is it safe to drop the old
        # one: deleting first would leave the scene blank if generation failed.
        if previous_media_id and previous_media_id != media.id:
            _discard_superseded(session, previous_media_id)

        jobs.finish(session, record, result_media_id=media.id, stage="Image ready")
        return "completed"

    except Exception as exc:  # noqa: BLE001
        logger.exception("Image generation failed for scene %s", scene_id)
        try:
            session.rollback()
            scene = session.get(Scene, scene_id)
            if scene is not None:
                _set_scene_error(
                    session, scene,
                    f"Image generation failed unexpectedly. ({type(exc).__name__})", record,
                )
        except Exception:  # noqa: BLE001
            logger.exception("Could not record the image failure for scene %s", scene_id)
        return "failed"
    finally:
        session.close()


def _reference_for(session, project: Project, scene: Scene) -> tuple[bytes | None, str]:
    """The picture that anchors the subject.

    The character's own reference wins: it is the one image the user chose to
    define the subject, and it stays the same across every project. Only when
    there is none do we fall back to the first image generated in this project,
    which at least keeps the scenes of one video consistent with each other.
    """
    chosen: Media | None = None
    if project.character is not None and project.character.reference_media is not None:
        chosen = project.character.reference_media
    else:
        earlier = [
            media
            for media in project.media
            if media.source == "ai_image" and media.id != scene.media_id
        ]
        if earlier:
            earlier.sort(key=lambda m: m.created_at)
            chosen = earlier[0]

    if chosen is None:
        return None, ""
    try:
        return get_storage().read_bytes(chosen.storage_key), chosen.content_type
    except Exception:  # noqa: BLE001
        logger.warning("Reference image %s could not be read; generating without it", chosen.id)
        return None, ""


def _discard_superseded(session, media_id: str) -> None:
    media = session.get(Media, media_id)
    # Only ever remove an image this pipeline produced. A user's upload stays,
    # even when a generated image replaces it on the scene.
    if media is not None and media.source == "ai_image":
        media_service.delete_media(session, media)
        session.commit()
