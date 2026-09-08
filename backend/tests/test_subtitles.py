"""Grouping spoken words into readable subtitle cards.

Pure domain: no network, no ffmpeg, no database. The timings below are shaped like
the ones Edge really returns — which is the detail that drives most of these
decisions, because Edge strips punctuation from its word events. The card break
therefore cannot rely on a full stop; it has to read the pause the speaker left.
"""
from __future__ import annotations

from app.domain.subtitles import (
    DEFAULT_MAX_CHARS,
    MIN_CUE_SECONDS,
    SpokenWord,
    SubtitleStyle,
    build_cues,
    cues_from_sentences,
    get_subtitle_preset,
    parse_words,
)


def words(*specs: tuple[str, float, float]) -> list[SpokenWord]:
    return [SpokenWord(text=t, start=s, duration=d) for t, s, d in specs]


# ------------------------------------------------------------------ parsing --


def test_parse_drops_entries_that_would_render_as_a_blank_highlight():
    parsed = parse_words(
        [
            {"text": "Bonjour", "start": 0.1, "duration": 0.5},
            {"text": "   ", "start": 0.7, "duration": 0.1},
            {"text": "", "start": 0.8, "duration": 0.1},
            "not a mapping",
            {"text": "monde", "start": 0.9, "duration": 0.4},
        ]
    )
    assert [w.text for w in parsed] == ["Bonjour", "monde"]


def test_parse_orders_by_time_whatever_order_it_was_stored_in():
    parsed = parse_words(
        [{"text": "b", "start": 1.0, "duration": 0.2}, {"text": "a", "start": 0.1, "duration": 0.2}]
    )
    assert [w.text for w in parsed] == ["a", "b"]


def test_parse_of_nothing_is_empty_not_an_error():
    assert parse_words(None) == []
    assert parse_words([]) == []


# ----------------------------------------------------------------- grouping --


def test_no_words_produces_no_cues():
    assert build_cues([]) == []


def test_a_pause_ends_the_card():
    # Edge gives no punctuation, so the silence is the only sentence boundary there is.
    cues = build_cues(
        words(("Bonjour", 0.1, 0.4), ("tous", 0.5, 0.3), ("Aujourd'hui", 1.6, 0.5))
    )
    assert len(cues) == 2
    assert cues[0].text == "Bonjour tous"
    assert cues[1].text == "Aujourd'hui"


def test_a_short_gap_does_not_end_the_card():
    cues = build_cues(words(("un", 0.0, 0.3), ("deux", 0.4, 0.3), ("trois", 0.8, 0.3)))
    assert len(cues) == 1
    assert cues[0].text == "un deux trois"


def test_a_card_is_capped_by_word_count():
    cues = build_cues(
        words(*[(f"m{i}", i * 0.3, 0.25) for i in range(9)]), max_words=4, max_chars=999
    )
    assert [len(cue.words) for cue in cues] == [4, 4, 1]


def test_a_card_is_capped_by_length_so_it_fits_the_frame():
    long_words = words(
        ("incompréhensible", 0.0, 0.4),
        ("anticonstitutionnel", 0.5, 0.4),
        ("court", 1.0, 0.4),
    )
    cues = build_cues(long_words, max_words=99, max_chars=20)
    assert all(len(cue.text) <= 20 for cue in cues)
    assert len(cues) >= 2


def test_a_full_stop_ends_the_card_when_the_provider_keeps_punctuation():
    cues = build_cues(words(("Voilà.", 0.0, 0.4), ("Ensuite", 0.5, 0.4)))
    assert [cue.text for cue in cues] == ["Voilà.", "Ensuite"]


# ------------------------------------------------------------------- timing --


def test_a_card_leaves_before_the_next_one_arrives():
    cues = build_cues(words(("un", 0.0, 0.3), ("deux", 2.0, 0.3)))
    assert len(cues) == 2
    assert cues[0].end <= cues[1].start, "two cards on screen at once is a bug you can see"


def test_a_card_does_not_freeze_on_screen_through_a_long_silence():
    cues = build_cues(words(("un", 0.0, 0.3), ("deux", 8.0, 0.3)))
    # It lingers a little past the word, then clears — it does not stretch to fill
    # the eight seconds of silence.
    assert cues[0].end < 1.5


def test_a_single_short_word_is_still_readable():
    cues = build_cues(words(("oui", 0.0, 0.12)))
    assert cues[0].duration >= MIN_CUE_SECONDS


def test_cards_past_the_end_of_the_video_are_dropped():
    # A narration longer than the picture must not emit cards over a finished video.
    cues = build_cues(
        words(("un", 0.0, 0.3), ("deux", 1.0, 0.3), ("trois", 5.0, 0.3)), limit=2.0
    )
    assert cues, "the cards inside the video must survive"
    assert all(cue.start < 2.0 for cue in cues)
    assert all(cue.end <= 2.0 for cue in cues)


# -------------------------------------------------------------- highlighting --


def test_the_active_word_follows_the_narration():
    cues = build_cues(words(("un", 0.0, 0.3), ("deux", 0.4, 0.3), ("trois", 0.8, 0.3)))
    cue = cues[0]
    assert cue.active_index(-1.0) == -1
    assert cue.active_index(0.1) == 0
    assert cue.active_index(0.5) == 1
    assert cue.active_index(0.9) == 2


def test_the_last_word_stays_marked_until_the_card_leaves():
    # Dropping the highlight on the final syllable leaves a card that looks broken.
    cues = build_cues(words(("un", 0.0, 0.3), ("deux", 0.4, 0.3)))
    cue = cues[0]
    assert cue.active_index(cue.end - 0.01) == 1


# ------------------------------------------------------------------ presets --


def test_every_style_except_none_has_a_preset():
    for style in SubtitleStyle:
        preset = get_subtitle_preset(style)
        if style is SubtitleStyle.NONE:
            assert preset is None
        else:
            assert preset is not None, f"{style} has no preset"
            assert preset.name and preset.description
            assert 0.0 < preset.position_y < 1.0


def test_an_unknown_style_is_not_an_exception():
    assert get_subtitle_preset("nonsense") is None


def test_each_style_marks_the_spoken_word_somehow():
    # A "highlight" style that changes nothing visible would be a silent no-op.
    for style in SubtitleStyle:
        preset = get_subtitle_preset(style)
        if preset is None:
            continue
        distinguishable = (
            preset.active_color.upper() != preset.color.upper()
            or preset.active_scale != 1.0
            or bool(preset.active_background)
            or preset.inactive_opacity < 1.0
        )
        assert distinguishable, f"{style} does not mark the word being spoken"


def test_the_tiktok_preset_breaks_shorter_lines_than_the_cinematic_one():
    assert get_subtitle_preset(SubtitleStyle.TIKTOK).max_chars < DEFAULT_MAX_CHARS
    assert get_subtitle_preset(SubtitleStyle.CINEMATIC).max_chars > DEFAULT_MAX_CHARS


# ----------------------------------------------------------------- fallback --


def test_without_timings_the_script_is_split_into_whole_lines():
    cues = cues_from_sentences("Bonjour a tous. Voici la suite. Et voila.", 9.0)
    assert len(cues) == 3
    assert cues[0].start == 0.0
    assert abs(cues[-1].end - 9.0) < 0.01
    # One span per card, never per word: there is no honest way to highlight a
    # word whose timing was invented.
    assert all(len(cue.words) == 1 for cue in cues)


def test_the_fallback_cards_do_not_overlap():
    cues = cues_from_sentences("Une. Deux. Trois. Quatre.", 8.0)
    for earlier, later in zip(cues, cues[1:]):
        assert earlier.end <= later.start + 1e-6


def test_the_fallback_refuses_to_invent_anything_from_nothing():
    assert cues_from_sentences("", 10.0) == []
    assert cues_from_sentences("Du texte.", 0.0) == []
