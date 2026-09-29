"""
storage/local.py — Phase 5: Local filesystem StorageProvider.

Directory layout:
  <ARTIFACT_LOCAL_BASE_PATH>/
  └── <org_id>/
      └── <run_id>/
          ├── screenshots/   step_001.png, step_004.png …
          ├── videos/        recording.mp4 …
          ├── logs/          execution.log …
          └── traces/        trace.zip …

Base path is resolved via `Path(settings.ARTIFACT_LOCAL_BASE_PATH).resolve()`
so both relative paths (.artifacts) and absolute paths (/var/lib/…) work.

Configuration:
  ARTIFACT_LOCAL_BASE_PATH=.artifacts     ← development default
  ARTIFACT_LOCAL_BASE_PATH=/var/lib/assureden/artifacts  ← production

Docker mount example:
  volumes:
    - ./backend/.artifacts:/app/.artifacts
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.storage.base import StorageProvider
from app.core.config import settings


class LocalStorageProvider(StorageProvider):
    """
    Stores artifacts on the local filesystem.

    `presign()` returns a relative HTTP path that the /artifacts/{key} route serves.
    Expiry is not enforced (local files are always accessible while the server runs).
    """

    def __init__(self) -> None:
        self._base = Path(settings.ARTIFACT_LOCAL_BASE_PATH).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        """Resolve a storage key to an absolute filesystem path."""
        # Guard against path traversal
        resolved = (self._base / key).resolve()
        if not resolved.is_relative_to(self._base) or resolved == self._base:
            raise ValueError(f"Unsafe artifact key: {key!r}")
        return resolved

    # ── StorageProvider interface ─────────────────────────────────────────────

    def save(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {key!r}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def presign(self, key: str, expires_seconds: int = 3600) -> str:
        """
        Returns a relative URL for the /artifacts/{key} serving route.
        `expires_seconds` is accepted but not enforced for local storage —
        files are always accessible while the server is running.
        """
        return f"/artifacts/{key}"

    def delete_run_artifacts(self, org_id: str, run_id: str) -> None:
        """Remove the entire <org_id>/<run_id>/ directory tree."""
        run_dir = self._resolve(f"{org_id}/{run_id}")
        if run_dir.exists() and run_dir.is_dir():
            shutil.rmtree(run_dir)
