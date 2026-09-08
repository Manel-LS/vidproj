"""Captions and hashtags written for the network, without a language model.

The behaviour these pin is that the four networks really do get different text.
The version this replaces emitted `"{subject} — {cta} 👀"` everywhere, which is a
template pretending to be writing, and the same one on Facebook — where hashtags
do nothing — as on TikTok.
"""
from __future__ import annotations

from app.domain.enums import Language, Platform, VideoStyle
from app.domain.social import TAG_BUDGET, build_caption, build_hashtags, compose

API = "/api/v1"

BASE = {
    "language": Language.FRENCH,
    "style": VideoStyle.PRODUCT_SHOWCASE,
    "subject": "cartables scolaires colores",
    "hook": "Voici la rentree la plus legere",
    "cta": "Decouvrir la collection",
    "description": "Notre gamme de cartables ergonomiques pour le primaire.",
}


# ---------------------------------------------------------------- hashtags --


def test_each_network_gets_the_number_of_tags_it_is_written_for():
    for platform, budget in TAG_BUDGET.items():
        tags = build_hashtags(
            platform=platform,
            language=Language.FRENCH,
            style=VideoStyle.PRODUCT_SHOWCASE,
            subject=BASE["subject"],
        )
        assert len(tags) <= budget, f"{platform} exceeded its budget"
        assert tags, f"{platform} produced nothing"


def test_the_video_s_own_words_come_before_the_category():
    tags = build_hashtags(
        platform=Platform.REELS,
        language=Language.FRENCH,
        style=VideoStyle.PRODUCT_SHOWCASE,
        subject="cartables scolaires",
    )
    # Every platform truncates the visible list, so specificity has to come first.
    assert tags[0] == "cartables"
    assert tags.index("cartables") < tags.index("produit")


def test_shorts_never_loses_its_defining_tag():
    """`#Shorts` is how the platform classifies the video at all.

    It was being pushed out by the subject's own words, because the budget there
    is three — which made the one tag that matters the one that got dropped.
    """
    tags = build_hashtags(
        platform=Platform.SHORTS,
        language=Language.FRENCH,
        style=VideoStyle.PRODUCT_SHOWCASE,
        subject="cartables scolaires colores tres longs mots",
    )
    assert "Shorts" in tags


def test_padding_words_are_not_tags():
    tags = build_hashtags(
        platform=Platform.REELS,
        language=Language.FRENCH,
        style=VideoStyle.PRODUCT_SHOWCASE,
        subject="les cartables pour la rentree",
    )
    assert "les" not in tags and "pour" not in tags
    assert "cartables" in tags


def test_tags_are_unique_whatever_the_source():
    tags = build_hashtags(
        platform=Platform.REELS,
        language=Language.FRENCH,
        style=VideoStyle.SALE,
        subject="promo promo soldes",
        extra=["Promo", "#promo"],
    )
    assert len(tags) == len({tag.lower() for tag in tags})


def test_arabic_tags_survive_cleaning():
    # A previous cleaner was ASCII-only and reduced Arabic tags to nothing.
    tags = build_hashtags(
        platform=Platform.TIKTOK,
        language=Language.TUNISIAN,
        style=VideoStyle.SALE,
        subject="محفظات مدرسية",
    )
    assert "محفظات" in tags


# ----------------------------------------------------------------- caption --


def test_the_four_networks_do_not_get_the_same_text():
    captions = {
        platform: build_caption(platform=platform, **BASE, hashtags=["a", "b"])
        for platform in (Platform.TIKTOK, Platform.REELS, Platform.SHORTS, Platform.STORY)
    }
    assert len(set(captions.values())) == 4


def test_shorts_opens_with_something_searchable():
    caption = build_caption(platform=Platform.SHORTS, **BASE, hashtags=[])
    # Its first line is indexed as a title, so it describes rather than teases.
    assert caption.splitlines()[0] == BASE["subject"]


def test_tiktok_opens_with_the_hook():
    caption = build_caption(platform=Platform.TIKTOK, **BASE, hashtags=[])
    assert caption.startswith(BASE["hook"])


def test_a_story_stays_on_one_line():
    caption = build_caption(platform=Platform.STORY, **BASE, hashtags=["a", "b"])
    assert "\n" not in caption
    # A story is glanced at; a wall of tags on it is noise.
    assert "#" not in caption


def test_reels_separates_the_tags_from_the_text():
    caption = build_caption(platform=Platform.REELS, **BASE, hashtags=["un", "deux"])
    assert "\n\n#un #deux" in caption


def test_a_caption_is_clipped_to_what_the_platform_accepts():
    caption = build_caption(
        platform=Platform.REELS,
        language=Language.FRENCH,
        style=VideoStyle.PRODUCT_SHOWCASE,
        subject="x",
        description="mot " * 2000,
        hashtags=[],
    )
    assert len(caption) <= 2200


def test_compose_returns_a_caption_that_carries_its_own_tags():
    caption, tags = compose(platform=Platform.TIKTOK, **BASE)
    assert tags
    assert f"#{tags[0]}" in caption


def test_the_same_input_always_gives_the_same_output():
    assert compose(platform=Platform.TIKTOK, **BASE) == compose(platform=Platform.TIKTOK, **BASE)


# --------------------------------------------------------------- endpoint --


def test_the_endpoint_writes_for_the_requested_network(client, auth, project):
    project_id = project["id"]
    client.patch(
        f"{API}/projects/{project_id}",
        json={"topic": "cartables scolaires", "language": "fr"},
        headers=auth["headers"],
    )

    tiktok = client.post(
        f"{API}/projects/{project_id}/social",
        json={"platform": "tiktok", "apply": False},
        headers=auth["headers"],
    )
    shorts = client.post(
        f"{API}/projects/{project_id}/social",
        json={"platform": "youtube_shorts", "apply": False},
        headers=auth["headers"],
    )
    assert tiktok.status_code == 200 and shorts.status_code == 200
    assert tiktok.json()["caption"] != shorts.json()["caption"]
    assert "Shorts" in shorts.json()["hashtags"]


def test_the_endpoint_defaults_to_the_project_s_own_platform(client, auth, project):
    response = client.post(
        f"{API}/projects/{project['id']}/social", json={"apply": False}, headers=auth["headers"]
    )
    assert response.status_code == 200
    assert response.json()["platform"] == project["platform"]


def test_applying_writes_it_onto_the_project(client, auth, project):
    project_id = project["id"]
    response = client.post(
        f"{API}/projects/{project_id}/social",
        json={"platform": "instagram_reels", "apply": True},
        headers=auth["headers"],
    )
    assert response.json()["applied"] is True

    detail = client.get(f"{API}/projects/{project_id}", headers=auth["headers"]).json()
    assert detail["caption"] == response.json()["caption"]
    assert detail["hashtags"] == response.json()["hashtags"]


def test_it_works_with_no_ai_provider_configured(client, auth, project):
    """The whole point: a caption without a key.

    The test environment has LLM_PROVIDER=heuristic, which is the state most
    installs are in.
    """
    response = client.post(
        f"{API}/projects/{project['id']}/social", json={"apply": False}, headers=auth["headers"]
    )
    assert response.status_code == 200
    assert response.json()["generated_by"] == "built-in"
    assert response.json()["caption"]


def test_a_stranger_cannot_write_captions_on_someone_else_s_project(client, user_factory, project):
    stranger = user_factory()
    response = client.post(
        f"{API}/projects/{project['id']}/social", json={}, headers=stranger["headers"]
    )
    assert response.status_code == 404
