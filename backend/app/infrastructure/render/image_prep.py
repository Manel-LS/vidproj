"""Prepare a source image for the animation stage.

The image is scaled to *cover* the target canvas at `supersample`x resolution and
centre-cropped around its focal point. Supersampling is what makes `zoompan` smooth:
at 2x, the integer x/y rounding zoompan performs is half an output pixel.

The crop moves the focal point, so the function returns its new normalised position
for the animation math to use.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from app.core.errors import RenderError


def _even(value: float) -> int:
    """H.264 needs even dimensions."""
    return max(2, int(round(value / 2)) * 2)


def prepare_scene_image(
    source: Path,
    target: Path,
    *,
    frame_width: int,
    frame_height: int,
    supersample: float = 2.0,
    focus: tuple[float, float] = (0.5, 0.5),
    max_zoom: float = 1.0,
) -> tuple[Path, tuple[float, float]]:
    """Cover-crop `source` into `target`; returns the path and the new focal point."""
    try:
        image = Image.open(source)
        image.load()
    except (OSError, ValueError) as exc:
        raise RenderError(
            f"The image for one of your scenes could not be read ({source.name}). "
            "Replace it and render again."
        ) from exc

    image = ImageOps.exif_transpose(image).convert("RGB")

    src_w, src_h = image.size

    # Supersampling only helps up to the detail the source actually has: enlarging a
    # 900px photo to 4K costs render time and buys nothing. Cap the factor at what the
    # zoom will magnify, and at 1.15x the source resolution.
    scale = max(1.0, min(supersample, max_zoom * 1.25))
    natural = max(src_w / frame_width, src_h / frame_height) * 1.15
    scale = max(1.0, min(scale, natural))
    out_w = _even(frame_width * scale)
    out_h = _even(frame_height * scale)

    ratio = max(out_w / src_w, out_h / src_h)
    resized_w, resized_h = max(out_w, int(round(src_w * ratio))), max(out_h, int(round(src_h * ratio)))
    resized = image.resize((resized_w, resized_h), Image.LANCZOS)

    # Centre the crop on the focal point, clamped to stay inside the resized image.
    fx, fy = focus
    left = int(round(fx * resized_w - out_w / 2))
    top = int(round(fy * resized_h - out_h / 2))
    left = max(0, min(left, resized_w - out_w))
    top = max(0, min(top, resized_h - out_h))
    cropped = resized.crop((left, top, left + out_w, top + out_h))

    target.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(target, format="JPEG", quality=95, subsampling=0)

    new_focus = (
        min(1.0, max(0.0, (fx * resized_w - left) / out_w)),
        min(1.0, max(0.0, (fy * resized_h - top) / out_h)),
    )
    return target, new_focus


def solid_frame(target: Path, *, width: int, height: int, color: str = "#000000") -> Path:
    """A flat colour frame, used for scenes that have no image of their own."""
    rgb = color.lstrip("#")
    if len(rgb) == 3:
        rgb = "".join(c * 2 for c in rgb)
    fill = tuple(int(rgb[i : i + 2], 16) for i in (0, 2, 4))
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (_even(width), _even(height)), fill).save(target, format="JPEG", quality=92)
    return target
