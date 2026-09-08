"""The `ImageProvider` chain: unconfigured behaviour, generation, and failures.

The provider here is a stand-in implementing the real interface, so the worker
and the route are driven exactly as a paid provider would drive them, with no
network call. What matters is that a generated image is treated like an uploaded
one — optimised, analysed, sized — because the planner and the renderer read
those fields, and that a failure is reported rather than swallowed.
"""
from __future__ import annotations

import pytest

from app.domain.enums import MediaKind
from app.infrastructure.image import factory as image_factory
from app.infrastructure.image.base import (
    GeneratedImage,
    ImageProvider,
    ImageRequest,
    ImageUnavailable,
    NullImageProvider,
)
from app.infrastructure.imaging.samples import generate_sample_image

API = "/api/v1"

PROMPT = (
    "Close-up of a Tunisian toddler in a red jebba with gold embroidery, warm "
    "golden window light, shallow depth of field, photorealistic, cinematic, 9:16"
)


class StubImageProvider(ImageProvider):
    name = "stub"
    display_name = "Stub images"
    supported_aspect_ratios = ("9:16", "1:1")

    def __init__(self, *, fail: str = "", supports_reference: bool = False):
        self.fail = fail
        self.supports_reference_image = supports_reference
        self.requests: list[ImageRequest] = []

    def is_available(self) -> bool:
        return True

    def generate(self, request: ImageRequest) -> GeneratedImage:
        self.requests.append(request)
        if self.fail:
            raise ImageUnavailable(self.fail)
        # A real JPEG, so the optimise/analyse path runs for real.
        return GeneratedImage(
            data=generate_sample_image(3, width=1080, height=1920),
            content_type="image/jpeg",
            extension="jpg",
            provider=self.name,
        )


@pytest.fixture()
def use_image_provider(monkeypatch):
    original = image_factory.get_image_provider

    def install(provider: ImageProvider) -> ImageProvider:
        original.cache_clear()
        monkeypatch.setattr(image_factory, "get_image_provider", lambda: provider)
        import app.api.v1.routes.ai as ai_routes
        import app.services.image_worker as worker

        monkeypatch.setattr(worker, "get_image_provider", lambda: provider)
        monkeypatch.setattr(ai_routes, "get_image_provider", lambda: provider)
        return provider

    yield install
    original.cache_clear()


def _first_scene(client, auth, project_id: str) -> dict:
    detail = client.get(f"{API}/projects/{project_id}", headers=auth["headers"])
    assert detail.status_code == 200, detail.text
    return detail.json()["scenes"][0]


def _run(project_id: str, user_id: str, scene_id: str) -> str:
    from app.services.image_worker import execute_image_job

    return execute_image_job(project_id, user_id, scene_id)


def _set_prompts(client, auth, project_id: str, prompt: str) -> None:
    """Store the prompt through the plan rather than the route.

    The route enqueues on the in-process queue, which really runs the job — so
    calling the route *and* the worker would generate twice and make assertions
    on call counts meaningless. Tests that drive the worker set the prompt this
    way; the route has its own tests.

    Note that saving a plan rewrites the scene rows wholesale, so scene ids change:
    always re-read the scenes after calling this.
    """
    plan = client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).json()["plan"]
    for scene in plan["scenes"]:
        scene["image_prompt"] = prompt
    assert (
        client.put(
            f"{API}/projects/{project_id}/plan", json={"plan": plan}, headers=auth["headers"]
        ).status_code
        == 200
    )


# ----------------------------------------------------------------- unconfigured --


def test_the_null_provider_reports_unavailable_and_explains_itself():
    provider = NullImageProvider()
    assert provider.is_available() is False
    with pytest.raises(ImageUnavailable) as exc:
        provider.generate(ImageRequest(prompt=PROMPT))
    assert "no image provider is configured" in str(exc.value)


def test_capabilities_reports_image_generation(client):
    body = client.get(f"{API}/capabilities").json()
    assert "image" in body, "the UI needs an `image` entry to enable or disable the feature"
    assert body["image"]["available"] is False
    assert body["image"]["message"], "an unavailable provider must say why"


def test_the_route_refuses_instead_of_pretending_when_unconfigured(
    client, auth, project_with_images
):
    """No key must mean a clear refusal — never a queued job that cannot succeed."""
    project_id = project_with_images["id"]
    scene = _first_scene(client, auth, project_id)
    response = client.post(
        f"{API}/projects/{project_id}/scenes/{scene['id']}/image",
        params={"prompt": PROMPT},
        headers=auth["headers"],
    )
    assert response.status_code == 503, response.text
    assert "no image provider is configured" in response.json()["error"]["message"]


# -------------------------------------------------------------------- success --


def test_generation_stores_the_image_and_attaches_it_to_the_scene(
    client, auth, project_with_images, use_image_provider
):
    provider = use_image_provider(StubImageProvider())
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id, PROMPT)
    scene = _first_scene(client, auth, project_id)  # ids changed with the plan save

    assert _run(project_id, auth["id"], scene["id"]) == "completed"

    assert len(provider.requests) == 1
    assert provider.requests[0].prompt == PROMPT
    assert provider.requests[0].aspect_ratio == "9:16"

    updated = _first_scene(client, auth, project_id)
    assert updated["media_id"] != scene["media_id"], "the scene must point at the new image"

    from app.db.base import session_scope
    from app.models import Media

    session = session_scope()
    try:
        media = session.get(Media, updated["media_id"])
        assert media is not None
        assert media.kind == MediaKind.IMAGE.value
        assert media.source == "ai_image"
        # Treated like an upload: sized, thumbnailed, analysed. The planner and
        # the renderer read all three.
        assert media.width and media.height
        assert media.thumbnail_key
        assert media.analysis
    finally:
        session.close()


def test_the_prompt_is_kept_on_the_scene_so_it_can_be_regenerated(
    client, auth, project_with_images, use_image_provider
):
    use_image_provider(StubImageProvider())
    project_id = project_with_images["id"]
    scene = _first_scene(client, auth, project_id)

    client.post(
        f"{API}/projects/{project_id}/scenes/{scene['id']}/image",
        params={"prompt": PROMPT},
        headers=auth["headers"],
    )
    plan = client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).json()["plan"]
    assert plan["scenes"][0]["image_prompt"] == PROMPT

    # And it survives a plan round-trip, which is how the editor saves.
    assert (
        client.put(
            f"{API}/projects/{project_id}/plan", json={"plan": plan}, headers=auth["headers"]
        ).status_code
        == 200
    )
    again = client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).json()["plan"]
    assert again["scenes"][0]["image_prompt"] == PROMPT


def test_a_reference_image_is_only_sent_to_providers_that_accept_one(
    client, auth, project_with_images, use_image_provider
):
    """Passing a reference blindly would make providers reject the request."""
    plain = use_image_provider(StubImageProvider(supports_reference=False))
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id, PROMPT)
    scenes = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()["scenes"]

    for scene in scenes[:2]:
        assert _run(project_id, auth["id"], scene["id"]) == "completed"
    assert all(request.reference_image is None for request in plain.requests)

    # A provider that does accept one gets the earlier generated image back.
    keen = use_image_provider(StubImageProvider(supports_reference=True))
    third = scenes[2]
    assert _run(project_id, auth["id"], third["id"]) == "completed"
    assert keen.requests[0].reference_image, "subject consistency needs the reference passed"


# -------------------------------------------------------------------- failure --


def test_a_provider_refusal_is_recorded_on_the_scene(
    client, auth, project_with_images, use_image_provider
):
    use_image_provider(StubImageProvider(fail="The provider refused this prompt."))
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id, PROMPT)
    scene = _first_scene(client, auth, project_id)

    assert _run(project_id, auth["id"], scene["id"]) == "failed"

    updated = _first_scene(client, auth, project_id)
    assert "refused this prompt" in (updated["ai_motion"] or {}).get("error", "")
    # The previous image must still be there: a failed generation loses nothing.
    assert updated["media_id"] == scene["media_id"]


def test_a_failed_generation_leaves_the_project_readable(
    client, auth, project_with_images, use_image_provider
):
    """The error is written into the scene, so the plan must still validate."""
    use_image_provider(StubImageProvider(fail="Rate limited."))
    project_id = project_with_images["id"]
    _set_prompts(client, auth, project_id, PROMPT)
    scene = _first_scene(client, auth, project_id)

    _run(project_id, auth["id"], scene["id"])

    assert client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).status_code == 200
    assert (
        client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).status_code == 200
    )


def test_an_empty_prompt_is_refused_before_anything_is_queued(
    client, auth, project_with_images, use_image_provider
):
    use_image_provider(StubImageProvider())
    project_id = project_with_images["id"]
    scene = _first_scene(client, auth, project_id)

    response = client.post(
        f"{API}/projects/{project_id}/scenes/{scene['id']}/image",
        params={"prompt": "   "},
        headers=auth["headers"],
    )
    assert response.status_code == 422, response.text


def test_another_users_project_is_not_reachable(
    client, auth, user_factory, project_with_images, use_image_provider
):
    use_image_provider(StubImageProvider())
    intruder = user_factory()
    project_id = project_with_images["id"]
    scene = _first_scene(client, auth, project_id)

    response = client.post(
        f"{API}/projects/{project_id}/scenes/{scene['id']}/image",
        params={"prompt": PROMPT},
        headers=intruder["headers"],
    )
    assert response.status_code == 404, response.text
