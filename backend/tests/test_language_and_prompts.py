"""Project language, and the prompt engine that consumes it.

Two claims are worth testing here and the rest is plumbing:

  * the language reaches the three places it changes behaviour — the planner's
    instruction, the default voice, and subtitle direction;
  * `capabilities` tells the truth per language. Reporting Tunisian derja as
    supported because the provider happens to have some Arabic voice is the kind
    of lie the user only discovers on hearing a Gulf accent.
"""
from __future__ import annotations

import pytest

from app.domain.enums import Language, VideoFormat, VideoStyle
from app.domain.language import get_profile, is_rtl, language_support, match_voice
from app.infrastructure.tts.base import Voice
from app.services import prompt_engine as pe

API = "/api/v1"


# ---------------------------------------------------------------- the profile --


def test_derja_is_not_collapsed_into_standard_arabic():
    """Different register, different voice tags. Merging them ruins the format."""
    derja = get_profile(Language.TUNISIAN)
    msa = get_profile(Language.ARABIC)

    assert derja.code != msa.code
    assert derja.prompt_instruction != msa.prompt_instruction
    assert "Modern Standard" in derja.prompt_instruction, "the model must be told NOT to use MSA"
    assert derja.voice_prefixes[0] == "ar-TN"
    assert msa.voice_prefixes[0] != "ar-TN"


def test_arabic_languages_are_right_to_left_and_others_are_not():
    assert is_rtl(Language.TUNISIAN) and is_rtl(Language.ARABIC)
    assert not is_rtl(Language.FRENCH) and not is_rtl(Language.ENGLISH)


def test_an_unknown_language_falls_back_instead_of_raising():
    assert get_profile("kl").code is Language.ENGLISH


# ----------------------------------------------------------------- the voices --


def _voices(*ids: str) -> list[Voice]:
    return [Voice(id=i, name=i) for i in ids]


def test_an_exact_voice_is_preferred_over_a_near_one():
    voice, exact = match_voice(_voices("ar-EG-Salma", "ar-TN-Hedi", "en-US-Ana"), Language.TUNISIAN)
    assert voice.id == "ar-TN-Hedi"
    assert exact is True


def test_a_fallback_accent_is_returned_but_flagged_as_not_exact():
    """Silently substituting an accent is the failure this flag exists to prevent."""
    voice, exact = match_voice(_voices("ar-EG-Salma", "en-US-Ana"), Language.TUNISIAN)
    assert voice.id == "ar-EG-Salma"
    assert exact is False


def test_no_arabic_at_all_means_unsupported_not_an_english_voice():
    voice, exact = match_voice(_voices("en-US-Ana", "fr-FR-Denise"), Language.TUNISIAN)
    assert voice is None and exact is False


def test_the_capability_report_is_honest_per_language():
    report = {row["code"]: row for row in language_support(_voices("ar-EG-Salma", "en-US-Ana"))}

    assert report["en"]["supported"] and report["en"]["exact"]
    assert report["ar"]["supported"] and report["ar"]["exact"]
    # Derja: reachable only through an Egyptian voice, and the report says so.
    assert report["tn"]["supported"] is True
    assert report["tn"]["exact"] is False
    assert "ar-EG-Salma" in report["tn"]["note"]
    # French: nothing at all, and no pretending otherwise.
    assert report["fr"]["supported"] is False


def test_capabilities_exposes_the_language_report(client):
    body = client.get(f"{API}/capabilities").json()
    assert "languages" in body["voiceover"]
    codes = {row["code"] for row in body["voiceover"]["languages"]}
    assert codes == {"tn", "ar", "fr", "en"}


# ---------------------------------------------------------------- the project --


def test_a_project_keeps_its_language_and_reports_direction(client, auth):
    response = client.post(
        f"{API}/projects",
        json={"name": "Derja story", "topic": "wedding", "language": "tn", "target_duration": 20},
        headers=auth["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["language"] == "tn"
    assert body["rtl"] is True, "the editor needs this to lay subtitles out"

    updated = client.patch(
        f"{API}/projects/{body['id']}", json={"language": "fr"}, headers=auth["headers"]
    )
    assert updated.status_code == 200
    assert updated.json()["language"] == "fr"
    assert updated.json()["rtl"] is False


def test_the_default_language_is_english(client, auth):
    body = client.post(
        f"{API}/projects", json={"name": "Plain", "target_duration": 10}, headers=auth["headers"]
    ).json()
    assert body["language"] == "en"
    assert body["rtl"] is False


# ----------------------------------------------------------- the prompt engine --


def test_prompts_are_deterministic():
    """Regenerating a scene has to reproduce the shot, not invent a new one."""
    shot = pe.ShotBrief(framing="Close-up", action="facing camera", environment="a home")
    first = pe.image_prompt(shot=shot, character_description="a toddler")
    second = pe.image_prompt(shot=shot, character_description="a toddler")
    assert first == second


def test_the_image_prompt_leads_with_the_subject_and_ends_with_the_technicals():
    prompt = pe.image_prompt(
        shot=pe.ShotBrief(framing="Close-up", action="frowning", environment="a home"),
        character_description="a toddler in a red jebba",
    )
    assert prompt.startswith("Close-up of the same a toddler in a red jebba")
    for clause in pe.IMAGE_TECHNICAL:
        assert clause in prompt
    assert prompt.endswith("9:16 vertical")


def test_framing_and_subject_read_as_one_phrase():
    """"Close-up, of the same toddler" reads as two fragments, not a shot."""
    prompt = pe.image_prompt(
        shot=pe.ShotBrief(framing="Medium shot"), character_description="a toddler"
    )
    assert "Medium shot of the same a toddler" in prompt
    assert ", of the same" not in prompt


def test_empty_fields_never_leave_stray_punctuation():
    prompt = pe.image_prompt(shot=pe.ShotBrief(framing="Close-up"))
    assert ", ," not in prompt
    assert not prompt.endswith(",")


def test_the_aspect_clause_follows_the_format():
    assert "9:16 vertical" in pe.image_prompt(shot=pe.ShotBrief(), format=VideoFormat.PORTRAIT_9_16)
    assert "1:1 square" in pe.image_prompt(shot=pe.ShotBrief(), format="1:1")
    assert "16:9 horizontal" in pe.image_prompt(shot=pe.ShotBrief(), format="16:9")


def test_the_video_prompt_names_each_moving_part():
    """"Move naturally" yields a frozen frame or a drifting face; naming works."""
    prompt = pe.video_prompt(
        motion=pe.MotionBrief(
            face="eyebrows lift",
            head="small tilt",
            hands="one hand waves",
            body="shoulders bounce",
            background="guests clap",
        ),
        duration_seconds=5,
    )
    for fragment in ("eyebrows lift", "small tilt", "one hand waves", "shoulders bounce"):
        assert fragment in prompt
    assert "in the background, guests clap" in prompt
    assert "no morphing" in prompt, "without it, i2v models melt faces between keyframes"
    assert "5 seconds" in prompt


def test_a_speaking_scene_gets_mouth_movement_even_when_unspecified():
    speaking = pe.video_prompt(motion=pe.MotionBrief(face="a blink"), duration_seconds=4)
    silent = pe.video_prompt(
        motion=pe.MotionBrief(face="a blink"), duration_seconds=4, speaking=False
    )
    assert "lips move" in speaking
    assert "lips move" not in silent


def test_the_story_prompt_expresses_length_in_words_not_only_seconds():
    """A model told "30 seconds" cannot count them and overshoots by half again."""
    prompt = pe.story_prompt(
        idea="A toddler explains weddings",
        language=Language.TUNISIAN,
        duration_seconds=30,
        style=VideoStyle.STORYTELLING,
    )
    assert "spoken words" in prompt
    assert "69 spoken words" in prompt  # 30 * 2.3
    assert "Tunisian Arabic (derja)" in prompt
    assert "Modern Standard" in prompt, "the model must be told what not to write"
    assert "hook" in prompt.lower()


def test_the_story_prompt_speaks_as_the_character_when_there_is_one():
    with_character = pe.story_prompt(
        idea="x", language=Language.ENGLISH, duration_seconds=10,
        style=VideoStyle.STORYTELLING, character_description="a 2-year-old boy",
    )
    assert "a 2-year-old boy" in with_character
    assert "not as a narrator" in with_character


@pytest.mark.parametrize("language", list(Language))
def test_every_language_produces_a_usable_voice_direction(language):
    prompt = pe.voice_prompt(language=language)
    assert get_profile(language).label in prompt
    assert "no announcer tone" in prompt


# -------------------------------------------------- the built-in planner's copy --


def test_the_builtin_planner_writes_in_the_project_language(client, auth, sample_images):
    """The heuristic planner runs whenever no LLM is configured — the default state.

    It used to write English regardless, so a French project came back with
    "Built to last" over its images: structurally right, unusable as it stood.
    """
    from app.infrastructure.imaging.samples import generate_sample_image  # noqa: F401

    seen: dict[str, str] = {}
    for language in ("fr", "ar", "tn", "en"):
        project = client.post(
            f"{API}/projects",
            json={
                "name": f"Copy {language}",
                "topic": "cartables",
                "language": language,
                "style": "product_showcase",
                "target_duration": 12,
            },
            headers=auth["headers"],
        ).json()
        client.post(
            f"{API}/projects/{project['id']}/media",
            files=sample_images(3),
            headers=auth["headers"],
        )
        body = client.post(
            f"{API}/projects/{project['id']}/plan/generate",
            json={"target_duration": 12},
            headers=auth["headers"],
        ).json()
        assert body["ai_used"] is False, "this test is about the heuristic path"
        plan = body["plan"]
        seen[language] = " ".join(
            [plan["hook"], plan["cta"]]
            + [t["content"] for scene in plan["scenes"] for t in scene["texts"]]
        )

    assert "Fait pour durer" in seen["fr"] or "Découvrez" in seen["fr"], seen["fr"]
    assert "Built to last" not in seen["fr"], "French project must not get English copy"

    # Arabic and derja must come back in Arabic script, not transliterated.
    assert any("؀" <= ch <= "ۿ" for ch in seen["ar"]), seen["ar"]
    assert any("؀" <= ch <= "ۿ" for ch in seen["tn"]), seen["tn"]
    assert seen["ar"] != seen["tn"], "derja and MSA must not produce identical copy"

    # English keeps the richer per-style tables it always had.
    assert "Built to last" in seen["en"] or "up close" in seen["en"], seen["en"]


def test_hashtags_follow_the_language_too(client, auth, sample_images):
    project = client.post(
        f"{API}/projects",
        json={"name": "Tags", "topic": "cartables", "language": "fr", "target_duration": 10},
        headers=auth["headers"],
    ).json()
    client.post(
        f"{API}/projects/{project['id']}/media", files=sample_images(2), headers=auth["headers"]
    )
    plan = client.post(
        f"{API}/projects/{project['id']}/plan/generate",
        json={"target_duration": 10},
        headers=auth["headers"],
    ).json()["plan"]
    assert any(tag in ("produit", "nouveaute", "boutique") for tag in plan["hashtags"]), plan["hashtags"]


def test_arabic_hashtags_survive_validation():
    """The ASCII-only class reduced #قصص_الأنبياء to "_".

    Every Arabic project in the database had lost its hashtags, and nothing
    reported it — the plan validated, it just came back emptied.
    """
    from app.domain.plan import VideoPlan

    plan = VideoPlan.model_validate(
        {
            "scenes": [{"order": 0, "media_id": "x", "duration": 2.0}],
            "hashtags": ["قصص_الأنبياء", "يونس", "#تونس", "fête", "bad!!chars"],
        }
    )
    assert "قصص_الأنبياء" in plan.hashtags
    assert "يونس" in plan.hashtags
    assert "تونس" in plan.hashtags, "the leading # must be stripped, not the word"
    assert "fête" in plan.hashtags, "accented Latin is not ASCII either"
    assert "badchars" in plan.hashtags, "punctuation must still go"


def test_the_cta_follows_the_project_language(client, auth):
    """A project born with an English CTA kept it forever: `request.cta` was then
    non-empty, so the planner's language table was never consulted."""
    project = client.post(
        f"{API}/projects",
        json={"name": "CTA", "topic": "x", "language": "fr", "style": "product_showcase",
              "target_duration": 10},
        headers=auth["headers"],
    ).json()
    assert project["cta"] == "Découvrir la collection", project["cta"]

    switched = client.patch(
        f"{API}/projects/{project['id']}", json={"language": "en"}, headers=auth["headers"]
    ).json()
    assert switched["cta"] != "Découvrir la collection", "an untouched CTA follows the language"


def test_a_cta_the_user_wrote_is_never_retranslated(client, auth):
    project = client.post(
        f"{API}/projects",
        json={"name": "CTA", "topic": "x", "language": "fr", "target_duration": 10},
        headers=auth["headers"],
    ).json()
    mine = "Passe à la boutique !"
    client.patch(f"{API}/projects/{project['id']}", json={"cta": mine}, headers=auth["headers"])

    switched = client.patch(
        f"{API}/projects/{project['id']}", json={"language": "en"}, headers=auth["headers"]
    ).json()
    assert switched["cta"] == mine, "the user's own words are theirs"
