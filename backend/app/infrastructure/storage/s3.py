"""S3-compatible object storage (AWS S3, Cloudflare R2, MinIO, ...).

`boto3` is an optional dependency: the module imports lazily so a deployment that
uses local storage never needs it installed.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import BinaryIO

from app.core.errors import NotFoundError, ProviderUnavailableError
from app.infrastructure.storage.base import StorageProvider, StoredObject, build_key


class S3StorageProvider(StorageProvider):
    name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        region: str = "",
        endpoint_url: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        public_base_url: str = "",
        cache_dir: Path | None = None,
    ):
        try:
            import boto3  # noqa: PLC0415  (optional dependency)
        except ImportError as exc:  # pragma: no cover - depends on deployment
            raise ProviderUnavailableError(
                "S3 storage is selected but boto3 is not installed. "
                "Install it with `pip install boto3` or set STORAGE_PROVIDER=local."
            ) from exc

        if not bucket:
            raise ProviderUnavailableError("S3 storage requires S3_BUCKET to be set.")

        self.bucket = bucket
        self.public_base_url = (public_base_url or "").rstrip("/")
        self._cache_dir = Path(cache_dir or Path(tempfile.gettempdir()) / "reelcraft-s3-cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = boto3.client(
            "s3",
            region_name=region or None,
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
        )

    def upload(self, key: str, data: BinaryIO | bytes, *, content_type: str) -> StoredObject:
        key = build_key(key)
        body = bytes(data) if isinstance(data, (bytes, bytearray)) else data.read()
        self._client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)
        return StoredObject(key=key, size=len(body), content_type=content_type)

    def upload_file(self, key: str, path: Path, *, content_type: str) -> StoredObject:
        key = build_key(key)
        self._client.upload_file(
            str(path), self.bucket, key, ExtraArgs={"ContentType": content_type}
        )
        return StoredObject(key=key, size=path.stat().st_size, content_type=content_type)

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=build_key(key))
        cached = self._cache_path(key)
        if cached.is_file():
            cached.unlink()

    def get_url(self, key: str) -> str:
        key = build_key(key)
        if self.public_base_url:
            return f"{self.public_base_url}/{key}"
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=3600
        )

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        try:
            self._client.head_object(Bucket=self.bucket, Key=build_key(key))
            return True
        except ClientError:
            return False

    def open(self, key: str) -> BinaryIO:
        return self.local_path(key).open("rb")

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / build_key(key).replace("/", "__")

    def local_path(self, key: str) -> Path:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        target = self._cache_path(key)
        if target.is_file():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client.download_file(self.bucket, build_key(key), str(target))
        except ClientError as exc:
            raise NotFoundError("That file is no longer available.") from exc
        return target
