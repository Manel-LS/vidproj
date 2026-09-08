"""Persistence models (requirement 21).

The scene list is stored as normalised rows rather than one JSON blob so the editor
can update a single scene without rewriting the project, and so ordering constraints
are enforced by the database. `services.plan_assembler` projects these rows into the
domain `VideoPlan` used for rendering.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, UtcDateTime
from app.domain.enums import (
    CharacterKind,
    Language,
    AnimationType,
    GenerationMode,
    MediaKind,
    Platform,
    RenderStatus,
    TransitionType,
    VideoFormat,
    VideoStyle,
    VoiceOverStatus,
)
from app.domain.subtitles import SubtitleStyle


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    projects: Mapped[list["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    characters: Mapped[list["Character"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Character.updated_at.desc()",
        passive_deletes=True,
    )
    media: Mapped[list["Media"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_user_updated", "user_id", "updated_at"),)

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    topic: Mapped[str] = mapped_column(String(300), default="", nullable=False)

    platform: Mapped[str] = mapped_column(String(32), default=Platform.TIKTOK.value, nullable=False)
    format: Mapped[str] = mapped_column(String(16), default=VideoFormat.PORTRAIT_9_16.value, nullable=False)
    style: Mapped[str] = mapped_column(String(32), default=VideoStyle.PRODUCT_SHOWCASE.value, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default=Language.ENGLISH.value, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default=GenerationMode.STANDARD.value, nullable=False)
    fps: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    template_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Burned-in subtitle style; "none" means the video carries none.
    subtitle_style: Mapped[str] = mapped_column(
        String(16), default=SubtitleStyle.NONE.value, server_default=SubtitleStyle.NONE.value, nullable=False
    )
    character_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    target_duration: Mapped[float | None] = mapped_column(Float, nullable=True)

    hook: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    cta: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    caption: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hashtags: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    plan_generated_by: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    plan_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    #: Denormalised for the dashboard card; refreshed whenever scenes change.
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    thumbnail_media_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_render_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    user: Mapped[User] = relationship(back_populates="projects")
    character: Mapped["Character | None"] = relationship(
        foreign_keys=[character_id], lazy="joined"
    )
    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Scene.order_index",
        passive_deletes=True,
    )
    media: Mapped[list["Media"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Media.position",
        passive_deletes=True,
        foreign_keys="Media.project_id",
    )
    audio_track: Mapped["AudioTrack | None"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False, passive_deletes=True
    )
    voice_over: Mapped["VoiceOver | None"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False, passive_deletes=True
    )
    render_jobs: Mapped[list["RenderJob"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="RenderJob.created_at.desc()",
        passive_deletes=True,
    )


class Media(IdMixin, TimestampMixin, Base):
    __tablename__ = "media"
    __table_args__ = (Index("ix_media_project_position", "project_id", "position"),)

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), default=MediaKind.IMAGE.value, nullable=False)
    #: 'upload' | 'render' | 'voiceover' | 'ai_motion' | 'sample'
    source: Mapped[str] = mapped_column(String(24), default="upload", nullable=False)

    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    thumbnail_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Image analysis results (brightness, focus, dominant colours, ...).
    analysis: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="media")
    project: Mapped[Project | None] = relationship(back_populates="media", foreign_keys=[project_id])


class Scene(IdMixin, TimestampMixin, Base):
    __tablename__ = "scenes"
    __table_args__ = (
        UniqueConstraint("project_id", "order_index", name="uq_scene_order"),
        CheckConstraint("duration > 0", name="duration_positive"),
    )

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    media_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )

    duration: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    animation: Mapped[str] = mapped_column(String(32), default=AnimationType.KEN_BURNS.value, nullable=False)
    animation_intensity: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    focus_x: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    focus_y: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    transition: Mapped[str] = mapped_column(String(32), default=TransitionType.FADE.value, nullable=False)
    transition_duration: Mapped[float] = mapped_column(Float, default=0.4, nullable=False)
    background_color: Mapped[str] = mapped_column(String(9), default="#000000", nullable=False)
    note: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    #: Prompt handed to the image provider for this scene.
    image_prompt: Mapped[str] = mapped_column(String(1200), default="", nullable=False)

    #: List of TextOverlay dicts, validated against the domain model on write.
    texts: Mapped[list[Any]] = mapped_column(default=list, nullable=False)
    #: AiMotionSpec dict when AI Motion is used for this scene.
    ai_motion: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    project: Mapped[Project] = relationship(back_populates="scenes")
    media: Mapped[Media | None] = relationship(foreign_keys=[media_id], lazy="joined")


class AudioTrack(IdMixin, TimestampMixin, Base):
    __tablename__ = "audio_tracks"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    media_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    volume: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    fade_in: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    fade_out: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    start_offset: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    loop: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Key into the (future) royalty-free library; null when the user uploaded a file.
    library_track_key: Mapped[str | None] = mapped_column(String(64), nullable=True)

    project: Mapped[Project] = relationship(back_populates="audio_track")
    media: Mapped[Media | None] = relationship(foreign_keys=[media_id], lazy="joined")


class VoiceOver(IdMixin, TimestampMixin, Base):
    __tablename__ = "voice_overs"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    media_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    script: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=VoiceOverStatus.DRAFT.value, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    voice_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    volume: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    duck_music_to: Mapped[float] = mapped_column(Float, default=0.28, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: Per-word timings from the TTS provider, as [{"text","start","duration"}].
    #: Stored at synthesis because they cannot be recovered afterwards: getting them
    #: back would mean paying to synthesise the same narration again. Empty when the
    #: provider does not report them — which is a fact to surface, not to fake.
    #: `server_default` as well as the ORM default: a NOT NULL column with no
    #: database-level default breaks every INSERT that omits it, including those
    #: from a process still running the previous mapping during a deploy.
    word_timings: Mapped[list[Any]] = mapped_column(
        default=list, server_default=text("'[]'"), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="voice_over")
    media: Mapped[Media | None] = relationship(foreign_keys=[media_id], lazy="joined")


class Character(IdMixin, TimestampMixin, Base):
    """A reusable subject, kept so it looks the same in every video.

    An image model draws a different person on every call. Consistency comes from
    two things, and both are stored here: a **frozen description** replayed word
    for word into each prompt, and a **reference image** handed to providers that
    accept one. Rebuilding the description per generation would drift, which is
    exactly the failure this table exists to prevent.
    """

    __tablename__ = "characters"
    __table_args__ = (Index("ix_characters_user_updated", "user_id", "updated_at"),)

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default=CharacterKind.ADULT.value, nullable=False)

    age: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    gender: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    skin_tone: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    hair: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    clothes: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    headwear: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    expression: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    personality: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    environment: Mapped[str] = mapped_column(String(300), default="", nullable=False)

    #: The frozen sentence replayed into every prompt. Composed from the fields
    #: above when the user does not write one.
    description: Mapped[str] = mapped_column(String(1200), default="", nullable=False)
    #: `use_alter` because the three tables form a genuine cycle:
    #: characters -> media -> projects -> characters. Without it the metadata has
    #: no valid CREATE/DROP order and `create_all` fails on a fresh database.
    reference_media_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("media.id", ondelete="SET NULL", use_alter=True, name="fk_characters_reference_media"),
        nullable=True,
    )

    user: Mapped[User] = relationship(back_populates="characters")
    reference_media: Mapped["Media | None"] = relationship(
        foreign_keys=[reference_media_id], lazy="joined"
    )


class GenerationJob(IdMixin, TimestampMixin, Base):
    """One unit of queued work, whatever kind it is.

    Before this table, progress lived in three shapes: `render_jobs` for renders,
    a JSON blob on the scene for AI Motion and lip sync, a column on `voice_overs`
    for narration. Nothing could answer "what is this project doing right now",
    which is the one question the dashboard has to answer.

    It records rather than drives: the workers remain the source of truth for
    their own outputs, and write here so the work is visible.
    """

    __tablename__ = "generation_jobs"
    __table_args__ = (
        Index("ix_generation_jobs_project_created", "project_id", "created_at"),
        Index("ix_generation_jobs_status", "status"),
    )

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Null for project-wide work such as the voice-over or the final render.
    scene_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    type: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=RenderStatus.QUEUED.value, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage: Mapped[str] = mapped_column(String(80), default="Queued", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: The provider's own job id, so a support question can be traced.
    external_job_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    #: What the job produced, when it produced a file.
    result_media_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class RenderJob(IdMixin, TimestampMixin, Base):
    __tablename__ = "render_jobs"
    __table_args__ = (Index("ix_render_jobs_status_created", "status", "created_at"),)

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default=RenderStatus.QUEUED.value, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage: Mapped[str] = mapped_column(String(80), default="Queued", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    #: Immutable snapshot of the VideoPlan the job is rendering.
    plan: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    output_media_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    project: Mapped[Project] = relationship(back_populates="render_jobs")
    output_media: Mapped[Media | None] = relationship(foreign_keys=[output_media_id], lazy="joined")


class Template(IdMixin, TimestampMixin, Base):
    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("key", "user_id", name="uq_template_key_user"),)

    key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="General", nullable=False)
    style: Mapped[str] = mapped_column(String(32), default=VideoStyle.PRODUCT_SHOWCASE.value, nullable=False)
    format: Mapped[str] = mapped_column(String(16), default=VideoFormat.PORTRAIT_9_16.value, nullable=False)
    recommended_duration: Mapped[float] = mapped_column(Float, default=15.0, nullable=False)
    min_images: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_images: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Null for the built-in templates, set for user-saved ones.
    user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    #: Serialised slot blueprint.
    definition: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
