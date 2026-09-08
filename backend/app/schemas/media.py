from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import MediaKind
from app.schemas.common import APIModel


class MediaResponse(APIModel):
    id: str
    kind: MediaKind
    source: str
    url: str
    thumbnail_url: str | None = None
    original_filename: str
    content_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    position: int
    created_at: datetime
    #: Image analysis, exposed so the editor can show the detected focal point.
    analysis: dict = Field(default_factory=dict)


class ReorderMediaRequest(BaseModel):
    media_ids: list[str] = Field(min_length=1, max_length=100)


class CropRequest(BaseModel):
    """Crop rectangle in normalised [0, 1] image coordinates."""

    x: float = Field(ge=0.0, lt=1.0)
    y: float = Field(ge=0.0, lt=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)


class AudioTrackResponse(APIModel):
    id: str
    media_id: str | None
    media: MediaResponse | None = None
    volume: float
    fade_in: float
    fade_out: float
    start_offset: float
    loop: bool
    library_track_key: str | None = None


class AudioTrackUpdate(BaseModel):
    media_id: str | None = None
    volume: float | None = Field(default=None, ge=0.0, le=1.5)
    fade_in: float | None = Field(default=None, ge=0.0, le=10.0)
    fade_out: float | None = Field(default=None, ge=0.0, le=10.0)
    start_offset: float | None = Field(default=None, ge=0.0, le=3600.0)
    loop: bool | None = None
    #: Set explicitly to detach the current track.
    clear: bool = False


class LibraryTrack(BaseModel):
    """A slot in the future royalty-free music library (requirement 10).

    The catalogue is served from configuration rather than bundled audio: the product
    must not ship music it does not have a licence for.
    """

    key: str
    title: str
    mood: str
    bpm: int
    duration_seconds: float
    licence: str
    available: bool
    url: str | None = None
