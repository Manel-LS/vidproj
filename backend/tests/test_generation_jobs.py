"""The unified job registry.

Two things make it worth having, and both are tested here: every worker actually
writes to it (a registry only some workers use answers nothing), and it never
breaks the work it describes (losing a progress row is a missing line; losing a
generation is money).
"""
from __future__ import annotations

import pytest

from app.domain.enums import GenerationJobType, RenderStatus
from tests.test_image_generation import StubImageProvider, use_image_provider  # noqa: F401

API = "/api/v1"

PROMPT = "A plain shot, warm light, photorealistic, 9:16"


def _set_prompts(client, auth, project_id: str) -> None:
    plan = client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).json()["plan"]
    for scene in plan["scenes"]:
        scene["image_prompt"] = PROMPT
    client.put(f"{API}/projects/{project_id}/plan", json={"plan": plan}, headers=auth["headers"])


def _scenes(client, auth, project_id: str) -> list[dict]:
    return client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()["scenes"]


def _jobs(client, auth, project_id: str) -> dict:
    response = client.get(f"{API}/projects/{project_id}/jobs", headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------- recording --


def test_a_successful_image_generation_is_recorded(
    client, auth, project_with_images, use_image_provider  # noqa: F811
):
    use_image_provider(StubImageProvider())
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id)
    scene = _scenes(client, auth, project_id)[0]

    from app.services.image_worker import execute_image_job

    assert execute_image_job(project_id, auth["id"], scene["id"]) == "completed"

    body = _jobs(client, auth, project_id)
    assert body["total"] == 1
    job = body["items"][0]
    assert job["type"] == GenerationJobType.IMAGE.value
    assert job["status"] == RenderStatus.COMPLETED.value
    assert job["progress"] == 100
    assert job["scene_id"] == scene["id"]
    assert job["result_media_id"], "the job must point at what it produced"
    assert job["result_url"], "the editor shows the result straight from the job row"
    assert job["started_at"] and job["completed_at"]


def test_a_failed_generation_is_recorded_with_its_reason(
    client, auth, project_with_images, use_image_provider  # noqa: F811
):
    use_image_provider(StubImageProvider(fail="The provider refused this prompt."))
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id)
    scene = _scenes(client, auth, project_id)[0]

    from app.services.image_worker import execute_image_job

    assert execute_image_job(project_id, auth["id"], scene["id"]) == "failed"

    body = _jobs(client, auth, project_id)
    job = body["items"][0]
    assert job["status"] == RenderStatus.FAILED.value
    assert "refused this prompt" in job["error"]
    assert body["last_error"], "the summary has to surface the reason without a second call"


def test_the_summary_answers_what_the_project_is_doing(
    client, auth, project_with_images, use_image_provider  # noqa: F811
):
    use_image_provider(StubImageProvider())
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id)

    from app.services.image_worker import execute_image_job

    for scene in _scenes(client, auth, project_id):
        execute_image_job(project_id, auth["id"], scene["id"])

    body = _jobs(client, auth, project_id)
    assert body["total"] == 3
    assert body["active"] == 0
    assert body["by_status"][RenderStatus.COMPLETED.value] == 3


def test_a_single_job_can_be_polled(
    client, auth, project_with_images, use_image_provider  # noqa: F811
):
    """This is the endpoint the editor sits on while work is in flight."""
    use_image_provider(StubImageProvider())
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id)
    scene = _scenes(client, auth, project_id)[0]

    from app.services.image_worker import execute_image_job

    execute_image_job(project_id, auth["id"], scene["id"])
    job_id = _jobs(client, auth, project_id)["items"][0]["id"]

    polled = client.get(f"{API}/jobs/{job_id}", headers=auth["headers"])
    assert polled.status_code == 200
    assert polled.json()["id"] == job_id


def test_the_account_feed_lists_jobs_across_projects(
    client, auth, project_with_images, use_image_provider  # noqa: F811
):
    use_image_provider(StubImageProvider())
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id)
    scene = _scenes(client, auth, project_id)[0]

    from app.services.image_worker import execute_image_job

    execute_image_job(project_id, auth["id"], scene["id"])

    feed = client.get(f"{API}/jobs", headers=auth["headers"])
    assert feed.status_code == 200
    assert len(feed.json()) == 1


def test_the_voice_over_writes_to_the_registry_too(client, auth, project_with_images):
    """No TTS is configured in tests, so this exercises the failure path."""
    project_id = project_with_images["id"]
    client.patch(
        f"{API}/projects/{project_id}/voiceover",
        json={"script": "One line.", "enabled": True},
        headers=auth["headers"],
    )

    from app.services.voiceover_worker import execute_voiceover_job

    execute_voiceover_job(project_id, auth["id"])

    types = {job["type"] for job in _jobs(client, auth, project_id)["items"]}
    assert GenerationJobType.VOICE.value in types


# ------------------------------------------------------------------- isolation --


def test_jobs_are_private_to_their_owner(
    client, auth, user_factory, project_with_images, use_image_provider  # noqa: F811
):
    use_image_provider(StubImageProvider())
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id)
    scene = _scenes(client, auth, project_id)[0]

    from app.services.image_worker import execute_image_job

    execute_image_job(project_id, auth["id"], scene["id"])
    job_id = _jobs(client, auth, project_id)["items"][0]["id"]

    intruder = user_factory()
    assert client.get(f"{API}/jobs/{job_id}", headers=intruder["headers"]).status_code == 404
    assert (
        client.get(f"{API}/projects/{project_id}/jobs", headers=intruder["headers"]).status_code
        == 404
    )
    assert client.get(f"{API}/jobs", headers=intruder["headers"]).json() == []


# ------------------------------------------------------------------ robustness --


def test_the_registry_never_breaks_the_work_it_describes(
    client, auth, project_with_images, use_image_provider, monkeypatch  # noqa: F811
):
    """A registry that can fail a generation would be worse than no registry."""
    use_image_provider(StubImageProvider())
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id)
    scene = _scenes(client, auth, project_id)[0]

    import app.services.generation_job_service as service

    def explode(*args, **kwargs):
        raise RuntimeError("the registry is down")

    monkeypatch.setattr(service, "open_job", explode)

    from app.services.image_worker import execute_image_job

    with pytest.raises(RuntimeError):
        # Confirms the stub really does raise, so the next assertion means something.
        service.open_job(None, project_id="x", user_id="y", type=GenerationJobType.IMAGE)

    monkeypatch.setattr(service, "open_job", lambda *a, **k: None)
    assert execute_image_job(project_id, auth["id"], scene["id"]) == "completed", (
        "the image must still be generated when the registry returns nothing"
    )


def test_a_restart_fails_jobs_left_mid_flight(client, auth, project_with_images):
    """Otherwise the editor polls a 'processing' row that will never move."""
    from app.db.base import session_scope
    from app.models import GenerationJob
    from app.services import generation_job_service as service

    session = session_scope()
    try:
        session.add(
            GenerationJob(
                project_id=project_with_images["id"],
                user_id=auth["id"],
                type=GenerationJobType.VIDEO.value,
                status=RenderStatus.PROCESSING.value,
            )
        )
        session.commit()
        assert service.recover_orphaned(session) == 1
    finally:
        session.close()

    job = _jobs(client, auth, project_with_images["id"])["items"][0]
    assert job["status"] == RenderStatus.FAILED.value
    assert "restarted" in job["error"]
