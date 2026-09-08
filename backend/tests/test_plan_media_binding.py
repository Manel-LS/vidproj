"""A submitted plan must actually bind the audio and voice-over it names.

`plan_service.apply_plan` has always ownership-checked `audio.media_id`, but
`apply_plan_to_project` never wrote it — so a plan could name a track, be
accepted with 200, and then render with the previous audio. Nothing in the
response distinguished the two outcomes, which is the worst shape a bug can
take. The voice-over media id was neither validated nor applied.

These tests read the plan back through the API, which is what the editor does.
"""
from __future__ import annotations

API = "/api/v1"


def _plan_of(client, auth, project_id: str) -> dict:
    response = client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()["plan"]


def _put(client, auth, project_id: str, plan: dict):
    return client.put(
        f"{API}/projects/{project_id}/plan", json={"plan": plan}, headers=auth["headers"]
    )


def _upload_audio(client, auth, project_id: str, sample_audio, seconds: float = 6.0) -> str:
    response = client.post(
        f"{API}/projects/{project_id}/audio",
        files={"file": sample_audio(seconds)},
        headers=auth["headers"],
    )
    assert response.status_code in (200, 201), response.text
    body = response.json()
    return body["media"]["id"] if "media" in body else body["media_id"]


def test_plan_binds_detaches_and_rebinds_the_audio_track(client, auth, project_with_images, sample_audio):
    """Bind -> clear -> re-bind, through the plan only.

    A project holds one music track at a time, so the meaningful test is not
    "name the track already bound" — that passes even if the plan is ignored
    entirely. It is detaching it and putting it back: only a plan that is really
    applied can do both.
    """
    project_id = project_with_images["id"]
    media_id = _upload_audio(client, auth, project_id, sample_audio)
    assert _plan_of(client, auth, project_id)["audio"]["media_id"] == media_id

    plan = _plan_of(client, auth, project_id)
    plan["audio"]["media_id"] = None
    assert _put(client, auth, project_id, plan).status_code == 200
    assert _plan_of(client, auth, project_id)["audio"]["media_id"] is None

    plan = _plan_of(client, auth, project_id)
    plan["audio"]["media_id"] = media_id
    plan["audio"]["volume"] = 0.42
    assert _put(client, auth, project_id, plan).status_code == 200

    stored = _plan_of(client, auth, project_id)
    assert stored["audio"]["media_id"] == media_id
    assert stored["audio"]["volume"] == 0.42


def test_plan_binds_the_voice_over_it_names(client, auth, project_with_images, sample_audio):
    """The renderer reads the project row, so the plan's id has to reach it."""
    project_id = project_with_images["id"]
    media_id = _upload_audio(client, auth, project_id, sample_audio)

    plan = _plan_of(client, auth, project_id)
    plan["voiceover"]["enabled"] = True
    plan["voiceover"]["media_id"] = media_id
    plan["voiceover"]["script"] = "One short line of narration."
    assert _put(client, auth, project_id, plan).status_code == 200

    stored = _plan_of(client, auth, project_id)
    assert stored["voiceover"]["media_id"] == media_id
    assert stored["voiceover"]["enabled"] is True

    # The status describes the audio that exists; it must follow the media.
    voice = client.get(f"{API}/projects/{project_id}/voiceover", headers=auth["headers"]).json()
    assert voice["status"] == "ready"
    assert voice["media"]["id"] == media_id


def test_plan_cannot_borrow_media_from_another_project(
    client, auth, project_with_images, sample_audio
):
    """Ownership is re-checked on apply, for the voice-over as well as the track."""
    other = client.post(
        f"{API}/projects",
        json={"name": "Other project", "topic": "other", "target_duration": 8},
        headers=auth["headers"],
    )
    assert other.status_code == 201, other.text
    foreign_id = _upload_audio(client, auth, other.json()["id"], sample_audio)

    project_id = project_with_images["id"]
    plan = _plan_of(client, auth, project_id)
    plan["voiceover"]["enabled"] = True
    plan["voiceover"]["media_id"] = foreign_id
    response = _put(client, auth, project_id, plan)
    assert response.status_code == 422, response.text
    assert "not in this project" in response.json()["error"]["message"]

    assert _plan_of(client, auth, project_id)["voiceover"]["media_id"] is None
