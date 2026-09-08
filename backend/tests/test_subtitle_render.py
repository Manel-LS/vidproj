"""Rasterising the subtitle band, and burning it into a real video.

The rasterisation tests are cheap and check the things that were actually wrong
when this was written: a preset's `uppercase` and `letter_spacing` were read into
the dataclass and then ignored by the renderer, and the highlight pill was sized
from the nominal point size rather than the font's metrics, which drew a tall box
around a one-letter word.

The last test calls ffmpeg for real and inspects the output, because the failure
mode this module is exposed to — subtitles that render fine on their own and never
reach the video — cannot be caught any other way.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.domain.plan import validate_plan
from app.domain.subtitles import (
    SubtitleStyle,
    build_cues,
    get_subtitle_preset,
    parse_words,
)
from app.infrastructure.imaging.subtitle_renderer import (
    _layout,
    render_subtitle_track,
)
from app.infrastructure.imaging.fonts import load_font
from app.infrastructure.render.base import RenderRequest
from app.infrastructure.render.engine import FFmpegRenderEngine
from app.infrastructure.render.ffmpeg import probe_duration

FRAME = (1080, 1920)

TIMINGS = [
    {"text": "Bonjour", "start": 0.10, "duration": 0.62},
    {"text": "a", "start": 0.80, "duration": 0.10},
    {"text": "tous", "start": 0.95, "duration": 0.33},
    {"text": "voici", "start": 2.20, "duration": 0.40},
    {"text": "la", "start": 2.70, "duration": 0.12},
    {"text": "suite", "start": 2.90, "duration": 0.45},
]


def _track(tmp_path: Path, style: SubtitleStyle, *, duration: float = 4.0, fps: int = 30):
    preset = get_subtitle_preset(style)
    cues = build_cues(
        parse_words(TIMINGS),
        max_chars=preset.max_chars,
        max_words=preset.max_words,
        limit=duration,
    )
    asset = render_subtitle_track(
        cues,
        preset,
        frame_size=FRAME,
        fps=fps,
        total_duration=duration,
        output_dir=tmp_path / style.value,
    )
    return preset, cues, asset


# ------------------------------------------------------------------ layout --


def test_an_uppercase_preset_really_uppercases():
    # The field existed and was ignored, which is the worst shape for a setting:
    # present in the UI, absent from the picture.
    preset = get_subtitle_preset(SubtitleStyle.TIKTOK)
    assert preset.uppercase is True
    font = load_font(preset.font_family, 700, 60)
    cue = build_cues(parse_words(TIMINGS[:3]))[0]

    lines = _layout(
        cue, font, max_width=900, space_width=12, spacing=0.0, uppercase=True, rtl=False
    )
    assert [w.text for line in lines for w in line] == ["BONJOUR", "A", "TOUS"]


def test_letter_spacing_widens_the_measured_word():
    font = load_font(get_subtitle_preset(SubtitleStyle.CINEMATIC).font_family, 700, 60)
    cue = build_cues(parse_words(TIMINGS[:3]))[0]

    tight = _layout(cue, font, max_width=900, space_width=12, spacing=0.0, uppercase=False, rtl=False)
    loose = _layout(cue, font, max_width=900, space_width=12, spacing=6.0, uppercase=False, rtl=False)
    assert loose[0][0].width > tight[0][0].width


def test_right_to_left_lines_are_filled_from_the_right():
    preset = get_subtitle_preset(SubtitleStyle.CLEAN)
    font = load_font(preset.font_family, 700, 60, arabic=True)
    cue = build_cues(
        parse_words(
            [
                {"text": "أهلا", "start": 0.1, "duration": 0.3},
                {"text": "بكم", "start": 0.5, "duration": 0.3},
                {"text": "معانا", "start": 0.9, "duration": 0.3},
            ]
        )
    )[0]
    lines = _layout(cue, font, max_width=900, space_width=12, spacing=0.0, uppercase=False, rtl=True)
    xs = [word.x for word in lines[0]]
    # The first word of the sentence sits rightmost.
    assert xs == sorted(xs, reverse=True)


# ------------------------------------------------------------- rasterising --


def test_nothing_to_draw_produces_no_track(tmp_path):
    preset = get_subtitle_preset(SubtitleStyle.CLEAN)
    assert render_subtitle_track(
        [], preset, frame_size=FRAME, fps=30, total_duration=4.0, output_dir=tmp_path
    ) is None
    cues = build_cues(parse_words(TIMINGS))
    assert render_subtitle_track(
        cues, preset, frame_size=FRAME, fps=30, total_duration=0.0, output_dir=tmp_path
    ) is None


def test_the_sequence_covers_every_frame_of_the_video(tmp_path):
    _, _, asset = _track(tmp_path, SubtitleStyle.CLEAN, duration=4.0, fps=30)
    assert asset.frame_count == 120
    frames = sorted(Path(asset.sequence_pattern).parent.glob("*.png"))
    assert len(frames) == 120, "a gap in the sequence is a frame ffmpeg cannot read"


def test_only_distinct_pictures_are_drawn(tmp_path):
    """The whole point of the state/link split: 120 frames, a handful of images."""
    _, cues, asset = _track(tmp_path, SubtitleStyle.CLEAN)
    states = list((Path(asset.sequence_pattern).parent.parent / "states").glob("*.png"))
    expected = sum(len(cue.words) + 1 for cue in cues) + 1  # +1 per cue for "before", +1 blank
    assert len(states) == expected
    assert len(states) < asset.frame_count


def test_the_band_stays_inside_the_frame(tmp_path):
    for style in SubtitleStyle:
        if style is SubtitleStyle.NONE:
            continue
        _, _, asset = _track(tmp_path / style.value, style)
        assert asset.x >= 0 and asset.y >= 0
        assert asset.x + asset.width <= FRAME[0]
        assert asset.y + asset.height <= FRAME[1]


def test_the_band_is_transparent_where_there_is_no_card(tmp_path):
    # A card runs 0.1s..~1.9s; at 2.0s there is a gap before the next one.
    _, _, asset = _track(tmp_path, SubtitleStyle.CLEAN)
    frames_dir = Path(asset.sequence_pattern).parent
    gap = Image.open(frames_dir / "00060.png").convert("RGBA")
    assert gap.getbbox() is None, "the band must not sit on the picture between cards"


def test_the_highlight_moves_between_frames(tmp_path):
    """Two moments inside one card must not look the same."""
    _, _, asset = _track(tmp_path, SubtitleStyle.TIKTOK)
    frames_dir = Path(asset.sequence_pattern).parent
    early = Image.open(frames_dir / "00006.png").convert("RGBA").tobytes()   # t=0.2
    later = Image.open(frames_dir / "00033.png").convert("RGBA").tobytes()   # t=1.1
    assert early != later


def test_a_pill_style_leaves_room_for_its_pill(tmp_path):
    # The pill used to overlap the glyphs of the words either side of it.
    preset = get_subtitle_preset(SubtitleStyle.TIKTOK)
    font = load_font(preset.font_family, 700, 60)
    cue = build_cues(parse_words(TIMINGS[:3]))[0]
    scratch = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    plain = scratch.textlength(" ", font=font)
    lines = _layout(cue, font, max_width=2000, space_width=plain, spacing=0.0, uppercase=True, rtl=False)
    gap = lines[0][1].x - (lines[0][0].x + lines[0][0].width)
    assert gap >= plain


# --------------------------------------------------------------- in a video --


@pytest.mark.slow
def test_subtitles_are_burned_into_the_rendered_video(tmp_path, sample_images, sample_audio):
    """Rendering with subtitles must still produce a playable MP4 of the right length.

    The regression guarded here is the one that cannot be seen from unit tests: an
    extra input and an overlay added to the transition graph can desynchronise or
    lengthen the output, and ffmpeg reports success either way.
    """
    media: dict[str, Path] = {}
    for index in range(2):
        path = tmp_path / f"img{index}.jpg"
        path.write_bytes(sample_images(1)[0][1][1])
        media[f"m{index}"] = path
    voice = tmp_path / "voice.wav"
    voice.write_bytes(sample_audio(5.0)[1])
    media["v"] = voice

    def plan_for(style: str):
        return validate_plan(
            {
                "fps": 24,
                "scenes": [
                    {"order": 0, "media_id": "m0", "duration": 2.0, "transition": "none"},
                    {"order": 1, "media_id": "m1", "duration": 2.0, "transition": "fade",
                     "transition_duration": 0.4},
                ],
                "voiceover": {
                    "enabled": True,
                    "media_id": "v",
                    "script": "Bonjour a tous. Voici la suite.",
                    "word_timings": TIMINGS,
                },
                "subtitles": {"style": style},
            }
        )

    engine = FFmpegRenderEngine()
    outputs = {}
    for style in ("none", "tiktok"):
        plan = plan_for(style)
        target = tmp_path / f"{style}.mp4"
        result = engine.render(
            RenderRequest(
                plan=plan,
                media_paths=media,
                work_dir=tmp_path / f"work-{style}",
                output_path=target,
                poster_path=None,
                cancel_check=lambda: False,
            ),
            on_progress=lambda percent, stage: None,
        )
        assert target.is_file() and target.stat().st_size > 0
        assert result.width == 1080 and result.height == 1920
        # Subtitles must not stretch the timeline.
        assert abs(probe_duration(target) - plan.total_duration) < 0.35
        outputs[style] = target.stat().st_size

    # And they must actually be in the picture: burned-in text is detail, and
    # detail costs bits.
    assert outputs["tiktok"] > outputs["none"]
