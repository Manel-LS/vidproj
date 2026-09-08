"""`scenes.image_prompt` has to survive the round trip through the API.

The column was added with the image provider (migration `b1c4e7f20a91`) and the
generation route writes it, but `SceneResponse` never carried it — so the editor
could not show what a shot was asked for, nor pre-fill a regeneration with the
same wording, even though the route's own docstring promised exactly that.

The interesting case is not reading it back. It is editing something else
afterwards: the update path rebuilds a `PlanScene` from the row and writes the
result back, so a field missing from that reconstruction is silently reset to its
default by an unrelated change.
"""
from __future__ import annotations

API = "/api/v1"

PROMPT = (
    "A Tunisian toddler in a red chechia sitting on a woven mat, warm afternoon light "
    "through a window, shallow depth of field, no morphing"
)


def _scenes(client, auth, project_id: str) -> list[dict]:
    response = client.get(f"{API}/projects/{project_id}/scenes", headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def _patch(client, auth, project_id: str, scene_id: str, changes: dict):
    return client.patch(
        f"{API}/projects/{project_id}/scenes/{scene_id}", json=changes, headers=auth["headers"]
    )


def test_image_prompt_is_returned_by_the_api(client, auth, project_with_images):
    project_id = project_with_images["id"]
    scene = _scenes(client, auth, project_id)[0]
    assert "image_prompt" in scene, "the editor cannot show a field the API never sends"
    assert scene["image_prompt"] == ""

    assert _patch(client, auth, project_id, scene["id"], {"image_prompt": PROMPT}).status_code == 200
    assert _scenes(client, auth, project_id)[0]["image_prompt"] == PROMPT


def test_an_unrelated_edit_does_not_blank_the_prompt(client, auth, project_with_images):
    """The regression this module exists for."""
    project_id = project_with_images["id"]
    scene = _scenes(client, auth, project_id)[0]
    _patch(client, auth, project_id, scene["id"], {"image_prompt": PROMPT})

    # Nudge the duration — nothing to do with the prompt.
    assert _patch(client, auth, project_id, scene["id"], {"duration": 4.5}).status_code == 200

    after = _scenes(client, auth, project_id)[0]
    assert after["duration"] == 4.5
    assert after["image_prompt"] == PROMPT


def test_the_project_detail_carries_the_prompt_too(client, auth, project_with_images):
    # The editor loads the project, not the scene list, so both paths must agree.
    project_id = project_with_images["id"]
    scene = _scenes(client, auth, project_id)[0]
    _patch(client, auth, project_id, scene["id"], {"image_prompt": PROMPT})

    detail = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()
    assert detail["scenes"][0]["image_prompt"] == PROMPT


def test_duplicating_a_scene_keeps_its_prompt(client, auth, project_with_images):
    """A prompt is a creative input; losing it on duplicate means retyping it."""
    project_id = project_with_images["id"]
    scene = _scenes(client, auth, project_id)[0]
    _patch(client, auth, project_id, scene["id"], {"image_prompt": PROMPT})

    response = client.post(
        f"{API}/projects/{project_id}/scenes/{scene['id']}/duplicate", headers=auth["headers"]
    )
    assert response.status_code in (200, 201), response.text

    scenes = response.json()
    assert scenes[1]["image_prompt"] == PROMPT
    assert scenes[1]["id"] != scene["id"]


def test_an_overlong_prompt_is_rejected_rather_than_truncated(client, auth, project_with_images):
    project_id = project_with_images["id"]
    scene = _scenes(client, auth, project_id)[0]
    response = _patch(client, auth, project_id, scene["id"], {"image_prompt": "x" * 1201})
    assert response.status_code == 422
    assert _scenes(client, auth, project_id)[0]["image_prompt"] == ""
