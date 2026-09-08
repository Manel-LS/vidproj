"""API tests: authentication, project permissions, media upload, scene editing."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app.infrastructure.imaging.samples import generate_sample_image

API = "/api/v1"


# ------------------------------------------------------------------ system --


def test_health_reports_dependencies(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] is True


def test_capabilities_lists_every_provider(client):
    body = client.get(f"{API}/capabilities").json()
    for section in ("render", "ai_planner", "voiceover", "ai_motion", "queue", "storage"):
        assert section in body
    assert body["render"]["available"] is True, "ffmpeg must be available for the test suite"
    # Nothing external is configured in tests, and that must be reported honestly.
    assert body["voiceover"]["available"] is False
    assert body["ai_motion"]["available"] is False
    assert body["ai_motion"]["message"]


def test_catalog_endpoints(client):
    assert len(client.get(f"{API}/styles").json()) == 10
    templates = client.get(f"{API}/templates").json()
    assert templates["items"] and templates["categories"]
    formats = client.get(f"{API}/formats").json()
    assert any(f["key"] == "9:16" and f["default"] for f in formats["formats"])
    options = client.get(f"{API}/options").json()
    assert "ken_burns" in options["animations"]
    assert client.get(f"{API}/plan-schema").json()["title"] == "VideoPlan"


# -------------------------------------------------------------------- auth --


def test_register_and_login(client):
    payload = {"email": "newuser@example.com", "password": "supersecret", "full_name": "New"}
    created = client.post(f"{API}/auth/register", json=payload)
    assert created.status_code == 201
    assert created.json()["user"]["email"] == "newuser@example.com"

    logged_in = client.post(
        f"{API}/auth/login", json={"email": "NewUser@Example.com", "password": "supersecret"}
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["access_token"]


def test_duplicate_email_is_rejected(client, auth):
    again = client.post(
        f"{API}/auth/register", json={"email": auth["email"], "password": "password123"}
    )
    assert again.status_code == 409
    assert "already exists" in again.json()["error"]["message"]


def test_weak_password_is_rejected(client):
    response = client.post(f"{API}/auth/register", json={"email": "a@b.com", "password": "short"})
    assert response.status_code == 422


def test_wrong_password_is_rejected(client, auth):
    response = client.post(
        f"{API}/auth/login", json={"email": auth["email"], "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert "incorrect" in response.json()["error"]["message"]


def test_protected_routes_require_a_token(client):
    assert client.get(f"{API}/projects").status_code == 401
    assert client.get(f"{API}/projects", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_me_returns_the_signed_in_user(client, auth):
    body = client.get(f"{API}/auth/me", headers=auth["headers"]).json()
    assert body["email"] == auth["email"]


# ---------------------------------------------------------------- projects --


def test_create_and_fetch_a_project(client, auth):
    created = client.post(
        f"{API}/projects",
        json={"name": "Summer fashion", "style": "luxury", "platform": "instagram_reels"},
        headers=auth["headers"],
    )
    assert created.status_code == 201
    body = created.json()
    assert body["style"] == "luxury"
    assert body["format"] == "9:16"
    assert body["audio"] is not None and body["voice_over"] is not None

    fetched = client.get(f"{API}/projects/{body['id']}", headers=auth["headers"])
    assert fetched.status_code == 200


def test_project_isolation_between_users(client, user_factory, project):
    other = user_factory()
    for method, path in [
        ("get", f"{API}/projects/{project['id']}"),
        ("patch", f"{API}/projects/{project['id']}"),
        ("delete", f"{API}/projects/{project['id']}"),
        ("get", f"{API}/projects/{project['id']}/scenes"),
        ("post", f"{API}/projects/{project['id']}/render"),
    ]:
        response = getattr(client, method)(
            path, headers=other["headers"], **({"json": {}} if method == "patch" else {})
        )
        assert response.status_code == 404, f"{method} {path} leaked another user's project"


def test_project_listing_only_shows_your_own(client, auth, user_factory, project):
    other = user_factory()
    client.post(f"{API}/projects", json={"name": "Theirs"}, headers=other["headers"])

    mine = client.get(f"{API}/projects", headers=auth["headers"]).json()
    assert all(item["name"] != "Theirs" for item in mine["items"])
    assert any(item["id"] == project["id"] for item in mine["items"])


def test_update_and_delete_a_project(client, auth, project):
    updated = client.patch(
        f"{API}/projects/{project['id']}",
        json={"name": "Renamed", "cta": "Buy now", "hashtags": ["#sale", "deal"]},
        headers=auth["headers"],
    ).json()
    assert updated["name"] == "Renamed"
    assert updated["hashtags"] == ["sale", "deal"]

    assert client.delete(f"{API}/projects/{project['id']}", headers=auth["headers"]).status_code == 204
    assert client.get(f"{API}/projects/{project['id']}", headers=auth["headers"]).status_code == 404


def test_creating_a_project_with_an_unknown_template_fails(client, auth):
    response = client.post(
        f"{API}/projects", json={"name": "x", "template_key": "nope"}, headers=auth["headers"]
    )
    assert response.status_code == 422


# ------------------------------------------------------------------- media --


def test_upload_images_creates_scenes(client, auth, project, sample_images):
    response = client.post(
        f"{API}/projects/{project['id']}/media", files=sample_images(3), headers=auth["headers"]
    )
    assert response.status_code == 201
    uploaded = response.json()
    assert len(uploaded) == 3
    assert all(item["thumbnail_url"] for item in uploaded)
    assert all(item["analysis"]["focus_x"] for item in uploaded)

    detail = client.get(f"{API}/projects/{project['id']}", headers=auth["headers"]).json()
    assert len(detail["scenes"]) == 3
    assert detail["total_duration"] > 0


def test_uploaded_images_are_served_back(client, auth, project_with_images):
    url = project_with_images["media"][0]["url"]
    response = client.get(url.replace("http://localhost:8000", ""))
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_non_image_upload_is_rejected(client, auth, project):
    response = client.post(
        f"{API}/projects/{project['id']}/media",
        files=[("files", ("evil.jpg", b"<?php system($_GET[0]); ?>", "image/jpeg"))],
        headers=auth["headers"],
    )
    assert response.status_code == 422
    assert "could not be read as an image" in response.json()["error"]["message"]


def test_oversized_upload_is_rejected(client, auth, project, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_image_bytes", 1024)
    response = client.post(
        f"{API}/projects/{project['id']}/media",
        files=[("files", ("big.jpg", generate_sample_image(0), "image/jpeg"))],
        headers=auth["headers"],
    )
    assert response.status_code == 422
    assert "larger than" in response.json()["error"]["message"]


def test_uploads_are_stripped_of_exif_and_downscaled(client, auth, project, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "image_max_dimension", 400)
    big = Image.new("RGB", (2000, 1000), (120, 30, 30))
    buffer = io.BytesIO()
    big.save(buffer, format="JPEG", exif=Image.Exif().tobytes())

    response = client.post(
        f"{API}/projects/{project['id']}/media",
        files=[("files", ("wide.jpg", buffer.getvalue(), "image/jpeg"))],
        headers=auth["headers"],
    )
    assert response.status_code == 201
    assert max(response.json()[0]["width"], response.json()[0]["height"]) <= 400


def test_reorder_replace_crop_and_delete_media(client, auth, project_with_images, sample_images):
    project_id = project_with_images["id"]
    images = [m for m in project_with_images["media"] if m["kind"] == "image"]
    reversed_ids = [m["id"] for m in reversed(images)]

    reordered = client.post(
        f"{API}/projects/{project_id}/media/reorder",
        json={"media_ids": reversed_ids},
        headers=auth["headers"],
    ).json()
    assert [m["id"] for m in reordered] == reversed_ids

    target = images[0]["id"]
    replaced = client.put(
        f"{API}/projects/{project_id}/media/{target}",
        files={"file": ("new.jpg", generate_sample_image(4, width=800, height=800), "image/jpeg")},
        headers=auth["headers"],
    ).json()
    assert replaced["id"] == target, "replacing must keep the id so scenes still resolve"
    assert replaced["width"] == replaced["height"]

    cropped = client.post(
        f"{API}/projects/{project_id}/media/{target}/crop",
        json={"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5},
        headers=auth["headers"],
    ).json()
    assert cropped["width"] < replaced["width"]

    assert client.delete(
        f"{API}/projects/{project_id}/media/{target}", headers=auth["headers"]
    ).status_code == 204

    after = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()
    assert len(after["scenes"]) == 3, "deleting an image must not delete the scene"
    assert any(scene["media_id"] is None for scene in after["scenes"])


def test_invalid_crop_is_rejected(client, auth, project_with_images):
    project_id = project_with_images["id"]
    media_id = project_with_images["media"][0]["id"]
    response = client.post(
        f"{API}/projects/{project_id}/media/{media_id}/crop",
        json={"x": 0.8, "y": 0.1, "width": 0.5, "height": 0.5},
        headers=auth["headers"],
    )
    assert response.status_code == 422


# ------------------------------------------------------------------ scenes --


def test_scene_crud(client, auth, project_with_images):
    project_id = project_with_images["id"]
    scenes = client.get(f"{API}/projects/{project_id}/scenes", headers=auth["headers"]).json()
    assert len(scenes) == 3
    assert scenes[0]["transition"] == "none"

    updated = client.patch(
        f"{API}/projects/{project_id}/scenes/{scenes[1]['id']}",
        json={
            "duration": 4.5,
            "animation": "pan_right",
            "transition": "blur",
            "transition_duration": 0.5,
            "texts": [
                {
                    "role": "title",
                    "content": "Everything you need",
                    "position": "center",
                    "animation": "pop",
                    "font_size": 90,
                }
            ],
        },
        headers=auth["headers"],
    ).json()
    assert updated["duration"] == 4.5
    assert updated["animation"] == "pan_right"
    assert updated["texts"][0]["content"] == "Everything you need"

    duplicated = client.post(
        f"{API}/projects/{project_id}/scenes/{scenes[1]['id']}/duplicate", headers=auth["headers"]
    ).json()
    assert len(duplicated) == 4
    assert [s["order"] for s in duplicated] == [0, 1, 2, 3]

    reordered = client.post(
        f"{API}/projects/{project_id}/scenes/reorder",
        json={"scene_ids": [s["id"] for s in reversed(duplicated)]},
        headers=auth["headers"],
    ).json()
    assert reordered[0]["id"] == duplicated[-1]["id"]
    assert reordered[0]["transition"] == "none", "the new first scene must lose its transition"

    remaining = client.delete(
        f"{API}/projects/{project_id}/scenes/{reordered[0]['id']}", headers=auth["headers"]
    ).json()
    assert len(remaining) == 3


def test_scene_start_times_are_reported(client, auth, project_with_images):
    project_id = project_with_images["id"]
    scenes = client.get(f"{API}/projects/{project_id}/scenes", headers=auth["headers"]).json()
    assert scenes[0]["start_time"] == 0.0
    assert scenes[1]["start_time"] > 0
    assert scenes[2]["start_time"] > scenes[1]["start_time"]


def test_scene_rejects_invalid_values(client, auth, project_with_images):
    project_id = project_with_images["id"]
    scene_id = project_with_images["scenes"][0]["id"]
    for payload in (
        {"duration": 0.0},
        {"animation": "teleport"},
        {"texts": [{"content": "x", "color": "not-a-colour"}]},
        {"transition_duration": 99},
    ):
        response = client.patch(
            f"{API}/projects/{project_id}/scenes/{scene_id}", json=payload, headers=auth["headers"]
        )
        assert response.status_code == 422, payload


def test_a_scene_cannot_use_another_projects_image(client, auth, project_with_images):
    other = client.post(f"{API}/projects", json={"name": "Other"}, headers=auth["headers"]).json()
    foreign_media_id = project_with_images["media"][0]["id"]
    response = client.post(
        f"{API}/projects/{other['id']}/scenes",
        json={"media_id": foreign_media_id},
        headers=auth["headers"],
    )
    assert response.status_code == 422


def test_last_scene_cannot_be_deleted(client, auth, project, sample_images):
    client.post(f"{API}/projects/{project['id']}/media", files=sample_images(1), headers=auth["headers"])
    scenes = client.get(f"{API}/projects/{project['id']}/scenes", headers=auth["headers"]).json()
    response = client.delete(
        f"{API}/projects/{project['id']}/scenes/{scenes[0]['id']}", headers=auth["headers"]
    )
    assert response.status_code == 422
    assert "at least one scene" in response.json()["error"]["message"]


# ------------------------------------------------------------------- audio --


def test_audio_upload_and_settings(client, auth, project_with_images, sample_audio):
    project_id = project_with_images["id"]
    uploaded = client.post(
        f"{API}/projects/{project_id}/audio",
        files={"file": sample_audio()},
        headers=auth["headers"],
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["media"]["kind"] == "audio"

    updated = client.patch(
        f"{API}/projects/{project_id}/audio",
        json={"volume": 0.4, "fade_in": 1.0, "fade_out": 2.0},
        headers=auth["headers"],
    ).json()
    assert updated["volume"] == 0.4

    cleared = client.patch(
        f"{API}/projects/{project_id}/audio", json={"clear": True}, headers=auth["headers"]
    ).json()
    assert cleared["media_id"] is None


def test_non_audio_upload_is_rejected(client, auth, project):
    response = client.post(
        f"{API}/projects/{project['id']}/audio",
        files={"file": ("fake.mp3", b"not really audio at all", "audio/mpeg")},
        headers=auth["headers"],
    )
    assert response.status_code == 422
    assert "not a readable MP3 or WAV" in response.json()["error"]["message"]


def test_music_library_is_empty_and_honest(client, auth, project):
    response = client.get(f"{API}/projects/{project['id']}/audio/library", headers=auth["headers"])
    assert response.status_code == 200
    assert response.json() == []
