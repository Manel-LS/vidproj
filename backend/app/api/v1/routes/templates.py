from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, SessionDep, rate_limit
from app.api.serializers import serialize_project_detail
from app.schemas.project import ProjectDetail
from app.services import project_service, template_service

router = APIRouter(prefix="/projects/{project_id}", tags=["templates"], dependencies=[Depends(rate_limit)])


@router.post("/apply-template/{template_key}", response_model=ProjectDetail,
             summary="Apply a template to this project")
def apply_template(
    project_id: str,
    template_key: str,
    session: SessionDep,
    user: CurrentUser,
    target_duration: float | None = None,
) -> ProjectDetail:
    """Rebuild the project's scenes from a template's blueprint (requirement 18)."""
    project = project_service.get_owned_project(session, project_id, user)
    template_service.apply_template(
        session, project, template_key, target_duration=target_duration
    )
    session.commit()
    session.refresh(project)
    return serialize_project_detail(project)
