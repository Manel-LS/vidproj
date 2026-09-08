"""AI Motion: a generated clip must actually reach the renderer.

The scene's generated clip is resolved by id from the paths the worker hands the
engine. If the plan does not list that id, the lookup misses and the engine falls
back to the still image — silently, with no error and no log. These tests pin the
contract that keeps the generated motion in the output.
"""
from __future__ import annotations

import subprocess

import pytest

from app.domain.plan import validate_plan
from app.infrastructure.render.base import RenderRequest
from app.infrastructure.render.engine import FFmpegRenderEngine
from app.infrastructure.render.ffmpeg import ffmpeg_path, probe_duration
from app.infrastructure.imaging.samples import generate_sample_image


def _plan_with_clip(clip_media_id: str | None = "clip-1"):
    return validate_plan(
        {
            "scenes": [
                {
                    "order": 0,
                    "media_id": "still-1",
                    "duration": 1.5,
                    "animation": "none",
                    "ai_motion": {
                        "enabled": True,
                        "prompt": "subtle motion",
                        "generated_media_id": clip_media_id,
                        "provider": "stub",
                    },
                }
            ]
        }
    )


def test_generated_clip_is_listed_among_required_media():
    plan = _plan_with_clip()
    assert "clip-1" in plan.media_ids(), (
        "the AI Motion clip must be requested, or the renderer cannot find it"
    )
    assert "still-1" in plan.media_ids()


def test_a_scene_without_a_generated_clip_asks_for_nothing_extra():
    plan = _plan_with_clip(clip_media_id=None)
    assert plan.media_ids() == ["still-1"]


def test_media_ids_covers_audio_and_voiceover():
    plan = validate_plan(
        {
            "scenes": [{"order": 0, "media_id": "a", "duration": 1.0}],
            "audio": {"media_id": "music-1"},
            "voiceover": {"enabled": True, "media_id": "voice-1", "script": "hello"},
        }
    )
    assert set(plan.media_ids()) == {"a", "music-1", "voice-1"}


@pytest.fixture()
def moving_clip(tmp_path):
    """A short clip whose content changes over time, so we can prove it was used."""
    frames = tmp_path / "frames"
    frames.mkdir()
    from PIL import Image

    for index in range(30):
        # A frame that is almost entirely one colour, sweeping from black to red.
        Image.new("RGB", (540, 960), (index * 8, 0, 0)).save(frames / f"{index:04d}.jpg", quality=90)

    clip = tmp_path / "clip.mp4"
    subprocess.run(
        [
            ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
            "-framerate", "30", "-i", str(frames / "%04d.jpg"),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p", str(clip),
        ],
        check=True,
    )
    return clip


def test_render_uses_the_clip_instead_of_the_still(tmp_path, moving_clip):
    """The rendered frames must come from the clip, not from the still image."""
    still = tmp_path / "still.jpg"
    still.write_bytes(generate_sample_image(0, width=540, height=960))

    output = tmp_path / "out.mp4"
    FFmpegRenderEngine().render(
        RenderRequest(
            plan=_plan_with_clip(),
            media_paths={"still-1": still, "clip-1": moving_clip},
            output_path=output,
            work_dir=tmp_path / "work",
        ),
        lambda percent, stage: None,
    )

    assert output.is_file()
    assert probe_duration(output) == pytest.approx(1.5, abs=0.25)

    # The clip is a red ramp; the sample image is not. Sampling the output tells us
    # which one was actually encoded.
    probe = tmp_path / "probe.png"
    subprocess.run(
        [
            ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(output), "-vf", r"select=eq(n\,20),scale=8:8", "-frames:v", "1", str(probe),
        ],
        check=True,
    )
    from PIL import Image

    with Image.open(probe) as image:
        pixels = list(image.convert("RGB").getdata())
    red = sum(p[0] for p in pixels) / len(pixels)
    green = sum(p[1] for p in pixels) / len(pixels)
    blue = sum(p[2] for p in pixels) / len(pixels)

    assert red > green + 30 and red > blue + 30, (
        f"the frame is not the red clip (r={red:.0f} g={green:.0f} b={blue:.0f}); "
        "the renderer fell back to the still image"
    )


# ------------------------------------------------- rendre sans fournisseur ---


def _ai_motion_project(client, auth, sample_images, *, with_clip: bool):
    """A project in AI Motion mode, optionally with its clip already generated."""
    project = client.post(
        "/api/v1/projects",
        json={"name": "AI Motion", "mode": "ai_motion", "target_duration": 3},
        headers=auth["headers"],
    ).json()
    client.post(
        f"/api/v1/projects/{project['id']}/media",
        files=sample_images(1),
        headers=auth["headers"],
    )
    plan = client.get(f"/api/v1/projects/{project['id']}/plan", headers=auth["headers"]).json()["plan"]
    plan["mode"] = "ai_motion"
    plan["scenes"][0]["ai_motion"] = {
        "enabled": True,
        "prompt": "",
        # A clip id that exists as far as the plan is concerned; the point of these
        # tests is the availability check, not the file.
        "generated_media_id": plan["scenes"][0]["media_id"] if with_clip else None,
        "provider": "local",
    }
    applied = client.put(
        f"/api/v1/projects/{project['id']}/plan", json={"plan": plan}, headers=auth["headers"]
    )
    assert applied.status_code == 200, applied.text
    return project["id"]


def test_render_is_refused_when_a_clip_is_still_missing(client, auth, sample_images):
    """No provider and no clip yet: the render must be refused, and say which scene."""
    project_id = _ai_motion_project(client, auth, sample_images, with_clip=False)
    response = client.post(f"/api/v1/projects/{project_id}/render", headers=auth["headers"])

    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "no video generation provider" in message
    assert "scene 1" in message, "the message should name the scene that needs a clip"


def test_render_is_allowed_once_every_clip_exists(client, auth, sample_images):
    """Clips already generated: the project stays renderable with no provider.

    Requiring the provider here would strand finished work the moment an API key
    expires or the provider is switched off.
    """
    from app.infrastructure.i2v.factory import get_i2v_provider

    assert not get_i2v_provider().is_available(), "this test assumes no provider is configured"

    project_id = _ai_motion_project(client, auth, sample_images, with_clip=True)
    response = client.post(f"/api/v1/projects/{project_id}/render", headers=auth["headers"])

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "queued"
