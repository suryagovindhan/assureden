"""
storage/__init__.py — Storage provider factory.

Usage:
  from app.storage import get_storage

  provider = get_storage()
  provider.save(key, data, content_type)
"""

from __future__ import annotations

from functools import lru_cache

from app.storage.base import StorageProvider


@lru_cache(maxsize=1)
def get_storage() -> StorageProvider:
    """
    Return the configured storage provider singleton.

    Controlled by ARTIFACT_STORAGE_PROVIDER env var:
      local     → LocalStorageProvider (default)
      s3        → (Phase 6+) S3StorageProvider
      gcs       → (Phase 6+) GCSStorageProvider
      azure     → (Phase 6+) AzureBlobStorageProvider
    """
    from app.core.config import settings
    provider = settings.ARTIFACT_STORAGE_PROVIDER.lower()

    if provider == "local":
        from app.storage.local import LocalStorageProvider
        return LocalStorageProvider()

    # Future providers registered here:
    # if provider == "s3":
    #     from app.storage.s3 import S3StorageProvider
    #     return S3StorageProvider()

    raise ValueError(
        f"Unknown ARTIFACT_STORAGE_PROVIDER: {provider!r}. "
        f"Supported: local"
    )
