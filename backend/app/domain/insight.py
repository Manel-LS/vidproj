"""Image analysis results consumed by the planner.

Produced by `infrastructure.imaging.analyzer` (Pillow). Kept in the domain so the
planner stays free of any I/O dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImageInsight:
    media_id: str
    width: int
    height: int
    #: Mean luminance 0..1 of the whole frame.
    brightness: float = 0.5
    #: Mean luminance of the region where text will sit, per position key.
    region_brightness: dict[str, float] = field(default_factory=dict)
    #: Standard deviation of luminance — a proxy for visual business.
    contrast: float = 0.2
    #: Estimated subject centre in normalised coordinates.
    focus_x: float = 0.5
    focus_y: float = 0.5
    #: Up to three dominant colours as #RRGGBB.
    dominant_colors: tuple[str, ...] = ()
    #: True when the source is wider than it is tall.
    landscape: bool = False

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 1.0

    @property
    def is_dark(self) -> bool:
        return self.brightness < 0.42

    def brightness_at(self, position: str) -> float:
        return self.region_brightness.get(position, self.brightness)

    def needs_text_scrim(self, position: str) -> bool:
        """Busy or bright backgrounds need a plate behind the text to stay legible."""
        region = self.brightness_at(position)
        return region > 0.58 or self.contrast > 0.30


def neutral_insight(media_id: str, width: int = 1080, height: int = 1920) -> ImageInsight:
    return ImageInsight(media_id=media_id, width=width, height=height)
