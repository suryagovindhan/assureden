"""
server/core/storage.py — Pluggable Artifact Storage Provider
──────────────────────────────────────────────────────────────
M1: LocalStorageProvider — stores files in /server/static/artifacts/
Future: S3CompatibleProvider (same interface, swap by config)
"""

import os
import shutil
from abc import ABC, abstractmethod
from datetime import datetime

# Base artifacts directory — sibling to server/
_ARTIFACTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "server", "static", "artifacts"
)


# ─────────────────────────────────────────────────────────────────────────────
# Abstract Interface
# ─────────────────────────────────────────────────────────────────────────────

class StorageProvider(ABC):
    @abstractmethod
    def save(self, data: bytes, run_id: str, filename: str) -> str:
        """
        Persists binary data and returns a relative URL path
        (e.g. /static/artifacts/run_abc/step_1_screenshot.png).
        """
        ...

    @abstractmethod
    def get_url(self, storage_path: str) -> str:
        """Returns the publicly accessible URL for a stored artifact."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Local Implementation (M1 default)
# ─────────────────────────────────────────────────────────────────────────────

class LocalStorageProvider(StorageProvider):
    def __init__(self, base_dir: str = _ARTIFACTS_DIR):
        self._base = base_dir
        os.makedirs(self._base, exist_ok=True)

    def save(self, data: bytes, run_id: str, filename: str) -> str:
        run_dir = os.path.join(self._base, run_id)
        os.makedirs(run_dir, exist_ok=True)
        dest = os.path.join(run_dir, filename)
        with open(dest, "wb") as f:
            f.write(data)
        # Return web-accessible relative path
        return f"/static/artifacts/{run_id}/{filename}"

    def get_url(self, storage_path: str) -> str:
        return storage_path  # Already a relative URL for local


# ─────────────────────────────────────────────────────────────────────────────
# S3-Compatible stub (Future — same interface)
# ─────────────────────────────────────────────────────────────────────────────

class S3StorageProvider(StorageProvider):
    """
    Placeholder — connect to MinIO, AWS S3, or Azure Blob by
    implementing save() with boto3 / azure-storage-blob.
    """
    def save(self, data: bytes, run_id: str, filename: str) -> str:
        raise NotImplementedError("S3StorageProvider not yet configured.")

    def get_url(self, storage_path: str) -> str:
        raise NotImplementedError("S3StorageProvider not yet configured.")


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_provider: StorageProvider | None = None


def get_storage_provider() -> StorageProvider:
    global _provider
    if _provider is None:
        _provider = LocalStorageProvider()
    return _provider
