"""AI planning, voice-over, image generation, AI Motion and lip-sync endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep, rate_limit, upload_rate_limit
from app.api.serializers import serialize_project_detail, serialize_voice_over
from app.core.config import settings
from app.core.errors import ProviderUnavailableError, ValidationError
from app.domain import social
from app.domain.enums import (
    GenerationMode,
    Language,
    Platform,
    VideoStyle,
    VoiceOverStatus,
)
from app.domain.language import match_voice
from app.domain.planner import build_voiceover_script
from app.domain.plan import IMAGE_PROMPT_MAX_LENGTH
from app.infrastructure.i2v.factory import get_i2v_provider, i2v_status
from app.infrastructure.image.factory import get_image_provider, image_status
from app.infrastructure.lipsync.factory import get_lipsync_provider, lipsync_status
from app.infrastructure.jobs.factory import get_job_queue
from app.infrastructure.tts.factory import get_voice_provider, voice_status
from app.schemas.common import APIModel
from app.schemas.project import (
    PlanApplyRequest,
    PlanGenerateRequest,
    PlanResponse,
    ProjectDetail,
    VoiceOverResponse,
    VoiceOverUpdate,
)
from app.services import media_service, plan_service, project_service, scene_service
from app.services.plan_assembler import project_to_plan

router = APIRouter(prefix="/projects/{project_id}", tags=["ai"], dependencies=[Depends(rate_limit)])


@router.post("/plan/generate", response_model=PlanResponse, summary="Create the video plan with AI")
def generate_plan(
    project_id: str, payload: PlanGenerateRequest, session: SessionDep, user: CurrentUser
) -> PlanResponse:
    """Build a scene-by-scene plan (requirement 26).

    Falls back to the deterministic planner whenever the AI provider is missing or
    fails; `ai_used` and `notice` say which path ran.
    """
    project = project_service.get_owned_project(session, project_id, user)
    outcome = plan_service.generate_plan(
        project,
        instruction=payload.instruction,
        style=payload.style,
        target_duration=payload.target_duration,
        include_voiceover=payload.include_voiceover,
        template_key=payload.template_key,
        use_ai=payload.use_ai,
    )

    applied = False
    if payload.apply:
        plan_service.apply_plan(session, project, outcome.plan)
        if payload.include_voiceover and project.voice_over is not None:
            project.voice_over.enabled = True
            if outcome.plan.voiceover and outcome.plan.voiceover.script:
                project.voice_over.script = outcome.plan.voiceover.script
        session.commit()
        applied = True

    return PlanResponse(
        plan=outcome.plan,
        generated_by=outcome.generated_by,
        ai_used=outcome.ai_used,
        notice=outcome.notice,
        applied=applied,
        total_duration=outcome.plan.total_duration,
        scene_start_times=outcome.plan.scene_start_times(),
    )


@router.get("/plan", response_model=PlanResponse, summary="The project's current plan")
def get_plan(project_id: str, session: SessionDep, user: CurrentUser) -> PlanResponse:
    project = project_service.get_owned_project(session, project_id, user)
    plan = project_to_plan(project)
    return PlanResponse(
        plan=plan,
        generated_by=plan.generated_by,
        ai_used=plan.generated_by not in ("manual", "heuristic"),
        applied=True,
        total_duration=plan.total_duration,
        scene_start_times=plan.scene_start_times(),
    )


@router.put("/plan", response_model=ProjectDetail, summary="Replace the plan with an edited one")
def apply_plan(
    project_id: str, payload: PlanApplyRequest, session: SessionDep, user: CurrentUser
) -> ProjectDetail:
    """Validate a client-supplied plan and write it onto the project (requirement 19)."""
    project = project_service.get_owned_project(session, project_id, user)
    plan = plan_service.validate_incoming_plan(payload.plan)
    plan_service.apply_plan(session, project, plan)
    session.commit()
    session.refresh(project)
    return serialize_project_detail(project)


# ------------------------------------------------------------- voice-over ----


@router.get("/voiceover", response_model=VoiceOverResponse, summary="Voice-over state")
def get_voiceover(project_id: str, session: SessionDep, user: CurrentUser) -> VoiceOverResponse:
    project = project_service.get_owned_project(session, project_id, user)
    if project.voice_over is None:
        raise ValidationError("This project has no voice-over slot.")
    return serialize_voice_over(project.voice_over)


@router.patch("/voiceover", response_model=VoiceOverResponse, summary="Edit the voice-over script")
def update_voiceover(
    project_id: str, payload: VoiceOverUpdate, session: SessionDep, user: CurrentUser
) -> VoiceOverResponse:
    project = project_service.get_owned_project(session, project_id, user)
    voice = project.voice_over
    if voice is None:
        raise ValidationError("This project has no voice-over slot.")
    changes = payload.model_dump(exclude_unset=True)
    script_changed = (
        changes.get("script") is not None and changes["script"].strip() != (voice.script or "").strip()
    )
    for field, value in changes.items():
        if value is not None:
            setattr(voice, field, value)

    if script_changed and voice.status == VoiceOverStatus.READY.value:
        # The audio on file now says something else. Keep it — the user may still
        # want to render with it — but stop calling it ready, and drop the word
        # timings, which would otherwise subtitle the new script with the old
        # words' clocks.
        voice.status = VoiceOverStatus.DRAFT.value
        voice.word_timings = []

    # No voice chosen: pick one that actually speaks the project's language rather
    # than letting the provider fall back to its own default, which is English.
    if not voice.voice_id:
        provider = get_voice_provider()
        if provider.is_available():
            matched, _exact = match_voice(provider.list_voices(), project.language)
            if matched is not None:
                voice.voice_id = matched.id

    session.commit()
    return serialize_voice_over(voice)


@router.post("/voiceover/script", response_model=VoiceOverResponse, summary="Draft a narration script")
def draft_voiceover_script(
    project_id: str, session: SessionDep, user: CurrentUser
) -> VoiceOverResponse:
    """Assemble a script from the plan's on-screen copy, for the user to edit."""
    project = project_service.get_owned_project(session, project_id, user)
    voice = project.voice_over
    if voice is None:
        raise ValidationError("This project has no voice-over slot.")

    plan = project_to_plan(project)
    lines = [text.content for scene in plan.scenes for text in scene.texts]
    voice.script = build_voiceover_script(lines, plan.hook, plan.cta)
    voice.status = VoiceOverStatus.DRAFT.value
    session.commit()
    return serialize_voice_over(voice)


@router.post(
    "/voiceover/generate",
    response_model=VoiceOverResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Synthesise the voice-over",
)
def generate_voiceover(project_id: str, session: SessionDep, user: CurrentUser) -> VoiceOverResponse:
    project = project_service.get_owned_project(session, project_id, user)
    voice = project.voice_over
    if voice is None:
        raise ValidationError("This project has no voice-over slot.")

    provider = get_voice_provider()
    if not provider.is_available():
        raise ProviderUnavailableError(str(voice_status()["message"]))
    if not (voice.script or "").strip():
        raise ValidationError("Write a voice-over script first, then generate the audio.")

    voice.status = VoiceOverStatus.GENERATING.value
    voice.error = ""
    session.commit()

    get_job_queue().enqueue_voiceover(project.id, user.id)
    return serialize_voice_over(voice)


# ------------------------------------------------------------ scene image ----


@router.post(
    "/scenes/{scene_id}/image",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate this scene's still image from a prompt",
    dependencies=[Depends(rate_limit)],
)
def generate_scene_image(
    project_id: str,
    scene_id: str,
    session: SessionDep,
    user: CurrentUser,
    prompt: str = "",
) -> dict:
    """Queue an image generation for one scene.

    The prompt is stored on the scene before the job starts, so regenerating
    reproduces the same shot and the editor can show what was asked for even
    while the job is still running.
    """
    project = project_service.get_owned_project(session, project_id, user)
    scene = scene_service.get_scene(session, project, scene_id)

    provider = get_image_provider()
    if not provider.is_available():
        raise ProviderUnavailableError(str(image_status()["message"]))

    prompt = (prompt or scene.image_prompt or "").strip()
    if not prompt:
        raise ValidationError("Describe the image you want before generating it.")
    if len(prompt) > IMAGE_PROMPT_MAX_LENGTH:
        raise ValidationError(
            f"That image prompt is too long (limit {IMAGE_PROMPT_MAX_LENGTH} characters)."
        )

    scene.image_prompt = prompt
    # Clear the previous failure: leaving it would make a running job look broken.
    if scene.ai_motion:
        scene.ai_motion = {**scene.ai_motion, "error": ""}
    session.commit()

    get_job_queue().enqueue_image(project.id, user.id, scene.id)
    return {
        "status": "queued",
        "message": "Generating this scene's image. This usually takes under a minute.",
        "scene_id": scene.id,
        "provider": provider.name,
    }


# -------------------------------------------------------------- AI motion ----


@router.post(
    "/scenes/{scene_id}/motion-clip",
    status_code=status.HTTP_201_CREATED,
    summary="Attach a video clip generated elsewhere to one scene",
    dependencies=[Depends(upload_rate_limit)],
)
def import_motion_clip(
    project_id: str,
    scene_id: str,
    session: SessionDep,
    user: CurrentUser,
    file: UploadFile = File(..., description="MP4, MOV or WebM"),
) -> dict:
    """Play a clip the user brought, where a generated one would have gone.

    AI Motion needs a paid provider, but the renderer's ability to play a clip in a
    scene does not — it only ever needed a video to point at. This accepts one from
    anywhere: a rented GPU, another tool, a camera. The scene then composites text,
    music and voice-over over it exactly as it would over a generated shot, so the
    rest of the pipeline cannot tell the difference and nothing downstream changes.
    """
    project = project_service.get_owned_project(session, project_id, user)
    scene = scene_service.get_scene(session, project, scene_id)

    data = media_service.read_upload(
        file, max_bytes=settings.max_video_bytes, label=f"'{file.filename or 'clip'}'"
    )
    clip = media_service.add_motion_clip(
        session,
        project,
        media_service.UploadPayload(
            filename=file.filename or "motion-clip.mp4",
            content_type=file.content_type or "video/mp4",
            data=data,
        ),
    )

    previous = (scene.ai_motion or {}).get("generated_media_id")
    scene.ai_motion = {
        "enabled": True,
        "prompt": (scene.ai_motion or {}).get("prompt", ""),
        # Recorded as `import` rather than a provider name: this clip was not generated
        # here, and a later regeneration must not silently claim it was.
        "provider": "import",
        "generated_media_id": clip.id,
        "job_reference": None,
        "error": "",
    }
    project.mode = GenerationMode.AI_MOTION.value
    session.commit()

    # Only once the scene points at the new clip, so a failure above leaves the old one.
    if previous and previous != clip.id:
        old = session.get(type(clip), previous)
        if old is not None:
            media_service.delete_media(session, old)
            session.commit()

    return {
        "scene_id": scene.id,
        "media_id": clip.id,
        "duration_seconds": clip.duration_seconds,
        "width": clip.width,
        "height": clip.height,
        "message": "Clip attached. Render the project to see it in the timeline.",
    }


@router.post(
    "/scenes/{scene_id}/ai-motion",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate an AI Motion clip for one scene",
)
def generate_ai_motion(
    project_id: str,
    scene_id: str,
    session: SessionDep,
    user: CurrentUser,
    prompt: str = "",
) -> dict:
    project = project_service.get_owned_project(session, project_id, user)
    scene = scene_service.get_scene(session, project, scene_id)

    provider = get_i2v_provider()
    if not provider.is_available():
        raise ProviderUnavailableError(str(i2v_status()["message"]))
    if not scene.media_id:
        raise ValidationError("Add an image to this scene before generating AI Motion.")

    scene.ai_motion = {
        "enabled": True,
        "prompt": (prompt or "")[:800],
        "provider": provider.name,
        "generated_media_id": None,
        "job_reference": None,
    }
    project.mode = GenerationMode.AI_MOTION.value
    session.commit()

    get_job_queue().enqueue_ai_motion(project.id, user.id, scene.id)
    return {
        "status": "queued",
        "message": "Generating motion for this scene. This can take a couple of minutes.",
        "scene_id": scene.id,
    }


# ---------------------------------------------------------------- lip sync ----


@router.post(
    "/scenes/{scene_id}/lipsync",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Lip-sync this scene's clip to its slice of the voice-over",
    dependencies=[Depends(rate_limit)],
)
def generate_lipsync(
    project_id: str,
    scene_id: str,
    session: SessionDep,
    user: CurrentUser,
) -> dict:
    """Queue a lip-sync pass for one scene.

    Everything the provider needs already exists on the project — the motion clip
    on the scene, the narration on the project — so this endpoint takes no body.
    The scene's window into the narration is computed by the worker.
    """
    project = project_service.get_owned_project(session, project_id, user)
    scene = scene_service.get_scene(session, project, scene_id)

    provider = get_lipsync_provider()
    if not provider.is_available():
        raise ProviderUnavailableError(str(lipsync_status()["message"]))

    spec = scene.ai_motion or {}
    if not (spec.get("silent_media_id") or spec.get("generated_media_id")):
        raise ValidationError("Generate this scene's motion clip before lip-syncing it.")
    if project.voice_over is None or not project.voice_over.media_id:
        raise ValidationError("Generate the voice-over before lip-syncing this scene.")

    scene.ai_motion = {**spec, "error": ""}
    session.commit()

    get_job_queue().enqueue_lipsync(project.id, user.id, scene.id)
    return {
        "status": "queued",
        "message": "Syncing this scene's lips to the narration. This can take a few minutes.",
        "scene_id": scene.id,
        "provider": provider.name,
    }


# ------------------------------------------------------------------ social ----


class SocialRequest(BaseModel):
    """Which network to write for. Defaults to the project's own platform."""

    platform: Platform | None = None
    apply: bool = True


class SocialResponse(APIModel):
    platform: Platform
    caption: str
    hashtags: list[str]
    applied: bool
    generated_by: str


@router.post(
    "/social",
    response_model=SocialResponse,
    summary="Write the caption and hashtags for one network",
)
def generate_social(
    project_id: str, payload: SocialRequest, session: SessionDep, user: CurrentUser
) -> SocialResponse:
    """Compose the post text for a platform.

    Deliberately not behind the AI provider: this is convention, not creativity,
    and a deployment with no API key should still get a caption written for the
    network it is posting to rather than one generic line for all of them.
    """
    project = project_service.get_owned_project(session, project_id, user)
    platform = payload.platform or Platform(project.platform)

    caption, hashtags = social.compose(
        platform=platform,
        language=Language(project.language),
        style=VideoStyle(project.style),
        subject=project.topic or project.name,
        hook=project.hook,
        cta=project.cta,
        description=project.description,
    )

    if payload.apply:
        project.caption = caption
        project.hashtags = hashtags
        session.commit()

    return SocialResponse.model_validate(
        {
            "platform": platform,
            "caption": caption,
            "hashtags": hashtags,
            "applied": payload.apply,
            "generated_by": "built-in",
        }
    )
