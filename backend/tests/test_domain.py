"""Pure-domain tests: animation math, plan validation, planner, templates."""
from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.domain.animation import MAX_ZOOM, build_motion
from app.domain.enums import AnimationType, TransitionType, VideoFormat, VideoStyle
from app.domain.insight import ImageInsight
from app.domain.plan import MAX_TOTAL_SECONDS, validate_plan
from app.domain.planner import PlanRequest, build_plan, fit_to_duration
from app.domain.styles import STYLE_PRESETS
from app.domain.templates import BUILTIN_TEMPLATES, get_template


def insights(count: int = 4) -> list[ImageInsight]:
    return [
        ImageInsight(
            media_id=f"m{i}",
            width=1200,
            height=1600,
            brightness=0.3 + 0.1 * i,
            contrast=0.2,
            focus_x=0.45,
            focus_y=0.4,
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------- animation --


@pytest.mark.parametrize("animation", list(AnimationType))
def test_every_animation_stays_inside_the_image(animation: AnimationType):
    """The visible window must never sample outside the source, at any intensity."""
    for intensity in (0.3, 1.0, 2.0):
        motion = build_motion(animation, intensity=intensity, focus=(0.05, 0.95))
        for progress in (0.0, 0.25, 0.5, 0.75, 1.0):
            viewport = motion.at(progress)
            assert 1.0 <= viewport.zoom <= MAX_ZOOM
            half = 0.5 / viewport.zoom
            assert half - 1e-6 <= viewport.cx <= 1.0 - half + 1e-6
            assert half - 1e-6 <= viewport.cy <= 1.0 - half + 1e-6


def test_zoom_in_and_out_are_mirror_images():
    zoom_in = build_motion(AnimationType.ZOOM_IN, intensity=1.0)
    zoom_out = build_motion(AnimationType.ZOOM_OUT, intensity=1.0)
    assert zoom_in.end.zoom > zoom_in.start.zoom
    assert zoom_out.end.zoom < zoom_out.start.zoom


def test_rotate_slight_requests_rotation():
    assert build_motion(AnimationType.ROTATE_SLIGHT).needs_rotation
    assert not build_motion(AnimationType.KEN_BURNS).needs_rotation


# --------------------------------------------------------------------- plan --


def test_plan_timeline_accounts_for_transition_overlap():
    plan = validate_plan(
        {
            "scenes": [
                {"order": 0, "media_id": "a", "duration": 3.0},
                {"order": 1, "media_id": "b", "duration": 2.0,
                 "transition": "fade", "transition_duration": 0.5},
                {"order": 2, "media_id": "c", "duration": 2.0,
                 "transition": "none", "transition_duration": 0.0},
            ]
        }
    )
    assert plan.total_duration == pytest.approx(3.0 + 2.0 + 2.0 - 0.5)
    assert plan.scene_start_times() == [0.0, 2.5, 4.5]


def test_first_scene_never_has_a_transition():
    plan = validate_plan(
        {"scenes": [{"order": 0, "duration": 2.0, "transition": "zoom", "transition_duration": 0.8}]}
    )
    assert plan.scenes[0].transition is TransitionType.NONE
    assert plan.scenes[0].transition_duration == 0.0


def test_transition_is_clamped_to_the_shorter_neighbour():
    plan = validate_plan(
        {
            "scenes": [
                {"order": 0, "duration": 1.0},
                {"order": 1, "duration": 3.0, "transition": "fade", "transition_duration": 2.5},
            ]
        }
    )
    assert plan.effective_transition_duration(1) == pytest.approx(0.9)


def test_text_is_clamped_to_its_scene():
    plan = validate_plan(
        {
            "scenes": [
                {
                    "order": 0,
                    "duration": 2.0,
                    "texts": [{"content": "Hello", "start": 0.5, "duration": 10.0}],
                }
            ]
        }
    )
    text = plan.scenes[0].texts[0]
    assert text.start + text.duration <= 2.0 + 1e-6


@pytest.mark.parametrize(
    "payload",
    [
        {"scenes": []},
        {"scenes": [{"order": 0, "duration": 3, "texts": [{"content": "x", "color": "red"}]}]},
        {"scenes": [{"order": 0, "duration": 3, "unexpected_field": 1}]},
        {"scenes": [{"order": 0, "duration": 0.01}]},
        {"scenes": [{"order": 0, "duration": 3, "animation": "teleport"}]},
        {"scenes": [{"order": 0, "duration": 3}], "format": "3:4"},
    ],
)
def test_invalid_plans_are_rejected(payload):
    with pytest.raises(PydanticValidationError):
        validate_plan(payload)


def test_plan_longer_than_the_maximum_is_rejected():
    scenes = [{"order": i, "duration": 30.0, "transition": "none"} for i in range(8)]
    with pytest.raises(PydanticValidationError):
        validate_plan({"scenes": scenes})
    assert sum(s["duration"] for s in scenes) > MAX_TOTAL_SECONDS


def test_plan_normalisation_resequences_orders_and_fills_ids():
    plan = validate_plan(
        {"scenes": [{"order": 7, "duration": 2.0}, {"order": 3, "duration": 2.0}]}
    )
    assert [scene.order for scene in plan.scenes] == [0, 1]
    assert all(scene.id for scene in plan.scenes)


# ------------------------------------------------------------------ planner --


@pytest.mark.parametrize("style", list(VideoStyle))
def test_planner_produces_a_valid_plan_for_every_style(style: VideoStyle):
    plan = build_plan(PlanRequest(images=insights(), style=style, topic="test subject"))
    assert plan.scenes
    assert plan.total_duration > 0
    assert plan.cta
    validate_plan(plan.model_dump(mode="json"))


def test_planner_is_deterministic():
    request = lambda: PlanRequest(images=insights(), style=VideoStyle.LUXURY, topic="watch")  # noqa: E731
    assert build_plan(request()).model_dump(mode="json") == build_plan(request()).model_dump(mode="json")


def test_planner_requires_images():
    with pytest.raises(ValueError):
        build_plan(PlanRequest(images=[], style=VideoStyle.MINIMAL))


@pytest.mark.parametrize("target", [6.0, 15.0, 30.0, 60.0])
def test_fit_to_duration_hits_the_target(target: float):
    plan = build_plan(PlanRequest(images=insights(5), style=VideoStyle.FOOD, topic="pizza"))
    fitted = fit_to_duration(plan, target)
    assert fitted.total_duration == pytest.approx(target, rel=0.02)


def test_planner_respects_format():
    plan = build_plan(
        PlanRequest(images=insights(2), style=VideoStyle.MINIMAL, format=VideoFormat.SQUARE_1_1)
    )
    assert plan.dimensions == (1080, 1080)


def test_bright_backgrounds_get_a_text_scrim():
    bright = [
        ImageInsight(
            media_id="bright",
            width=1080,
            height=1920,
            brightness=0.9,
            region_brightness={p: 0.9 for p in ("top", "upper_third", "center", "lower_third", "bottom")},
            contrast=0.4,
        )
    ]
    plan = build_plan(PlanRequest(images=bright, style=VideoStyle.PRODUCT_SHOWCASE, topic="x"))
    scrims = [text.background.value for scene in plan.scenes for text in scene.texts]
    assert any(value != "none" for value in scrims)


# ---------------------------------------------------------------- templates --


@pytest.mark.parametrize("template", BUILTIN_TEMPLATES, ids=lambda t: t.key)
def test_every_template_expands_and_plans(template):
    for count in (1, 2, 5, 9):
        slots = template.expand(count)
        assert sum(1 for slot in slots if slot.needs_image) <= count
        plan = build_plan(
            PlanRequest(
                images=insights(count),
                style=template.style,
                template=template,
                topic="sample topic",
                target_duration=template.recommended_duration,
            )
        )
        assert plan.scenes
        assert plan.total_duration == pytest.approx(template.recommended_duration, rel=0.05)


def test_unknown_template_key_returns_none():
    assert get_template("does-not-exist") is None


def test_every_style_has_a_preset():
    assert set(STYLE_PRESETS) == set(VideoStyle)
