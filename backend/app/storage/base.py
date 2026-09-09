"""
storage/base.py — Phase 5: Full StorageProvider protocol.

Extends the earlier StorageBackend stub into a complete interface covering
save / read / delete / exists / presign operations.

The artifact key follows the layout:
  <org_id>/<run_id>/<artifact_type>/<filename>

  e.g.  org_abc/run_xyz/screenshots/step_001.png

This maps cleanly to S3/GCS object keys (same structure, different prefix).

Adding a new backend (S3, GCS, Azure Blob):
  1. Implement StorageProvider
  2. Register in storage/factory.py
  3. Change ARTIFACT_STORAGE_PROVIDER in .env
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class StorageProvider(ABC):
    """
    Full artifact storage interface.

    All methods accept/return a relative `key` of the form:
      <org_id>/<run_id>/<type>/<filename>

    The provider is responsible for resolving the key to a backing store location.
    """

    @abstractmethod
    def save(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Persist `data` at `key`. Returns the resolved storage key (same as input).
        Creates any intermediate directories as needed.
        """

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Read and return the artifact bytes. Raises FileNotFoundError if missing."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the artifact. No-op if not found."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if the artifact exists."""

    @abstractmethod
    def presign(self, key: str, expires_seconds: int = 3600) -> str:
        """
        Return a URL that provides access to the artifact.

        For local storage: a relative HTTP path served by the /artifacts route.
        For S3/GCS: a time-limited presigned URL.
        The `expires_seconds` parameter is honoured only by cloud backends.
        """

    @abstractmethod
    def delete_run_artifacts(self, org_id: str, run_id: str) -> None:
        """
        Remove ALL artifacts for a run (e.g. on run deletion).
        Equivalent to deleting the directory `<org_id>/<run_id>/`.
        """
