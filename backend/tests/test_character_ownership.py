"""A project may only point at a character its own owner saved.

`character_id` was accepted verbatim on both project creation and update, with no
ownership check. That is not a cosmetic hole: the frozen description is replayed
into every image prompt (`character_service.prompt_prefix`), it is returned to the
client as `character_description`, and the image worker prefers the character's
reference image over anything in the project — so a borrowed id would read another
user's text and their picture.
"""
from __future__ import annotations

API = "/api/v1"

CHARACTER = {
    "name": "Skander",
    "kind": "baby",
    "age": "2 years old",
    "skin_tone": "olive skin",
    "clothes": "a red velvet jebba",
    "headwear": "a red chechia",
}


def _make_character(client, owner) -> dict:
    response = client.post(f"{API}/characters", json=CHARACTER, headers=owner["headers"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["description"], "the frozen description is what a thief would be after"
    return body


def test_a_stranger_cannot_borrow_a_character_at_creation(client, user_factory):
    owner, stranger = user_factory(), user_factory()
    character = _make_character(client, owner)

    response = client.post(
        f"{API}/projects",
        json={"name": "Borrowed", "character_id": character["id"]},
        headers=stranger["headers"],
    )
    assert response.status_code == 404, response.text
    # And nothing was created holding the id.
    listing = client.get(f"{API}/projects", headers=stranger["headers"]).json()
    assert listing["total"] == 0


def test_a_stranger_cannot_borrow_a_character_by_update(client, user_factory):
    owner, stranger = user_factory(), user_factory()
    character = _make_character(client, owner)

    project = client.post(
        f"{API}/projects", json={"name": "Mine"}, headers=stranger["headers"]
    ).json()

    response = client.patch(
        f"{API}/projects/{project['id']}",
        json={"character_id": character["id"]},
        headers=stranger["headers"],
    )
    assert response.status_code == 404, response.text

    after = client.get(f"{API}/projects/{project['id']}", headers=stranger["headers"]).json()
    assert after["character_id"] is None
    assert after["character_description"] == "", "another user's description must not leak"


def test_the_owner_can_attach_and_detach_their_own_character(client, user_factory):
    owner = user_factory()
    character = _make_character(client, owner)
    project = client.post(f"{API}/projects", json={"name": "Mine"}, headers=owner["headers"]).json()

    attached = client.patch(
        f"{API}/projects/{project['id']}",
        json={"character_id": character["id"]},
        headers=owner["headers"],
    )
    assert attached.status_code == 200, attached.text
    assert attached.json()["character_id"] == character["id"]
    assert attached.json()["character_description"] == character["description"]

    # An explicit null detaches. Every other optional field on this endpoint reads
    # None as "not sent", which is exactly why detaching used to be impossible.
    detached = client.patch(
        f"{API}/projects/{project['id']}", json={"character_id": None}, headers=owner["headers"]
    )
    assert detached.status_code == 200, detached.text
    assert detached.json()["character_id"] is None
    assert detached.json()["character_description"] == ""


def test_omitting_the_field_leaves_the_character_alone(client, user_factory):
    """Detaching on null must not turn every unrelated edit into a detach."""
    owner = user_factory()
    character = _make_character(client, owner)
    project = client.post(
        f"{API}/projects",
        json={"name": "Mine", "character_id": character["id"]},
        headers=owner["headers"],
    ).json()

    renamed = client.patch(
        f"{API}/projects/{project['id']}", json={"name": "Renamed"}, headers=owner["headers"]
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Renamed"
    assert renamed.json()["character_id"] == character["id"]


def test_an_unknown_character_id_is_refused(client, auth):
    response = client.post(
        f"{API}/projects",
        json={"name": "Ghost", "character_id": "0" * 32},
        headers=auth["headers"],
    )
    assert response.status_code == 404, response.text
