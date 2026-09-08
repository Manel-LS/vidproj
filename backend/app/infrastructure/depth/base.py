"""DepthProvider: estimating how far away each pixel is.

A depth map is what turns a still photograph into a shot with volume: the camera
moves, and the foreground shifts further than the background. Without one, a
"parallax" animation can only slide the whole picture, which is the flat effect
the renderer already has.

Two rules this abstraction exists to hold.

**Depth is estimated on the source image, never on a composited frame.** A model
asked for the depth of a frame that already carries burned-in text reads the text
panels as physical objects — measured, not guessed — and the parallax then peels
the captions off the picture.

**An unavailable estimator is reported, not faked.** There is no plausible depth
map to invent for an image; a scene without one keeps the flat animation it has
today and the UI says why.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass(frozen=True)
class DepthMap:
    """Normalised depth, row-major, one float per pixel in [0, 1].

    1.0 is nearest to the camera and 0.0 is furthest — the convention the renderer
    displaces by, so a bigger value means a bigger shift.
    """

    width: int
    height: int
    #: Flat tuple of `width * height` values. A plain sequence rather than a numpy
    #: array so the domain and the tests never need numpy to read one.
    values: tuple[float, ...]

    def at(self, x: int, y: int) -> float:
        return self.values[y * self.width + x]

    # There is deliberately no "is this image flat enough to skip" helper here.
    # The obvious one — the spread of these values — cannot answer it: the map is
    # normalised to [0, 1], so a screenshot of a web page and a landscape both
    # come back spanning almost the full range. Measured, not assumed. Anything
    # that wants to judge flatness has to do it on the raw prediction, inside the
    # provider that still has it.


class DepthUnavailable(RuntimeError):
    """No estimator is configured, or the model could not be run."""


class DepthProvider(abc.ABC):
    name: str = "abstract"
    display_name: str = "Abstract"

    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @abc.abstractmethod
    def estimate(self, image_path, *, max_size: int = 518) -> DepthMap:
        """Depth for one image. Raises `DepthUnavailable` rather than returning a guess."""


class NullDepthProvider(DepthProvider):
    """Used when no estimator is configured.

    Reports itself unavailable so the renderer keeps the flat parallax it already
    has and the UI can explain the difference, instead of failing at render time.
    """

    name = "none"
    display_name = "Not configured"

    def is_available(self) -> bool:
        return False

    def estimate(self, image_path, *, max_size: int = 518) -> DepthMap:
        raise DepthUnavailable(
            "Depth-based parallax is unavailable because no depth model is configured. "
            "Install the optional dependencies and run `python scripts/fetch_depth_model.py`."
        )
