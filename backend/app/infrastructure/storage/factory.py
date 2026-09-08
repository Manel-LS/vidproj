"""Storage provider selection."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.infrastructure.storage.base import StorageProvider
from app.infrastructure.storage.local import LocalStorageProvider


@lru_cache
def get_storage() -> StorageProvider:
    if settings.storage_provider == "s3":
        from app.infrastructure.storage.s3 import S3StorageProvider

        return S3StorageProvider(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            public_base_url=settings.s3_public_base_url,
        )
    return LocalStorageProvider(
        root=settings.storage_local_root,
        public_base_url=settings.storage_public_base_url,
    )
