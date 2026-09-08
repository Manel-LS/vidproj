"""The AI Motion *generation* path, exercised against a stand-in provider.

The existing AI Motion tests cover what happens once a clip exists. Nothing
covered how the clip is obtained: submit to the provider, poll, download, store,
and record the id on the scene. That is the code that runs the first time a real
key is configured — the worst moment to discover it is broken, because the user
has already paid the provider for the generation.

The provider here is a stand-in implementing the real `ImageToVideoProvider`
interface, so the worker is driven exactly as a paid provider would drive it,
without any network call.
"""
from __future__ import annotations

import pytest

from app.domain.enums import MediaKind
from app.infrastructure.i2v import factory as i2v_factory
from app.infrastructure.i2v.base import (
    GeneratedVideo,
    GenerationRequest,
    GenerationState,
    GenerationStatus,
    ImageToVideoProvider,
    ImageToVideoUnavailable,
)

API = "/api/v1"


class StubProvider(ImageToVideoProvider):
    """Answers like a real provider: a job reference, then N polls, then a clip."""

    name = "stub"
    display_name = "Stub provider"
    supported_durations = (5.0,)
    supported_aspect_ratios = ("9:16",)

    def __init__(self, *, polls_before_ready: int = 2, fail: str = "", never_finishes: bool = False):
        self.polls_before_ready = polls_before_ready
        self.fail = fail
        self.never_finishes = never_finishes
        self.requests: list[GenerationRequest] = []
        self.polls = 0

    def is_available(self) -> bool:
        return True

    def generate_video_from_image(self, request: GenerationRequest) -> str:
        if self.fail == "submit":
            raise ImageToVideoUnavailable("The provider rejected the request.")
        self.requests.append(request)
        return "job-abc"

    def get_generation_status(self, job_reference: str) -> GenerationStatus:
        self.polls += 1
        if self.fail == "generate":
            return GenerationStatus(job_id=job_reference, state=GenerationState.FAILED,
                                    error="Content policy refusal.")
        if self.never_finishes or self.polls <= self.polls_before_ready:
            return GenerationStatus(job_id=job_reference, state=GenerationState.PROCESSING)
        return GenerationStatus(job_id=job_reference, state=GenerationState.COMPLETED)

    def get_video_result(self, job_reference: str) -> GeneratedVideo:
        return GeneratedVideo(
            data=b"\x00\x00\x00\x18ftypmp42fake-clip-bytes",
            content_type="video/mp4",
            extension="mp4",
            provider=self.name,
        )


@pytest.fixture()
def use_stub(monkeypatch):
    """Install a stand-in provider, honouring the factory's cache."""

    original = i2v_factory.get_i2v_provider

    def install(provider: ImageToVideoProvider) -> ImageToVideoProvider:
        original.cache_clear()
        monkeypatch.setattr(i2v_factory, "get_i2v_provider", lambda: provider)
        # The worker imported the factory function by name, so patch it there too.
        import app.services.ai_motion_worker as worker

        monkeypatch.setattr(worker, "get_i2v_provider", lambda: provider)
        return provider

    yield install
    # Clear the real cache, not the lambda monkeypatch left in its place.
    original.cache_clear()


@pytest.fixture()
def fast_polling(monkeypatch):
    """The worker sleeps between polls; tests must not."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "i2v_poll_interval_seconds", 0.0)
    monkeypatch.setattr(settings, "i2v_timeout_seconds", 5.0)


def _scene_of(client, auth, project_id: str) -> dict:
    detail = client.get(f"{API}/projects/{project_id}", headers=auth["headers"])
    assert detail.status_code == 200, detail.text
    scenes = detail.json()["scenes"]
    assert scenes, "the project should have at least one scene"
    return scenes[0]


def _run_worker(project_id: str, user_id: str, scene_id: str) -> str:
    from app.services.ai_motion_worker import execute_ai_motion_job

    return execute_ai_motion_job(project_id, user_id, scene_id)


def test_generation_stores_the_clip_and_records_it_on_the_scene(
    client, auth, project_with_images, use_stub, fast_polling
):
    provider = use_stub(StubProvider(polls_before_ready=2))
    project_id = project_with_images["id"]
    scene = _scene_of(client, auth, project_id)

    assert _run_worker(project_id, auth["id"], scene["id"]) == "completed"

    # The provider was handed the scene's actual image, not an empty payload.
    assert len(provider.requests) == 1
    assert provider.requests[0].image, "the still image must be sent to the provider"
    assert provider.requests[0].aspect_ratio == "9:16"

    updated = _scene_of(client, auth, project_id)
    clip_id = updated["ai_motion"]["generated_media_id"]
    assert clip_id, "the generated clip id must be recorded on the scene"
    assert not updated["ai_motion"].get("error")

    from app.db.base import session_scope
    from app.models import Media

    session = session_scope()
    try:
        clip = session.get(Media, clip_id)
        assert clip is not None
        assert clip.kind == MediaKind.VIDEO.value
        assert clip.project_id == project_id
        assert clip.source == "ai_motion"
    finally:
        session.close()


def test_a_provider_refusal_is_reported_on_the_scene_not_swallowed(
    client, auth, project_with_images, use_stub, fast_polling
):
    use_stub(StubProvider(fail="generate"))
    project_id = project_with_images["id"]
    scene = _scene_of(client, auth, project_id)

    assert _run_worker(project_id, auth["id"], scene["id"]) == "failed"

    updated = _scene_of(client, auth, project_id)
    assert "Content policy refusal." in (updated["ai_motion"].get("error") or "")
    assert not updated["ai_motion"].get("generated_media_id")


def test_a_generation_that_never_finishes_times_out_instead_of_hanging(
    client, auth, project_with_images, use_stub, fast_polling
):
    """Without a deadline the worker would hold its thread until the process dies."""
    use_stub(StubProvider(never_finishes=True))
    project_id = project_with_images["id"]
    scene = _scene_of(client, auth, project_id)

    assert _run_worker(project_id, auth["id"], scene["id"]) == "failed"

    updated = _scene_of(client, auth, project_id)
    assert "timed out" in (updated["ai_motion"].get("error") or "").lower()


def test_a_render_after_a_successful_generation_is_accepted(
    client, auth, project_with_images, use_stub, fast_polling
):
    """The end the user cares about: generate, then render without being blocked."""
    use_stub(StubProvider(polls_before_ready=1))
    project_id = project_with_images["id"]

    detail = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()
    for scene in detail["scenes"]:
        assert _run_worker(project_id, auth["id"], scene["id"]) == "completed"

    client.patch(f"{API}/projects/{project_id}", json={"mode": "ai_motion"}, headers=auth["headers"])
    response = client.post(f"{API}/projects/{project_id}/render", headers=auth["headers"])
    assert response.status_code in (201, 202), response.text
