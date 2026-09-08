"""Filtergraph construction.

Every value written here is a validated number or an enum-mapped constant. Nothing
that came from a user or an LLM as free text is ever interpolated into a filter.
"""
from __future__ import annotations

from app.domain.animation import Motion
from app.domain.enums import TransitionType
from app.infrastructure.render.ffmpeg import supported_xfade_transitions

#: Domain transition -> the xfade name we prefer, then progressively safer fallbacks.
_XFADE_MAP: dict[TransitionType, tuple[str, ...]] = {
    TransitionType.FADE: ("fade",),
    TransitionType.CROSS_DISSOLVE: ("dissolve", "fade"),
    TransitionType.SLIDE_LEFT: ("smoothleft", "slideleft", "fade"),
    TransitionType.SLIDE_RIGHT: ("smoothright", "slideright", "fade"),
    TransitionType.PUSH: ("slideleft", "smoothleft", "fade"),
    TransitionType.ZOOM: ("zoomin", "circleopen", "fade"),
    TransitionType.BLUR: ("hblur", "fadeblack", "fade"),
    TransitionType.WIPE: ("wipeleft", "wiperight", "fade"),
}


def xfade_name(transition: TransitionType) -> str:
    available = supported_xfade_transitions()
    for candidate in _XFADE_MAP.get(transition, ("fade",)):
        if candidate in available:
            return candidate
    return "fade"


def _n(value: float, places: int = 6) -> str:
    """Format a float for a filter expression, without scientific notation."""
    return f"{float(value):.{places}f}".rstrip("0").rstrip(".") or "0"


def zoompan_filter(motion: Motion, *, frames: int, out_w: int, out_h: int, fps: int) -> str:
    """Linear (zoom, centre) interpolation over `frames` output frames.

    `zoompan` gives x/y as the top-left of the crop window in *input* coordinates and
    sizes that window as `iw/zoom x ih/zoom`, so a normalised centre `c` becomes
    `c*iw - (iw/zoom)/2`. Because the source has already been supersampled, the
    integer rounding zoompan applies to x/y is sub-pixel at output resolution, which
    is what removes the jitter this filter is notorious for.
    """
    last = max(1, frames - 1)
    start, end = motion.start.normalised(), motion.end.normalised()

    progress = f"(on/{last})"
    zoom_expr = f"{_n(start.zoom)}+({_n(end.zoom - start.zoom)})*{progress}"
    cx_expr = f"{_n(start.cx)}+({_n(end.cx - start.cx)})*{progress}"
    cy_expr = f"{_n(start.cy)}+({_n(end.cy - start.cy)})*{progress}"

    # Clamp inside the source so a rounding error can never sample outside the image.
    x_expr = f"max(0\\,min(iw-iw/zoom\\,({cx_expr})*iw-(iw/zoom)/2))"
    y_expr = f"max(0\\,min(ih-ih/zoom\\,({cy_expr})*ih-(ih/zoom)/2))"

    return (
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}'"
        f":d={frames}:s={out_w}x{out_h}:fps={fps}"
    )


def rotate_filter(motion: Motion, *, duration: float) -> str:
    """Time-interpolated rotation. Applied on an overscanned frame, then centre-cropped."""
    import math

    a0 = math.radians(motion.rotation_start_deg)
    a1 = math.radians(motion.rotation_end_deg)
    duration = max(duration, 0.001)
    return (
        f"rotate=a='{_n(a0)}+({_n(a1 - a0)})*min(t/{_n(duration)}\\,1)'"
        f":c=none:ow=iw:oh=ih"
    )


def overlay_filter(
    *,
    x: int,
    y: int,
    start: float,
    end: float,
    drift_px: float = 0.0,
) -> str:
    """Place a text layer. `drift_px` gives the parallax counter-motion."""
    if abs(drift_px) > 0.01:
        span = max(end - start, 0.001)
        x_expr = f"'{_n(x)}+({_n(drift_px)})*min(max((t-{_n(start)})/{_n(span)}\\,0)\\,1)'"
    else:
        x_expr = str(int(x))
    return (
        f"overlay=x={x_expr}:y={int(y)}"
        f":enable='between(t\\,{_n(start)}\\,{_n(end)})'"
        f":format=auto:eval=frame"
    )


def xfade_filter(transition: TransitionType, *, duration: float, offset: float) -> str:
    return (
        f"xfade=transition={xfade_name(transition)}"
        f":duration={_n(max(duration, 0.04))}:offset={_n(max(offset, 0.0))}"
    )


def music_filter_chain(
    *,
    total_duration: float,
    volume: float,
    fade_in: float,
    fade_out: float,
    start_offset: float,
) -> str:
    """Trim/level/fade a background track to exactly the video length."""
    parts = [f"atrim=start={_n(start_offset)}:end={_n(start_offset + total_duration)}", "asetpts=PTS-STARTPTS"]
    if fade_in > 0:
        parts.append(f"afade=t=in:st=0:d={_n(min(fade_in, total_duration / 2))}")
    if fade_out > 0:
        fade_out = min(fade_out, total_duration / 2)
        parts.append(f"afade=t=out:st={_n(max(0.0, total_duration - fade_out))}:d={_n(fade_out)}")
    parts.append(f"volume={_n(max(0.0, volume))}")
    parts.append("aresample=48000")
    return ",".join(parts)


def voice_filter_chain(*, total_duration: float, volume: float) -> str:
    return ",".join([
        "asetpts=PTS-STARTPTS",
        f"apad=whole_dur={_n(total_duration)}",
        f"atrim=end={_n(total_duration)}",
        f"volume={_n(max(0.0, volume))}",
        "aresample=48000",
    ])
