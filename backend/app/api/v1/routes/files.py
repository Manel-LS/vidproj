"""Serves blobs from the local storage provider during development.

In production, `STORAGE_PROVIDER=s3` and `S3_PUBLIC_BASE_URL` (or a CDN) serve these
directly and this router is never hit.

Two properties matter here:
  * the key is resolved through the storage provider, which refuses to escape its root;
  * responses carry `X-Content-Type-Options: nosniff` and a fixed content type, so a
    stored file cannot be coaxed into executing as HTML in the user's browser.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response

from app.api.deps import rate_limit
from app.core.config import settings
from app.core.errors import NotFoundError
from app.infrastructure.storage.factory import get_storage
from app.infrastructure.storage.local import LocalStorageProvider

router = APIRouter(prefix="/files", tags=["files"], dependencies=[Depends(rate_limit)])

_SAFE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


@router.get("/{key:path}", summary="Fetch a stored file (development storage)")
def get_file(key: str, request: Request) -> Response:
    storage = get_storage()
    if not isinstance(storage, LocalStorageProvider):
        raise NotFoundError("Files are served directly by the storage provider.")

    path: Path = storage.local_path(key)
    suffix = path.suffix.lower()
    content_type = _SAFE_TYPES.get(suffix)
    if content_type is None:
        guessed, _ = mimetypes.guess_type(path.name)
        content_type = guessed if (guessed or "").split("/")[0] in ("image", "video", "audio") else "application/octet-stream"

    return FileResponse(
        path,
        media_type=content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600" if settings.environment != "development" else "no-cache",
            "Content-Disposition": "inline",
        },
    )
