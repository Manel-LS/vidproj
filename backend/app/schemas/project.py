from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import (
    Language,
    AnimationType,
    GenerationMode,
    Platform,
    RenderStatus,
    TransitionType,
    VideoFormat,
    VideoStyle,
    VoiceOverStatus,
)
from app.domain.plan import IMAGE_PROMPT_MAX_LENGTH, TextOverlay, VideoPlan
from app.domain.subtitles import SubtitleStyle
from app.schemas.common import APIModel
from app.schemas.media import AudioTrackResponse, MediaResponse


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    topic: str = Field(default="", max_length=300)
    platform: Platform = Platform.TIKTOK
    format: VideoFormat | None = None
    style: VideoStyle = VideoStyle.PRODUCT_SHOWCASE
    language: Language = Language.ENGLISH
    template_key: str | None = None
    character_id: str | None = None
    target_duration: float | None = Field(default=None, ge=2.0, le=180.0)
    mode: GenerationMode = GenerationMode.STANDARD
    subtitle_style: SubtitleStyle = SubtitleStyle.NONE


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    topic: str | None = Field(default=None, max_length=300)
    platform: Platform | None = None
    format: VideoFormat | None = None
    style: VideoStyle | None = None
    language: Language | None = None
    mode: GenerationMode | None = None
    fps: int | None = Field(default=None, ge=15, le=60)
    template_key: str | None = None
    character_id: str | None = None
    target_duration: float | None = Field(default=None, ge=2.0, le=180.0)
    hook: str | None = Field(default=None, max_length=300)
    cta: str | None = Field(default=None, max_length=300)
    caption: str | None = Field(default=None, max_length=2200)
    hashtags: list[str] | None = Field(default=None, max_length=30)
    subtitle_style: SubtitleStyle | None = None


class SceneResponse(APIModel):
    id: str
    order: int = Field(validation_alias="order_index")
    media_id: str | None
    duration: float
    animation: AnimationType
    animation_intensity: float
    focus_x: float
    focus_y: float
    transition: TransitionType
    transition_duration: float
    texts: list[TextOverlay]
    background_color: str
    note: str
    #: What the image provider was asked for. Returned so the editor can show what
    #: produced this shot and pre-fill a regeneration with the same prompt — the
    #: column existed and was written, but never left the server.
    image_prompt: str = ""
    ai_motion: dict | None = None
    #: Absolute start time on the final timeline; filled in by the router.
    start_time: float = 0.0
    media: MediaResponse | None = None


class SceneCreate(BaseModel):
    media_id: str | None = None
    position: int | None = Field(default=None, ge=0, le=40)
    duration: float | None = Field(default=None, ge=0.4, le=30.0)


class SceneUpdate(BaseModel):
    media_id: str | None = None
    duration: float | None = Field(default=None, ge=0.4, le=30.0)
    animation: AnimationType | None = None
    animation_intensity: float | None = Field(default=None, ge=0.3, le=2.0)
    focus_x: float | None = Field(default=None, ge=0.0, le=1.0)
    focus_y: float | None = Field(default=None, ge=0.0, le=1.0)
    transition: TransitionType | None = None
    transition_duration: float | None = Field(default=None, ge=0.0, le=3.0)
    texts: list[TextOverlay] | None = Field(default=None, max_length=4)
    background_color: str | None = None
    note: str | None = Field(default=None, max_length=400)
    image_prompt: str | None = Field(default=None, max_length=IMAGE_PROMPT_MAX_LENGTH)


class ReorderScenesRequest(BaseModel):
    scene_ids: list[str] = Field(min_length=1, max_length=40)


class WordTimingResponse(APIModel):
    text: str
    start: float
    duration: float


class VoiceOverResponse(APIModel):
    id: str
    enabled: bool
    script: str
    status: VoiceOverStatus
    provider: str | None
    voice_id: str | None
    volume: float
    duck_music_to: float
    error: str
    media: MediaResponse | None = None
    #: Per-word timings from the provider, in seconds from the start of the audio.
    #: The browser preview uses them to draw the same highlight the renderer burns
    #: in, so preview and export agree.
    word_timings: list[WordTimingResponse] = Field(default_factory=list)
    #: Word-level subtitles are only possible when the provider reported timings.
    #: Published rather than inferred from the list being empty, so the UI can say
    #: *why* the option is unavailable.
    has_word_timings: bool = False


class VoiceOverUpdate(BaseModel):
    enabled: bool | None = None
    script: str | None = Field(default=None, max_length=4000)
    voice_id: str | None = Field(default=None, max_length=120)
    volume: float | None = Field(default=None, ge=0.0, le=1.5)
    duck_music_to: float | None = Field(default=None, ge=0.0, le=1.0)


class RenderJobResponse(APIModel):
    id: str
    project_id: str
    status: RenderStatus
    progress: int
    stage: str
    error: str
    message: str = ""
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_media: MediaResponse | None = None
    download_url: str | None = None


class ProjectSummary(APIModel):
    id: str
    name: str
    description: str
    platform: Platform
    format: VideoFormat
    style: VideoStyle
    mode: GenerationMode
    duration_seconds: float
    created_at: datetime
    updated_at: datetime
    scene_count: int = 0
    image_count: int = 0
    thumbnail_url: str | None = None
    render_status: RenderStatus | None = None
    render_progress: int = 0
    download_url: str | None = None


class ProjectDetail(ProjectSummary):
    topic: str
    fps: int
    template_key: str | None
    #: Burned-in subtitles; "none" means the video carries none.
    subtitle_style: SubtitleStyle = SubtitleStyle.NONE
    #: Drives the planner's language, the default voice and subtitle direction.
    language: Language = Language.ENGLISH
    rtl: bool = False
    character_id: str | None = None
    #: The frozen character description, so the editor can show what every image
    #: prompt is being prefixed with.
    character_description: str = ""
    target_duration: float | None
    hook: str
    cta: str
    caption: str
    hashtags: list[str]
    plan_generated_by: str
    plan_notes: str
    scenes: list[SceneResponse]
    media: list[MediaResponse]
    audio: AudioTrackResponse | None = None
    voice_over: VoiceOverResponse | None = None
    total_duration: float = 0.0


class PlanGenerateRequest(BaseModel):
    """The 'Create with AI' request (requirement 26)."""

    instruction: str = Field(default="", max_length=1000)
    style: VideoStyle | None = None
    template_key: str | None = None
    target_duration: float | None = Field(default=None, ge=2.0, le=180.0)
    include_voiceover: bool = False
    use_ai: bool = True
    #: When false the plan is returned for preview without touching the project.
    apply: bool = True


class PlanResponse(BaseModel):
    plan: VideoPlan
    generated_by: str
    ai_used: bool
    notice: str = ""
    applied: bool = False
    total_duration: float = 0.0
    scene_start_times: list[float] = Field(default_factory=list)


class PlanApplyRequest(BaseModel):
    """Submit a hand-edited plan (requirement 19: validated before use)."""

    plan: dict
