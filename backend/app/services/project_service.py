"""Project lifecycle: create, list, update, duplicate, delete.

Every lookup goes through `get_owned_project`, which is the single place user/project
isolation is enforced (requirement 20).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.domain.enums import (
    GenerationMode,
    Language,
    MediaKind,
    Platform,
    VideoFormat,
    VideoStyle,
)
from app.domain import copy as copy_tables
from app.domain.styles import get_style_preset
from app.domain.templates import get_template
from app.infrastructure.storage.base import unique_key
from app.infrastructure.storage.factory import get_storage
from app.models import AudioTrack, Media, Project, RenderJob, Scene, User, VoiceOver
from app.services.plan_assembler import refresh_project_duration

logger = get_logger(__name__)

MAX_NAME_LENGTH = 160


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Please give your project a name.")
    return name[:MAX_NAME_LENGTH]


def get_owned_project(session: Session, project_id: str, user: User) -> Project:
    project = session.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.scenes).selectinload(Scene.media),
            selectinload(Project.media),
            selectinload(Project.audio_track),
            selectinload(Project.voice_over),
        )
    )
    if project is None or project.user_id != user.id:
        # A project owned by someone else is indistinguishable from one that does not
        # exist, so ownership cannot be probed.
        raise NotFoundError("That project could not be found.")
    return project


def list_projects(
    session: Session, user: User, *, limit: int = 50, offset: int = 0, search: str = ""
) -> tuple[list[Project], int]:
    query = select(Project).where(Project.user_id == user.id)
    if search.strip():
        pattern = f"%{search.strip().lower()}%"
        query = query.where(func.lower(Project.name).like(pattern))

    total = int(
        session.scalar(select(func.count()).select_from(query.subquery())) or 0
    )
    projects = list(
        session.scalars(
            query.order_by(Project.updated_at.desc())
            .limit(max(1, min(limit, 100)))
            .offset(max(0, offset))
            .options(selectinload(Project.media), selectinload(Project.scenes))
        )
    )
    return projects, total


def create_project(
    session: Session,
    user: User,
    *,
    name: str,
    description: str = "",
    topic: str = "",
    platform: Platform = Platform.TIKTOK,
    format: VideoFormat | None = None,
    style: VideoStyle = VideoStyle.PRODUCT_SHOWCASE,
    language: Language = Language.ENGLISH,
    template_key: str | None = None,
    character_id: str | None = None,
    target_duration: float | None = None,
    mode: GenerationMode = GenerationMode.STANDARD,
) -> Project:
    if template_key and get_template(template_key) is None:
        raise ValidationError(f"There is no template called '{template_key}'.")

    template = get_template(template_key) if template_key else None
    if template is not None:
        style = template.style
        target_duration = target_duration or template.recommended_duration

    project = Project(
        user_id=user.id,
        name=_clean_name(name),
        description=(description or "").strip()[:4000],
        topic=(topic or "").strip()[:300],
        platform=platform.value,
        format=(format or platform.default_format).value,
        style=style.value,
        language=language.value,
        mode=mode.value,
        template_key=template_key,
        character_id=character_id,
        target_duration=target_duration,
        # The style preset's CTA is English. A project created in another language
        # would carry it forever, and because `request.cta` is then non-empty the
        # planner's language table was never reached.
        cta=(
            copy_tables.cta(language, style)
            if copy_tables.has_copy(language)
            else get_style_preset(style).default_cta
        ),
    )
    session.add(project)
    session.flush()

    # Every project owns an audio slot and a voice-over slot from the start; the editor
    # then only ever updates them, which keeps the API surface simple.
    session.add(AudioTrack(project_id=project.id, volume=get_style_preset(style).music_volume))
    session.add(VoiceOver(project_id=project.id))
    session.flush()
    session.refresh(project)
    return project


def _known_ctas(style: VideoStyle, language: str) -> set[str]:
    """Every CTA this app could have written for that style and language."""
    options = {get_style_preset(style).default_cta}
    if copy_tables.has_copy(language):
        options.add(copy_tables.cta(language, style))
    return options


def update_project(session: Session, project: Project, **changes) -> Project:
    if "name" in changes and changes["name"] is not None:
        project.name = _clean_name(changes["name"])
    for field in ("description", "topic", "hook", "cta", "caption"):
        if changes.get(field) is not None:
            project.__setattr__(field, str(changes[field]).strip()[:4000])
    if changes.get("hashtags") is not None:
        project.hashtags = [str(tag).lstrip("#")[:40] for tag in changes["hashtags"]][:30]
    previous_language = project.language
    for field in ("platform", "format", "style", "language", "mode", "template_key"):
        if changes.get(field) is not None:
            value = changes[field]
            project.__setattr__(field, value.value if hasattr(value, "value") else value)

    # `character_id` is the one field where an explicit null carries meaning: it is
    # how a project drops its character. Everywhere else None means "not sent", but
    # the caller passes `exclude_unset=True`, so the key is present only when the
    # client really sent it — and skipping None made detaching impossible.
    if "character_id" in changes:
        project.character_id = changes["character_id"]

    if changes.get("language") is not None and project.language != previous_language:
        # Re-translate the CTA, but only while it is still one of ours: a phrase
        # the user wrote is theirs, whatever language they switch to.
        style = VideoStyle(project.style)
        was_default = project.cta in _known_ctas(style, previous_language)
        if was_default and copy_tables.has_copy(project.language):
            project.cta = copy_tables.cta(project.language, style)
        elif was_default:
            project.cta = get_style_preset(style).default_cta
    if changes.get("fps") is not None:
        project.fps = max(15, min(int(changes["fps"]), 60))
    if changes.get("target_duration") is not None:
        project.target_duration = max(2.0, min(float(changes["target_duration"]), 180.0))

    refresh_project_duration(project)
    session.flush()
    return project


def duplicate_project(session: Session, project: Project, user: User) -> Project:
    """Deep-copy a project, including its media blobs, so edits stay independent."""
    storage = get_storage()

    copy = Project(
        user_id=user.id,
        name=f"{project.name} (copy)"[:MAX_NAME_LENGTH],
        description=project.description,
        topic=project.topic,
        platform=project.platform,
        format=project.format,
        style=project.style,
        mode=project.mode,
        fps=project.fps,
        template_key=project.template_key,
        target_duration=project.target_duration,
        hook=project.hook,
        cta=project.cta,
        caption=project.caption,
        hashtags=list(project.hashtags or []),
        plan_generated_by=project.plan_generated_by,
        plan_notes=project.plan_notes,
        duration_seconds=project.duration_seconds,
    )
    session.add(copy)
    session.flush()

    media_map: dict[str, str] = {}
    for media in project.media:
        if media.source in ("render", "ai_motion"):
            continue  # outputs are not worth copying; they are cheap to regenerate
        new_key = unique_key(
            f"users/{user.id}/projects/{copy.id}/media",
            media.original_filename or media.storage_key.rsplit("/", 1)[-1],
        )
        new_thumb_key = None
        try:
            storage.upload(new_key, storage.read_bytes(media.storage_key), content_type=media.content_type)
            if media.thumbnail_key:
                new_thumb_key = f"{new_key.rsplit('.', 1)[0]}-thumb.jpg"
                storage.upload(
                    new_thumb_key, storage.read_bytes(media.thumbnail_key), content_type="image/jpeg"
                )
        except Exception:
            logger.warning("Skipping unreadable media %s while duplicating", media.id)
            continue

        clone = Media(
            user_id=user.id,
            project_id=copy.id,
            kind=media.kind,
            source=media.source,
            storage_key=new_key,
            thumbnail_key=new_thumb_key,
            original_filename=media.original_filename,
            content_type=media.content_type,
            size_bytes=media.size_bytes,
            width=media.width,
            height=media.height,
            duration_seconds=media.duration_seconds,
            position=media.position,
            analysis=dict(media.analysis or {}),
        )
        session.add(clone)
        session.flush()
        media_map[media.id] = clone.id

    for scene in project.scenes:
        session.add(
            Scene(
                project_id=copy.id,
                order_index=scene.order_index,
                media_id=media_map.get(scene.media_id or ""),
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
        )

    source_audio = project.audio_track
    session.add(
        AudioTrack(
            project_id=copy.id,
            media_id=media_map.get(source_audio.media_id or "") if source_audio else None,
            volume=source_audio.volume if source_audio else 0.7,
            fade_in=source_audio.fade_in if source_audio else 0.6,
            fade_out=source_audio.fade_out if source_audio else 1.0,
            start_offset=source_audio.start_offset if source_audio else 0.0,
            loop=source_audio.loop if source_audio else True,
        )
    )
    source_voice = project.voice_over
    session.add(
        VoiceOver(
            project_id=copy.id,
            enabled=source_voice.enabled if source_voice else False,
            script=source_voice.script if source_voice else "",
            volume=source_voice.volume if source_voice else 1.0,
            duck_music_to=source_voice.duck_music_to if source_voice else 0.28,
        )
    )

    session.flush()
    session.refresh(copy)
    return copy


def delete_project(session: Session, project: Project) -> None:
    """Remove the project and everything it owns, blobs included."""
    storage = get_storage()
    for media in list(project.media):
        for key in (media.storage_key, media.thumbnail_key):
            if key:
                try:
                    storage.delete(key)
                except Exception:  # pragma: no cover
                    logger.warning("Could not delete stored object %s", key)
    session.delete(project)
    session.flush()


def most_recent_project(session: Session, user: User) -> Project | None:
    """The project the user last touched.

    Used to file media that belongs to the user rather than to one project — a
    character reference, for instance. Storage keys are namespaced per project,
    so something has to own the file on disk even when the concept does not.
    """
    return session.scalar(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.updated_at.desc())
        .limit(1)
    )


def latest_render(session: Session, project: Project) -> RenderJob | None:
    return session.scalar(
        select(RenderJob)
        .where(RenderJob.project_id == project.id)
        .order_by(RenderJob.created_at.desc())
        .limit(1)
    )


def project_thumbnail_media(project: Project) -> Media | None:
    """Prefer the poster from the most recent render, else the first image."""
    if project.thumbnail_media_id:
        for media in project.media:
            if media.id == project.thumbnail_media_id:
                return media
    images = [m for m in project.media if m.kind == MediaKind.IMAGE.value]
    if not images:
        return None
    return sorted(images, key=lambda m: (m.position, m.created_at))[0]
