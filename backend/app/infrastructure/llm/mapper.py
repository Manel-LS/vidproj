"""Merge an `LLMPlanDraft` into a real `VideoPlan`.

The model contributes creative choices; everything structural — typography, colours,
media ids, timing clamps — comes from the style preset and the project. Any scene the
model got wrong (an out-of-range image index, an empty scene list) is repaired here
rather than failing the request.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.domain.enums import GenerationMode, TextRole, TransitionType
from app.domain.plan import AudioPlan, PlanScene, VideoPlan, VoiceOverPlan
from app.domain.planner import PlanRequest, build_plan, build_text_overlay, fit_to_duration
from app.infrastructure.llm.base import LLMPlanDraft

logger = get_logger(__name__)

_ROLE_TO_TEXT_ROLE = {
    "hook": TextRole.TITLE,
    "content": TextRole.SUBTITLE,
    "cta": TextRole.CTA,
}


def draft_to_plan(draft: LLMPlanDraft, request: PlanRequest, *, generated_by: str) -> VideoPlan:
    preset = request.preset
    images = request.images
    if not images:
        raise ValueError("Please upload at least one image before generating a plan.")

    cta_text = draft.cta.strip() or request.cta or preset.default_cta
    scenes: list[PlanScene] = []
    last_index = 0

    for order, scene_draft in enumerate(draft.scenes):
        index = scene_draft.image_index
        if index < 0 or index >= len(images):
            # -1 means "a card with no image of its own"; anything else is a mistake we
            # silently repair by reusing the previous image.
            insight = images[min(last_index, len(images) - 1)]
            media_id = None if index < 0 else insight.media_id
        else:
            insight = images[index]
            media_id = insight.media_id
            last_index = index

        transition = (
            TransitionType.NONE if order == 0 else LLMPlanDraft.to_transition(scene_draft.transition)
        )
        text_role = _ROLE_TO_TEXT_ROLE.get(scene_draft.role, TextRole.SUBTITLE)
        content = scene_draft.text.strip()
        if scene_draft.role == "cta" and not content:
            content = cta_text

        texts = []
        if content:
            texts.append(
                build_text_overlay(
                    content=content,
                    role=text_role,
                    preset=preset,
                    insight=insight,
                    position=LLMPlanDraft.to_text_position(scene_draft.text_position),
                    animation=LLMPlanDraft.to_text_animation(scene_draft.text_animation),
                )
            )

        scenes.append(
            PlanScene(
                order=order,
                media_id=media_id,
                duration=round(float(scene_draft.duration_seconds), 2),
                animation=LLMPlanDraft.to_animation(scene_draft.animation),
                animation_intensity=preset.motion_intensity,
                focus_x=insight.focus_x,
                focus_y=insight.focus_y,
                transition=transition,
                transition_duration=0.0 if order == 0 else preset.transition_seconds,
                texts=texts,
                note=scene_draft.reason[:400],
            )
        )

    if not scenes:  # the schema forbids this, but never trust a remote system
        logger.warning("LLM returned no scenes; using the deterministic planner instead.")
        return build_plan(request)

    plan = VideoPlan(
        format=request.format,
        fps=request.fps,
        style=request.style,
        mode=request.mode or GenerationMode.STANDARD,
        scenes=scenes,
        audio=AudioPlan(media_id=request.audio_media_id, volume=preset.music_volume),
        voiceover=VoiceOverPlan(
            enabled=request.include_voiceover,
            script=draft.voiceover_script.strip() if request.include_voiceover else "",
        ),
        hook=draft.hook.strip()[:280],
        cta=cta_text[:280],
        caption=draft.caption.strip()[:2200],
        hashtags=list(draft.hashtags),
        generated_by=generated_by,
        notes=preset.prompt_hint,
    )

    if request.target_duration:
        plan = fit_to_duration(plan, request.target_duration)
    return plan.normalised()
