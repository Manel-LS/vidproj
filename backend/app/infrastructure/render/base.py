"""RenderEngine abstraction.

The application service depends on this interface only, so a cloud renderer can be
dropped in later without touching anything above the infrastructure layer.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.domain.plan import VideoPlan

#: (percent 0..100, human-readable stage) -> None
ProgressReporter = Callable[[int, str], None]


@dataclass
class RenderRequest:
    plan: VideoPlan
    #: media_id -> local file path, resolved by the service from the storage provider.
    media_paths: dict[str, Path]
    output_path: Path
    work_dir: Path
    poster_path: Path | None = None
    #: Returns True when the job has been cancelled and the engine should stop.
    cancel_check: Callable[[], bool] = field(default=lambda: False)


@dataclass
class RenderResult:
    video_path: Path
    poster_path: Path | None
    duration: float
    width: int
    height: int
    size_bytes: int


class RenderEngine(abc.ABC):
    name: str = "abstract"

    @abc.abstractmethod
    def render(self, request: RenderRequest, on_progress: ProgressReporter) -> RenderResult: ...

    @abc.abstractmethod
    def is_available(self) -> bool: ...
