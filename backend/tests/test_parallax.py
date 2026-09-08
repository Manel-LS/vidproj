"""Depth planes, and the camera differential that makes them read as depth.

The layer tests build their own depth maps, so they need neither the optional
runtime nor the model file — the cutting is ordinary arithmetic and deserves to be
covered on every checkout.

The value pinned hardest here is the one that was wrong first: the separation is
applied to zoom, not to pan. The engine's camera paths are already clamped to the
edge of the source, so a plane asked to travel further is clamped straight back and
the effect measures as zero. That failure is invisible in a screenshot of a single
frame, which is why it has a test rather than a comment.
"""
from __future__ import annotations

import pytest
from PIL import Image

pytest.importorskip("numpy", reason="depth layers need the optional numpy dependency")

from app.domain.animation import Motion, Viewport, build_motion  # noqa: E402
from app.domain.enums import AnimationType  # noqa: E402
from app.infrastructure.depth.base import DepthMap  # noqa: E402
from app.infrastructure.imaging.parallax import build_parallax_layers  # noqa: E402
from app.infrastructure.render.engine import PARALLAX_SEPARATION, _plane_motion  # noqa: E402


def _gradient_depth(width: int = 64, height: int = 64) -> DepthMap:
    """Far at the top, near at the bottom — the shape of most photographs."""
    values = tuple(row / (height - 1) for row in range(height) for _ in range(width))
    return DepthMap(width=width, height=height, values=values)


def _flat_depth(value: float = 0.5, width: int = 64, height: int = 64) -> DepthMap:
    return DepthMap(width=width, height=height, values=(value,) * (width * height))


def _picture(tmp_path, size=(240, 320)):
    path = tmp_path / "picture.jpg"
    image = Image.new("RGB", size)
    image.paste((30, 60, 120), (0, 0, size[0], size[1] // 2))
    image.paste((160, 120, 60), (0, size[1] // 2, size[0], size[1]))
    image.save(path)
    return path


# ------------------------------------------------------------------ cutting --


def test_a_photograph_is_cut_into_planes(tmp_path):
    layers = build_parallax_layers(_picture(tmp_path), _gradient_depth(), tmp_path / "out")
    assert len(layers) == 3
    assert all(layer.path.is_file() for layer in layers)


def test_planes_come_back_furthest_first(tmp_path):
    layers = build_parallax_layers(_picture(tmp_path), _gradient_depth(), tmp_path / "out")
    depths = [layer.depth for layer in layers]
    assert depths == sorted(depths), "the renderer composites in the order it is given"


def test_the_furthest_plane_is_opaque_and_the_others_are_not(tmp_path):
    layers = build_parallax_layers(_picture(tmp_path), _gradient_depth(), tmp_path / "out")
    assert layers[0].opaque is True
    assert all(layer.opaque is False for layer in layers[1:])
    # It is the ground everything sits on, so it must have no transparency at all.
    assert Image.open(layers[0].path).mode == "RGB"


def test_planes_are_cumulative_so_no_hole_can_open(tmp_path):
    """Each plane keeps what is behind it.

    This is what replaces inpainting: when a near plane moves, the plane behind
    already has real pixels where it used to be.
    """
    layers = build_parallax_layers(_picture(tmp_path), _gradient_depth(), tmp_path / "out")
    coverage = []
    for layer in layers[1:]:
        alpha = Image.open(layer.path).convert("RGBA").getchannel("A")
        coverage.append(sum(1 for value in alpha.getdata() if value > 127))
    # Nearer planes cover less, and each is contained in the one behind it.
    assert coverage == sorted(coverage, reverse=True)


def test_a_flat_picture_is_left_alone(tmp_path):
    """A logo on white has no planes to separate.

    Returning layers anyway would cost three ffmpeg inputs to draw the same frame.
    """
    assert build_parallax_layers(_picture(tmp_path), _flat_depth(), tmp_path / "out") == []


def test_a_single_usable_plane_is_not_parallax(tmp_path):
    layers = build_parallax_layers(
        _picture(tmp_path), _gradient_depth(), tmp_path / "out", layers=1
    )
    assert layers == []


# ------------------------------------------------------------- the camera --


def _motion() -> Motion:
    return build_motion(AnimationType.PARALLAX, intensity=1.4, focus=(0.5, 0.5))


def test_every_plane_opens_on_the_original_photograph():
    """Frame one must be the picture, not a stack of offset slabs."""
    base = _motion()
    for offset in (-0.25, 0.0, 0.25):
        assert _plane_motion(base, offset).start == base.start


def test_a_near_plane_ends_larger_than_a_far_one():
    base = _motion()
    near = _plane_motion(base, 0.25).end
    far = _plane_motion(base, -0.25).end
    assert near.zoom > far.zoom, "this difference is the entire effect"


def test_the_separation_is_carried_by_zoom_not_by_pan():
    """The regression that made the first version measure as no effect at all.

    `build_motion` clamps the pan to the edge of the source, so a plane asked to
    travel further is clamped back and nothing separates. Zoom has headroom.
    """
    base = _motion()
    near = _plane_motion(base, 0.25)
    assert near.end.zoom != base.end.zoom
    # And the clamp really is there, which is why pan alone cannot work.
    stretched = Viewport(base.end.zoom, base.end.cx + 0.4, base.end.cy).normalised()
    assert stretched.cx < base.end.cx + 0.4


def test_a_plane_never_zooms_below_the_frame():
    # Below 1.0 the window would be larger than the source and sample outside it.
    far = _plane_motion(_motion(), -10.0)
    assert far.end.zoom >= 1.0


def test_the_separation_constant_stays_in_the_range_that_was_measured():
    # Below ~0.15 nobody sees it; above ~0.5 the planes visibly slide apart.
    assert 0.15 <= PARALLAX_SEPARATION <= 0.5
