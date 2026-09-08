"""Image analysis and optimisation (Pillow).

Two jobs:
  * `optimise_upload` — validate that the bytes really are an image, strip EXIF,
    auto-orient, downscale to a sane maximum, and re-encode. Uploaded bytes are never
    trusted or served back verbatim.
  * `analyse` — measure the properties the planner needs: brightness overall and in
    each text region, contrast, dominant colours and an estimated subject centre.
"""
from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from app.core.errors import ValidationError
from app.domain.enums import TextPosition
from app.domain.insight import ImageInsight

# Guard against decompression-bomb DoS: Pillow raises above this pixel count.
Image.MAX_IMAGE_PIXELS = 80_000_000

#: Vertical band (top, bottom) as a fraction of height for each text position.
TEXT_REGIONS: dict[str, tuple[float, float]] = {
    TextPosition.TOP.value: (0.02, 0.20),
    TextPosition.UPPER_THIRD.value: (0.16, 0.40),
    TextPosition.CENTER.value: (0.36, 0.64),
    TextPosition.LOWER_THIRD.value: (0.60, 0.84),
    TextPosition.BOTTOM.value: (0.78, 0.98),
}


class OptimisedImage:
    def __init__(self, data: bytes, width: int, height: int, fmt: str, content_type: str):
        self.data = data
        self.width = width
        self.height = height
        self.format = fmt
        self.content_type = content_type

    @property
    def size(self) -> int:
        return len(self.data)


def _open_verified(data: bytes) -> Image.Image:
    """Decode bytes into an image or raise a user-facing validation error."""
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()  # structural check; consumes the file object
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError(
            "That file could not be read as an image. Please upload a JPG, PNG or WEBP."
        ) from exc
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (OSError, ValueError) as exc:
        raise ValidationError("That image appears to be corrupted. Please try another file.") from exc
    return image


def optimise_upload(data: bytes, *, max_dimension: int = 2560, quality: int = 88) -> OptimisedImage:
    """Normalise an uploaded image: orient, flatten alpha, downscale, re-encode."""
    image = _open_verified(data)
    original_format = (image.format or "").upper()

    image = ImageOps.exif_transpose(image)  # honour camera rotation, then drop EXIF
    has_alpha = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )

    if has_alpha:
        image = image.convert("RGBA")
        out_format, content_type, ext_kwargs = "PNG", "image/png", {"optimize": True}
    else:
        image = image.convert("RGB")
        out_format, content_type, ext_kwargs = (
            "JPEG",
            "image/jpeg",
            {"quality": quality, "optimize": True, "progressive": True},
        )

    if max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format=out_format, **ext_kwargs)
    payload = buffer.getvalue()

    # If re-encoding a JPEG made it bigger, keep the smaller original bytes as long as
    # nothing had to change (no rotation, no resize, same format).
    if (
        out_format == "JPEG"
        and original_format in ("JPEG", "JPG")
        and len(payload) > len(data)
        and image.size == Image.open(io.BytesIO(data)).size
    ):
        payload = data

    return OptimisedImage(payload, image.width, image.height, out_format, content_type)


def make_thumbnail(data: bytes, *, size: int = 512, quality: int = 82) -> OptimisedImage:
    image = _open_verified(data)
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((size, size), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return OptimisedImage(buffer.getvalue(), image.width, image.height, "JPEG", "image/jpeg")


def _dominant_colors(image: Image.Image, count: int = 3) -> tuple[str, ...]:
    small = image.convert("RGB").resize((64, 64), Image.LANCZOS)
    quantised = small.quantize(colors=max(count, 4), method=Image.MEDIANCUT)
    palette = quantised.getpalette() or []
    counts = sorted(quantised.getcolors() or [], reverse=True)[:count]
    colors: list[str] = []
    for _, index in counts:
        r, g, b = palette[index * 3 : index * 3 + 3] or (0, 0, 0)
        colors.append(f"#{r:02X}{g:02X}{b:02X}")
    return tuple(colors)


def _estimate_focus(gray: Image.Image) -> tuple[float, float]:
    """Centre of mass of edge energy — a cheap, dependency-free saliency estimate.

    Edges concentrate on the subject rather than on flat backgrounds, so weighting
    pixel coordinates by edge strength lands close to what a person would call the
    subject. The result is pulled 40% back toward the frame centre to stay conservative.
    """
    small = gray.resize((64, 64), Image.BILINEAR).filter(ImageFilter.FIND_EDGES)
    pixels = list(small.getdata())
    total = sum(pixels)
    if total <= 0:
        return 0.5, 0.5
    sum_x = sum_y = 0.0
    for index, value in enumerate(pixels):
        if value:
            sum_x += (index % 64) * value
            sum_y += (index // 64) * value
    cx = (sum_x / total) / 63.0
    cy = (sum_y / total) / 63.0
    return 0.5 + (cx - 0.5) * 0.6, 0.5 + (cy - 0.5) * 0.6


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def analyse(data: bytes, media_id: str) -> ImageInsight:
    """Measure everything the planner needs from one image."""
    image = _open_verified(data)
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size

    gray = image.convert("L")
    small_gray = gray.resize((96, 96), Image.BILINEAR)
    pixels = list(small_gray.getdata())
    brightness = _mean(pixels) / 255.0
    mean = brightness * 255.0
    variance = _mean((p - mean) ** 2 for p in pixels)
    contrast = (variance ** 0.5) / 255.0

    region_brightness: dict[str, float] = {}
    for name, (top, bottom) in TEXT_REGIONS.items():
        y0 = int(top * 96)
        y1 = max(y0 + 1, int(bottom * 96))
        band = pixels[y0 * 96 : y1 * 96]
        region_brightness[name] = _mean(band) / 255.0

    focus_x, focus_y = _estimate_focus(gray)

    return ImageInsight(
        media_id=media_id,
        width=width,
        height=height,
        brightness=round(brightness, 4),
        region_brightness={k: round(v, 4) for k, v in region_brightness.items()},
        contrast=round(contrast, 4),
        focus_x=round(focus_x, 4),
        focus_y=round(focus_y, 4),
        dominant_colors=_dominant_colors(image),
        landscape=width >= height,
    )


def analyse_path(path: Path, media_id: str) -> ImageInsight:
    return analyse(Path(path).read_bytes(), media_id)


def insight_from_media(media_id: str, width: int, height: int, stored: dict | None) -> ImageInsight:
    """Rebuild an insight from the JSON persisted on the Media row."""
    base = ImageInsight(media_id=media_id, width=width, height=height, landscape=width >= height)
    if not stored:
        return base
    return replace(
        base,
        brightness=float(stored.get("brightness", base.brightness)),
        region_brightness={k: float(v) for k, v in (stored.get("region_brightness") or {}).items()},
        contrast=float(stored.get("contrast", base.contrast)),
        focus_x=float(stored.get("focus_x", base.focus_x)),
        focus_y=float(stored.get("focus_y", base.focus_y)),
        dominant_colors=tuple(stored.get("dominant_colors") or ()),
    )


def crop_image(
    data: bytes, *, x: float, y: float, width: float, height: float, quality: int = 90
) -> OptimisedImage:
    """Crop using normalised [0,1] coordinates (requirement 4: crop in the uploader)."""
    image = _open_verified(data)
    image = ImageOps.exif_transpose(image)
    iw, ih = image.size
    left = max(0, min(int(x * iw), iw - 1))
    top = max(0, min(int(y * ih), ih - 1))
    right = max(left + 1, min(int((x + width) * iw), iw))
    bottom = max(top + 1, min(int((y + height) * ih), ih))
    cropped = image.crop((left, top, right, bottom))

    buffer = io.BytesIO()
    if cropped.mode in ("RGBA", "LA", "P"):
        cropped = cropped.convert("RGBA")
        cropped.save(buffer, format="PNG", optimize=True)
        return OptimisedImage(buffer.getvalue(), cropped.width, cropped.height, "PNG", "image/png")
    cropped = cropped.convert("RGB")
    cropped.save(buffer, format="JPEG", quality=quality, optimize=True)
    return OptimisedImage(buffer.getvalue(), cropped.width, cropped.height, "JPEG", "image/jpeg")
