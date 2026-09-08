"""AI plan generation, validation and template application."""
from __future__ import annotations

import pytest

from app.domain.enums import VideoStyle
from app.domain.insight import ImageInsight
from app.domain.planner import PlanRequest
from app.infrastructure.llm.base import LLMPlanDraft, LLMProvider, LLMUnavailable, PlanBrief
from app.infrastructure.llm.mapper import draft_to_plan

API = "/api/v1"


def test_generate_plan_falls_back_to_the_builtin_planner(client, auth, project_with_images):
    """No LLM is configured in tests: the response must say so, and still work."""
    response = client.post(
        f"{API}/projects/{project_with_images['id']}/plan/generate",
        json={"instruction": "Make it energetic and modern", "target_duration": 10},
        headers=auth["headers"],
    )
    assert response.status_code == 200
    body = response.json()

    assert body["ai_used"] is False
    assert body["generated_by"] == "heuristic"
    assert "built-in planner" in body["notice"]
    assert body["applied"] is True
    assert body["total_duration"] == pytest.approx(10.0, rel=0.05)
    assert len(body["plan"]["scenes"]) >= 3
    assert body["scene_start_times"][0] == 0.0
    assert all(scene["texts"] for scene in body["plan"]["scenes"][:1])


def test_generated_plan_is_persisted_onto_the_project(client, auth, project_with_images):
    project_id = project_with_images["id"]
    client.post(
        f"{API}/projects/{project_id}/plan/generate",
        json={"target_duration": 12},
        headers=auth["headers"],
    )
    detail = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()
    assert detail["total_duration"] == pytest.approx(12.0, rel=0.05)
    assert detail["plan_generated_by"] == "heuristic"
    assert detail["hook"]
    assert detail["cta"]


def test_plan_preview_does_not_touch_the_project(client, auth, project_with_images):
    project_id = project_with_images["id"]
    before = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()
    response = client.post(
        f"{API}/projects/{project_id}/plan/generate",
        json={"apply": False, "target_duration": 25},
        headers=auth["headers"],
    ).json()
    assert response["applied"] is False

    after = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()
    assert after["total_duration"] == before["total_duration"]


def test_plan_requires_images(client, auth, project):
    response = client.post(
        f"{API}/projects/{project['id']}/plan/generate", json={}, headers=auth["headers"]
    )
    assert response.status_code == 422
    assert "upload at least one image" in response.json()["error"]["message"]


def test_edited_plan_round_trips(client, auth, project_with_images):
    project_id = project_with_images["id"]
    plan = client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).json()["plan"]

    plan["scenes"][0]["duration"] = 5.0
    plan["scenes"][0]["animation"] = "pan_left"
    plan["scenes"][0]["texts"] = [
        {"role": "title", "content": "Edited by hand", "position": "center", "animation": "rise"}
    ]
    plan["cta"] = "Visit the shop"

    response = client.put(f"{API}/projects/{project_id}/plan", json={"plan": plan}, headers=auth["headers"])
    assert response.status_code == 200
    detail = response.json()
    assert detail["scenes"][0]["duration"] == 5.0
    assert detail["scenes"][0]["texts"][0]["content"] == "Edited by hand"
    assert detail["cta"] == "Visit the shop"


def test_invalid_plan_submission_is_rejected_with_field_details(client, auth, project_with_images):
    project_id = project_with_images["id"]
    plan = client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).json()["plan"]
    plan["scenes"][0]["animation"] = "teleport"

    response = client.put(f"{API}/projects/{project_id}/plan", json={"plan": plan}, headers=auth["headers"])
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert any("animation" in detail["field"] for detail in error["details"])


def test_a_plan_cannot_reference_another_projects_media(client, auth, project_with_images):
    other = client.post(f"{API}/projects", json={"name": "Other"}, headers=auth["headers"]).json()
    plan = client.get(
        f"{API}/projects/{project_with_images['id']}/plan", headers=auth["headers"]
    ).json()["plan"]

    response = client.put(f"{API}/projects/{other['id']}/plan", json={"plan": plan}, headers=auth["headers"])
    assert response.status_code == 422
    assert "not part of this project" in response.json()["error"]["message"]


@pytest.mark.parametrize("template_key", ["product_tiktok", "flash_sale", "educational_tips"])
def test_apply_template(client, auth, project_with_images, template_key):
    project_id = project_with_images["id"]
    response = client.post(
        f"{API}/projects/{project_id}/apply-template/{template_key}", headers=auth["headers"]
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["template_key"] == template_key
    assert detail["scenes"]
    assert detail["total_duration"] > 0


def test_apply_unknown_template(client, auth, project_with_images):
    response = client.post(
        f"{API}/projects/{project_with_images['id']}/apply-template/nope", headers=auth["headers"]
    )
    assert response.status_code == 404


# ------------------------------------------------------- the LLM code path --


class _StubLLM(LLMProvider):
    """Exercises the AI branch without a network call."""

    name = "stub"
    display_name = "Stub"

    def __init__(self, draft=None, fail=False):
        self._draft = draft
        self._fail = fail

    def is_available(self) -> bool:
        return True

    def generate_plan(self, brief: PlanBrief) -> LLMPlanDraft:
        if self._fail:
            raise LLMUnavailable("stub is down")
        return self._draft


def _insights(count=3):
    return [ImageInsight(media_id=f"m{i}", width=1200, height=1600) for i in range(count)]


def test_llm_draft_is_merged_into_a_valid_plan():
    draft = LLMPlanDraft(
        hook="Hungry?",
        cta="Order now",
        caption="Fresh every day",
        hashtags=["food", "pizza"],
        voiceover_script="Hungry? Order now.",
        scenes=[
            {"image_index": 0, "role": "hook", "duration_seconds": 2.0, "text": "Hungry?",
             "text_position": "center", "text_animation": "pop", "animation": "zoom_in",
             "transition": "fade"},
            {"image_index": 1, "role": "content", "duration_seconds": 2.5, "text": "From the oven",
             "animation": "ken_burns", "transition": "zoom"},
            {"image_index": -1, "role": "cta", "duration_seconds": 2.0, "text": "",
             "animation": "zoom_in", "transition": "push"},
        ],
    )
    request = PlanRequest(images=_insights(), style=VideoStyle.FOOD, topic="pizza")
    plan = draft_to_plan(draft, request, generated_by="stub")

    assert plan.generated_by == "stub"
    assert plan.hook == "Hungry?"
    assert plan.scenes[0].texts[0].content == "Hungry?"
    assert plan.scenes[-1].media_id is None
    assert plan.scenes[-1].texts[0].content == "Order now", "an empty CTA is filled from the plan"
    assert plan.scenes[0].transition.value == "none"


def test_out_of_range_image_index_is_repaired():
    draft = LLMPlanDraft(
        scenes=[
            {"image_index": 0, "duration_seconds": 2.0, "text": "one"},
            {"image_index": 42, "duration_seconds": 2.0, "text": "two"},
        ]
    )
    request = PlanRequest(images=_insights(2), style=VideoStyle.MINIMAL)
    plan = draft_to_plan(draft, request, generated_by="stub")
    assert plan.scenes[1].media_id in ("m0", "m1")


def test_a_failing_llm_falls_back(monkeypatch, client, auth, project_with_images):
    from app.services import plan_service

    monkeypatch.setattr(plan_service, "get_llm_provider", lambda: _StubLLM(fail=True))
    response = client.post(
        f"{API}/projects/{project_with_images['id']}/plan/generate",
        json={"instruction": "anything"},
        headers=auth["headers"],
    ).json()

    assert response["ai_used"] is False
    assert response["generated_by"] == "heuristic"
    assert response["plan"]["scenes"]


def test_a_working_llm_is_used(monkeypatch, client, auth, project_with_images):
    from app.services import plan_service

    draft = LLMPlanDraft(
        hook="Stop scrolling",
        cta="Grab yours",
        scenes=[
            {"image_index": 0, "role": "hook", "duration_seconds": 2.0, "text": "Stop scrolling"},
            {"image_index": 1, "role": "content", "duration_seconds": 2.0, "text": "Look at this"},
            {"image_index": 2, "role": "cta", "duration_seconds": 2.0, "text": "Grab yours"},
        ],
    )
    monkeypatch.setattr(plan_service, "get_llm_provider", lambda: _StubLLM(draft=draft))

    response = client.post(
        f"{API}/projects/{project_with_images['id']}/plan/generate",
        json={"instruction": "energetic"},
        headers=auth["headers"],
    ).json()

    assert response["ai_used"] is True
    assert response["generated_by"] == "stub"
    assert response["plan"]["hook"] == "Stop scrolling"
    assert response["notice"] == ""


# -------------------------------------------------------------- voice-over --


def test_voiceover_script_can_be_drafted_and_edited(client, auth, project_with_images):
    project_id = project_with_images["id"]
    client.post(f"{API}/projects/{project_id}/plan/generate", json={}, headers=auth["headers"])

    drafted = client.post(
        f"{API}/projects/{project_id}/voiceover/script", headers=auth["headers"]
    ).json()
    assert drafted["script"]
    assert drafted["status"] == "draft"

    edited = client.patch(
        f"{API}/projects/{project_id}/voiceover",
        json={"script": "My own narration.", "enabled": True},
        headers=auth["headers"],
    ).json()
    assert edited["script"] == "My own narration."
    assert edited["enabled"] is True


def test_voiceover_generation_reports_unavailable_provider(client, auth, project_with_images):
    project_id = project_with_images["id"]
    client.patch(
        f"{API}/projects/{project_id}/voiceover",
        json={"script": "Narration."},
        headers=auth["headers"],
    )
    response = client.post(f"{API}/projects/{project_id}/voiceover/generate", headers=auth["headers"])
    assert response.status_code == 503
    assert "no text-to-speech provider is configured" in response.json()["error"]["message"]


def test_ai_motion_reports_unavailable_provider(client, auth, project_with_images):
    project_id = project_with_images["id"]
    scene_id = project_with_images["scenes"][0]["id"]
    response = client.post(
        f"{API}/projects/{project_id}/scenes/{scene_id}/ai-motion", headers=auth["headers"]
    )
    assert response.status_code == 503
    assert "no video generation provider is configured" in response.json()["error"]["message"]
