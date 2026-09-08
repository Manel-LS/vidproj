"""Rasterise text overlays into RGBA layers (requirement 9).

Why Pillow instead of ffmpeg's `drawtext`:

  1. Security — user-supplied text never reaches an ffmpeg filter string, so the
     whole class of filtergraph-escaping injections simply does not exist.
  2. Typography — letter spacing, wrapping, pill/gradient scrims and per-line
     alignment are all straightforward here and painful in `drawtext`.

Output is either a single PNG (static text) or a short PNG sequence covering the
animation window. The renderer overlays the sequence and lets ffmpeg's `overlay`
repeat the final frame for the rest of the layer's lifetime, so a 0.45s animation
costs ~14 small files no matter how long the scene is.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.domain.enums import TextAlign, TextAnimation, TextBackground, TextPosition
from app.domain.plan import TextOverlay
from app.infrastructure.imaging.fonts import load_font

#: Fraction of frame height at which each position anchors the text block.
_POSITION_ANCHORS: dict[TextPosition, tuple[str, float]] = {
    TextPosition.TOP: ("top", 0.065),
    TextPosition.UPPER_THIRD: ("center", 0.27),
    TextPosition.CENTER: ("center", 0.50),
    TextPosition.LOWER_THIRD: ("center", 0.72),
    TextPosition.BOTTOM: ("bottom", 0.935),
}

_SLIDE_TRAVEL = 130
_RISE_TRAVEL = 80
_POP_OVERSHOOT = 1.08
_ZOOM_START = 1.35


@dataclass
class TextLayerAsset:
    """Everything the ffmpeg compiler needs to place one text layer."""

    #: Static PNG (animation == NONE) or the first frame of the sequence.
    path: Path
    #: printf pattern for the sequence, e.g. `.../text-1/%05d.png`; None when static.
    sequence_pattern: str | None
    frame_count: int
    fps: int
    #: Top-left of the layer canvas within the video frame.
    x: int
    y: int
    width: int
    height: int
    start: float
    duration: float

    @property
    def is_sequence(self) -> bool:
        return self.sequence_pattern is not None and self.frame_count > 1

    @property
    def end(self) -> float:
        return self.start + self.duration


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def _ease_out_back(t: float) -> float:
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


#: Unicode blocks whose scripts read right to left and join their letters.
_RTL_RANGES = (
    (0x0590, 0x05FF),  # Hebrew
    (0x0600, 0x06FF),  # Arabic
    (0x0700, 0x074F),  # Syriac
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB1D, 0xFDFF),  # Hebrew/Arabic presentation forms
    (0xFE70, 0xFEFF),  # Arabic presentation forms-B
)


def is_rtl(text: str) -> bool:
    """True when the text is written in a right-to-left, letter-joining script.

    Such scripts cannot be drawn glyph by glyph: Arabic letters change shape
    depending on their neighbours, so splitting the string to apply letter spacing
    would produce disconnected letters in reverse order.
    """
    return any(
        any(low <= ord(char) <= high for low, high in _RTL_RANGES) for char in text
    )


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, spacing: float) -> float:
    if not text:
        return 0.0
    if is_rtl(text):
        return draw.textlength(text, font=font, direction="rtl")
    width = draw.textlength(text, font=font)
    if spacing:
        width += spacing * max(0, len(text) - 1)
    return width


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: float,
    spacing: float,
) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if _text_width(draw, candidate, font, spacing) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines or [""]


def _draw_spaced_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    spacing: float,
) -> None:
    # Right-to-left scripts are handed to the shaper whole. Letter spacing is
    # deliberately ignored for them: it is meaningless in a joining script, and
    # applying it the naive way severs every ligature.
    if is_rtl(text):
        draw.text(xy, text, font=font, fill=fill, direction="rtl")
        return
    if not spacing:
        draw.text(xy, text, font=font, fill=fill)
        return
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + spacing


@dataclass
class _Block:
    """Measured text block: the lines, their widths and the box they occupy."""

    lines: list[str]
    line_widths: list[float]
    width: float
    height: float
    line_height: float
    ascent_offset: float


def _measure(overlay: TextOverlay, font: ImageFont.FreeTypeFont, max_width: float) -> _Block:
    scratch = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    lines = _wrap(scratch, overlay.display_text, font, max_width, overlay.letter_spacing)
    widths = [_text_width(scratch, line, font, overlay.letter_spacing) for line in lines]
    ascent, descent = font.getmetrics()
    line_height = (ascent + descent) * overlay.line_height
    return _Block(
        lines=lines,
        line_widths=widths,
        width=max(widths) if widths else 0.0,
        height=line_height * len(lines),
        line_height=line_height,
        ascent_offset=0.0,
    )


def _padding_for(overlay: TextOverlay, font_size: int) -> tuple[int, int]:
    if overlay.background is TextBackground.NONE:
        return (0, 0)
    if overlay.background is TextBackground.PILL:
        return (int(font_size * 0.55), int(font_size * 0.28))
    if overlay.background is TextBackground.BOX:
        return (int(font_size * 0.40), int(font_size * 0.26))
    return (int(font_size * 0.50), int(font_size * 0.55))  # GRADIENT scrim


def _paint_background(
    canvas: Image.Image,
    box: tuple[float, float, float, float],
    overlay: TextOverlay,
    alpha_scale: float,
) -> None:
    if overlay.background is TextBackground.NONE:
        return
    left, top, right, bottom = box
    rgb = _hex_to_rgb(overlay.background_color)
    alpha = int(255 * overlay.background_opacity * alpha_scale)
    if alpha <= 0:
        return

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    if overlay.background is TextBackground.GRADIENT:
        height = max(1, int(bottom - top))
        width = max(1, int(right - left))
        gradient = Image.new("L", (1, height))
        for y in range(height):
            t = y / max(1, height - 1)
            # Strongest in the middle of the band, feathered at both edges.
            falloff = math.sin(math.pi * t) ** 0.7
            gradient.putpixel((0, y), int(alpha * falloff))
        gradient = gradient.resize((width, height))
        band = Image.new("RGBA", (width, height), (*rgb, 255))
        band.putalpha(gradient)
        layer.paste(band, (int(left), int(top)))
    else:
        radius = (
            int((bottom - top) / 2)
            if overlay.background is TextBackground.PILL
            else max(8, int((bottom - top) * 0.10))
        )
        draw.rounded_rectangle([left, top, right, bottom], radius=radius, fill=(*rgb, alpha))

    canvas.alpha_composite(layer)


def _render_frame(
    overlay: TextOverlay,
    block: _Block,
    font: ImageFont.FreeTypeFont,
    canvas_size: tuple[int, int],
    *,
    scale: float,
    dx: float,
    dy: float,
    alpha: float,
    visible_chars: int | None,
) -> Image.Image:
    """Draw one frame of the layer at `canvas_size`, centred, with a transform."""
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    if alpha <= 0.001:
        return canvas

    pad_x, pad_y = _padding_for(overlay, overlay.font_size)
    block_w = block.width + pad_x * 2
    block_h = block.height + pad_y * 2

    # Render at scale 1 into an intermediate, then resize — keeps glyph metrics exact
    # and avoids re-shaping the text on every frame.
    inner = Image.new("RGBA", (max(1, int(block_w)), max(1, int(block_h))), (0, 0, 0, 0))
    _paint_background(inner, (0, 0, block_w, block_h), overlay, 1.0)
    draw = ImageDraw.Draw(inner)

    color = (*_hex_to_rgb(overlay.color), 255)
    shadow_color = (0, 0, 0, 150)
    remaining = visible_chars

    y = pad_y
    for line, line_width in zip(block.lines, block.line_widths):
        text = line
        if remaining is not None:
            if remaining <= 0:
                break
            text = line[:remaining]
            remaining -= len(line)
        if overlay.align is TextAlign.LEFT:
            x = pad_x
        elif overlay.align is TextAlign.RIGHT:
            x = pad_x + (block.width - line_width)
        else:
            x = pad_x + (block.width - line_width) / 2

        if overlay.shadow and text:
            shadow = Image.new("RGBA", inner.size, (0, 0, 0, 0))
            _draw_spaced_text(
                ImageDraw.Draw(shadow),
                (x, y + max(2, overlay.font_size * 0.045)),
                text,
                font,
                shadow_color,
                overlay.letter_spacing,
            )
            inner.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(max(2, overlay.font_size * 0.035))))
            draw = ImageDraw.Draw(inner)

        _draw_spaced_text(draw, (x, y), text, font, color, overlay.letter_spacing)
        y += block.line_height

    if scale != 1.0:
        new_size = (max(1, int(inner.width * scale)), max(1, int(inner.height * scale)))
        inner = inner.resize(new_size, Image.LANCZOS)

    combined = alpha * overlay.opacity
    if combined < 1.0:
        inner.putalpha(inner.getchannel("A").point(lambda v: int(v * combined)))

    cx = canvas_size[0] / 2 + dx
    cy = canvas_size[1] / 2 + dy
    canvas.alpha_composite(inner, (int(cx - inner.width / 2), int(cy - inner.height / 2)))
    return canvas


def _transform_at(overlay: TextOverlay, t: float) -> tuple[float, float, float, float, int | None]:
    """(scale, dx, dy, alpha, visible_chars) for eased progress `t` in [0, 1]."""
    animation = overlay.animation
    eased = _ease_out_cubic(t)

    if animation is TextAnimation.NONE:
        return 1.0, 0.0, 0.0, 1.0, None
    if animation is TextAnimation.FADE:
        return 1.0, 0.0, 0.0, eased, None
    if animation is TextAnimation.SLIDE:
        direction = -1 if overlay.align is not TextAlign.RIGHT else 1
        return 1.0, direction * _SLIDE_TRAVEL * (1 - eased), 0.0, eased, None
    if animation is TextAnimation.RISE:
        return 1.0, 0.0, _RISE_TRAVEL * (1 - eased), min(1.0, eased * 1.3), None
    if animation is TextAnimation.ZOOM:
        return _ZOOM_START + (1.0 - _ZOOM_START) * eased, 0.0, 0.0, min(1.0, t * 1.8), None
    # POP and TYPEWRITER need per-frame state the caller owns; they are handled there.
    return 1.0, 0.0, 0.0, 1.0, None


def _pop_scale(t: float) -> float:
    """0.55 -> 1.08 -> 1.0 with a settle, via an ease-out-back curve."""
    return 0.55 + (1.0 - 0.55) * _ease_out_back(t)


def render_text_layer(
    overlay: TextOverlay,
    *,
    frame_size: tuple[int, int],
    output_dir: Path,
    layer_id: str,
    fps: int,
    scene_duration: float,
) -> TextLayerAsset:
    """Rasterise one overlay into PNG assets and compute its frame placement."""
    frame_w, frame_h = frame_size
    output_dir.mkdir(parents=True, exist_ok=True)

    font = load_font(
        overlay.font_family,
        overlay.font_weight,
        overlay.font_size,
        arabic=is_rtl(overlay.display_text),
    )
    max_text_width = frame_w * overlay.max_width_pct
    pad_x, pad_y = _padding_for(overlay, overlay.font_size)
    block = _measure(overlay, font, max_text_width - pad_x * 2)

    block_w = block.width + pad_x * 2
    block_h = block.height + pad_y * 2

    # The canvas must contain the block at its largest scale plus any travel.
    max_scale = 1.0
    travel_x = travel_y = 0.0
    if overlay.animation is TextAnimation.POP:
        max_scale = _POP_OVERSHOOT
    elif overlay.animation is TextAnimation.ZOOM:
        max_scale = _ZOOM_START
    elif overlay.animation is TextAnimation.SLIDE:
        travel_x = _SLIDE_TRAVEL
    elif overlay.animation is TextAnimation.RISE:
        travel_y = _RISE_TRAVEL

    canvas_w = min(frame_w * 2, int(math.ceil(block_w * max_scale + travel_x * 2 + 8)))
    canvas_h = min(frame_h * 2, int(math.ceil(block_h * max_scale + travel_y * 2 + 8)))

    # Resting centre of the block within the video frame.
    anchor, ratio = _POSITION_ANCHORS[overlay.position]
    if anchor == "top":
        center_y = frame_h * ratio + block_h / 2
    elif anchor == "bottom":
        center_y = frame_h * ratio - block_h / 2
    else:
        center_y = frame_h * ratio
    center_y += overlay.offset_y_pct * frame_h

    if overlay.align is TextAlign.LEFT:
        center_x = frame_w * 0.06 + block_w / 2
    elif overlay.align is TextAlign.RIGHT:
        center_x = frame_w * 0.94 - block_w / 2
    else:
        center_x = frame_w / 2
    center_x += overlay.offset_x_pct * frame_w

    duration = overlay.resolved_duration(scene_duration)
    animation_seconds = min(overlay.animation_duration, max(0.05, duration))

    layer_dir = output_dir / layer_id
    layer_dir.mkdir(parents=True, exist_ok=True)

    total_chars = sum(len(line) for line in block.lines)
    frame_count = 1
    sequence_pattern: str | None = None

    if overlay.animation is TextAnimation.NONE:
        frame = _render_frame(
            overlay, block, font, (canvas_w, canvas_h),
            scale=1.0, dx=0.0, dy=0.0, alpha=1.0, visible_chars=None,
        )
        path = layer_dir / "static.png"
        frame.save(path)
    else:
        frame_count = max(2, int(math.ceil(animation_seconds * fps)))
        for index in range(frame_count):
            t = index / (frame_count - 1)
            if overlay.animation is TextAnimation.TYPEWRITER:
                scale, dx, dy, alpha = 1.0, 0.0, 0.0, 1.0
                visible = max(1, int(math.ceil(total_chars * t)))
            elif overlay.animation is TextAnimation.POP:
                scale, dx, dy, alpha, visible = _pop_scale(t), 0.0, 0.0, min(1.0, t * 2.2), None
            else:
                scale, dx, dy, alpha, visible = _transform_at(overlay, t)
                visible = None
            _render_frame(
                overlay, block, font, (canvas_w, canvas_h),
                scale=scale, dx=dx, dy=dy, alpha=alpha, visible_chars=visible,
            ).save(layer_dir / f"{index:05d}.png")
        path = layer_dir / "00000.png"
        sequence_pattern = str(layer_dir / "%05d.png")

    return TextLayerAsset(
        path=path,
        sequence_pattern=sequence_pattern,
        frame_count=frame_count,
        fps=fps,
        x=int(round(center_x - canvas_w / 2)),
        y=int(round(center_y - canvas_h / 2)),
        width=canvas_w,
        height=canvas_h,
        start=overlay.start,
        duration=duration,
    )
