from __future__ import annotations

import unicodedata
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentUser, SessionDep, rate_limit
from app.api.serializers import serialize_render_job
from app.core.errors import NotFoundError
from app.domain.enums import RenderStatus
from app.infrastructure.storage.factory import get_storage
from app.schemas.project import RenderJobResponse
from app.services import project_service, render_service

router = APIRouter(tags=["render"], dependencies=[Depends(rate_limit)])


@router.post(
    "/projects/{project_id}/render",
    response_model=RenderJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a render",
)
def start_render(project_id: str, session: SessionDep, user: CurrentUser) -> RenderJobResponse:
    """Queue the render and return immediately (requirement 16)."""
    project = project_service.get_owned_project(session, project_id, user)
    job = render_service.create_render_job(session, project, user)
    return serialize_render_job(job)


@router.get(
    "/projects/{project_id}/renders",
    response_model=list[RenderJobResponse],
    summary="Render history",
)
def list_renders(project_id: str, session: SessionDep, user: CurrentUser) -> list[RenderJobResponse]:
    project = project_service.get_owned_project(session, project_id, user)
    return [serialize_render_job(job) for job in render_service.list_jobs(session, project)]


@router.get(
    "/render-jobs/{job_id}",
    response_model=RenderJobResponse,
    summary="Poll a render job",
)
def get_render_job(job_id: str, session: SessionDep, user: CurrentUser) -> RenderJobResponse:
    job = render_service.get_job(session, job_id, user)
    session.refresh(job)
    return serialize_render_job(job)


@router.post(
    "/render-jobs/{job_id}/cancel",
    response_model=RenderJobResponse,
    summary="Cancel a render",
)
def cancel_render_job(job_id: str, session: SessionDep, user: CurrentUser) -> RenderJobResponse:
    job = render_service.get_job(session, job_id, user)
    render_service.cancel_job(session, job)
    return serialize_render_job(job)


@router.get(
    "/render-jobs/{job_id}/download",
    summary="Download the finished MP4",
    response_class=Response,
)
def download_render(job_id: str, session: SessionDep, user: CurrentUser) -> Response:
    """Stream the rendered file with a filename the browser will save as."""
    job = render_service.get_job(session, job_id, user)
    if job.status != RenderStatus.COMPLETED.value or job.output_media is None:
        raise NotFoundError("That render has not produced a video yet.")

    storage = get_storage()
    data = storage.read_bytes(job.output_media.storage_key)
    filename = job.output_media.original_filename or "video.mp4"
    return Response(
        content=data,
        media_type="video/mp4",
        headers={
            "Content-Disposition": content_disposition(filename),
            "Content-Length": str(len(data)),
        },
    )


def content_disposition(filename: str) -> str:
    """Build a `Content-Disposition` value that survives a non-ASCII filename.

    HTTP headers are Latin-1, so a project named in Arabic, Chinese or Cyrillic
    would raise while encoding the response. RFC 6266 solves this with two
    parameters: a plain ASCII `filename` every client understands, and a
    percent-encoded `filename*` that modern browsers prefer.
    """
    # Transliterate the stem only. Judging the whole string would let the ".mp4"
    # of a name written entirely in another script pass as "content", yielding the
    # nonsense fallback "mp4.mp4".
    stem = filename[:-4] if filename.lower().endswith(".mp4") else filename
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    ascii_stem = "".join(ch for ch in ascii_stem if ch.isalnum() or ch in "._- ").strip(" .-")
    if not any(ch.isalnum() for ch in ascii_stem):
        ascii_stem = "video"

    encoded = quote(filename or "video.mp4", safe="")
    return f"attachment; filename=\"{ascii_stem}.mp4\"; filename*=UTF-8''{encoded}"
