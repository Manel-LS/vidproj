"""Rasterise subtitle cards into a PNG sequence the renderer can overlay.

Same reasoning as `text_renderer`: user text never reaches an ffmpeg filter string,
and Pillow gives us the Arabic shaping and the typography that `drawtext` cannot.
The bundled ffmpeg happens to carry libass, but a deployment is free to point
`FFMPEG_BINARY` at a build without it, and subtitles that silently disappear on
someone else's server are worse than subtitles that are drawn here.

The cost problem this module solves: a 60-second narration at 30 fps is 1800
frames, and writing 1800 full-frame RGBA PNGs to render a strip of text would be
absurd. Two things keep it cheap.

  * Only the **band** is drawn — a strip a few hundred pixels tall — not the frame.
  * The picture only changes when the highlighted word changes, so one PNG is drawn
    per *state* (a card, with one of its words lit) and the numbered sequence ffmpeg
    reads is built from hard links to those. A card of five words costs five images
    however long it is on screen.
"""
from __future__ import annotations

import math
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.core.logging import get_logger
from app.domain.enums import TextBackground
from app.domain.subtitles import SubtitleCue, SubtitlePreset
from app.infrastructure.imaging.fonts import load_font
from app.infrastructure.imaging.text_renderer import _hex_to_rgb, is_rtl

logger = get_logger(__name__)

#: Reference canvas the preset's pixel sizes are authored against.
_REFERENCE_WIDTH = 1080
#: Breathing room around the band so an outline or a scaled-up word is not clipped.
_BAND_PADDING = 28


@dataclass
class SubtitleTrackAsset:
    """What the ffmpeg compiler needs to lay the subtitle band over the video."""

    sequence_pattern: str
    frame_count: int
    fps: int
    #: Top-left of the band within the video frame.
    x: int
    y: int
    width: int
    height: int

    @property
    def duration(self) -> float:
        return round(self.frame_count / self.fps, 4) if self.fps else 0.0


@dataclass
class _PlacedWord:
    text: str
    #: Index of this word within its cue, so a state can be matched to it.
    index: int
    x: float
    width: float


def _scaled(value: float, frame_width: int) -> int:
    return max(1, int(round(value * frame_width / _REFERENCE_WIDTH)))


def _rgba(colour: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
    r, g, b = _hex_to_rgb(colour)
    return (r, g, b, max(0, min(255, int(round(alpha * 255)))))


def _measure_word(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    spacing: float,
    rtl: bool,
) -> float:
    if not text:
        return 0.0
    if rtl:
        # Letter spacing is meaningless in a joining script and severs ligatures
        # when applied naively, so it is deliberately not measured in either.
        return draw.textlength(text, font=font, direction="rtl")
    width = draw.textlength(text, font=font)
    if spacing:
        width += spacing * max(0, len(text) - 1)
    return width


def _draw_word(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    fill: tuple[int, int, int, int],
    spacing: float,
    rtl: bool,
    stroke_width: int,
    stroke_fill: tuple[int, int, int, int] | None,
) -> None:
    if rtl or not spacing:
        draw.text(
            xy, text, font=font, fill=fill,
            direction="rtl" if rtl else None,
            stroke_width=stroke_width, stroke_fill=stroke_fill,
        )
        return
    x, y = xy
    for char in text:
        draw.text(
            (x, y), char, font=font, fill=fill,
            stroke_width=stroke_width, stroke_fill=stroke_fill,
        )
        x += draw.textlength(char, font=font) + spacing


def _layout(
    cue: SubtitleCue,
    font: ImageFont.FreeTypeFont,
    *,
    max_width: float,
    space_width: float,
    spacing: float,
    uppercase: bool,
    rtl: bool,
) -> list[list[_PlacedWord]]:
    """Break a cue into lines and give every word its x position.

    Words are placed individually because one of them has to be highlighted. That
    is safe for Arabic: letters join within a word, never across the space between
    two, so each word is still shaped as a whole string. What does change is the
    direction — an RTL line is filled from the right edge.
    """
    scratch = ImageDraw.Draw(Image.new("RGBA", (8, 8)))

    rows: list[list[tuple[str, int, float]]] = [[]]
    used = 0.0
    for index, word in enumerate(cue.words):
        # Case is applied here, before measuring: uppercasing after layout would
        # size every line against the lower-case width and overflow the frame.
        text = word.text.upper() if uppercase else word.text
        w = _measure_word(scratch, text, font, spacing=spacing, rtl=rtl)
        extra = w if not rows[-1] else space_width + w
        if rows[-1] and used + extra > max_width:
            rows.append([])
            used = 0.0
            extra = w
        rows[-1].append((text, index, w))
        used += extra

    lines: list[list[_PlacedWord]] = []
    for row in rows:
        if not row:
            continue
        total = sum(item[2] for item in row) + space_width * (len(row) - 1)
        start = (max_width - total) / 2
        placed: list[_PlacedWord] = []
        if rtl:
            # Fill from the right: the first word of the sentence sits rightmost.
            cursor = start + total
            for text, index, w in row:
                cursor -= w
                placed.append(_PlacedWord(text=text, index=index, x=cursor, width=w))
                cursor -= space_width
        else:
            cursor = start
            for text, index, w in row:
                placed.append(_PlacedWord(text=text, index=index, x=cursor, width=w))
                cursor += w + space_width
        lines.append(placed)
    return lines


def _paint_band(image: Image.Image, preset: SubtitlePreset, size: tuple[int, int]) -> None:
    """The scrim behind the band.

    A flat box has a visible top edge that reads as a black bar sitting on the
    picture. `GRADIENT` fades it out towards the top instead, which is what the
    cinematic preset is actually asking for — rendering it as a box was a setting
    that quietly did nothing.
    """
    width, height = size
    r, g, b = _hex_to_rgb(preset.background_color)
    peak = max(0, min(255, int(round(preset.background_opacity * 255))))

    if preset.background is not TextBackground.GRADIENT:
        overlay = Image.new("RGBA", size, (r, g, b, peak))
        image.alpha_composite(overlay)
        return

    band = Image.new("RGBA", size)
    pixels = band.load()
    for y in range(height):
        # Opaque at the bottom, gone at the top.
        alpha = int(round(peak * (y / max(1, height - 1)) ** 0.85))
        for x in range(width):
            pixels[x, y] = (r, g, b, alpha)
    image.alpha_composite(band)


def _render_state(
    lines: list[list[_PlacedWord]],
    *,
    active: int,
    preset: SubtitlePreset,
    font: ImageFont.FreeTypeFont,
    active_font: ImageFont.FreeTypeFont,
    canvas: tuple[int, int],
    line_height: float,
    outline: int,
    frame_width: int,
    rtl: bool,
) -> Image.Image:
    """Draw one card with one of its words lit."""
    width, height = canvas
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    block_height = line_height * len(lines)
    top = (height - block_height) / 2

    if preset.background_opacity > 0:
        # A scrim behind the whole band; the per-word pill is a separate thing.
        _paint_band(image, preset, (width, height))

    # The pill hugs the glyphs, so it is sized from the font's own metrics rather
    # than from the nominal point size — `size * 1.22` drew a tall box around a
    # one-letter word, which read as a rectangle standing on end.
    ascent, descent = font.getmetrics()
    glyph_h = ascent + descent
    pill_pad_x = _scaled(preset.font_size * 0.34, frame_width)
    pill_pad_y = _scaled(preset.font_size * 0.08, frame_width)
    radius = _scaled(preset.font_size * 0.22, frame_width)

    for row_index, row in enumerate(lines):
        y = top + row_index * line_height
        for word in row:
            lit = word.index == active
            chosen = active_font if (lit and preset.active_scale != 1.0) else font

            # A scaled word is re-centred on its slot so the rest of the line does
            # not shuffle sideways every time the highlight moves.
            if chosen is font:
                drawn_width, x, dy = word.width, word.x, 0.0
            else:
                drawn_width = _measure_word(
                    draw, word.text, chosen, spacing=preset.letter_spacing, rtl=rtl
                )
                x = word.x - (drawn_width - word.width) / 2
                dy = -(chosen.size - font.size) * 0.5

            if lit and preset.active_background:
                grown_h = glyph_h * (chosen.size / font.size)
                draw.rounded_rectangle(
                    [
                        (x - pill_pad_x, y + dy - pill_pad_y),
                        (x + drawn_width + pill_pad_x, y + dy + grown_h + pill_pad_y),
                    ],
                    radius=radius,
                    fill=_rgba(preset.active_background),
                )

            alpha = 1.0 if lit else preset.inactive_opacity
            _draw_word(
                draw,
                (x, y + dy),
                word.text,
                chosen,
                fill=_rgba(preset.active_color if lit else preset.color, alpha),
                spacing=preset.letter_spacing,
                rtl=rtl,
                # An outline under a filled pill only muddies its edge.
                stroke_width=0 if (lit and preset.active_background) else outline,
                stroke_fill=_rgba(preset.outline_color, alpha) if outline else None,
            )
    return image


def render_subtitle_track(
    cues: list[SubtitleCue],
    preset: SubtitlePreset,
    *,
    frame_size: tuple[int, int],
    fps: int,
    total_duration: float,
    output_dir: Path,
) -> SubtitleTrackAsset | None:
    """Rasterise the whole subtitle band into a numbered PNG sequence.

    Returns None when there is nothing to draw, so the caller can skip the overlay
    entirely rather than compositing a transparent layer over every frame.
    """
    if not cues or total_duration <= 0 or fps <= 0:
        return None

    frame_w, frame_h = frame_size
    output_dir.mkdir(parents=True, exist_ok=True)
    states_dir = output_dir / "states"
    frames_dir = output_dir / "frames"
    states_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    rtl = any(is_rtl(cue.text) for cue in cues)
    font_size = _scaled(preset.font_size, frame_w)
    font = load_font(preset.font_family, 700, font_size, arabic=rtl)
    active_font = load_font(
        preset.font_family,
        700,
        max(font_size + 1, int(round(font_size * preset.active_scale))),
        arabic=rtl,
    )
    outline = _scaled(preset.outline_px, frame_w) if preset.outline_px else 0

    ascent, descent = font.getmetrics()
    line_height = (ascent + descent) * preset.line_height
    max_width = frame_w * preset.max_width_pct
    space_width = ImageDraw.Draw(Image.new("RGBA", (8, 8))).textlength(" ", font=font) or font_size * 0.3
    if preset.active_background:
        # Reserve the pill's own padding in the gap, or it overlaps the glyphs of
        # the words either side of the one it is highlighting.
        space_width += _scaled(preset.font_size * 0.34, frame_w) * 2

    layouts = [
        _layout(
            cue,
            font,
            max_width=max_width,
            space_width=space_width,
            spacing=preset.letter_spacing,
            uppercase=preset.uppercase,
            rtl=rtl,
        )
        for cue in cues
    ]
    max_lines = max((len(layout) for layout in layouts), default=1)

    band_h = int(
        math.ceil(line_height * max_lines * max(1.0, preset.active_scale)) + _BAND_PADDING * 2 + outline * 2
    )
    band_h = min(band_h, frame_h)
    band_w = frame_w
    band_x = 0
    band_y = int(round(preset.position_y * frame_h - band_h / 2))
    band_y = max(0, min(band_y, frame_h - band_h))

    # One image per (card, lit word). A blank covers the gaps between cards.
    blank = Image.new("RGBA", (band_w, band_h), (0, 0, 0, 0))
    blank_path = states_dir / "blank.png"
    blank.save(blank_path)

    state_paths: dict[tuple[int, int], Path] = {}
    for cue_index, (cue, layout) in enumerate(zip(cues, layouts)):
        if not layout:
            continue
        # -1 is the moment a card appears before its first word is spoken.
        for active in range(-1, len(cue.words)):
            path = states_dir / f"cue{cue_index:04d}-w{active + 1:03d}.png"
            _render_state(
                layout,
                active=active,
                preset=preset,
                font=font,
                active_font=active_font,
                canvas=(band_w, band_h),
                line_height=line_height,
                outline=outline,
                frame_width=frame_w,
                rtl=rtl,
            ).save(path)
            state_paths[(cue_index, active)] = path

    frame_count = max(1, int(round(total_duration * fps)))
    for frame_index in range(frame_count):
        at = frame_index / fps
        source = blank_path
        for cue_index, cue in enumerate(cues):
            if cue.start <= at < cue.end:
                source = state_paths.get((cue_index, cue.active_index(at)), blank_path)
                break
        _link(source, frames_dir / f"{frame_index:05d}.png")

    return SubtitleTrackAsset(
        sequence_pattern=str(frames_dir / "%05d.png"),
        frame_count=frame_count,
        fps=fps,
        x=band_x,
        y=band_y,
        width=band_w,
        height=band_h,
    )


def _link(source: Path, target: Path) -> None:
    """Hard-link a state image into the sequence, copying if links are unavailable.

    The sequence has one entry per frame, but only a few dozen distinct pictures.
    Links keep a minute of subtitles at the size of its states instead of the size
    of its frames.
    """
    try:
        os.link(source, target)
    except (OSError, NotImplementedError):  # pragma: no cover - filesystem dependent
        shutil.copyfile(source, target)
