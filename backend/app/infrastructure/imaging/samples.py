"""Procedurally generated sample images.

Used by the database seeder (so a fresh install has a demo project you can render)
and by the test-suite. Nothing here is bundled binary content, so there are no
licensing questions and the repository stays small.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter

from app.domain.enums import FontFamily
from app.infrastructure.imaging.fonts import load_font


@dataclass(frozen=True)
class SamplePalette:
    top: tuple[int, int, int]
    bottom: tuple[int, int, int]
    accent: tuple[int, int, int]


PALETTES: tuple[SamplePalette, ...] = (
    SamplePalette((28, 32, 68), (86, 40, 120), (255, 209, 102)),
    SamplePalette((10, 46, 58), (14, 116, 118), (94, 234, 212)),
    SamplePalette((60, 18, 24), (176, 62, 38), (253, 224, 71)),
    SamplePalette((240, 236, 228), (206, 190, 168), (60, 48, 40)),
    SamplePalette((18, 18, 22), (58, 58, 70), (236, 72, 153)),
    SamplePalette((236, 240, 244), (168, 190, 214), (30, 64, 120)),
)


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def generate_sample_image(
    index: int = 0,
    *,
    width: int = 1200,
    height: int = 1600,
    label: str = "",
) -> bytes:
    """Build a JPEG that has a clear subject, so image analysis has something to find."""
    palette = PALETTES[index % len(PALETTES)]
    image = Image.new("RGB", (width, height), palette.top)
    draw = ImageDraw.Draw(image)

    for y in range(height):
        t = y / max(1, height - 1)
        draw.line(
            [(0, y), (width, y)],
            fill=(
                _lerp(palette.top[0], palette.bottom[0], t),
                _lerp(palette.top[1], palette.bottom[1], t),
                _lerp(palette.top[2], palette.bottom[2], t),
            ),
        )

    # A soft radial glow behind the subject.
    glow = Image.new("L", (width, height), 0)
    ImageDraw.Draw(glow).ellipse(
        [width * 0.12, height * 0.24, width * 0.88, height * 0.76], fill=110
    )
    glow = glow.filter(ImageFilter.GaussianBlur(width * 0.06))
    image.paste(Image.new("RGB", (width, height), palette.accent), (0, 0), glow)

    # The "subject": a rounded card with a couple of geometric marks.
    cx, cy = width * 0.5, height * 0.47
    box_w, box_h = width * 0.46, height * 0.30
    draw.rounded_rectangle(
        [cx - box_w / 2, cy - box_h / 2, cx + box_w / 2, cy + box_h / 2],
        radius=int(width * 0.05),
        fill=palette.accent,
    )
    ring = int(width * 0.09)
    draw.ellipse(
        [cx - ring, cy - ring - height * 0.02, cx + ring, cy + ring - height * 0.02],
        outline=palette.top,
        width=max(4, int(width * 0.012)),
    )
    for i in range(3):
        angle = math.radians(30 + i * 55)
        r = width * 0.30
        draw.ellipse(
            [
                cx + math.cos(angle) * r - 22,
                cy + math.sin(angle) * r - 22,
                cx + math.cos(angle) * r + 22,
                cy + math.sin(angle) * r + 22,
            ],
            fill=palette.accent,
        )

    text = label or f"SAMPLE {index + 1:02d}"
    font = load_font(FontFamily.SANS_BOLD, 800, int(width * 0.055))
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((width - (bbox[2] - bbox[0])) / 2, height * 0.80),
        text,
        font=font,
        fill=(255, 255, 255),
    )

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


def generate_sample_set(count: int = 4, **kwargs) -> list[bytes]:
    return [generate_sample_image(i, **kwargs) for i in range(count)]


def generate_silent_wav(seconds: float = 12.0, *, sample_rate: int = 44100) -> bytes:
    """A soft, royalty-free-by-construction tone bed for the demo project.

    Deliberately synthetic: the product must never ship copyrighted music.
    """
    import struct

    frames = int(seconds * sample_rate)
    data = bytearray()
    for n in range(frames):
        t = n / sample_rate
        envelope = min(1.0, t / 0.8) * min(1.0, max(0.0, (seconds - t) / 1.2))
        value = (
            math.sin(2 * math.pi * 174.6 * t) * 0.16
            + math.sin(2 * math.pi * 261.6 * t) * 0.10
            + math.sin(2 * math.pi * 329.6 * t) * 0.07
        )
        # A gentle pulse on the beat so audio sync is audible in the demo.
        value *= 0.75 + 0.25 * (0.5 + 0.5 * math.sin(2 * math.pi * 2.0 * t))
        sample = int(max(-1.0, min(1.0, value * envelope)) * 24000)
        data += struct.pack("<h", sample)

    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    return header + bytes(data)
