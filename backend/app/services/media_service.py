"""Media upload, validation, optimisation and ordering (requirements 4 and 20).

Every uploaded byte goes through the same gate:

  1. size limit enforced while streaming, before anything is buffered whole;
  2. content sniffed by actually decoding it — the client's declared MIME type and the
     file extension are treated as hints, never as facts;
  3. re-encoded by Pillow, which drops EXIF, any embedded payload, and any
     polyglot trickery, so what we store is a file we produced ourselves.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.domain.enums import MediaKind
from app.infrastructure.imaging.analyzer import (
    analyse,
    crop_image,
    make_thumbnail,
    optimise_upload,
)
from app.infrastructure.render.ffmpeg import probe_duration
from app.infrastructure.storage.base import StorageProvider, unique_key
from app.infrastructure.storage.factory import get_storage
from app.models import Media, Project

logger = get_logger(__name__)

#: Magic-number prefixes we accept for audio. Images are validated by decoding them.
_AUDIO_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"ID3", "audio/mpeg"),
    (b"\xff\xfb", "audio/mpeg"),
    (b"\xff\xf3", "audio/mpeg"),
    (b"\xff\xf2", "audio/mpeg"),
    (b"RIFF", "audio/wav"),
)


@dataclass
class UploadPayload:
    filename: str
    content_type: str
    data: bytes


def read_upload(file, *, max_bytes: int, label: str) -> bytes:
    """Read an UploadFile, refusing anything over the limit without buffering it all."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 256)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValidationError(
                f"{label} is larger than {max_bytes // (1024 * 1024)} MB. "
                "Please upload a smaller file."
            )
        chunks.append(chunk)
    if total == 0:
        raise ValidationError(f"{label} is empty.")
    return b"".join(chunks)


def _project_media_prefix(project: Project) -> str:
    return f"users/{project.user_id}/projects/{project.id}/media"


def next_position(session: Session, project_id: str) -> int:
    current = session.scalar(
        select(func.max(Media.position)).where(
            Media.project_id == project_id, Media.kind == MediaKind.IMAGE.value
        )
    )
    return (current or 0) + 1


def count_images(session: Session, project_id: str) -> int:
    return int(
        session.scalar(
            select(func.count(Media.id)).where(
                Media.project_id == project_id, Media.kind == MediaKind.IMAGE.value
            )
        )
        or 0
    )


def add_image(
    session: Session,
    project: Project,
    payload: UploadPayload,
    *,
    storage: StorageProvider | None = None,
    source: str = "upload",
) -> Media:
    """Validate, optimise, analyse and store one image.

    `source` distinguishes a user upload from an image this app generated, so the
    pipeline can clean up its own output without ever touching the user's files.
    """
    storage = storage or get_storage()

    if payload.content_type and payload.content_type not in settings.allowed_image_mimes:
        # A wrong header is not fatal on its own — decoding decides — but an obviously
        # unsupported type is worth rejecting early with a clear message.
        if not payload.content_type.startswith("image/"):
            raise ValidationError(
                "Only JPG, PNG and WEBP images are supported. "
                f"That file looked like '{payload.content_type}'."
            )

    if count_images(session, project.id) >= settings.max_images_per_project:
        raise ValidationError(
            f"This project already has the maximum of {settings.max_images_per_project} images."
        )

    optimised = optimise_upload(payload.data, max_dimension=settings.image_max_dimension)
    thumbnail = make_thumbnail(optimised.data)

    extension = "png" if optimised.content_type == "image/png" else "jpg"
    key = unique_key(_project_media_prefix(project), payload.filename or f"image.{extension}", default_ext=extension)
    thumb_key = f"{key.rsplit('.', 1)[0]}-thumb.jpg"

    storage.upload(key, optimised.data, content_type=optimised.content_type)
    storage.upload(thumb_key, thumbnail.data, content_type="image/jpeg")

    media = Media(
        user_id=project.user_id,
        project_id=project.id,
        kind=MediaKind.IMAGE.value,
        source=source,
        storage_key=key,
        thumbnail_key=thumb_key,
        original_filename=(payload.filename or "")[:255],
        content_type=optimised.content_type,
        size_bytes=optimised.size,
        width=optimised.width,
        height=optimised.height,
        position=next_position(session, project.id),
        analysis=_analysis_dict(optimised.data, ""),
    )
    session.add(media)
    session.flush()
    media.analysis = _analysis_dict(optimised.data, media.id)
    session.flush()
    return media


def _analysis_dict(data: bytes, media_id: str) -> dict:
    insight = analyse(data, media_id)
    return {
        "brightness": insight.brightness,
        "region_brightness": insight.region_brightness,
        "contrast": insight.contrast,
        "focus_x": insight.focus_x,
        "focus_y": insight.focus_y,
        "dominant_colors": list(insight.dominant_colors),
    }


def sniff_audio(data: bytes, declared: str) -> str:
    for signature, content_type in _AUDIO_SIGNATURES:
        if data.startswith(signature):
            if content_type == "audio/wav" and data[8:12] != b"WAVE":
                continue
            return content_type
    raise ValidationError(
        "That file is not a readable MP3 or WAV audio file. "
        f"(The browser reported '{declared or 'unknown'}'.)"
    )


def add_audio(
    session: Session,
    project: Project,
    payload: UploadPayload,
    *,
    storage: StorageProvider | None = None,
    source: str = "upload",
) -> Media:
    storage = storage or get_storage()
    content_type = sniff_audio(payload.data, payload.content_type)
    extension = "mp3" if content_type == "audio/mpeg" else "wav"

    key = unique_key(
        f"users/{project.user_id}/projects/{project.id}/audio",
        payload.filename or f"track.{extension}",
        default_ext=extension,
    )
    storage.upload(key, payload.data, content_type=content_type)

    media = Media(
        user_id=project.user_id,
        project_id=project.id,
        kind=MediaKind.AUDIO.value,
        source=source,
        storage_key=key,
        original_filename=(payload.filename or "")[:255],
        content_type=content_type,
        size_bytes=len(payload.data),
        position=0,
    )
    session.add(media)
    session.flush()

    try:
        media.duration_seconds = probe_duration(storage.local_path(key))
    except Exception:  # pragma: no cover - duration is a nicety, not a requirement
        logger.debug("Could not probe duration for %s", key)
    session.flush()
    return media


def store_generated_file(
    session: Session,
    project: Project,
    *,
    data: bytes | Path,
    filename: str,
    content_type: str,
    kind: MediaKind,
    source: str,
    storage: StorageProvider | None = None,
) -> Media:
    """Persist something the system produced (a render, a voice-over, an AI clip)."""
    storage = storage or get_storage()
    key = unique_key(
        f"users/{project.user_id}/projects/{project.id}/{source}",
        filename,
        default_ext=filename.rsplit(".", 1)[-1] if "." in filename else "bin",
    )
    if isinstance(data, Path):
        stored = storage.upload_file(key, data, content_type=content_type)
    else:
        stored = storage.upload(key, data, content_type=content_type)

    media = Media(
        user_id=project.user_id,
        project_id=project.id,
        kind=kind.value,
        source=source,
        storage_key=stored.key,
        original_filename=filename[:255],
        content_type=content_type,
        size_bytes=stored.size,
    )
    session.add(media)
    session.flush()
    return media


def get_media(session: Session, media_id: str, *, user_id: str) -> Media:
    media = session.get(Media, media_id)
    if media is None or media.user_id != user_id:
        raise NotFoundError("That file could not be found.")
    return media


def delete_media(session: Session, media: Media, *, storage: StorageProvider | None = None) -> None:
    storage = storage or get_storage()
    for key in (media.storage_key, media.thumbnail_key):
        if key:
            try:
                storage.delete(key)
            except Exception:  # pragma: no cover - orphaned blobs are not fatal
                logger.warning("Could not delete stored object %s", key)
    session.delete(media)
    session.flush()


def reorder_images(session: Session, project: Project, ordered_ids: list[str]) -> list[Media]:
    """Apply an explicit order. Unlisted images keep their relative order at the end."""
    images = {
        media.id: media
        for media in project.media
        if media.kind == MediaKind.IMAGE.value
    }
    unknown = [media_id for media_id in ordered_ids if media_id not in images]
    if unknown:
        raise ValidationError("The reorder request referenced images that are not in this project.")

    position = 1
    for media_id in ordered_ids:
        images[media_id].position = position
        position += 1
    for media in sorted(images.values(), key=lambda m: m.position):
        if media.id not in ordered_ids:
            media.position = position
            position += 1

    session.flush()
    return sorted(images.values(), key=lambda m: m.position)


def replace_image(
    session: Session,
    project: Project,
    media: Media,
    payload: UploadPayload,
    *,
    storage: StorageProvider | None = None,
) -> Media:
    """Swap the bytes behind an existing media row, keeping its id and position.

    Keeping the id means every scene that points at this image keeps working.
    """
    storage = storage or get_storage()
    optimised = optimise_upload(payload.data, max_dimension=settings.image_max_dimension)
    thumbnail = make_thumbnail(optimised.data)

    old_keys = [media.storage_key, media.thumbnail_key]
    extension = "png" if optimised.content_type == "image/png" else "jpg"
    key = unique_key(_project_media_prefix(project), payload.filename or f"image.{extension}", default_ext=extension)
    thumb_key = f"{key.rsplit('.', 1)[0]}-thumb.jpg"

    storage.upload(key, optimised.data, content_type=optimised.content_type)
    storage.upload(thumb_key, thumbnail.data, content_type="image/jpeg")

    media.storage_key = key
    media.thumbnail_key = thumb_key
    media.content_type = optimised.content_type
    media.size_bytes = optimised.size
    media.width = optimised.width
    media.height = optimised.height
    media.original_filename = (payload.filename or media.original_filename)[:255]
    media.analysis = _analysis_dict(optimised.data, media.id)
    session.flush()

    for old in old_keys:
        if old:
            try:
                storage.delete(old)
            except Exception:  # pragma: no cover
                logger.warning("Could not delete replaced object %s", old)
    return media


def crop_media(
    session: Session,
    media: Media,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    storage: StorageProvider | None = None,
) -> Media:
    """Crop in place using normalised coordinates."""
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < width <= 1 and 0 < height <= 1):
        raise ValidationError("The crop rectangle must be inside the image.")
    if x + width > 1.001 or y + height > 1.001:
        raise ValidationError("The crop rectangle extends past the edge of the image.")

    storage = storage or get_storage()
    original = storage.read_bytes(media.storage_key)
    cropped = crop_image(original, x=x, y=y, width=width, height=height)
    thumbnail = make_thumbnail(cropped.data)

    storage.upload(media.storage_key, cropped.data, content_type=cropped.content_type)
    if media.thumbnail_key:
        storage.upload(media.thumbnail_key, thumbnail.data, content_type="image/jpeg")

    media.content_type = cropped.content_type
    media.size_bytes = cropped.size
    media.width = cropped.width
    media.height = cropped.height
    media.analysis = _analysis_dict(cropped.data, media.id)
    session.flush()
    return media


def media_url(media: Media, *, storage: StorageProvider | None = None) -> str:
    return (storage or get_storage()).get_url(media.storage_key)


def thumbnail_url(media: Media, *, storage: StorageProvider | None = None) -> str | None:
    if not media.thumbnail_key:
        return None
    return (storage or get_storage()).get_url(media.thumbnail_key)


def project_images(project: Project) -> list[Media]:
    return sorted(
        (m for m in project.media if m.kind == MediaKind.IMAGE.value),
        key=lambda m: (m.position, m.created_at),
    )
