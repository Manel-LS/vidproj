"""StorageProvider abstraction (requirement 22)."""
from __future__ import annotations

import abc
import posixpath
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    content_type: str


def sanitize_filename(name: str, *, default_ext: str = "bin") -> str:
    """Reduce an untrusted filename to a safe, flat basename.

    Directory traversal is impossible by construction: separators and dots that
    could form `..` are stripped before the name is rebuilt.
    """
    name = (name or "").strip().replace("\\", "/")
    base = posixpath.basename(name)
    stem, _, ext = base.rpartition(".")
    if not stem:
        stem, ext = base, default_ext
    stem = _SAFE_SEGMENT.sub("-", stem).strip("-.")[:60] or "file"
    ext = _SAFE_SEGMENT.sub("", ext).lower()[:8] or default_ext
    return f"{stem}.{ext}"


def build_key(*parts: str) -> str:
    """Join key segments, sanitising each. Never yields an absolute or `..` path."""
    cleaned = []
    for part in parts:
        for segment in str(part).replace("\\", "/").split("/"):
            segment = _SAFE_SEGMENT.sub("-", segment).strip("-.")
            if segment and segment not in (".", ".."):
                cleaned.append(segment)
    return "/".join(cleaned)


def unique_key(prefix: str, filename: str, *, default_ext: str = "bin") -> str:
    safe = sanitize_filename(filename, default_ext=default_ext)
    return build_key(prefix, f"{uuid.uuid4().hex[:16]}-{safe}")


class StorageProvider(abc.ABC):
    """A flat key/value blob store. Keys look like `users/1/projects/2/media/x.jpg`."""

    name: str = "abstract"

    @abc.abstractmethod
    def upload(self, key: str, data: BinaryIO | bytes, *, content_type: str) -> StoredObject:
        """Store bytes under `key`, replacing anything already there."""

    @abc.abstractmethod
    def upload_file(self, key: str, path: Path, *, content_type: str) -> StoredObject:
        """Store a local file under `key`."""

    @abc.abstractmethod
    def delete(self, key: str) -> None:
        """Remove `key`. Deleting a missing key is not an error."""

    @abc.abstractmethod
    def get_url(self, key: str) -> str:
        """A URL the browser can fetch."""

    @abc.abstractmethod
    def exists(self, key: str) -> bool: ...

    @abc.abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Open the object for reading."""

    @abc.abstractmethod
    def local_path(self, key: str) -> Path:
        """A path on the local filesystem, materialising the object if needed.

        FFmpeg needs real files; remote providers download to a cache directory.
        """

    def read_bytes(self, key: str) -> bytes:
        with self.open(key) as handle:
            return handle.read()
