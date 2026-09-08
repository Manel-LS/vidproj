"""The image animation engine (requirement 7) — pure geometry, no ffmpeg, no I/O.

A scene's motion is expressed as two `Viewport`s (start and end) that are linearly
interpolated over the scene duration. A `Viewport` describes the sub-rectangle of the
source image visible in the frame:

    zoom = 1.0  -> the whole (already cover-cropped) image fills the frame
    zoom = 1.4  -> a 1/1.4 sized window, i.e. zoomed in 40%
    cx, cy      -> the window centre in normalised source coordinates [0, 1]

The identical math is mirrored in `frontend/src/lib/video/animation.ts` so the browser
preview and the ffmpeg render agree frame for frame.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import AnimationType

MIN_ZOOM = 1.0
MAX_ZOOM = 2.5


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


@dataclass(frozen=True)
class Viewport:
    zoom: float = 1.0
    cx: float = 0.5
    cy: float = 0.5

    def normalised(self) -> "Viewport":
        """Clamp so the visible window never leaves the source image."""
        zoom = clamp(self.zoom, MIN_ZOOM, MAX_ZOOM)
        half = 0.5 / zoom
        return Viewport(
            zoom=zoom,
            cx=clamp(self.cx, half, 1.0 - half),
            cy=clamp(self.cy, half, 1.0 - half),
        )


@dataclass(frozen=True)
class Motion:
    start: Viewport
    end: Viewport
    rotation_start_deg: float = 0.0
    rotation_end_deg: float = 0.0
    # Opposite drift applied to text layers to fake depth for PARALLAX.
    parallax_px: float = 0.0

    def at(self, progress: float) -> Viewport:
        t = clamp(progress, 0.0, 1.0)
        s, e = self.start, self.end
        return Viewport(
            zoom=s.zoom + (e.zoom - s.zoom) * t,
            cx=s.cx + (e.cx - s.cx) * t,
            cy=s.cy + (e.cy - s.cy) * t,
        )

    def rotation_at(self, progress: float) -> float:
        t = clamp(progress, 0.0, 1.0)
        return self.rotation_start_deg + (self.rotation_end_deg - self.rotation_start_deg) * t

    @property
    def needs_rotation(self) -> bool:
        return abs(self.rotation_start_deg) > 1e-3 or abs(self.rotation_end_deg) > 1e-3

    @property
    def max_zoom(self) -> float:
        return max(self.start.zoom, self.end.zoom)


# Intensity scales how far each animation travels; styles pick a value in [0.5, 1.6].
def build_motion(
    animation: AnimationType,
    *,
    intensity: float = 1.0,
    focus: tuple[float, float] = (0.5, 0.5),
) -> Motion:
    """Translate a named animation into concrete start/end viewports.

    `focus` is the point of interest of the image (from image analysis); pans and
    zooms bias towards it so the subject stays in frame.
    """
    i = clamp(intensity, 0.3, 2.0)
    fx, fy = clamp(focus[0], 0.0, 1.0), clamp(focus[1], 0.0, 1.0)
    z_small = 1.0 + 0.08 * i
    z_med = 1.0 + 0.18 * i
    z_large = 1.0 + 0.34 * i
    pan_travel = 0.16 * i

    def vp(zoom: float, cx: float = None, cy: float = None) -> Viewport:
        return Viewport(zoom, fx if cx is None else cx, fy if cy is None else cy).normalised()

    if animation is AnimationType.NONE:
        return Motion(vp(1.0, 0.5, 0.5), vp(1.0, 0.5, 0.5))

    if animation is AnimationType.ZOOM_IN:
        return Motion(vp(1.0, 0.5, 0.5), vp(z_med))

    if animation is AnimationType.ZOOM_OUT:
        return Motion(vp(z_med), vp(1.0, 0.5, 0.5))

    if animation is AnimationType.SLOW_ZOOM:
        return Motion(vp(1.0, 0.5, 0.5), vp(z_small))

    if animation is AnimationType.DYNAMIC_ZOOM:
        return Motion(vp(z_large), vp(1.0 + 0.02 * i, 0.5, 0.5))

    if animation in (
        AnimationType.PAN_LEFT,
        AnimationType.PAN_RIGHT,
        AnimationType.PAN_UP,
        AnimationType.PAN_DOWN,
    ):
        zoom = z_med
        half = 0.5 / zoom
        span = min(pan_travel, max(0.0, 0.5 - half))
        dx = {AnimationType.PAN_LEFT: -1, AnimationType.PAN_RIGHT: 1}.get(animation, 0)
        dy = {AnimationType.PAN_UP: -1, AnimationType.PAN_DOWN: 1}.get(animation, 0)
        # Pan *towards* the direction: start offset opposite, end offset along.
        return Motion(
            Viewport(zoom, 0.5 - dx * span, 0.5 - dy * span).normalised(),
            Viewport(zoom, 0.5 + dx * span, 0.5 + dy * span).normalised(),
        )

    if animation is AnimationType.KEN_BURNS:
        # Zoom and drift simultaneously toward the focal point.
        start = Viewport(1.0 + 0.04 * i, 0.5, 0.5).normalised()
        end = Viewport(z_med + 0.06 * i, fx, fy).normalised()
        return Motion(start, end)

    if animation is AnimationType.ROTATE_SLIGHT:
        amount = 1.2 * i
        return Motion(
            vp(z_small + 0.06, 0.5, 0.5),
            vp(z_small + 0.10, 0.5, 0.5),
            rotation_start_deg=-amount,
            rotation_end_deg=amount,
        )

    if animation is AnimationType.PARALLAX:
        zoom = z_med
        half = 0.5 / zoom
        span = min(0.10 * i, max(0.0, 0.5 - half))
        return Motion(
            Viewport(zoom, 0.5 - span, 0.5).normalised(),
            Viewport(zoom, 0.5 + span, 0.5).normalised(),
            parallax_px=42.0 * i,
        )

    return Motion(vp(1.0, 0.5, 0.5), vp(z_small))


#: Animations that read well as the opening shot of a video.
OPENING_ANIMATIONS = (AnimationType.ZOOM_IN, AnimationType.DYNAMIC_ZOOM, AnimationType.KEN_BURNS)
