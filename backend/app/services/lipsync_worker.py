"""Lip-sync one scene's clip against its slice of the narration.

The subtlety that makes this worth its own worker: the voice-over is **one file
for the whole video**, while each scene is a separate clip. Handing a provider the
full narration would lip-sync every scene to words spoken at t=0 — six scenes,
each confidently wrong, with nothing in the output to say so. The scene's window
is therefore computed from the plan and the audio is cut to it before submission.

The silent clip is never destroyed. `generated_media_id` moves to the speaking
clip and `silent_media_id` keeps the original, so lip sync can be redone — or
rolled back — without paying to generate the motion again.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

from app.core.logging import get_logger
from app.db.base import session_scope
from app.core.config import settings
from app.domain.enums import GenerationJobType, MediaKind
from app.domain.plan import ERROR_MAX_LENGTH
from app.infrastructure.lipsync.base import (
    LipSyncRequest,
    LipSyncState,
    LipSyncUnavailable,
)
from app.infrastructure.lipsync.factory import get_lipsync_provider
from app.infrastructure.render.ffmpeg import ffmpeg_path
from app.infrastructure.storage.factory import get_storage
from app.models import Media, Project, Scene
from app.services import generation_job_service as jobs, media_service
from app.services.plan_assembler import project_to_plan

logger = get_logger(__name__)


def _update_spec(scene: Scene, **changes) -> dict:
    """Write to `scene.ai_motion` as a new dict.

    Same reason as the AI Motion worker: mutating the dict the attribute already
    holds and reassigning it produces no UPDATE, and the change is lost silently.
    """
    spec = {**(scene.ai_motion or {}), **changes}
    scene.ai_motion = spec
    return spec


def _fail(session, scene: Scene, message: str, record=None) -> str:
    """Record the failure on the scene and, when there is one, on the job row."""
    _update_spec(scene, error=message[:ERROR_MAX_LENGTH])
    session.commit()
    jobs.fail(session, record, message)
    return "failed"


def _scene_window(project: Project, scene: Scene) -> tuple[float, float] | None:
    """(start, duration) of this scene inside the narration timeline."""
    try:
        plan = project_to_plan(project)
    except Exception:  # noqa: BLE001
        logger.warning("Could not assemble the plan for project %s", project.id)
        return None
    starts = plan.scene_start_times()
    for index, planned in enumerate(plan.scenes):
        if planned.id == scene.id or index == scene.order_index:
            return starts[index], planned.duration
    return None


def _cut_audio(source: Path, target: Path, start: float, duration: float) -> Path:
    """Extract the scene's slice of the voice-over.

    Re-encoded rather than stream-copied: a copy cuts on the nearest keyframe,
    which for MP3 can slip by tens of milliseconds — visible as lips leading or
    trailing the sound.
    """
    subprocess.run(
        [
            ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.1, duration):.3f}",
            "-i", str(source),
            "-vn", "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
            str(target),
        ],
        check=True,
    )
    return target


def _public_url(key: str) -> str:
    """A URL a third party can fetch, or empty when storage cannot serve one."""
    url = get_storage().get_url(key)
    return url if url.startswith(("http://", "https://")) else ""


def execute_lipsync_job(project_id: str, user_id: str, scene_id: str) -> str:
    session = session_scope()
    workspace: tempfile.TemporaryDirectory | None = None
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
            type=GenerationJobType.LIPSYNC, scene_id=scene.id,
        )

        def fail(message: str) -> str:
            return _fail(session, scene, message, record)

        provider = get_lipsync_provider()
        if not provider.is_available():
            from app.infrastructure.lipsync.factory import UNCONFIGURED_MESSAGE

            return fail(UNCONFIGURED_MESSAGE)

        spec = dict(scene.ai_motion or {})
        # Always start from the silent clip. Re-running on an already lip-synced
        # clip would sync a mouth that is already moving to the same words.
        source_id = spec.get("silent_media_id") or spec.get("generated_media_id")
        if not source_id:
            return fail("Generate this scene's motion clip before lip-syncing it.")
        clip = session.get(Media, source_id)
        if clip is None or clip.kind != MediaKind.VIDEO.value:
            return fail("This scene's motion clip is missing.")

        voice = project.voice_over
        if voice is None or not voice.media_id:
            return fail("Generate the voice-over before lip-syncing this scene.")
        voice_media = session.get(Media, voice.media_id)
        if voice_media is None:
            return fail("The voice-over audio is missing.")

        window = _scene_window(project, scene)
        if window is None:
            return fail("This scene is not on the timeline yet.")
        start, duration = window
        if duration > provider.max_clip_seconds:
            return fail(
                f"{provider.display_name} accepts clips up to "
                f"{provider.max_clip_seconds:.0f}s; this scene is {duration:.1f}s. "
                "Split it into shorter scenes."
            )

        storage = get_storage()
        workspace = tempfile.TemporaryDirectory(prefix="lipsync-")
        root = Path(workspace.name)

        clip_path = root / "clip.mp4"
        clip_path.write_bytes(storage.read_bytes(clip.storage_key))
        voice_path = root / "voice-full.mp3"
        voice_path.write_bytes(storage.read_bytes(voice_media.storage_key))
        slice_path = _cut_audio(voice_path, root / "voice-slice.mp3", start, duration)

        video_url = _public_url(clip.storage_key)
        audio_url = ""  # the slice exists only here, so it never has a URL
        if provider.needs_public_urls and not video_url:
            return fail(
                f"{provider.display_name} downloads the media itself, which local storage "
                "cannot serve. Switch STORAGE_PROVIDER to s3, or use a provider that "
                "accepts uploads."
            )

        try:
            job_reference = provider.generate_lipsync(
                LipSyncRequest(
                    video=clip_path.read_bytes(),
                    video_content_type=clip.content_type or "video/mp4",
                    audio=slice_path.read_bytes(),
                    audio_content_type="audio/mpeg",
                    video_url=video_url,
                    audio_url=audio_url,
                )
            )
        except LipSyncUnavailable as exc:
            return fail(str(exc))

        _update_spec(
            scene,
            lipsync_provider=provider.name,
            lipsync_job_reference=job_reference,
            error="",
        )
        session.commit()
        jobs.start(session, record, provider=provider.name, stage="Syncing lips")
        jobs.progress(session, record, 25, external_job_id=job_reference)

        deadline = time.monotonic() + settings.lipsync_timeout_seconds
        while time.monotonic() < deadline:
            time.sleep(settings.lipsync_poll_interval_seconds)
            try:
                status = provider.get_status(job_reference)
            except LipSyncUnavailable as exc:
                return fail(str(exc))
            if status.state is LipSyncState.COMPLETED:
                break
            if status.state is LipSyncState.FAILED:
                return fail(status.error or "The lip-sync provider reported a failure.")
        else:
            return fail(
                "Lip sync timed out. Try again, or split this scene into shorter ones."
            )

        try:
            result = provider.get_result(job_reference)
        except LipSyncUnavailable as exc:
            return fail(str(exc))

        spoken = media_service.store_generated_file(
            session,
            project,
            data=result.data,
            filename=f"lipsync-{scene.id[:8]}.{result.extension}",
            content_type=result.content_type,
            kind=MediaKind.VIDEO,
            source="lipsync",
        )
        _update_spec(
            scene,
            silent_media_id=source_id,
            generated_media_id=spoken.id,
            error="",
        )
        session.commit()
        jobs.finish(session, record, result_media_id=spoken.id, stage="Lip sync ready")
        return "completed"

    except Exception as exc:  # noqa: BLE001
        logger.exception("Lip sync failed for scene %s", scene_id)
        try:
            session.rollback()
            scene = session.get(Scene, scene_id)
            if scene is not None:
                # Not the closure: it is defined inside the `try`, so an exception
                # raised before that line would leave the name unbound here.
                _fail(session, scene, f"Lip sync failed unexpectedly. ({type(exc).__name__})", record)
        except Exception:  # noqa: BLE001
            logger.exception("Could not record the lip-sync failure for scene %s", scene_id)
        return "failed"
    finally:
        if workspace is not None:
            workspace.cleanup()
        session.close()
