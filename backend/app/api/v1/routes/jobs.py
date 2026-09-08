"""The unified job registry, read-side.

One place to answer "what is this project doing", across image generation, motion,
voice, lip sync and rendering. The editor polls `/projects/{id}/jobs` while work
is in flight; `/jobs` is the account-wide feed for the dashboard.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, SessionDep, rate_limit
from app.domain.enums import GenerationJobType, RenderStatus
from app.infrastructure.storage.factory import get_storage
from app.models import GenerationJob, Media
from app.schemas.common import APIModel
from app.services import generation_job_service as jobs
from app.services import project_service

router = APIRouter(tags=["jobs"], dependencies=[Depends(rate_limit)])


class GenerationJobResponse(APIModel):
    id: str
    project_id: str
    scene_id: str | None = None
    type: GenerationJobType
    provider: str
    status: RenderStatus
    progress: int
    stage: str
    error: str
    external_job_id: str
    result_media_id: str | None = None
    result_url: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ProjectJobsResponse(APIModel):
    """The list plus the one-line summary the dashboard card needs."""

    items: list[GenerationJobResponse]
    total: int
    active: int
    progress: int
    current_stage: str
    last_error: str
    by_status: dict[str, int]


def serialize_job(session, job: GenerationJob) -> GenerationJobResponse:
    url = None
    if job.result_media_id:
        media = session.get(Media, job.result_media_id)
        if media is not None:
            url = get_storage().get_url(media.storage_key)
    return GenerationJobResponse.model_validate(
        {
            "id": job.id,
            "project_id": job.project_id,
            "scene_id": job.scene_id,
            "type": job.type,
            "provider": job.provider,
            "status": job.status,
            "progress": job.progress,
            "stage": job.stage,
            "error": job.error,
            "external_job_id": job.external_job_id,
            "result_media_id": job.result_media_id,
            "result_url": url,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
        }
    )


@router.get(
    "/projects/{project_id}/jobs",
    response_model=ProjectJobsResponse,
    summary="Everything this project has generated or is generating",
)
def list_project_jobs(
    project_id: str,
    session: SessionDep,
    user: CurrentUser,
    limit: int = 50,
    active_only: bool = False,
) -> ProjectJobsResponse:
    project = project_service.get_owned_project(session, project_id, user)
    items = jobs.list_for_project(session, project, limit=limit, active_only=active_only)
    summary = jobs.project_summary(session, project)
    return ProjectJobsResponse.model_validate(
        {"items": [serialize_job(session, job) for job in items], **summary}
    )


@router.get("/jobs", response_model=list[GenerationJobResponse], summary="Your recent jobs")
def list_jobs(
    session: SessionDep, user: CurrentUser, limit: int = 50
) -> list[GenerationJobResponse]:
    return [serialize_job(session, job) for job in jobs.list_for_user(session, user, limit=limit)]


@router.get("/jobs/{job_id}", response_model=GenerationJobResponse, summary="Poll one job")
def get_job(job_id: str, session: SessionDep, user: CurrentUser) -> GenerationJobResponse:
    return serialize_job(session, jobs.get_owned_job(session, job_id, user))
