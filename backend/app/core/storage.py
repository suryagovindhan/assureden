"""
core/storage.py — Storage backend abstraction for screenshot and artifact URIs.

The storage backend translates a relative artifact key into a normalized URI string.
Switching backends (local → S3 → Azure Blob) requires only a config change — no
schema migration, because StepResult.screenshot_url stores the URI string directly.

URI scheme identifies the backend:
  file:///artifacts/screenshots/abc.png     ← local
  s3://bucket/screenshots/abc.png           ← S3
  https://account.blob.core.../abc.png      ← Azure Blob

To extend: implement StorageBackend and register it in get_storage_backend().
"""

from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings


class StorageBackend(ABC):
    """Abstract contract. Implementations return a normalized URI for a given key."""

    @abstractmethod
    def uri(self, key: str) -> str:
        """Convert a relative artifact key to an absolute URI."""

    @abstractmethod
    def public_url(self, key: str) -> str:
        """Return a public-accessible URL (may equal uri for S3/Azure)."""


class LocalStorageBackend(StorageBackend):
    """Stores artifacts on the local filesystem under ARTIFACT_LOCAL_BASE_PATH."""

    def __init__(self) -> None:
        self._base = Path(settings.ARTIFACT_LOCAL_BASE_PATH).resolve()

    def uri(self, key: str) -> str:
        return (self._base / key).as_uri()  # file:///...

    def public_url(self, key: str) -> str:
        # In production, this would be served via a static-file route or CDN.
        return f"/artifacts/{key}"


class S3StorageBackend(StorageBackend):
    """Stub for future S3 integration."""

    def __init__(self) -> None:
        self._bucket = "assureden-artifacts"

    def uri(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    def public_url(self, key: str) -> str:
        return f"https://{self._bucket}.s3.amazonaws.com/{key}"


def get_storage_backend() -> StorageBackend:
    """Factory — instantiate the configured backend."""
    provider = settings.ARTIFACT_STORAGE_PROVIDER.lower()
    if provider == "s3":
        return S3StorageBackend()
    # Default: local
    return LocalStorageBackend()


# Singleton used by services
storage = get_storage_backend()
