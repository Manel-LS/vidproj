"""Reusable characters, and the consistency they are supposed to buy.

The table exists for one reason: an image model draws a different person on every
call. The mechanism against that is a description written once and replayed
verbatim, plus a reference image. So the tests that matter are not the CRUD ones —
they are the two that check the frozen sentence actually reaches every prompt, and
that it stops drifting once it is written.
"""
from __future__ import annotations

from tests.test_image_generation import StubImageProvider, use_image_provider  # noqa: F401

API = "/api/v1"

BABY = {
    "name": "Tunisian Baby",
    "kind": "baby",
    "age": "2 years old",
    "skin_tone": "warm olive skin",
    "hair": "dark curly hair",
    "clothes": "a red traditional jebba with white and gold embroidery",
    "headwear": "a red Tunisian chechia",
    "expression": "a shy smile",
    "environment": "a Tunisian family home",
}


def _create(client, auth, **overrides) -> dict:
    response = client.post(
        f"{API}/characters", json={**BABY, **overrides}, headers=auth["headers"]
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------- description --


def test_the_description_is_composed_from_the_fields(client, auth):
    character = _create(client, auth)
    description = character["description"]

    assert "toddler" in description, "the kind has to open the sentence"
    for fragment in ("2 years old", "dark curly hair", "red traditional jebba", "chechia"):
        assert fragment in description, f"{fragment!r} missing from {description!r}"
    assert "in a Tunisian family home" in description


def test_empty_fields_are_dropped_rather_than_left_blank(client, auth):
    """A prompt containing 'wearing , with hair' measurably degrades the result."""
    character = _create(
        client, auth, skin_tone="", hair="", headwear="", expression="", environment=""
    )
    description = character["description"]
    assert ", ," not in description
    assert not description.rstrip().endswith(",")
    assert " in " not in description or "home" in description


def test_a_written_description_wins_over_the_composed_one(client, auth):
    """Someone who wrote their own prompt knows better than a set of dropdowns."""
    mine = "the exact toddler from my reference photo, unchanged in every shot"
    character = _create(client, auth, description=mine)
    assert character["description"] == mine


def test_editing_a_field_recomposes_the_description(client, auth):
    """Otherwise the frozen sentence keeps describing the character it used to be."""
    character = _create(client, auth)
    assert "red traditional jebba" in character["description"]

    updated = client.patch(
        f"{API}/characters/{character['id']}",
        json={"clothes": "a blue traditional jebba"},
        headers=auth["headers"],
    )
    assert updated.status_code == 200, updated.text
    assert "blue traditional jebba" in updated.json()["description"]
    assert "red traditional jebba" not in updated.json()["description"]


def test_a_custom_description_is_not_recomposed_behind_the_user_s_back(client, auth):
    mine = "my own carefully tuned prompt"
    character = _create(client, auth, description=mine)
    updated = client.patch(
        f"{API}/characters/{character['id']}",
        json={"description": mine, "clothes": "a green jebba"},
        headers=auth["headers"],
    )
    assert updated.json()["description"] == mine


def test_the_prefix_reads_as_english_whatever_the_description_starts_with(client, auth):
    """The clause is consumed as "the same {description}".

    A description opening with an article produced "the same an adorable
    toddler" — a malformed phrase that shows up in the generated image.
    """
    composed = _create(client, auth)["description"]
    assert not composed.lower().startswith(("a ", "an ", "the ")), composed

    from app.models import Character
    from app.services import character_service

    for written, expected in (
        ("A toddler in a red jebba", "the same toddler in a red jebba"),
        ("An elderly man", "the same elderly man"),
        ("the same kid with curly hair", "the same kid with curly hair"),
        ("toddler already fine", "the same toddler already fine"),
    ):
        character = Character(user_id="u", name="n", kind="baby", description=written)

        class _Project:
            pass

        project = _Project()
        project.character = character
        assert character_service.prompt_prefix(project) == expected


# ------------------------------------------------------------------ the point --


def test_the_character_clause_is_prefixed_to_every_scene_prompt(
    client, auth, project_with_images, use_image_provider  # noqa: F811
):
    """The one thing this feature is for: the same words in front of every prompt."""
    provider = use_image_provider(StubImageProvider())
    character = _create(client, auth)
    project_id = project_with_images["id"]

    assert (
        client.patch(
            f"{API}/projects/{project_id}",
            json={"character_id": character["id"]},
            headers=auth["headers"],
        ).status_code
        == 200
    )

    plan = client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).json()["plan"]
    for index, scene in enumerate(plan["scenes"]):
        scene["image_prompt"] = f"Scene {index}, warm light, photorealistic, 9:16"
    client.put(f"{API}/projects/{project_id}/plan", json={"plan": plan}, headers=auth["headers"])

    from app.services.image_worker import execute_image_job

    scenes = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()["scenes"]
    for scene in scenes[:2]:
        assert execute_image_job(project_id, auth["id"], scene["id"]) == "completed"

    assert len(provider.requests) == 2
    prefixes = [r.prompt.split(". Scene")[0] for r in provider.requests]
    assert prefixes[0] == prefixes[1], "the character clause has to be identical every time"
    assert prefixes[0].startswith("the same "), "the model must be told the subject returns"
    assert "red traditional jebba" in prefixes[0]
    # And the scene's own prompt survives in front of it being prefixed.
    assert "Scene 0" in provider.requests[0].prompt
    assert "Scene 1" in provider.requests[1].prompt


def test_without_a_character_the_prompt_is_left_alone(
    client, auth, project_with_images, use_image_provider  # noqa: F811
):
    provider = use_image_provider(StubImageProvider())
    project_id = project_with_images["id"]
    plan = client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).json()["plan"]
    for scene in plan["scenes"]:
        scene["image_prompt"] = "A plain shot, photorealistic, 9:16"
    client.put(f"{API}/projects/{project_id}/plan", json={"plan": plan}, headers=auth["headers"])

    from app.services.image_worker import execute_image_job

    scene = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()["scenes"][0]
    assert execute_image_job(project_id, auth["id"], scene["id"]) == "completed"
    assert provider.requests[0].prompt == "A plain shot, photorealistic, 9:16"


def test_the_detail_shows_which_description_is_being_prefixed(
    client, auth, project_with_images
):
    character = _create(client, auth)
    project_id = project_with_images["id"]
    client.patch(
        f"{API}/projects/{project_id}",
        json={"character_id": character["id"]},
        headers=auth["headers"],
    )
    detail = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()
    assert detail["character_id"] == character["id"]
    assert detail["character_description"] == character["description"]


# ------------------------------------------------------------------ isolation --


def test_characters_are_private_to_their_owner(client, auth, user_factory):
    character = _create(client, auth)
    intruder = user_factory()

    assert client.get(f"{API}/characters", headers=intruder["headers"]).json() == []
    assert (
        client.get(f"{API}/characters/{character['id']}", headers=intruder["headers"]).status_code
        == 404
    )
    assert (
        client.patch(
            f"{API}/characters/{character['id']}",
            json={"name": "stolen"},
            headers=intruder["headers"],
        ).status_code
        == 404
    )


def test_a_project_cannot_borrow_someone_else_s_character(
    client, auth, user_factory, project_with_images
):
    intruder = user_factory()
    theirs = client.post(f"{API}/characters", json=BABY, headers=intruder["headers"]).json()

    response = client.patch(
        f"{API}/projects/{project_with_images['id']}",
        json={"character_id": theirs["id"]},
        headers=auth["headers"],
    )
    assert response.status_code == 404, response.text


def test_deleting_a_character_leaves_its_projects_working(
    client, auth, project_with_images
):
    """The scenes keep their own prompts; only the shared clause goes away."""
    character = _create(client, auth)
    project_id = project_with_images["id"]
    client.patch(
        f"{API}/projects/{project_id}",
        json={"character_id": character["id"]},
        headers=auth["headers"],
    )

    assert (
        client.delete(f"{API}/characters/{character['id']}", headers=auth["headers"]).status_code
        == 204
    )

    detail = client.get(f"{API}/projects/{project_id}", headers=auth["headers"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["character_id"] is None
    assert (
        client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).status_code == 200
    )


def test_a_reference_image_can_be_uploaded_and_is_returned(
    client, auth, project_with_images, sample_images
):
    character = _create(client, auth)
    file = sample_images(1)[0][1]

    response = client.post(
        f"{API}/characters/{character['id']}/reference",
        files={"file": file},
        headers=auth["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reference_media_id"]
    assert body["reference_image_url"]
