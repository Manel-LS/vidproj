"""Brand kits: a brand's constants, and where they actually land.

The rule worth pinning is that a kit is **copied onto the plan**, not looked up at
render time. A plan is what a render is reproduced from, so a kit edited next
month must not silently change what an older render meant.
"""
from __future__ import annotations

import pytest

from app.domain.plan import validate_plan

API = "/api/v1"

KIT = {
    "name": "Nova",
    "brand_name": "Nova Stationery",
    "slogan": "La rentrée, en mieux",
    "primary_color": "#FFFFFF",
    "accent_color": "#39E08B",
    "background_color": "#101014",
    "logo_position": "bottom_right",
    "logo_scale": 0.2,
    "logo_opacity": 0.85,
}


def _create(client, auth, **overrides) -> dict:
    response = client.post(f"{API}/brand-kits", json={**KIT, **overrides}, headers=auth["headers"])
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------- CRUD --


def test_a_kit_round_trips(client, auth):
    kit = _create(client, auth)
    assert kit["brand_name"] == "Nova Stationery"
    assert kit["accent_color"] == "#39E08B"

    listing = client.get(f"{API}/brand-kits", headers=auth["headers"]).json()
    assert [item["id"] for item in listing] == [kit["id"]]


def test_colours_are_validated_rather_than_stored_as_typed(client, auth):
    response = client.post(
        f"{API}/brand-kits", json={**KIT, "accent_color": "chartreuse"}, headers=auth["headers"]
    )
    assert response.status_code == 422


def test_colours_are_normalised_so_two_spellings_are_one_colour(client, auth):
    kit = _create(client, auth, accent_color="#39e08b")
    assert kit["accent_color"] == "#39E08B"


def test_a_logo_cannot_swallow_the_frame(client, auth):
    # Above a third of the width it stops being a watermark.
    response = client.post(
        f"{API}/brand-kits", json={**KIT, "logo_scale": 0.9}, headers=auth["headers"]
    )
    assert response.status_code == 422


def test_an_invalid_corner_is_refused(client, auth):
    response = client.post(
        f"{API}/brand-kits", json={**KIT, "logo_position": "middle"}, headers=auth["headers"]
    )
    assert response.status_code == 422


def test_a_kit_can_be_edited_and_deleted(client, auth):
    kit = _create(client, auth)
    updated = client.patch(
        f"{API}/brand-kits/{kit['id']}", json={"slogan": "Autrement"}, headers=auth["headers"]
    ).json()
    assert updated["slogan"] == "Autrement"
    assert updated["brand_name"] == "Nova Stationery", "an unrelated field must survive"

    assert client.delete(f"{API}/brand-kits/{kit['id']}", headers=auth["headers"]).status_code == 204
    assert client.get(f"{API}/brand-kits/{kit['id']}", headers=auth["headers"]).status_code == 404


# -------------------------------------------------------------- ownership --


def test_a_stranger_cannot_read_a_kit(client, auth, user_factory):
    kit = _create(client, auth)
    stranger = user_factory()
    assert client.get(f"{API}/brand-kits/{kit['id']}", headers=stranger["headers"]).status_code == 404


def test_a_stranger_cannot_attach_a_kit_to_their_project(client, auth, user_factory):
    kit = _create(client, auth)
    stranger = user_factory()
    response = client.post(
        f"{API}/projects",
        json={"name": "Borrowed", "brand_kit_id": kit["id"]},
        headers=stranger["headers"],
    )
    assert response.status_code == 404


# ------------------------------------------------------- on the project --


def test_a_project_can_take_and_drop_a_kit(client, auth, project):
    kit = _create(client, auth)
    project_id = project["id"]

    attached = client.patch(
        f"{API}/projects/{project_id}", json={"brand_kit_id": kit["id"]}, headers=auth["headers"]
    ).json()
    assert attached["brand_kit_id"] == kit["id"]

    # An explicit null detaches, exactly as it does for a character.
    detached = client.patch(
        f"{API}/projects/{project_id}", json={"brand_kit_id": None}, headers=auth["headers"]
    ).json()
    assert detached["brand_kit_id"] is None


def test_an_unrelated_edit_keeps_the_kit(client, auth, project):
    kit = _create(client, auth)
    project_id = project["id"]
    client.patch(f"{API}/projects/{project_id}", json={"brand_kit_id": kit["id"]}, headers=auth["headers"])

    renamed = client.patch(
        f"{API}/projects/{project_id}", json={"name": "Renamed"}, headers=auth["headers"]
    ).json()
    assert renamed["brand_kit_id"] == kit["id"]


def test_deleting_a_kit_leaves_the_project_working(client, auth, project_with_images):
    kit = _create(client, auth)
    project_id = project_with_images["id"]
    client.patch(f"{API}/projects/{project_id}", json={"brand_kit_id": kit["id"]}, headers=auth["headers"])
    client.delete(f"{API}/brand-kits/{kit['id']}", headers=auth["headers"])

    detail = client.get(f"{API}/projects/{project_id}", headers=auth["headers"])
    assert detail.status_code == 200
    assert detail.json()["brand_kit_id"] is None


# ------------------------------------------------------------ on the plan --


def test_the_kit_is_copied_onto_the_plan(client, auth, project_with_images):
    kit = _create(client, auth)
    project_id = project_with_images["id"]
    client.patch(f"{API}/projects/{project_id}", json={"brand_kit_id": kit["id"]}, headers=auth["headers"])

    plan = client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).json()["plan"]
    assert plan["brand"] is not None
    assert plan["brand"]["brand_name"] == "Nova Stationery"
    assert plan["brand"]["accent_color"] == "#39E08B"
    assert plan["brand"]["logo_position"] == "bottom_right"


def test_a_project_without_a_kit_carries_no_brand(client, auth, project_with_images):
    plan = client.get(
        f"{API}/projects/{project_with_images['id']}/plan", headers=auth["headers"]
    ).json()["plan"]
    assert plan["brand"] is None


def test_the_logo_is_listed_among_the_media_the_render_needs():
    """It has to be delivered to the engine like any other file.

    An AI Motion clip was once left out of this list and the renderer silently
    fell back to the still image; the same omission here would drop the logo.
    """
    plan = validate_plan(
        {
            "scenes": [{"order": 0, "duration": 3, "media_id": "img"}],
            "brand": {"logo_media_id": "logo-1"},
        }
    )
    assert "logo-1" in plan.media_ids()


def test_a_brand_without_a_logo_asks_for_nothing_extra():
    plan = validate_plan(
        {"scenes": [{"order": 0, "duration": 3, "media_id": "img"}], "brand": {"brand_name": "Nova"}}
    )
    assert plan.media_ids() == ["img"]


# ------------------------------------------------------------- rendering --


@pytest.mark.slow
def test_the_logo_reaches_the_video(tmp_path, sample_images):
    """A missing logo must not fail the render, and a present one must be drawn."""
    from PIL import Image

    from app.domain.plan import validate_plan as _validate
    from app.infrastructure.render.base import RenderRequest
    from app.infrastructure.render.engine import FFmpegRenderEngine

    scene = tmp_path / "scene.jpg"
    scene.write_bytes(sample_images(1)[0][1][1])
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (300, 120), (255, 60, 90, 255)).save(logo)

    def plan_for(media_id: str | None):
        return _validate(
            {
                "fps": 24,
                "scenes": [{"order": 0, "media_id": "m", "duration": 1.5, "transition": "none"}],
                "brand": {"logo_media_id": media_id, "logo_scale": 0.25},
            }
        )

    engine = FFmpegRenderEngine()
    sizes = {}
    for label, media_id, paths in (
        ("with", "L", {"m": scene, "L": logo}),
        ("without", None, {"m": scene}),
        ("missing", "L", {"m": scene}),  # the plan names a logo that is not delivered
    ):
        target = tmp_path / f"{label}.mp4"
        engine.render(
            RenderRequest(
                plan=plan_for(media_id),
                media_paths=paths,
                work_dir=tmp_path / f"work-{label}",
                output_path=target,
                poster_path=None,
                cancel_check=lambda: False,
            ),
            on_progress=lambda percent, stage: None,
        )
        assert target.is_file() and target.stat().st_size > 0
        sizes[label] = target.stat().st_size

    # A drawn logo is detail, and detail costs bits.
    assert sizes["with"] > sizes["without"]
    # A logo the plan names but the engine was not given is not a render failure.
    assert sizes["missing"] > 0
