"""Scene editing (requirement 13): create, update, reorder, duplicate, delete.

All timing/animation/text values are validated by round-tripping through the domain
`PlanScene` model, so the database can never hold a scene the renderer would reject.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.domain.enums import AnimationType, MediaKind, TransitionType
from app.domain.plan import MAX_SCENES, PlanScene, TextOverlay
from app.domain.styles import get_style_preset
from app.domain.enums import VideoStyle
from app.models import Media, Project, Scene
from app.services.plan_assembler import refresh_project_duration


def get_scene(session: Session, project: Project, scene_id: str) -> Scene:
    for scene in project.scenes:
        if scene.id == scene_id:
            return scene
    raise NotFoundError("That scene could not be found.")


#: Parking range for the first pass of a reorder; well clear of MAX_SCENES.
_PARK_BASE = 1000


def _assign_orders(session: Session, ordered: list[Scene]) -> None:
    """Write a new ordering without ever colliding on (project_id, order_index).

    The unique constraint is checked per statement, so moving scene 2 to slot 1 while
    scene 1 still occupies it fails. Parking every row in a reserved negative range
    first makes any permutation safe, on PostgreSQL and SQLite alike. The range is far
    from the small negatives used as temporary values for freshly inserted rows, so the
    two never overlap.
    """
    for offset, scene in enumerate(ordered):
        scene.order_index = -(_PARK_BASE + offset)
    session.flush()
    for index, scene in enumerate(ordered):
        scene.order_index = index
    session.flush()


def _resequence(session: Session, project: Project) -> None:
    _assign_orders(session, sorted(project.scenes, key=lambda s: s.order_index))


def _validate_media(session: Session, project: Project, media_id: str | None) -> str | None:
    if media_id is None:
        return None
    media = session.get(Media, media_id)
    if media is None or media.project_id != project.id:
        raise ValidationError("That image is not part of this project.")
    if media.kind != MediaKind.IMAGE.value:
        raise ValidationError("A scene's media must be an image.")
    return media.id


def _apply_domain_scene(scene: Scene, plan_scene: PlanScene) -> None:
    scene.duration = plan_scene.duration
    scene.animation = plan_scene.animation.value
    scene.animation_intensity = plan_scene.animation_intensity
    scene.focus_x = plan_scene.focus_x
    scene.focus_y = plan_scene.focus_y
    scene.transition = plan_scene.transition.value
    scene.transition_duration = plan_scene.transition_duration
    scene.texts = [text.model_dump(mode="json") for text in plan_scene.texts]
    scene.background_color = plan_scene.background_color
    scene.note = plan_scene.note


def create_scene(
    session: Session,
    project: Project,
    *,
    media_id: str | None = None,
    position: int | None = None,
    duration: float | None = None,
) -> Scene:
    if len(project.scenes) >= MAX_SCENES:
        raise ValidationError(f"A video can have at most {MAX_SCENES} scenes.")

    preset = get_style_preset(VideoStyle(project.style))
    media_id = _validate_media(session, project, media_id)

    index = len(project.scenes) if position is None else max(0, min(position, len(project.scenes)))

    plan_scene = PlanScene(
        order=index,
        media_id=media_id,
        duration=duration or preset.scene_seconds[0],
        animation=preset.animations[0],
        animation_intensity=preset.motion_intensity,
        transition=TransitionType.NONE if index == 0 else preset.transitions[0],
        transition_duration=0.0 if index == 0 else preset.transition_seconds,
    )

    existing = sorted(project.scenes, key=lambda s: s.order_index)
    scene = Scene(project_id=project.id, order_index=-(len(existing) + 1), media_id=media_id)
    _apply_domain_scene(scene, plan_scene)
    session.add(scene)
    project.scenes.append(scene)
    session.flush()

    _assign_orders(session, existing[:index] + [scene] + existing[index:])
    refresh_project_duration(project)
    session.flush()
    return scene


def update_scene(session: Session, project: Project, scene: Scene, changes: dict) -> Scene:
    """Apply a partial update, validated through the domain model."""
    current = PlanScene(
        id=scene.id,
        order=scene.order_index,
        media_id=scene.media_id,
        duration=scene.duration,
        animation=AnimationType(scene.animation),
        animation_intensity=scene.animation_intensity,
        focus_x=scene.focus_x,
        focus_y=scene.focus_y,
        transition=TransitionType(scene.transition),
        transition_duration=scene.transition_duration,
        texts=[TextOverlay.model_validate(text) for text in (scene.texts or [])],
        background_color=scene.background_color,
        note=scene.note or "",
    )

    payload = current.model_dump(mode="json")
    if "media_id" in changes:
        scene.media_id = _validate_media(session, project, changes["media_id"])
        payload["media_id"] = scene.media_id
    for field in (
        "duration", "animation", "animation_intensity", "focus_x", "focus_y",
        "transition", "transition_duration", "background_color", "note",
    ):
        if field in changes and changes[field] is not None:
            value = changes[field]
            payload[field] = value.value if hasattr(value, "value") else value
    if "texts" in changes and changes["texts"] is not None:
        payload["texts"] = [
            text if isinstance(text, dict) else text.model_dump(mode="json")
            for text in changes["texts"]
        ]

    # The first scene never has an incoming transition.
    if scene.order_index == 0:
        payload["transition"] = TransitionType.NONE.value
        payload["transition_duration"] = 0.0

    validated = PlanScene.model_validate(payload)
    _apply_domain_scene(scene, validated)
    refresh_project_duration(project)
    session.flush()
    return scene


def reorder_scenes(session: Session, project: Project, ordered_ids: list[str]) -> list[Scene]:
    by_id = {scene.id: scene for scene in project.scenes}
    if set(ordered_ids) != set(by_id):
        raise ValidationError(
            "The reorder request must list every scene in this project exactly once."
        )
    _assign_orders(session, [by_id[scene_id] for scene_id in ordered_ids])

    # The scene that is now first must not carry a transition in.
    first = by_id[ordered_ids[0]]
    first.transition = TransitionType.NONE.value
    first.transition_duration = 0.0

    refresh_project_duration(project)
    session.flush()
    return sorted(by_id.values(), key=lambda s: s.order_index)


def duplicate_scene(session: Session, project: Project, scene: Scene) -> Scene:
    if len(project.scenes) >= MAX_SCENES:
        raise ValidationError(f"A video can have at most {MAX_SCENES} scenes.")

    index = scene.order_index + 1
    existing = sorted(project.scenes, key=lambda s: s.order_index)

    clone = Scene(
        project_id=project.id,
        order_index=-(len(existing) + 1),
        media_id=scene.media_id,
        duration=scene.duration,
        animation=scene.animation,
        animation_intensity=scene.animation_intensity,
        focus_x=scene.focus_x,
        focus_y=scene.focus_y,
        transition=scene.transition,
        transition_duration=scene.transition_duration,
        texts=list(scene.texts or []),
        background_color=scene.background_color,
        note=scene.note,
    )
    session.add(clone)
    project.scenes.append(clone)
    session.flush()

    _assign_orders(session, existing[:index] + [clone] + existing[index:])
    refresh_project_duration(project)
    session.flush()
    return clone


def delete_scene(session: Session, project: Project, scene: Scene) -> None:
    if len(project.scenes) <= 1:
        raise ValidationError("A video needs at least one scene. Delete the project instead.")
    project.scenes.remove(scene)
    session.delete(scene)
    session.flush()

    _resequence(session, project)
    if project.scenes:
        first = min(project.scenes, key=lambda s: s.order_index)
        first.transition = TransitionType.NONE.value
        first.transition_duration = 0.0
    refresh_project_duration(project)
    session.flush()
