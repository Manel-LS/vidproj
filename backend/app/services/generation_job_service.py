"""The unified job registry: recording work so it can be watched.

This service **records**, it does not drive. Each worker stays the source of
truth for its own output; it opens a row here when it starts and closes it when
it finishes, so the dashboard can answer "what is this project doing" without
knowing how six different subsystems store their state.

Every function swallows its own failures. A registry that can break the work it
is describing would be worse than no registry: losing a progress row is a missing
line in a list, losing a generation is money.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.domain.enums import GenerationJobType, RenderStatus
from app.models import GenerationJob, Project, User

logger = get_logger(__name__)

ACTIVE = (RenderStatus.QUEUED.value, RenderStatus.PROCESSING.value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def open_job(
    session: Session,
    *,
    project_id: str,
    user_id: str,
    type: GenerationJobType,
    scene_id: str | None = None,
    provider: str = "",
    stage: str = "Queued",
) -> GenerationJob | None:
    """Record that work has been queued. Returns None if the registry failed."""
    try:
        job = GenerationJob(
            project_id=project_id,
            user_id=user_id,
            scene_id=scene_id,
            type=type.value,
            provider=provider,
            status=RenderStatus.QUEUED.value,
            stage=stage,
        )
        session.add(job)
        session.commit()
        return job
    except Exception:  # noqa: BLE001
        logger.warning("Could not open a %s job row for project %s", type.value, project_id)
        session.rollback()
        return None


def start(session: Session, job: GenerationJob | None, *, provider: str = "", stage: str = "Working") -> None:
    if job is None:
        return
    try:
        job.status = RenderStatus.PROCESSING.value
        job.stage = stage
        job.started_at = _now()
        if provider:
            job.provider = provider
        session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("Could not mark job %s as started", job.id)
        session.rollback()


def progress(
    session: Session,
    job: GenerationJob | None,
    percent: int,
    *,
    stage: str = "",
    external_job_id: str = "",
) -> None:
    if job is None:
        return
    try:
        job.progress = max(0, min(100, int(percent)))
        if stage:
            job.stage = stage
        if external_job_id:
            job.external_job_id = external_job_id[:120]
        session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("Could not update progress on job %s", job.id)
        session.rollback()


def finish(
    session: Session,
    job: GenerationJob | None,
    *,
    result_media_id: str | None = None,
    stage: str = "Done",
) -> None:
    if job is None:
        return
    try:
        job.status = RenderStatus.COMPLETED.value
        job.progress = 100
        job.stage = stage
        job.error = ""
        job.result_media_id = result_media_id
        job.completed_at = _now()
        session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("Could not close job %s", job.id)
        session.rollback()


def fail(session: Session, job: GenerationJob | None, message: str) -> None:
    if job is None:
        return
    try:
        job.status = RenderStatus.FAILED.value
        job.stage = "Failed"
        job.error = message[:2000]
        job.completed_at = _now()
        session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("Could not fail job %s", job.id)
        session.rollback()


def list_for_project(
    session: Session, project: Project, *, limit: int = 50, active_only: bool = False
) -> list[GenerationJob]:
    query = select(GenerationJob).where(GenerationJob.project_id == project.id)
    if active_only:
        query = query.where(GenerationJob.status.in_(ACTIVE))
    return list(
        session.scalars(query.order_by(GenerationJob.created_at.desc()).limit(max(1, min(limit, 200))))
    )


def list_for_user(session: Session, user: User, *, limit: int = 50) -> list[GenerationJob]:
    return list(
        session.scalars(
            select(GenerationJob)
            .where(GenerationJob.user_id == user.id)
            .order_by(GenerationJob.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
    )


def get_owned_job(session: Session, job_id: str, user: User) -> GenerationJob:
    job = session.get(GenerationJob, job_id)
    if job is None or job.user_id != user.id:
        raise NotFoundError("That job could not be found.")
    return job


def project_summary(session: Session, project: Project) -> dict:
    """What the project is doing, in one object the dashboard can render."""
    jobs = list_for_project(session, project, limit=200)
    by_status: dict[str, int] = {}
    for job in jobs:
        by_status[job.status] = by_status.get(job.status, 0) + 1

    active = [job for job in jobs if job.status in ACTIVE]
    # Overall progress is the mean across everything still running: one scene at
    # 90% while five are queued is not a project at 90%.
    overall = int(sum(job.progress for job in active) / len(active)) if active else 0

    return {
        "total": len(jobs),
        "by_status": by_status,
        "active": len(active),
        "progress": overall,
        "current_stage": active[0].stage if active else "",
        "last_error": next((job.error for job in jobs if job.error), ""),
    }


def recover_orphaned(session: Session) -> int:
    """Fail rows left mid-flight by a crash, so nothing polls them forever."""
    stuck = list(
        session.scalars(
            select(GenerationJob).where(GenerationJob.status == RenderStatus.PROCESSING.value)
        )
    )
    for job in stuck:
        job.status = RenderStatus.FAILED.value
        job.stage = "Failed"
        job.error = "This job stopped unexpectedly because the server restarted. Try again."
        job.completed_at = _now()
    if stuck:
        session.commit()
    return len(stuck)
