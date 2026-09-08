"""Template listing and application (requirement 18)."""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.domain.enums import Language, VideoStyle
from app.domain.planner import PlanRequest, build_plan
from app.domain.styles import get_style_preset
from app.domain.templates import BUILTIN_TEMPLATES, VideoTemplate, get_template
from app.models import Project
from app.services import media_service
from app.services.plan_assembler import apply_plan_to_project, media_insights


def template_payload(template: VideoTemplate) -> dict:
    preset = template.preset
    return {
        "key": template.key,
        "name": template.name,
        "description": template.description,
        "category": template.category,
        "style": template.style.value,
        "format": template.format.value,
        "recommended_duration": template.recommended_duration,
        "min_images": template.min_images,
        "max_images": template.max_images,
        "gradient": list(template.gradient),
        "default_cta": template.default_cta or preset.default_cta,
        "scene_count_hint": len(template.slots),
        "typography": {
            "family": preset.typography.family.value,
            "color": preset.typography.color,
            "accent_color": preset.typography.accent_color,
            "uppercase": preset.typography.uppercase,
        },
        "slots": [
            {
                "kind": slot.kind,
                "duration": slot.duration,
                "animation": slot.animation.value if slot.animation else None,
                "transition": slot.transition.value if slot.transition else None,
                "text_role": slot.text_role.value if slot.text_role else None,
                "text_template": slot.text_template,
                "repeat": slot.repeat,
                "needs_image": slot.needs_image,
            }
            for slot in template.slots
        ],
    }


def list_templates(category: str = "") -> list[dict]:
    templates = BUILTIN_TEMPLATES
    if category:
        templates = tuple(t for t in templates if t.category.lower() == category.lower())
    return [template_payload(t) for t in templates]


def list_categories() -> list[str]:
    return sorted({template.category for template in BUILTIN_TEMPLATES})


def apply_template(
    session: Session,
    project: Project,
    template_key: str,
    *,
    target_duration: float | None = None,
) -> Project:
    template = get_template(template_key)
    if template is None:
        raise NotFoundError(f"There is no template called '{template_key}'.")

    images = media_service.project_images(project)
    if not images:
        raise ValidationError("Please upload at least one image before applying a template.")
    if len(images) < template.min_images:
        raise ValidationError(
            f"The {template.name} template needs at least {template.min_images} images; "
            f"this project has {len(images)}."
        )

    audio = project.audio_track
    plan = build_plan(
        PlanRequest(
            images=media_insights(images),
            style=template.style,
            format=template.format,
            fps=project.fps,
            topic=project.topic or project.name,
            description=project.description,
            cta=project.cta or template.default_cta,
            target_duration=target_duration or project.target_duration or template.recommended_duration,
            template=template,
            include_voiceover=bool(project.voice_over and project.voice_over.enabled),
            language=Language(project.language),
            audio_media_id=audio.media_id if audio else None,
            generated_by=f"template:{template.key}",
        )
    )

    project.template_key = template.key
    project.style = template.style.value
    project.format = template.format.value
    if not project.cta:
        project.cta = template.default_cta or get_style_preset(template.style).default_cta
    return apply_plan_to_project(session, project, plan)
