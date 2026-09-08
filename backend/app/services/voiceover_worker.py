"""Voice-over synthesis (requirement 11), run in the background."""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.base import session_scope
from app.domain.enums import GenerationJobType, MediaKind, VoiceOverStatus
from app.infrastructure.render.ffmpeg import probe_duration
from app.infrastructure.storage.factory import get_storage
from app.infrastructure.tts.base import VoiceUnavailable
from app.infrastructure.tts.factory import get_voice_provider
from app.models import Project, VoiceOver
from app.services import generation_job_service as jobs, media_service

logger = get_logger(__name__)


def execute_voiceover_job(project_id: str, user_id: str) -> str:
    session = session_scope()
    record = None
    try:
        project = session.get(Project, project_id)
        if project is None or project.user_id != user_id:
            return VoiceOverStatus.FAILED.value
        record = jobs.open_job(
            session, project_id=project.id, user_id=user_id, type=GenerationJobType.VOICE
        )
        voice = project.voice_over
        if voice is None:
            voice = VoiceOver(project_id=project.id)
            session.add(voice)
            session.flush()

        voice.status = VoiceOverStatus.GENERATING.value
        jobs.start(session, record, stage="Synthesising voice")
        voice.error = ""
        session.commit()

        provider = get_voice_provider()
        try:
            result = provider.synthesize(voice.script, voice_id=voice.voice_id)
        except VoiceUnavailable as exc:
            voice.status = VoiceOverStatus.FAILED.value
            voice.error = str(exc)
            session.commit()
            jobs.fail(session, record, str(exc))
            return VoiceOverStatus.FAILED.value

        old_media_id = voice.media_id
        media = media_service.store_generated_file(
            session,
            project,
            data=result.audio,
            filename=f"voiceover.{result.extension}",
            content_type=result.content_type,
            kind=MediaKind.AUDIO,
            source="voiceover",
        )
        try:
            media.duration_seconds = probe_duration(get_storage().local_path(media.storage_key))
        except Exception:  # pragma: no cover
            pass

        voice.media_id = media.id
        voice.provider = result.provider
        voice.voice_id = result.voice_id
        voice.status = VoiceOverStatus.READY.value
        voice.enabled = True
        session.commit()
        jobs.finish(session, record, result_media_id=media.id, stage="Voice ready")

        if old_media_id:
            old = session.get(type(media), old_media_id)
            if old is not None:
                media_service.delete_media(session, old)
                session.commit()

        return VoiceOverStatus.READY.value

    except Exception as exc:  # noqa: BLE001
        logger.exception("Voice-over generation failed for project %s", project_id)
        try:
            session.rollback()
            project = session.get(Project, project_id)
            if project is not None and project.voice_over is not None:
                project.voice_over.status = VoiceOverStatus.FAILED.value
                project.voice_over.error = (
                    f"Voice-over generation failed unexpectedly. ({type(exc).__name__})"
                )
                session.commit()
            jobs.fail(session, record, f"Voice-over generation failed. ({type(exc).__name__})")
        except Exception:  # pragma: no cover
            logger.exception("Could not record the voice-over failure")
        return VoiceOverStatus.FAILED.value
    finally:
        session.close()
