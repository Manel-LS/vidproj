"""Word-level timings: captured at synthesis, or honestly absent.

Word-by-word subtitles need to know when each word is spoken. The provider
reports that *while streaming the audio* and nowhere else, so the timings are
captured then or never — recovering them later would mean paying to synthesise
the same narration again.

The other half of the module is refusing to pretend: a provider that does not
report timings must produce an empty list, and a script edited after synthesis
must drop the timings it invalidated rather than subtitle the new words with the
old words' clocks.
"""
from __future__ import annotations

import pytest

from app.infrastructure.tts.base import (
    NullVoiceProvider,
    SynthesisResult,
    VoiceProvider,
    VoiceUnavailable,
    WordTiming,
)

API = "/api/v1"


def test_a_timing_knows_when_it_ends():
    word = WordTiming(text="bonjour", start=0.1, duration=0.625)
    assert word.end == 0.725


def test_a_result_without_timings_is_a_valid_result():
    # Not every provider reports them; the type must not force a lie.
    result = SynthesisResult(
        audio=b"x", content_type="audio/mpeg", extension="mp3", voice_id="v", provider="p"
    )
    assert result.words == ()


def test_providers_declare_word_timing_support_rather_than_it_being_guessed():
    # Inferring support from an empty list would confuse "this provider cannot"
    # with "this narration predates the feature".
    assert VoiceProvider.supports_word_timings is False
    assert NullVoiceProvider().supports_word_timings is False

    from app.infrastructure.tts.providers import (
        EdgeVoiceProvider,
        ElevenLabsVoiceProvider,
        OpenAITTSVoiceProvider,
    )

    assert EdgeVoiceProvider().supports_word_timings is True
    assert ElevenLabsVoiceProvider().supports_word_timings is False
    assert OpenAITTSVoiceProvider().supports_word_timings is False


def test_capabilities_publish_word_timing_support(client):
    body = client.get(f"{API}/capabilities").json()
    assert "supports_word_timings" in body["voiceover"]
    # No provider is configured in the test environment, so it must be false —
    # and false because there is no provider, not because we forgot the key.
    assert body["voiceover"]["available"] is False
    assert body["voiceover"]["supports_word_timings"] is False


# ---------------------------------------------------------------- storage ----


class _TimedProvider(VoiceProvider):
    """A provider that reports timings, so the worker path can be exercised."""

    name = "fake-timed"
    display_name = "Fake"
    supports_word_timings = True

    def is_available(self) -> bool:
        return True

    def list_voices(self):
        return []

    def synthesize(self, text: str, *, voice_id: str | None = None) -> SynthesisResult:
        from app.infrastructure.imaging.samples import generate_silent_wav

        return SynthesisResult(
            audio=generate_silent_wav(2.0),
            content_type="audio/wav",
            extension="wav",
            voice_id="fake-voice",
            provider=self.name,
            words=(
                WordTiming("Bonjour", 0.1, 0.625),
                WordTiming("le", 1.0375, 0.1),
                WordTiming("monde", 1.2, 0.4),
            ),
        )


class _UntimedProvider(_TimedProvider):
    name = "fake-untimed"
    supports_word_timings = False

    def synthesize(self, text: str, *, voice_id: str | None = None) -> SynthesisResult:
        result = super().synthesize(text, voice_id=voice_id)
        return SynthesisResult(
            audio=result.audio,
            content_type=result.content_type,
            extension=result.extension,
            voice_id=result.voice_id,
            provider=self.name,
        )


@pytest.fixture()
def voiced_project(client, auth, project_with_images, monkeypatch):
    """Give the project a script, then let a fake provider synthesise it."""

    def make(provider: VoiceProvider) -> dict:
        from app.infrastructure.tts import factory
        from app.services import voiceover_worker

        monkeypatch.setattr(factory, "get_voice_provider", lambda: provider)
        monkeypatch.setattr(voiceover_worker, "get_voice_provider", lambda: provider)

        project_id = project_with_images["id"]
        client.patch(
            f"{API}/projects/{project_id}/voiceover",
            json={"script": "Bonjour le monde", "enabled": True},
            headers=auth["headers"],
        )
        voiceover_worker.execute_voiceover_job(project_id, auth["id"])
        return client.get(f"{API}/projects/{project_id}/voiceover", headers=auth["headers"]).json()

    return make


def test_timings_are_stored_and_returned(voiced_project):
    voice = voiced_project(_TimedProvider())
    assert voice["status"] == "ready"
    assert voice["has_word_timings"] is True
    assert [w["text"] for w in voice["word_timings"]] == ["Bonjour", "le", "monde"]
    assert voice["word_timings"][0]["start"] == 0.1


def test_a_provider_without_timings_stores_an_empty_list(voiced_project):
    voice = voiced_project(_UntimedProvider())
    assert voice["status"] == "ready", "no timings must not fail the synthesis"
    assert voice["word_timings"] == []
    assert voice["has_word_timings"] is False


def test_editing_the_script_drops_the_timings_it_invalidated(
    client, auth, project_with_images, voiced_project
):
    project_id = project_with_images["id"]
    assert voiced_project(_TimedProvider())["has_word_timings"] is True

    edited = client.patch(
        f"{API}/projects/{project_id}/voiceover",
        json={"script": "Something else entirely, much longer than before"},
        headers=auth["headers"],
    ).json()

    # The audio is kept — the user may still want to render with it — but it no
    # longer matches the script, so it stops claiming to be ready.
    assert edited["status"] == "draft"
    assert edited["word_timings"] == []
    assert edited["media"] is not None


def test_an_unrelated_voiceover_edit_keeps_the_timings(
    client, auth, project_with_images, voiced_project
):
    project_id = project_with_images["id"]
    voiced_project(_TimedProvider())

    same = client.patch(
        f"{API}/projects/{project_id}/voiceover",
        json={"volume": 0.8},
        headers=auth["headers"],
    ).json()
    assert same["status"] == "ready"
    assert same["has_word_timings"] is True
