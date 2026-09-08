from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep, rate_limit
from app.api.serializers import serialize_scene
from app.schemas.project import (
    ReorderScenesRequest,
    SceneCreate,
    SceneResponse,
    SceneUpdate,
)
from app.services import project_service, scene_service
from app.services.plan_assembler import project_to_plan

router = APIRouter(
    prefix="/projects/{project_id}/scenes", tags=["scenes"], dependencies=[Depends(rate_limit)]
)


def _serialize_all(project) -> list[SceneResponse]:
    try:
        starts = project_to_plan(project).scene_start_times()
    except Exception:
        starts = []
    ordered = sorted(project.scenes, key=lambda s: s.order_index)
    return [
        serialize_scene(scene, start_time=starts[index] if index < len(starts) else 0.0)
        for index, scene in enumerate(ordered)
    ]


@router.get("", response_model=list[SceneResponse], summary="List scenes")
def list_scenes(project_id: str, session: SessionDep, user: CurrentUser) -> list[SceneResponse]:
    project = project_service.get_owned_project(session, project_id, user)
    return _serialize_all(project)


@router.post("", response_model=list[SceneResponse], status_code=status.HTTP_201_CREATED,
             summary="Add a scene")
def create_scene(
    project_id: str, payload: SceneCreate, session: SessionDep, user: CurrentUser
) -> list[SceneResponse]:
    project = project_service.get_owned_project(session, project_id, user)
    scene_service.create_scene(
        session,
        project,
        media_id=payload.media_id,
        position=payload.position,
        duration=payload.duration,
    )
    session.commit()
    session.refresh(project)
    return _serialize_all(project)


@router.patch("/{scene_id}", response_model=SceneResponse, summary="Edit a scene")
def update_scene(
    project_id: str,
    scene_id: str,
    payload: SceneUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> SceneResponse:
    project = project_service.get_owned_project(session, project_id, user)
    scene = scene_service.get_scene(session, project, scene_id)
    scene_service.update_scene(
        session, project, scene, payload.model_dump(exclude_unset=True)
    )
    session.commit()
    session.refresh(project)
    index = sorted(project.scenes, key=lambda s: s.order_index).index(scene)
    try:
        starts = project_to_plan(project).scene_start_times()
    except Exception:
        starts = []
    return serialize_scene(scene, start_time=starts[index] if index < len(starts) else 0.0)


@router.post("/reorder", response_model=list[SceneResponse], summary="Reorder scenes")
def reorder_scenes(
    project_id: str, payload: ReorderScenesRequest, session: SessionDep, user: CurrentUser
) -> list[SceneResponse]:
    project = project_service.get_owned_project(session, project_id, user)
    scene_service.reorder_scenes(session, project, payload.scene_ids)
    session.commit()
    session.refresh(project)
    return _serialize_all(project)


@router.post("/{scene_id}/duplicate", response_model=list[SceneResponse],
             status_code=status.HTTP_201_CREATED, summary="Duplicate a scene")
def duplicate_scene(
    project_id: str, scene_id: str, session: SessionDep, user: CurrentUser
) -> list[SceneResponse]:
    project = project_service.get_owned_project(session, project_id, user)
    scene = scene_service.get_scene(session, project, scene_id)
    scene_service.duplicate_scene(session, project, scene)
    session.commit()
    session.refresh(project)
    return _serialize_all(project)


@router.delete("/{scene_id}", response_model=list[SceneResponse], summary="Delete a scene")
def delete_scene(
    project_id: str, scene_id: str, session: SessionDep, user: CurrentUser
) -> list[SceneResponse]:
    project = project_service.get_owned_project(session, project_id, user)
    scene = scene_service.get_scene(session, project, scene_id)
    scene_service.delete_scene(session, project, scene)
    session.commit()
    session.refresh(project)
    return _serialize_all(project)
