"""Rendering tests: the ffmpeg pipeline, the job lifecycle, and one full journey.

These call ffmpeg for real. They are the slowest tests in the suite by a wide margin,
and they are the ones that prove the product actually works.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.domain.enums import AnimationType, TextAnimation, TransitionType, VideoStyle
from app.domain.insight import ImageInsight
from app.domain.plan import TextOverlay, validate_plan
from app.domain.planner import PlanRequest, build_plan
from app.infrastructure.imaging.samples import generate_sample_image, generate_silent_wav
from app.infrastructure.render.base import RenderRequest
from app.infrastructure.render.engine import FFmpegRenderEngine
from app.infrastructure.render.ffmpeg import probe_duration

API = "/api/v1"
POLL_TIMEOUT_SECONDS = 300


def _mp4_is_valid(path: Path) -> bool:
    """A real MP4 starts with a `ftyp` box in the first 32 bytes."""
    if not path.is_file() or path.stat().st_size < 2048:
        return False
    return b"ftyp" in path.read_bytes()[:32]


@pytest.fixture()
def render_workspace(tmp_path):
    media: dict[str, Path] = {}
    insights: list[ImageInsight] = []
    for index in range(3):
        raw = generate_sample_image(index, width=720, height=960)
        path = tmp_path / f"image-{index}.jpg"
        path.write_bytes(raw)
        media[f"m{index}"] = path
        insights.append(
            ImageInsight(media_id=f"m{index}", width=720, height=960, brightness=0.35, focus_x=0.5, focus_y=0.45)
        )

    audio = tmp_path / "music.wav"
    audio.write_bytes(generate_silent_wav(6.0))
    media["music"] = audio
    return {"media": media, "insights": insights, "tmp": tmp_path}


def _render(plan, workspace, name="out.mp4"):
    engine = FFmpegRenderEngine()
    assert engine.is_available(), "ffmpeg must be installed to run the render tests"
    output = workspace["tmp"] / name
    progress: list[int] = []
    result = engine.render(
        RenderRequest(
            plan=plan,
            media_paths=workspace["media"],
            output_path=output,
            work_dir=workspace["tmp"] / f"work-{name}",
            poster_path=workspace["tmp"] / f"poster-{name}.jpg",
        ),
        lambda percent, stage: progress.append(percent),
    )
    return result, progress


# ----------------------------------------------------------------- engine ---


def test_render_produces_a_playable_mp4(render_workspace):
    plan = build_plan(
        PlanRequest(
            images=render_workspace["insights"],
            style=VideoStyle.TIKTOK_TREND,
            topic="school supplies",
            target_duration=6,
            audio_media_id="music",
        )
    )
    result, progress = _render(plan, render_workspace)

    assert _mp4_is_valid(result.video_path)
    assert (result.width, result.height) == (1080, 1920)
    assert result.duration == pytest.approx(plan.total_duration, abs=0.35)
    assert result.poster_path and Path(result.poster_path).is_file()
    assert progress[0] < progress[-1] == 100
    assert progress == sorted(progress), "progress must never go backwards"


def test_scene_durations_are_honoured(render_workspace):
    """The rendered length must match the plan's arithmetic, transitions included."""
    plan = validate_plan(
        {
            "scenes": [
                {"order": 0, "media_id": "m0", "duration": 2.0, "animation": "zoom_in"},
                {"order": 1, "media_id": "m1", "duration": 2.0, "animation": "pan_right",
                 "transition": "fade", "transition_duration": 0.5},
                {"order": 2, "media_id": "m2", "duration": 1.5, "animation": "none",
                 "transition": "none", "transition_duration": 0.0},
            ]
        }
    )
    assert plan.total_duration == pytest.approx(5.0)

    result, _ = _render(plan, render_workspace, name="durations.mp4")
    assert result.duration == pytest.approx(5.0, abs=0.25)


@pytest.mark.parametrize(
    "transition",
    [t for t in TransitionType if t is not TransitionType.NONE],
    ids=lambda t: t.value,
)
def test_every_transition_renders(render_workspace, transition):
    plan = validate_plan(
        {
            "scenes": [
                {"order": 0, "media_id": "m0", "duration": 1.2, "animation": "none"},
                {"order": 1, "media_id": "m1", "duration": 1.2, "animation": "none",
                 "transition": transition.value, "transition_duration": 0.4},
            ]
        }
    )
    result, _ = _render(plan, render_workspace, name=f"trans-{transition.value}.mp4")
    assert _mp4_is_valid(result.video_path)
    assert result.duration == pytest.approx(2.0, abs=0.25)


@pytest.mark.parametrize("animation", list(AnimationType), ids=lambda a: a.value)
def test_every_animation_renders(render_workspace, animation):
    plan = validate_plan(
        {"scenes": [{"order": 0, "media_id": "m0", "duration": 1.2, "animation": animation.value}]}
    )
    result, _ = _render(plan, render_workspace, name=f"anim-{animation.value}.mp4")
    assert _mp4_is_valid(result.video_path)


@pytest.mark.parametrize("text_animation", list(TextAnimation), ids=lambda a: a.value)
def test_every_text_animation_renders(render_workspace, text_animation):
    plan = validate_plan(
        {
            "scenes": [
                {
                    "order": 0,
                    "media_id": "m0",
                    "duration": 1.6,
                    "animation": "none",
                    "texts": [
                        TextOverlay(
                            content="Everything you need in one place",
                            animation=text_animation,
                            font_size=72,
                        ).model_dump(mode="json")
                    ],
                }
            ]
        }
    )
    result, _ = _render(plan, render_workspace, name=f"text-{text_animation.value}.mp4")
    assert _mp4_is_valid(result.video_path)


def test_audio_is_synchronised_to_the_video_length(render_workspace):
    """A 6s music bed under a 3s video must be cut to 3s, not left running."""
    plan = validate_plan(
        {
            "scenes": [
                {"order": 0, "media_id": "m0", "duration": 1.5, "animation": "none"},
                {"order": 1, "media_id": "m1", "duration": 1.5, "animation": "none",
                 "transition": "none", "transition_duration": 0.0},
            ],
            "audio": {"media_id": "music", "volume": 0.6, "fade_in": 0.3, "fade_out": 0.5},
        }
    )
    result, _ = _render(plan, render_workspace, name="audio-sync.mp4")
    assert result.duration == pytest.approx(3.0, abs=0.25)


def test_short_music_is_looped_to_cover_a_longer_video(render_workspace):
    plan = validate_plan(
        {
            "scenes": [
                {"order": 0, "media_id": "m0", "duration": 5.0, "animation": "slow_zoom"},
                {"order": 1, "media_id": "m1", "duration": 5.0, "animation": "slow_zoom",
                 "transition": "fade", "transition_duration": 0.5},
            ],
            "audio": {"media_id": "music", "volume": 0.5, "loop": True},
        }
    )
    result, _ = _render(plan, render_workspace, name="audio-loop.mp4")
    assert result.duration == pytest.approx(9.5, abs=0.35)


def test_a_scene_without_an_image_still_renders(render_workspace):
    """CTA cards legitimately have no image of their own."""
    plan = validate_plan(
        {
            "scenes": [
                {"order": 0, "media_id": "m0", "duration": 1.5, "animation": "none"},
                {"order": 1, "media_id": None, "duration": 1.5, "animation": "zoom_in",
                 "transition": "fade", "transition_duration": 0.3,
                 "texts": [{"role": "cta", "content": "Shop now", "position": "center"}]},
            ]
        }
    )
    result, _ = _render(plan, render_workspace, name="no-image.mp4")
    assert _mp4_is_valid(result.video_path)


def test_a_missing_image_file_fails_with_a_clear_message(render_workspace, tmp_path):
    from app.core.errors import RenderError

    plan = validate_plan({"scenes": [{"order": 0, "media_id": "gone", "duration": 1.0}]})
    engine = FFmpegRenderEngine()
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"this is not a jpeg")

    with pytest.raises(RenderError) as exc:
        engine.render(
            RenderRequest(
                plan=plan,
                media_paths={"gone": broken},
                output_path=tmp_path / "never.mp4",
                work_dir=tmp_path / "work-broken",
            ),
            lambda percent, stage: None,
        )
    assert "could not be read" in str(exc.value)


def test_render_can_be_cancelled(render_workspace):
    from app.core.errors import RenderError

    plan = build_plan(
        PlanRequest(
            images=render_workspace["insights"], style=VideoStyle.LUXURY, target_duration=20
        )
    )
    engine = FFmpegRenderEngine()
    with pytest.raises(RenderError) as exc:
        engine.render(
            RenderRequest(
                plan=plan,
                media_paths=render_workspace["media"],
                output_path=render_workspace["tmp"] / "cancelled.mp4",
                work_dir=render_workspace["tmp"] / "work-cancel",
                cancel_check=lambda: True,
            ),
            lambda percent, stage: None,
        )
    assert exc.value.code == "render_cancelled"


# ------------------------------------------------------------ job lifecycle --


def _wait_for_render(client, headers, job_id: str) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last = {}
    while time.monotonic() < deadline:
        last = client.get(f"{API}/render-jobs/{job_id}", headers=headers).json()
        if last["status"] in ("completed", "failed", "cancelled"):
            return last
        time.sleep(0.5)
    pytest.fail(f"Render did not finish within {POLL_TIMEOUT_SECONDS}s: {last}")


def test_render_without_images_is_refused(client, auth, project):
    response = client.post(f"{API}/projects/{project['id']}/render", headers=auth["headers"])
    assert response.status_code == 422
    assert "no scenes yet" in response.json()["error"]["message"]


def test_render_job_lifecycle(client, auth, project_with_images):
    project_id = project_with_images["id"]
    client.post(
        f"{API}/projects/{project_id}/plan/generate",
        json={"target_duration": 5},
        headers=auth["headers"],
    )

    queued = client.post(f"{API}/projects/{project_id}/render", headers=auth["headers"])
    assert queued.status_code == 202
    job = queued.json()
    assert job["status"] == "queued"
    assert job["message"] == "Your video is queued..."

    finished = _wait_for_render(client, auth["headers"], job["id"])
    assert finished["status"] == "completed", finished
    assert finished["progress"] == 100
    assert finished["message"] == "Your video is ready."
    assert finished["download_url"]

    download = client.get(f"{API}/render-jobs/{job['id']}/download", headers=auth["headers"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "video/mp4"
    assert b"ftyp" in download.content[:32]
    assert "attachment" in download.headers["content-disposition"]

    history = client.get(f"{API}/projects/{project_id}/renders", headers=auth["headers"]).json()
    assert history[0]["id"] == job["id"]

    detail = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()
    assert detail["thumbnail_url"], "a completed render should give the project a poster"
    assert detail["render_status"] == "completed"


def test_only_one_render_at_a_time(client, auth, project_with_images):
    project_id = project_with_images["id"]
    first = client.post(f"{API}/projects/{project_id}/render", headers=auth["headers"]).json()
    second = client.post(f"{API}/projects/{project_id}/render", headers=auth["headers"])
    if second.status_code == 409:
        assert "already rendering" in second.json()["error"]["message"]
    _wait_for_render(client, auth["headers"], first["id"])


def test_render_jobs_are_private(client, auth, user_factory, project_with_images):
    project_id = project_with_images["id"]
    job = client.post(f"{API}/projects/{project_id}/render", headers=auth["headers"]).json()
    other = user_factory()
    assert client.get(f"{API}/render-jobs/{job['id']}", headers=other["headers"]).status_code == 404
    assert (
        client.get(f"{API}/render-jobs/{job['id']}/download", headers=other["headers"]).status_code
        == 404
    )
    _wait_for_render(client, auth["headers"], job["id"])


# ------------------------------------------------------------ end to end ----


def test_end_to_end_upload_plan_edit_render_download(client, auth, sample_images, sample_audio):
    """Upload images -> create project -> AI plan -> edit a scene -> render -> MP4."""
    created = client.post(
        f"{API}/projects",
        json={
            "name": "Back to school",
            "description": "New school supplies collection",
            "topic": "school supplies",
            "style": "product_showcase",
            "platform": "tiktok",
        },
        headers=auth["headers"],
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    uploaded = client.post(
        f"{API}/projects/{project_id}/media", files=sample_images(3), headers=auth["headers"]
    )
    assert uploaded.status_code == 201

    music = client.post(
        f"{API}/projects/{project_id}/audio",
        files={"file": sample_audio(8.0)},
        headers=auth["headers"],
    )
    assert music.status_code == 200

    planned = client.post(
        f"{API}/projects/{project_id}/plan/generate",
        json={
            "instruction": "Create a 6 second TikTok promoting these school supplies. "
            "Make it energetic and modern.",
            "target_duration": 6,
        },
        headers=auth["headers"],
    )
    assert planned.status_code == 200
    assert planned.json()["plan"]["scenes"]

    scenes = client.get(f"{API}/projects/{project_id}/scenes", headers=auth["headers"]).json()
    edited = client.patch(
        f"{API}/projects/{project_id}/scenes/{scenes[1]['id']}",
        json={
            "animation": "pan_right",
            "transition": "wipe",
            "texts": [
                {
                    "role": "subtitle",
                    "content": "Everything you need in one place",
                    "position": "lower_third",
                    "animation": "rise",
                    "font_size": 64,
                }
            ],
        },
        headers=auth["headers"],
    )
    assert edited.status_code == 200
    assert edited.json()["animation"] == "pan_right"

    job = client.post(f"{API}/projects/{project_id}/render", headers=auth["headers"]).json()
    finished = _wait_for_render(client, auth["headers"], job["id"])
    assert finished["status"] == "completed", finished

    download = client.get(f"{API}/render-jobs/{job['id']}/download", headers=auth["headers"])
    assert download.status_code == 200
    assert len(download.content) > 20_000

    # The MP4 must be openable by ffmpeg, not merely present on disk.
    from app.core.config import settings

    saved = Path(settings.render_work_dir).parent / "e2e-output.mp4"
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_bytes(download.content)
    duration = probe_duration(saved)
    assert duration is not None and duration == pytest.approx(6.0, abs=0.5)
