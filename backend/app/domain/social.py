"""Captions and hashtags, written for the network the video is going to.

The planner used to emit one caption — `"{subject} — {cta} 👀"` — for every
platform, and a hashtag list made of the subject's own words plus three generic
tags. That is a template, not writing, and it is the same on TikTok as on
Facebook where hashtags barely work at all.

None of this needs a language model. What separates a TikTok caption from a
YouTube Shorts description is convention, and convention is exactly the kind of
thing that can be written down:

* **TikTok** — short, the hook first, few tags, and the broad discovery tags that
  the audience there actually uses.
* **Instagram Reels** — room to breathe, a line break before the tags, and many
  more of them; the platform surfaces posts by tag far more than TikTok does.
* **YouTube Shorts** — the first line is read as a title and is searchable, so it
  is descriptive rather than teasing, and `#Shorts` is the one tag that matters.
* **Facebook** — plain and conversational. Hashtags are close to useless there,
  so stuffing them in only makes the post look automated.

Pure domain: no I/O, deterministic, and identical input gives identical output.
"""
from __future__ import annotations

import re

from app.domain import copy as copy_tables
from app.domain.enums import Language, Platform, VideoStyle

#: How many tags each network is written for. Beyond these the extra tags are
#: noise: TikTok's own guidance is a handful, and Facebook's feed treats a wall
#: of tags as spam.
TAG_BUDGET: dict[Platform, int] = {
    Platform.TIKTOK: 5,
    Platform.REELS: 12,
    Platform.STORY: 5,
    Platform.SHORTS: 3,
}

CAPTION_LIMIT = 2200

#: Discovery tags per platform and language. Deliberately short lists — a tag
#: nobody searches is a tag that costs a line and returns nothing.
_DISCOVERY: dict[Platform, dict[Language, list[str]]] = {
    Platform.TIKTOK: {
        Language.FRENCH: ["pourtoi", "fyp"],
        Language.ENGLISH: ["fyp", "foryou"],
        Language.ARABIC: ["اكسبلور", "فوريو"],
        Language.TUNISIAN: ["اكسبلور", "تونس"],
    },
    Platform.REELS: {
        Language.FRENCH: ["reels", "explore", "instagram"],
        Language.ENGLISH: ["reels", "explore", "instagram"],
        Language.ARABIC: ["ريلز", "اكسبلور"],
        Language.TUNISIAN: ["ريلز", "تونس"],
    },
    Platform.STORY: {
        Language.FRENCH: ["story"],
        Language.ENGLISH: ["story"],
        Language.ARABIC: ["ستوري"],
        Language.TUNISIAN: ["ستوري"],
    },
    Platform.SHORTS: {
        Language.FRENCH: ["Shorts"],
        Language.ENGLISH: ["Shorts"],
        Language.ARABIC: ["Shorts"],
        Language.TUNISIAN: ["Shorts"],
    },
}

_ENGLISH_TAGS: dict[str, list[str]] = {
    "promo": ["product", "new", "shop"],
    "sale": ["sale", "deal", "discount"],
    "trend": ["viral", "trending", "foryou"],
    "story": ["story", "behindthescenes", "brand"],
    "place": ["realestate", "hometour", "property"],
    "food": ["food", "foodie", "tasty"],
    "teach": ["tips", "howto", "learn"],
}

_STOPWORDS = {
    "the", "and", "for", "with", "your", "our", "les", "des", "une", "pour",
    "avec", "notre", "votre", "من", "في", "على", "الى",
}

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _tone(style: VideoStyle) -> str:
    return copy_tables.tone_of(style)


def _subject_tags(subject: str, limit: int = 3) -> list[str]:
    """Tags taken from what the video is about.

    Short and very common words are dropped: `#de` and `#the` are not discovery,
    they are padding that pushes a real tag out of the budget.
    """
    tags: list[str] = []
    for word in _WORD_RE.findall(subject or ""):
        lowered = word.lower()
        if len(lowered) < 3 or lowered in _STOPWORDS:
            continue
        if lowered not in tags:
            tags.append(lowered)
        if len(tags) >= limit:
            break
    return tags


def build_hashtags(
    *,
    platform: Platform,
    language: Language,
    style: VideoStyle,
    subject: str,
    extra: list[str] | None = None,
) -> list[str]:
    """Tags for one network, most specific first.

    Order matters and is not cosmetic: every platform truncates the visible list,
    so the tag that describes *this* video has to come before the one that
    describes the category, which comes before the broad discovery tag.
    """
    budget = TAG_BUDGET.get(platform, 8)

    topical = (
        copy_tables.hashtags(language, style)
        if copy_tables.has_copy(language)
        else list(_ENGLISH_TAGS.get(_tone(style), _ENGLISH_TAGS["promo"]))
    )
    discovery = list(_DISCOVERY.get(platform, {}).get(language, []))

    # Some tags are not discovery, they are how the platform classifies the post.
    # `#Shorts` is the whole reason a vertical video is treated as a Short, so it
    # cannot be the one the budget drops.
    pinned = [tag for tag in discovery if tag.lower() == "shorts"]
    discovery = [tag for tag in discovery if tag.lower() != "shorts"]

    ordered = pinned + _subject_tags(subject) + list(extra or []) + topical + discovery

    seen: set[str] = set()
    result: list[str] = []
    for tag in ordered:
        cleaned = re.sub(r"[^\w]", "", str(tag).lstrip("#"), flags=re.UNICODE)[:40]
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        result.append(cleaned)
        if len(result) >= budget:
            break
    return result


def build_caption(
    *,
    platform: Platform,
    language: Language,
    style: VideoStyle,
    subject: str,
    hook: str = "",
    cta: str = "",
    description: str = "",
    hashtags: list[str] | None = None,
) -> str:
    """The post text for one network, tags included where they belong.

    Every branch is a convention, not a preference. The Shorts caption opens
    descriptively because its first line is indexed as a title; the TikTok one
    opens with the hook because the feed shows one line and it has to stop a
    thumb; Facebook gets almost no tags because they do nothing there.
    """
    subject = (subject or "").strip()
    hook = (hook or "").strip()
    cta = (cta or "").strip()
    description = (description or "").strip()
    tags = hashtags or []
    tag_line = " ".join(f"#{tag}" for tag in tags)

    if platform is Platform.SHORTS:
        # Searchable first, teasing second.
        title = subject or hook or description[:80]
        body = [title]
        if cta:
            body.append(cta)
        caption = "\n".join(part for part in body if part)
        return _clip(f"{caption}\n{tag_line}".strip() if tag_line else caption)

    if platform is Platform.REELS:
        parts = [hook or subject]
        if description and description.lower() != (hook or "").lower():
            parts.append(description)
        if cta:
            parts.append(cta)
        # The blank line before the tags is the convention that keeps the caption
        # readable when the platform collapses it to one line.
        body = "\n\n".join(part for part in parts if part)
        return _clip(f"{body}\n\n{tag_line}".strip() if tag_line else body)

    if platform is Platform.STORY:
        # A story is glanced at, not read. One line.
        return _clip(" · ".join(part for part in (hook or subject, cta) if part))

    # TikTok, and the default for anything new.
    lead = hook or subject
    body = " ".join(part for part in (lead, cta) if part)
    return _clip(f"{body} {tag_line}".strip() if tag_line else body)


def _clip(text: str) -> str:
    text = text.strip()
    if len(text) <= CAPTION_LIMIT:
        return text
    return text[: CAPTION_LIMIT - 1].rstrip() + "…"


def compose(
    *,
    platform: Platform,
    language: Language,
    style: VideoStyle,
    subject: str,
    hook: str = "",
    cta: str = "",
    description: str = "",
    extra_tags: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Caption and hashtags together, since the caption embeds the tags."""
    tags = build_hashtags(
        platform=platform, language=language, style=style, subject=subject, extra=extra_tags
    )
    # Facebook-style feeds and stories read badly with a tag wall; the caption
    # builders above decide whether to use them, but the list is still returned
    # so the user can paste what they want.
    caption = build_caption(
        platform=platform,
        language=language,
        style=style,
        subject=subject,
        hook=hook,
        cta=cta,
        description=description,
        hashtags=tags,
    )
    return caption, tags
