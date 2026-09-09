from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, SessionDep, rate_limit
from app.api.serializers import serialize_project_detail, serialize_project_summary
from app.schemas.common import Page
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectSummary, ProjectUpdate
from app.services import brand_kit_service, character_service, project_service

router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[Depends(rate_limit)])


@router.get("", response_model=Page[ProjectSummary], summary="List your projects")
def list_projects(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default="", max_length=160),
) -> Page[ProjectSummary]:
    projects, total = project_service.list_projects(
        session, user, limit=limit, offset=offset, search=search
    )
    items = [
        serialize_project_summary(project, latest_job=project_service.latest_render(session, project))
        for project in projects
    ]
    return Page[ProjectSummary](items=items, total=total, limit=limit, offset=offset)


@router.post(
    "",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a video project",
)
def create_project(payload: ProjectCreate, session: SessionDep, user: CurrentUser) -> ProjectDetail:
    if payload.character_id:
        # Validated here rather than trusted: an unchecked id would let a project
        # point at someone else's character.
        character_service.get_owned_character(session, payload.character_id, user)
    if payload.brand_kit_id:
        brand_kit_service.get_owned_kit(session, payload.brand_kit_id, user)
    project = project_service.create_project(
        session,
        user,
        name=payload.name,
        description=payload.description,
        topic=payload.topic,
        platform=payload.platform,
        format=payload.format,
        style=payload.style,
        language=payload.language,
        template_key=payload.template_key,
        character_id=payload.character_id,
        brand_kit_id=payload.brand_kit_id,
        target_duration=payload.target_duration,
        mode=payload.mode,
        subtitle_style=payload.subtitle_style,
    )
    session.commit()
    return serialize_project_detail(project)


@router.get("/{project_id}", response_model=ProjectDetail, summary="Get one project")
def get_project(project_id: str, session: SessionDep, user: CurrentUser) -> ProjectDetail:
    project = project_service.get_owned_project(session, project_id, user)
    return serialize_project_detail(
        project, latest_job=project_service.latest_render(session, project)
    )


@router.patch("/{project_id}", response_model=ProjectDetail, summary="Update a project")
def update_project(
    project_id: str, payload: ProjectUpdate, session: SessionDep, user: CurrentUser
) -> ProjectDetail:
    project = project_service.get_owned_project(session, project_id, user)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("character_id"):
        character_service.get_owned_character(session, changes["character_id"], user)
    if changes.get("brand_kit_id"):
        brand_kit_service.get_owned_kit(session, changes["brand_kit_id"], user)
    project_service.update_project(session, project, **changes)
    session.commit()
    session.refresh(project)
    return serialize_project_detail(project)


@router.post(
    "/{project_id}/duplicate",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate a project",
)
def duplicate_project(project_id: str, session: SessionDep, user: CurrentUser) -> ProjectDetail:
    project = project_service.get_owned_project(session, project_id, user)
    copy = project_service.duplicate_project(session, project, user)
    session.commit()
    return serialize_project_detail(copy)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a project",
)
def delete_project(project_id: str, session: SessionDep, user: CurrentUser) -> None:
    project = project_service.get_owned_project(session, project_id, user)
    project_service.delete_project(session, project)
    session.commit()
