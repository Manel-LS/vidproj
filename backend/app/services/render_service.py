"""Render job creation and status (requirements 15, 16)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domain.enums import GenerationMode, RenderStatus
from app.domain.plan import VideoPlan
from app.infrastructure.jobs.factory import get_job_queue
from app.infrastructure.render.ffmpeg import FFmpegNotAvailableError, ffmpeg_path
from app.models import Project, RenderJob, User
from app.services.plan_assembler import project_to_plan

ACTIVE_STATUSES = (RenderStatus.QUEUED.value, RenderStatus.PROCESSING.value)


def _ensure_renderable(project: Project, plan: VideoPlan) -> None:
    if not plan.scenes:
        raise ValidationError("Please upload at least one image before rendering.")

    missing = [
        scene.order + 1
        for scene in plan.scenes
        if scene.media_id is None and not (scene.ai_motion and scene.ai_motion.generated_media_id)
    ]
    # A CTA card with no image is legitimate as long as it is not the only scene.
    if len(missing) == len(plan.scenes):
        raise ValidationError("None of your scenes has an image yet. Add one and try again.")

    try:
        ffmpeg_path()
    except FFmpegNotAvailableError as exc:
        raise ValidationError(str(exc)) from exc

    if plan.mode is GenerationMode.AI_MOTION:
        # The provider is only needed to *create* clips. A project whose clips are
        # already generated must stay renderable — otherwise an expired key or a
        # switched-off provider would strand work that is finished and paid for.
        awaiting = [
            scene.order + 1
            for scene in plan.scenes
            if scene.ai_motion
            and scene.ai_motion.enabled
            and not scene.ai_motion.generated_media_id
        ]
        if awaiting:
            from app.infrastructure.i2v.factory import get_i2v_provider

            if not get_i2v_provider().is_available():
                raise ValidationError(
                    "AI Motion is unavailable because no video generation provider is "
                    f"configured, and scene{'s' if len(awaiting) > 1 else ''} "
                    f"{', '.join(str(n) for n in awaiting)} still "
                    f"need{'' if len(awaiting) > 1 else 's'} a clip. Generate the "
                    "missing clips, or switch the project to Standard mode to render."
                )


def active_job(session: Session, project: Project) -> RenderJob | None:
    return session.scalar(
        select(RenderJob)
        .where(RenderJob.project_id == project.id, RenderJob.status.in_(ACTIVE_STATUSES))
        .order_by(RenderJob.created_at.desc())
        .limit(1)
    )


def create_render_job(session: Session, project: Project, user: User) -> RenderJob:
    """Snapshot the plan and queue the render. Returns immediately (requirement 16)."""
    existing = active_job(session, project)
    if existing is not None:
        raise ConflictError(
            "This project is already rendering. Wait for it to finish or cancel it first.",
            details={"render_job_id": existing.id},
        )

    plan = project_to_plan(project)
    _ensure_renderable(project, plan)

    job = RenderJob(
        project_id=project.id,
        user_id=user.id,
        status=RenderStatus.QUEUED.value,
        progress=0,
        stage="Queued",
        plan=plan.model_dump(mode="json"),
    )
    session.add(job)
    project.last_render_id = job.id
    session.flush()
    session.commit()  # the worker runs in another thread/process; it must see the row

    get_job_queue().enqueue_render(job.id)
    return job


def get_job(session: Session, job_id: str, user: User) -> RenderJob:
    job = session.get(RenderJob, job_id)
    if job is None or job.user_id != user.id:
        raise NotFoundError("That render job could not be found.")
    return job


def list_jobs(session: Session, project: Project, *, limit: int = 20) -> list[RenderJob]:
    return list(
        session.scalars(
            select(RenderJob)
            .where(RenderJob.project_id == project.id)
            .order_by(RenderJob.created_at.desc())
            .limit(max(1, min(limit, 100)))
        )
    )


def cancel_job(session: Session, job: RenderJob) -> RenderJob:
    if job.status not in ACTIVE_STATUSES:
        raise ConflictError("That render has already finished.")
    job.cancel_requested = True
    if job.status == RenderStatus.QUEUED.value:
        # It never started, so we can settle it immediately.
        job.status = RenderStatus.CANCELLED.value
        job.stage = "Cancelled"
    session.flush()
    session.commit()
    return job


def recover_orphaned_jobs(session: Session) -> int:
    """Fail jobs left mid-render by a crash, so nothing polls forever."""
    stuck = list(
        session.scalars(select(RenderJob).where(RenderJob.status == RenderStatus.PROCESSING.value))
    )
    for job in stuck:
        job.status = RenderStatus.FAILED.value
        job.error = "Rendering stopped unexpectedly because the server restarted. Try again."
        job.stage = "Failed"
    if stuck:
        session.commit()
    return len(stuck)


def status_message(job: RenderJob) -> str:
    return {
        RenderStatus.QUEUED.value: "Your video is queued...",
        RenderStatus.PROCESSING.value: "Your video is being generated...",
        RenderStatus.COMPLETED.value: "Your video is ready.",
        RenderStatus.FAILED.value: job.error or "Video rendering failed. Try again.",
        RenderStatus.CANCELLED.value: "Rendering was cancelled.",
    }.get(job.status, "")
