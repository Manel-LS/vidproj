"""The background render worker.

Runs under either job queue. It owns its own database session, writes progress as it
goes so the client's polling shows movement, and always cleans up its temp directory —
including on failure (requirement 20: temporary file cleanup).
"""
from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.errors import AppError, RenderError
from app.core.logging import get_logger
from app.domain.enums import GenerationJobType, MediaKind, RenderStatus
from app.domain.plan import VideoPlan
from app.db.base import session_scope
from app.infrastructure.render.base import RenderRequest
from app.infrastructure.render.engine import FFmpegRenderEngine
from app.infrastructure.storage.factory import get_storage
from app.models import GenerationJob, Media, Project, RenderJob
from app.services import generation_job_service as jobs
from app.services import media_service

logger = get_logger(__name__)

#: Write progress to the database at most this often, to avoid a write per frame.
_PROGRESS_WRITE_INTERVAL = 0.5


def _mirror(session, job: RenderJob) -> None:
    """Copy a render job's state onto its row in the unified registry.

    Mirroring rather than threading a handle through: `_finish` is reached from
    five paths, and an edit that forgets one leaves a job stuck at "processing"
    in the dashboard forever.
    """
    try:
        record = session.scalar(
            select(GenerationJob).where(GenerationJob.external_job_id == job.id).limit(1)
        )
        if record is None:
            return
        record.status = job.status
        record.progress = job.progress
        record.stage = job.stage
        record.error = job.error or ""
        record.result_media_id = job.output_media_id
        if job.status not in (RenderStatus.QUEUED.value, RenderStatus.PROCESSING.value):
            record.completed_at = datetime.now(timezone.utc)
        session.commit()
    except Exception:  # noqa: BLE001
        # The registry must never take the render down with it.
        logger.warning("Could not mirror render job %s into the registry", job.id)
        session.rollback()


def execute_render_job(job_id: str) -> str:
    """Render one job. Returns the final status; never raises to the queue."""
    session = session_scope()
    work_dir: Path | None = None
    try:
        job = session.get(RenderJob, job_id)
        if job is None:
            logger.warning("Render job %s no longer exists", job_id)
            return RenderStatus.FAILED.value
        if job.cancel_requested or job.status == RenderStatus.CANCELLED.value:
            _finish(session, job, RenderStatus.CANCELLED, stage="Cancelled")
            return RenderStatus.CANCELLED.value

        project = session.get(Project, job.project_id)
        if project is None:
            _finish(session, job, RenderStatus.FAILED, error="The project was deleted.")
            return RenderStatus.FAILED.value

        record = jobs.open_job(
            session,
            project_id=job.project_id,
            user_id=job.user_id,
            type=GenerationJobType.RENDER,
            provider="ffmpeg",
            stage="Rendering",
        )
        if record is not None:
            # The render job's own id is the key `_mirror` looks the row up by.
            record.external_job_id = job.id
            session.commit()
            jobs.start(session, record, provider="ffmpeg", stage="Rendering")

        job.status = RenderStatus.PROCESSING.value
        job.started_at = datetime.now(timezone.utc)
        job.stage = "Starting"
        job.progress = 1
        session.commit()

        plan = VideoPlan.model_validate(job.plan)
        storage = get_storage()

        media_paths: dict[str, Path] = {}
        for media_id in set(plan.media_ids()):
            media = session.get(Media, media_id)
            if media is None or media.project_id != project.id:
                continue
            try:
                media_paths[media_id] = storage.local_path(media.storage_key)
            except AppError:
                logger.warning("Media %s is missing from storage; skipping", media_id)

        work_dir = Path(settings.render_work_dir) / f"job-{job.id}"
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)

        output_path = work_dir / "output.mp4"
        poster_path = work_dir / "poster.jpg"
        last_write = 0.0

        def on_progress(percent: int, stage: str) -> None:
            nonlocal last_write
            now = time.monotonic()
            if percent >= 100 or now - last_write >= _PROGRESS_WRITE_INTERVAL:
                last_write = now
                job.progress = max(job.progress, min(99, percent))
                job.stage = stage
                session.commit()

        def cancel_check() -> bool:
            session.refresh(job, attribute_names=["cancel_requested"])
            return bool(job.cancel_requested)

        engine = FFmpegRenderEngine()
        result = engine.render(
            RenderRequest(
                plan=plan,
                media_paths=media_paths,
                output_path=output_path,
                work_dir=work_dir / "tmp",
                poster_path=poster_path,
                cancel_check=cancel_check,
            ),
            on_progress,
        )

        video_media = media_service.store_generated_file(
            session,
            project,
            data=result.video_path,
            filename=f"{_safe_slug(project.name)}.mp4",
            content_type="video/mp4",
            kind=MediaKind.VIDEO,
            source="render",
        )
        video_media.width = result.width
        video_media.height = result.height
        video_media.duration_seconds = result.duration

        if result.poster_path and Path(result.poster_path).is_file():
            poster_media = media_service.store_generated_file(
                session,
                project,
                data=Path(result.poster_path),
                filename=f"{_safe_slug(project.name)}-poster.jpg",
                content_type="image/jpeg",
                kind=MediaKind.IMAGE,
                source="render",
            )
            project.thumbnail_media_id = poster_media.id

        job.output_media_id = video_media.id
        project.duration_seconds = result.duration
        project.last_render_id = job.id
        _finish(session, job, RenderStatus.COMPLETED, stage="Completed", progress=100)
        logger.info("Render %s completed: %s (%.1fs)", job.id, video_media.storage_key, result.duration)
        return RenderStatus.COMPLETED.value

    except RenderError as exc:
        status = (
            RenderStatus.CANCELLED if exc.code == "render_cancelled" else RenderStatus.FAILED
        )
        _safe_finish(session, job_id, status, error=exc.message)
        return status.value
    except Exception as exc:  # noqa: BLE001 - a worker must never die silently
        logger.exception("Render job %s crashed", job_id)
        _safe_finish(
            session,
            job_id,
            RenderStatus.FAILED,
            error=f"Video rendering failed unexpectedly. Try again. ({type(exc).__name__})",
        )
        return RenderStatus.FAILED.value
    finally:
        if work_dir is not None and not settings.keep_render_workdir:
            shutil.rmtree(work_dir, ignore_errors=True)
        session.close()


def _safe_slug(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in (name or "video"))
    return cleaned.strip("-")[:48].lower() or "video"


def _finish(
    session,
    job: RenderJob,
    status: RenderStatus,
    *,
    stage: str = "",
    error: str = "",
    progress: int | None = None,
) -> None:
    job.status = status.value
    job.stage = stage or status.value.title()
    job.error = error
    if progress is not None:
        job.progress = progress
    job.finished_at = datetime.now(timezone.utc)
    session.commit()
    _mirror(session, job)


def _safe_finish(session, job_id: str, status: RenderStatus, *, error: str = "") -> None:
    try:
        session.rollback()
        job = session.get(RenderJob, job_id)
        if job is not None:
            _finish(session, job, status, error=error)
    except Exception:  # pragma: no cover - the database itself is in trouble
        logger.exception("Could not record the failure of render job %s", job_id)
