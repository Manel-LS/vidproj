"""Lip sync: the provider chain, and the slicing that makes it correct.

The test that carries this module is `test_each_scene_gets_its_own_slice...`.
The voice-over is one file for the whole video while each scene is a separate
clip, so a worker that forwarded the whole narration would lip-sync every scene
to words spoken at t=0 — and nothing in the output would say so. That is the
failure this suite exists to prevent.
"""
from __future__ import annotations

import subprocess

import pytest

from app.domain.enums import MediaKind
from app.infrastructure.lipsync import factory as lipsync_factory
from app.infrastructure.lipsync.base import (
    GeneratedLipSync,
    LipSyncProvider,
    LipSyncRequest,
    LipSyncState,
    LipSyncStatus,
    LipSyncUnavailable,
    NullLipSyncProvider,
)
from app.infrastructure.render.ffmpeg import ffmpeg_path

API = "/api/v1"


class StubLipSync(LipSyncProvider):
    name = "stub"
    display_name = "Stub lip sync"

    def __init__(self, *, fail: str = "", state_fails: bool = False, never_finishes: bool = False,
                 needs_urls: bool = False, max_clip_seconds: float = 60.0):
        self.fail = fail
        self.state_fails = state_fails
        self.never_finishes = never_finishes
        self.needs_public_urls = needs_urls
        self.max_clip_seconds = max_clip_seconds
        self.requests: list[LipSyncRequest] = []

    def is_available(self) -> bool:
        return True

    def generate_lipsync(self, request: LipSyncRequest) -> str:
        if self.fail:
            raise LipSyncUnavailable(self.fail)
        self.requests.append(request)
        return "job-1"

    def get_status(self, job_id: str) -> LipSyncStatus:
        if self.state_fails:
            return LipSyncStatus(job_id=job_id, state=LipSyncState.FAILED, error="Face not found.")
        if self.never_finishes:
            return LipSyncStatus(job_id=job_id, state=LipSyncState.PROCESSING)
        return LipSyncStatus(job_id=job_id, state=LipSyncState.COMPLETED, result_url="x")

    def get_result(self, job_id: str) -> GeneratedLipSync:
        return GeneratedLipSync(
            data=b"\x00\x00\x00\x18ftypmp42spoken-clip",
            content_type="video/mp4",
            extension="mp4",
            provider=self.name,
        )


@pytest.fixture()
def use_lipsync(monkeypatch):
    original = lipsync_factory.get_lipsync_provider

    def install(provider: LipSyncProvider) -> LipSyncProvider:
        original.cache_clear()
        monkeypatch.setattr(lipsync_factory, "get_lipsync_provider", lambda: provider)
        import app.api.v1.routes.ai as ai_routes
        import app.services.lipsync_worker as worker

        monkeypatch.setattr(worker, "get_lipsync_provider", lambda: provider)
        monkeypatch.setattr(ai_routes, "get_lipsync_provider", lambda: provider)
        return provider

    yield install
    original.cache_clear()


@pytest.fixture()
def fast_polling(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "lipsync_poll_interval_seconds", 0.0)
    monkeypatch.setattr(settings, "lipsync_timeout_seconds", 3.0)


@pytest.fixture()
def tone_wav():
    """A real audio file with a *changing* signal, so a slice can be told apart.

    Silence would make every slice identical and the slicing test vacuous.
    """

    def make(seconds: float = 30.0):
        import tempfile
        from pathlib import Path

        target = Path(tempfile.mkdtemp()) / "sweep.wav"
        subprocess.run(
            [
                ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"sine=frequency=200:duration={seconds}",
                "-af", f"volume='0.1+0.9*t/{seconds}':eval=frame",
                str(target),
            ],
            check=True,
        )
        return target.read_bytes()

    return make


def _prepare(client, auth, project_with_images, tone_wav, *, scenes: int = 3):
    """A project with a voice-over and one silent motion clip per scene."""
    from app.db.base import session_scope
    from app.domain.enums import VoiceOverStatus
    from app.models import Project, Scene
    from app.services import media_service

    project_id = project_with_images["id"]
    session = session_scope()
    try:
        project = session.get(Project, project_id)
        voice_media = media_service.add_audio(
            session,
            project,
            media_service.UploadPayload(
                filename="voice.wav", content_type="audio/wav", data=tone_wav(30.0)
            ),
            source="voiceover",
        )
        project.voice_over.media_id = voice_media.id
        project.voice_over.enabled = True
        project.voice_over.status = VoiceOverStatus.READY.value
        project.voice_over.script = "Some narration."

        for scene in list(project.scenes)[:scenes]:
            clip = media_service.store_generated_file(
                session,
                project,
                data=b"\x00\x00\x00\x18ftypmp42silent",
                filename=f"clip-{scene.id[:6]}.mp4",
                content_type="video/mp4",
                kind=MediaKind.VIDEO,
                source="ai_motion",
            )
            scene.ai_motion = {
                "enabled": True,
                "prompt": "",
                "generated_media_id": clip.id,
                "provider": "stub",
            }
            scene.duration = 4.0
            scene.transition_duration = 0.0 if scene.order_index == 0 else 0.5
        session.commit()
    finally:
        session.close()
    return project_id


def _run(project_id: str, user_id: str, scene_id: str) -> str:
    from app.services.lipsync_worker import execute_lipsync_job

    return execute_lipsync_job(project_id, user_id, scene_id)


def _scenes(client, auth, project_id: str) -> list[dict]:
    return client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()["scenes"]


# ---------------------------------------------------------------- unconfigured --


def test_the_null_provider_reports_unavailable_and_explains_the_consequence():
    provider = NullLipSyncProvider()
    assert provider.is_available() is False
    with pytest.raises(LipSyncUnavailable) as exc:
        provider.get_status("x")
    message = str(exc.value)
    assert "no lip-sync provider is configured" in message
    # It has to say what still works, or the user assumes rendering is broken too.
    assert "without matching lips" in message


def test_capabilities_reports_lipsync(client):
    body = client.get(f"{API}/capabilities").json()
    assert "lipsync" in body
    assert body["lipsync"]["available"] is False
    assert body["lipsync"]["message"]


def test_the_route_refuses_when_unconfigured(client, auth, project_with_images, tone_wav):
    project_id = _prepare(client, auth, project_with_images, tone_wav)
    scene = _scenes(client, auth, project_id)[0]
    response = client.post(
        f"{API}/projects/{project_id}/scenes/{scene['id']}/lipsync", headers=auth["headers"]
    )
    assert response.status_code == 503, response.text


# ----------------------------------------------------------------- the slicing --


def test_each_scene_gets_its_own_slice_of_the_narration(
    client, auth, project_with_images, tone_wav, use_lipsync, fast_polling
):
    """The point of the whole worker.

    Scene 2 starts 3.5s in (4.0s long, 0.5s transition overlap), so its audio must
    differ from scene 1's. The narration ramps in volume, so two different windows
    produce measurably different loudness — identical bytes would mean both scenes
    were handed the same audio.
    """
    provider = use_lipsync(StubLipSync())
    project_id = _prepare(client, auth, project_with_images, tone_wav)
    scenes = _scenes(client, auth, project_id)

    for scene in scenes[:2]:
        assert _run(project_id, auth["id"], scene["id"]) == "completed"

    assert len(provider.requests) == 2
    first, second = provider.requests[0].audio, provider.requests[1].audio
    assert first and second
    assert first != second, "both scenes were handed the same audio"

    # And each slice is about one scene long, not the whole 30s narration.
    import tempfile
    from pathlib import Path

    from app.infrastructure.render.ffmpeg import probe_duration

    for payload in (first, second):
        path = Path(tempfile.mkdtemp()) / "slice.mp3"
        path.write_bytes(payload)
        duration = probe_duration(path)
        assert duration is not None
        assert 3.0 < duration < 5.5, f"slice is {duration}s, expected about one scene"


def test_the_speaking_clip_replaces_the_silent_one_without_losing_it(
    client, auth, project_with_images, tone_wav, use_lipsync, fast_polling
):
    use_lipsync(StubLipSync())
    project_id = _prepare(client, auth, project_with_images, tone_wav)
    scene = _scenes(client, auth, project_id)[0]
    silent_id = scene["ai_motion"]["generated_media_id"]

    assert _run(project_id, auth["id"], scene["id"]) == "completed"

    updated = _scenes(client, auth, project_id)[0]["ai_motion"]
    assert updated["generated_media_id"] != silent_id, "the renderer must use the speaking clip"
    assert updated["silent_media_id"] == silent_id, "the silent clip must be kept"
    assert not updated.get("error")

    from app.db.base import session_scope
    from app.models import Media

    session = session_scope()
    try:
        assert session.get(Media, silent_id) is not None, "the silent clip must not be deleted"
        spoken = session.get(Media, updated["generated_media_id"])
        assert spoken is not None and spoken.source == "lipsync"
    finally:
        session.close()


def test_running_twice_syncs_the_silent_clip_again_not_the_spoken_one(
    client, auth, project_with_images, tone_wav, use_lipsync, fast_polling
):
    """Otherwise a second pass syncs a mouth that already moves to those words."""
    provider = use_lipsync(StubLipSync())
    project_id = _prepare(client, auth, project_with_images, tone_wav)
    scene = _scenes(client, auth, project_id)[0]
    silent_id = scene["ai_motion"]["generated_media_id"]

    assert _run(project_id, auth["id"], scene["id"]) == "completed"
    assert _run(project_id, auth["id"], scene["id"]) == "completed"

    assert provider.requests[0].video == provider.requests[1].video, "the source must be the silent clip"
    assert _scenes(client, auth, project_id)[0]["ai_motion"]["silent_media_id"] == silent_id


# -------------------------------------------------------------------- failures --


def test_a_missing_voice_over_is_refused_with_a_useful_message(
    client, auth, project_with_images, tone_wav, use_lipsync, fast_polling
):
    use_lipsync(StubLipSync())
    project_id = _prepare(client, auth, project_with_images, tone_wav)

    from app.db.base import session_scope
    from app.models import Project

    session = session_scope()
    try:
        session.get(Project, project_id).voice_over.media_id = None
        session.commit()
    finally:
        session.close()

    scene = _scenes(client, auth, project_id)[0]
    assert _run(project_id, auth["id"], scene["id"]) == "failed"
    assert "voice-over" in _scenes(client, auth, project_id)[0]["ai_motion"]["error"]


def test_a_missing_clip_is_refused(client, auth, project_with_images, tone_wav, use_lipsync):
    use_lipsync(StubLipSync())
    project_id = _prepare(client, auth, project_with_images, tone_wav, scenes=0)
    scene = _scenes(client, auth, project_id)[0]
    assert _run(project_id, auth["id"], scene["id"]) == "failed"
    assert "motion clip" in _scenes(client, auth, project_id)[0]["ai_motion"]["error"]


def test_a_provider_failure_is_reported_and_keeps_the_silent_clip(
    client, auth, project_with_images, tone_wav, use_lipsync, fast_polling
):
    use_lipsync(StubLipSync(state_fails=True))
    project_id = _prepare(client, auth, project_with_images, tone_wav)
    scene = _scenes(client, auth, project_id)[0]
    silent_id = scene["ai_motion"]["generated_media_id"]

    assert _run(project_id, auth["id"], scene["id"]) == "failed"
    spec = _scenes(client, auth, project_id)[0]["ai_motion"]
    assert "Face not found." in spec["error"]
    assert spec["generated_media_id"] == silent_id, "the render must still work"


def test_a_job_that_never_finishes_times_out(
    client, auth, project_with_images, tone_wav, use_lipsync, fast_polling
):
    use_lipsync(StubLipSync(never_finishes=True))
    project_id = _prepare(client, auth, project_with_images, tone_wav)
    scene = _scenes(client, auth, project_id)[0]

    assert _run(project_id, auth["id"], scene["id"]) == "failed"
    assert "timed out" in _scenes(client, auth, project_id)[0]["ai_motion"]["error"].lower()


def test_a_url_only_provider_says_so_instead_of_failing_obscurely(
    client, auth, project_with_images, tone_wav, use_lipsync, fast_polling
):
    """Local storage serves relative URLs, which a third party cannot fetch."""
    use_lipsync(StubLipSync(needs_urls=True))
    project_id = _prepare(client, auth, project_with_images, tone_wav)
    scene = _scenes(client, auth, project_id)[0]

    assert _run(project_id, auth["id"], scene["id"]) == "failed"
    error = _scenes(client, auth, project_id)[0]["ai_motion"]["error"]
    assert "s3" in error.lower(), error


def test_a_scene_longer_than_the_provider_allows_is_refused_up_front(
    client, auth, project_with_images, tone_wav, use_lipsync, fast_polling
):
    """Refused before submission, so the user is not billed for a doomed job."""
    provider = use_lipsync(StubLipSync(max_clip_seconds=2.0))
    project_id = _prepare(client, auth, project_with_images, tone_wav)
    scene = _scenes(client, auth, project_id)[0]

    assert _run(project_id, auth["id"], scene["id"]) == "failed"
    assert provider.requests == [], "nothing should have been submitted"
    assert "up to 2s" in _scenes(client, auth, project_id)[0]["ai_motion"]["error"]


def test_a_failed_lipsync_leaves_the_project_readable(
    client, auth, project_with_images, tone_wav, use_lipsync, fast_polling
):
    use_lipsync(StubLipSync(state_fails=True))
    project_id = _prepare(client, auth, project_with_images, tone_wav)
    _run(project_id, auth["id"], _scenes(client, auth, project_id)[0]["id"])

    assert client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).status_code == 200
    assert (
        client.get(f"{API}/projects/{project_id}/plan", headers=auth["headers"]).status_code == 200
    )
