"""Local filesystem storage — the development default."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from app.core.errors import NotFoundError
from app.infrastructure.storage.base import StorageProvider, StoredObject, build_key


class LocalStorageProvider(StorageProvider):
    name = "local"

    def __init__(self, root: Path, public_base_url: str):
        self.root = Path(root).resolve()
        self.public_base_url = public_base_url.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    # -- internal ------------------------------------------------------------

    def _resolve(self, key: str) -> Path:
        """Map a key to a path, guaranteed to stay inside the storage root."""
        safe_key = build_key(key)
        if not safe_key:
            raise ValueError("Empty storage key.")
        path = (self.root / safe_key).resolve()
        if not str(path).startswith(str(self.root)):
            raise ValueError("Storage key escapes the storage root.")
        return path

    # -- StorageProvider -----------------------------------------------------

    def upload(self, key: str, data: BinaryIO | bytes, *, content_type: str) -> StoredObject:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (bytes, bytearray)):
            path.write_bytes(bytes(data))
        else:
            with path.open("wb") as out:
                shutil.copyfileobj(data, out)
        return StoredObject(key=build_key(key), size=path.stat().st_size, content_type=content_type)

    def upload_file(self, key: str, path: Path, *, content_type: str) -> StoredObject:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        return StoredObject(key=build_key(key), size=target.stat().st_size, content_type=content_type)

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink()

    def get_url(self, key: str) -> str:
        """A URL for the browser.

        Relative by default (`/api/v1/files/...`), which the client resolves against
        the API host it is already talking to.
        """
        return f"{self.public_base_url}/{build_key(key)}"

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def open(self, key: str) -> BinaryIO:
        path = self._resolve(key)
        if not path.is_file():
            raise NotFoundError("That file is no longer available.")
        return path.open("rb")

    def local_path(self, key: str) -> Path:
        path = self._resolve(key)
        if not path.is_file():
            raise NotFoundError("That file is no longer available.")
        return path
