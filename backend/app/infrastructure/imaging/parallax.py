"""Splitting a still into depth layers, so a camera move gives it volume.

The effect is old and well understood: cut the picture into a few planes by
distance, move the near ones further than the far ones, and the eye reads depth.
What makes or breaks it is what sits *behind* the near plane once it has moved —
slide a foreground across and you expose pixels it was covering.

The answer here is cumulative planes rather than inpainting. Each layer keeps
everything at its depth **and beyond**, so the plane behind always has real
content exactly where the plane in front used to be. A first version diffused
neighbouring pixels into the holes; measuring it showed the holes never occur,
and forty lines of plausible-looking fill were doing nothing at all.

Deliberately few layers. Three planes read as depth; twelve read as a stack of
cardboard, cost twelve ffmpeg inputs, and multiply the edge artefacts by four.

numpy is imported inside the functions: it arrives with the optional depth
runtime, and nothing here is reachable without a depth map anyway.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter

from app.core.logging import get_logger
from app.infrastructure.depth.base import DepthMap

logger = get_logger(__name__)

#: Three planes: background, subject, foreground.
DEFAULT_LAYERS = 3
#: Softness of the cut between planes, as a fraction of the frame's short side.
#: A hard edge is what makes 2.5D look like cut-out paper.
FEATHER_PCT = 0.012


@dataclass(frozen=True)
class ParallaxLayer:
    """One depth plane, ready to be handed to ffmpeg as its own input."""

    path: Path
    #: Mean depth of the plane, 0 far and 1 near. The renderer scales the camera
    #: move by this, which is the whole effect.
    depth: float
    #: The furthest plane is opaque and complete; the others carry alpha.
    opaque: bool

    @property
    def is_background(self) -> bool:
        return self.opaque


def _to_depth_image(depth: DepthMap, size: tuple[int, int]) -> Image.Image:
    """The depth map as an 8-bit image at the picture's own size.

    The model works on a small square, so the map has to be stretched back. It is
    also blurred slightly: the raw prediction has block edges from the patch grid,
    and those edges would become visible seams between planes.
    """
    raw = Image.new("L", (depth.width, depth.height))
    raw.putdata([int(round(value * 255)) for value in depth.values])
    resized = raw.resize(size, Image.BICUBIC)
    radius = max(1.0, min(size) * 0.004)
    return resized.filter(ImageFilter.GaussianBlur(radius))


def build_parallax_layers(
    image_path: Path,
    depth: DepthMap,
    output_dir: Path,
    *,
    layers: int = DEFAULT_LAYERS,
) -> list[ParallaxLayer]:
    """Cut `image_path` into depth planes, furthest first.

    Returns an empty list when the picture has no usable depth structure — a flat
    graphic, a screenshot, a product on white. Displacing planes that all sit at
    the same distance costs three ffmpeg inputs to produce the same frame, so the
    caller falls back to the ordinary camera move.
    """
    import numpy as np  # noqa: PLC0415

    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as handle:
        picture = handle.convert("RGB")

    depth_image = _to_depth_image(depth, picture.size)
    d = np.asarray(depth_image, dtype=np.float32) / 255.0

    # Cut at quantiles, not at even thresholds: an image whose depth sits mostly
    # in one band would otherwise put every pixel in one plane and leave the
    # others empty, and we would pay for inputs that draw nothing.
    edges = [float(np.quantile(d, q)) for q in np.linspace(0.0, 1.0, layers + 1)]
    edges[0], edges[-1] = -0.001, 1.001
    for index in range(1, len(edges)):
        edges[index] = max(edges[index], edges[index - 1] + 1e-4)

    # Planes separated by less than this are not telling us anything the camera
    # move would show; treat the picture as flat and let the caller skip it.
    if edges[-2] - edges[1] < 0.05:
        logger.info("Parallax skipped for %s: depth is too uniform to read", image_path.name)
        return []

    rgb = np.asarray(picture, dtype=np.uint8)
    feather = max(1.0, min(picture.size) * FEATHER_PCT)
    built: list[ParallaxLayer] = []

    for index in range(layers):
        low, high = edges[index], edges[index + 1]
        band = (d >= low) & (d < high)
        if not band.any():
            continue

        # Every plane also carries what is behind it, so a gap opened by the plane
        # in front is filled with real pixels rather than with a hole.
        covered = d >= low
        alpha = np.where(covered, 255, 0).astype(np.uint8)
        alpha_image = Image.fromarray(alpha, mode="L").filter(ImageFilter.GaussianBlur(feather))

        is_background = index == 0
        if is_background:
            # The furthest plane is the whole picture: `covered` is everything at
            # its depth or nearer, and it is the furthest, so nothing is missing.
            # Saved without alpha — it is the ground everything else sits on.
            layer = Image.fromarray(rgb, mode="RGB")
            path = output_dir / f"layer-{index}.jpg"
            layer.save(path, quality=95)
        else:
            layer = Image.fromarray(rgb, mode="RGB").convert("RGBA")
            layer.putalpha(alpha_image)
            path = output_dir / f"layer-{index}.png"
            layer.save(path)

        built.append(
            ParallaxLayer(
                path=path,
                depth=float(d[band].mean()),
                opaque=is_background,
            )
        )

    # One plane is not parallax. Say so by returning nothing rather than by
    # rendering an effect that cannot move.
    return built if len(built) >= 2 else []
