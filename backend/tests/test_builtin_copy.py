"""The built-in planner's writing, which is what most installs actually get.

An LLM key is optional and most people do not have one, so the copy this planner
produces is the product for them. It had two faults that a screenshot of one
scene would never show:

* a six-scene video cycled four lines and repeated from the fifth;
* none of those lines ever named what was being sold — six cards of "Built to
  last" over six pictures of a school bag.

And one that only surfaces in the recording: a Latin brand woven into an Arabic
line is read letter by letter by an Arabic voice, which also drags the subtitle
timings with it.
"""
from __future__ import annotations

from app.domain.enums import Language, Platform, VideoStyle
from app.domain.insight import ImageInsight
from app.domain.language import is_arabic_script, scripts_match
from app.domain.planner import PlanRequest, build_plan, default_beat

API = "/api/v1"


def _plan(*, language=Language.FRENCH, subject="cartables scolaires", scenes=7, **kwargs):
    images = [ImageInsight(media_id=f"m{i}", width=1080, height=1440) for i in range(scenes)]
    return build_plan(
        PlanRequest(
            images=images,
            style=VideoStyle.PRODUCT_SHOWCASE,
            topic=subject,
            language=language,
            target_duration=22,
            **kwargs,
        )
    )


def _lines(plan) -> list[str]:
    return [text.content for scene in plan.scenes for text in scene.texts]


# -------------------------------------------------------------------- beats --


def test_the_copy_names_what_the_video_is_about():
    lines = _lines(_plan())
    named = [line for line in lines if "artables" in line]
    assert len(named) >= 2, f"the product is never mentioned: {lines}"


def test_a_long_video_does_not_repeat_itself_immediately():
    lines = _lines(_plan(scenes=7))
    # It used to cycle four lines, so line five equalled line one.
    assert len(set(lines)) >= 5, f"only {len(set(lines))} distinct lines: {lines}"


def test_generic_beats_use_the_whole_table_before_repeating():
    seen = [default_beat(VideoStyle.PRODUCT_SHOWCASE, i, Language.FRENCH, "sacs") for i in range(8)]
    generic = [line for i, line in enumerate(seen) if i % 2 == 0]
    assert len(set(generic)) >= 4, f"generic beats repeat too early: {generic}"


def test_the_first_beat_does_not_repeat_the_hook():
    # The hook has just named the product; naming it again immediately reads as a stutter.
    assert "{subject}" not in default_beat(VideoStyle.PRODUCT_SHOWCASE, 0, Language.FRENCH, "sacs")


def test_the_same_request_always_writes_the_same_copy():
    assert _lines(_plan()) == _lines(_plan())


# ------------------------------------------------------------------ scripts --


def test_arabic_is_recognised_by_majority_not_by_presence():
    # A French line quoting one Arabic word is still French.
    assert is_arabic_script("محفظات مدرسية") is True
    assert is_arabic_script("Cartables Nova") is False
    assert is_arabic_script("Nos cartables مدرسية pour la rentree") is False


def test_scripts_match_compares_against_the_language_not_the_alphabet():
    assert scripts_match("محفظات", Language.TUNISIAN) is True
    assert scripts_match("Cartables Nova", Language.TUNISIAN) is False
    assert scripts_match("Cartables Nova", Language.FRENCH) is True
    assert scripts_match("", Language.TUNISIAN) is True, "nothing to mismatch"


def test_a_latin_subject_is_kept_out_of_arabic_body_copy():
    """The voice reads this text; a Latin name inside it is spelled out."""
    lines = _lines(_plan(language=Language.TUNISIAN, subject="Cartables Nova"))
    body = lines[1:-1]  # the hook may legitimately carry a brand name
    assert not any("Cartables" in line for line in body), body


def test_an_arabic_subject_is_woven_in_normally():
    lines = _lines(_plan(language=Language.TUNISIAN, subject="محفظات مدرسية"))
    assert any("محفظات" in line for line in lines[1:-1])


# ----------------------------------------------------------------- caption --


def test_the_plan_caption_is_written_for_the_project_s_network():
    tiktok = _plan(platform=Platform.TIKTOK)
    shorts = _plan(platform=Platform.SHORTS)
    assert tiktok.caption != shorts.caption
    assert "Shorts" in shorts.hashtags


def test_the_caption_is_no_longer_one_template_for_everything():
    plan = _plan()
    assert plan.caption
    # The old shape was exactly "{subject} — {cta} 👀".
    assert "—" not in plan.caption or "👀" not in plan.caption


# ----------------------------------------------------------------- notice --


def test_the_planner_warns_when_the_subject_is_in_the_wrong_script(client, auth, project_with_images):
    project_id = project_with_images["id"]
    client.patch(
        f"{API}/projects/{project_id}",
        json={"language": "tn", "topic": "Cartables Nova"},
        headers=auth["headers"],
    )
    response = client.post(
        f"{API}/projects/{project_id}/plan/generate",
        json={"use_ai": False, "apply": False},
        headers=auth["headers"],
    )
    assert response.status_code == 200, response.text
    assert "not written in" in response.json()["notice"]


def test_no_warning_when_the_subject_matches_the_language(client, auth, project_with_images):
    project_id = project_with_images["id"]
    client.patch(
        f"{API}/projects/{project_id}",
        json={"language": "tn", "topic": "محفظات مدرسية"},
        headers=auth["headers"],
    )
    response = client.post(
        f"{API}/projects/{project_id}/plan/generate",
        json={"use_ai": False, "apply": False},
        headers=auth["headers"],
    )
    assert "not written in" not in response.json()["notice"]
