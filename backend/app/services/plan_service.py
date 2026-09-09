"""AI video planning (requirements 6, 19, 26).

The flow is always the same, whether or not an LLM is configured:

    project + media  ->  PlanRequest  ->  VideoPlan (validated)  ->  scene rows

When an LLM provider is available it supplies the creative draft and
`llm.mapper.draft_to_plan` merges it with the style preset. When it is not — or when
it errors, or returns something that fails validation — the deterministic planner runs
instead and the response says so, so the UI can tell the user the truth.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.domain.enums import Language, GenerationMode, Platform, VideoFormat, VideoStyle
from app.domain.language import get_profile, scripts_match
from app.domain.plan import VideoPlan, validate_plan
from app.domain.subtitles import SubtitleStyle
from app.domain.planner import PlanRequest, build_plan
from app.domain.templates import get_template
from app.infrastructure.llm.base import LLMUnavailable, PlanBrief
from app.infrastructure.llm.factory import get_llm_provider
from app.infrastructure.llm.mapper import draft_to_plan
from app.models import Project
from app.services import media_service
from app.services.plan_assembler import apply_plan_to_project, media_insights

logger = get_logger(__name__)


@dataclass
class PlanOutcome:
    plan: VideoPlan
    generated_by: str
    ai_used: bool
    #: Non-empty when the AI path was attempted and did not work out.
    notice: str = ""


def _build_request(
    project: Project,
    *,
    style: VideoStyle | None,
    target_duration: float | None,
    include_voiceover: bool,
    template_key: str | None,
) -> PlanRequest:
    images = media_service.project_images(project)
    if not images:
        raise ValidationError("Please upload at least one image.")

    audio = project.audio_track
    return PlanRequest(
        images=media_insights(images),
        style=style or VideoStyle(project.style),
        format=VideoFormat(project.format),
        fps=project.fps,
        topic=project.topic or project.name,
        description=project.description,
        cta=project.cta,
        hook=project.hook,
        target_duration=target_duration or project.target_duration,
        template=get_template(template_key or project.template_key or ""),
        include_voiceover=include_voiceover,
        language=Language(project.language),
        mode=GenerationMode(project.mode),
        platform=Platform(project.platform),
        subtitle_style=SubtitleStyle(project.subtitle_style or "none"),
        audio_media_id=audio.media_id if audio else None,
    )


def generate_plan(
    project: Project,
    *,
    instruction: str = "",
    style: VideoStyle | None = None,
    target_duration: float | None = None,
    include_voiceover: bool = False,
    template_key: str | None = None,
    use_ai: bool = True,
) -> PlanOutcome:
    """Produce a plan for the project. Never raises because the AI is down."""
    request = _build_request(
        project,
        style=style,
        target_duration=target_duration,
        include_voiceover=include_voiceover,
        template_key=template_key,
    )

    provider = get_llm_provider() if use_ai else None
    if provider is None:
        request.generated_by = "heuristic"
        notice = (
            ""
            if not use_ai
            else "AI generation is temporarily unavailable. Your plan was built with the "
            "built-in planner — you can still edit every scene."
        )
        notice = " ".join(part for part in (notice, _script_warning(project, request.subject)) if part)
        return PlanOutcome(build_plan(request), "heuristic", ai_used=False, notice=notice)

    brief = PlanBrief(
        style=request.style,
        images=request.images,
        topic=request.topic,
        description=request.description,
        instruction=instruction,
        target_duration=request.target_duration or 15.0,
        platform=project.platform,
        cta=request.cta,
        include_voiceover=include_voiceover,
        # A directive, not a language name: given just "Tunisian Arabic" the model
        # drafts in English and translates, which reads like a translation.
        language=get_profile(project.language).prompt_instruction,
    )

    try:
        draft = provider.generate_plan(brief)
        plan = draft_to_plan(draft, request, generated_by=provider.name)
        return PlanOutcome(plan, provider.name, ai_used=True)
    except (LLMUnavailable, PydanticValidationError, ValueError) as exc:
        logger.warning("AI planning failed (%s); using the built-in planner.", exc)
        request.generated_by = "heuristic"
        return PlanOutcome(
            build_plan(request),
            "heuristic",
            ai_used=False,
            notice=(
                "AI generation is temporarily unavailable. Your plan was built with the "
                "built-in planner — you can still edit every scene."
            ),
        )


def _script_warning(project: Project, subject: str) -> str:
    """Warn when the subject is not written in the language's own script.

    Not a style opinion. The narration is synthesised from this text, so a Latin
    brand inside an Arabic script is read letter by letter, and because the
    subtitle timings come from that same synthesis the highlighting drifts with
    it. The planner already declines to weave a mismatched subject into the body
    copy; this is what tells the user why their video says less about the product
    than they expected.
    """
    if not subject.strip() or scripts_match(subject, project.language):
        return ""
    label = get_profile(project.language).label
    return (
        f"Your subject is not written in {label}. The on-screen copy leaves it out, "
        f"and a {label} voice will mispronounce it — rewrite the topic in {label} "
        "to have it read and shown properly."
    )


def apply_plan(session: Session, project: Project, plan: VideoPlan) -> Project:
    """Persist a plan onto the project after re-validating every media reference."""
    owned_media = {media.id for media in project.media}
    for scene in plan.scenes:
        if scene.media_id and scene.media_id not in owned_media:
            raise ValidationError(
                "The plan refers to an image that is not part of this project."
            )
    if plan.audio and plan.audio.media_id and plan.audio.media_id not in owned_media:
        raise ValidationError("The plan refers to an audio track that is not in this project.")
    if plan.voiceover and plan.voiceover.media_id and plan.voiceover.media_id not in owned_media:
        raise ValidationError("The plan refers to a voice-over that is not in this project.")

    return apply_plan_to_project(session, project, plan)


def validate_incoming_plan(raw: dict) -> VideoPlan:
    """Validate a plan submitted by a client (requirement 19)."""
    try:
        return validate_plan(raw)
    except PydanticValidationError as exc:
        details = [
            {"field": ".".join(str(part) for part in error["loc"]), "problem": error["msg"]}
            for error in exc.errors()[:10]
        ]
        raise ValidationError(
            "That video plan is not valid. Fix the highlighted fields and try again.",
            details=details,
        ) from exc
