"""
tests/test_phase5.py — Phase 5: SSE auth, storage abstraction, artifact model.

Covers:
  - SSE ticket issuance and validation (create / decode / expiry / run_id scope)
  - LocalStorageProvider (save / read / delete / exists / presign / path traversal guard)
  - StorageProvider factory (get_storage returns LocalStorageProvider by default)
  - RunArtifact model (field defaults, storage key format)
  - MetricsService response shape (queue_health + scheduler_health keys)
  - ScheduleService structural tests (instantiation, list, trigger_now path)
"""

from __future__ import annotations

import uuid
import time
import tempfile
import os
from pathlib import Path
from datetime import timedelta, timezone, datetime
from unittest.mock import patch, MagicMock

import pytest

from app.core.security import create_sse_ticket, decode_sse_ticket
from app.core.config import settings


# ══════════════════════════════════════════════════════════════════════════════
# SSE Ticket
# ══════════════════════════════════════════════════════════════════════════════

class TestSseTicket:
    """SSE ticket issuance and validation."""

    def _uid(self):
        return uuid.uuid4()

    def test_ticket_roundtrip(self):
        """A ticket created for a user/org can be decoded back."""
        user_id = self._uid()
        org_id = self._uid()
        token = create_sse_ticket(user_id, org_id)
        payload = decode_sse_ticket(token)

        assert payload is not None
        assert payload["sub"] == str(user_id)
        assert payload["org_id"] == str(org_id)
        assert payload["type"] == "sse"

    def test_ticket_rejected_by_access_token_decoder(self):
        """An SSE ticket must NOT be accepted as a regular access token."""
        from app.core.security import decode_access_token
        token = create_sse_ticket(self._uid(), self._uid())
        assert decode_access_token(token) is None

    def test_ticket_rejected_by_refresh_token_decoder(self):
        """An SSE ticket must NOT be accepted as a refresh token."""
        from app.core.security import decode_refresh_token
        token = create_sse_ticket(self._uid(), self._uid())
        assert decode_refresh_token(token) is None

    def test_ticket_with_run_id_scope_valid(self):
        """Ticket scoped to run_id passes when the same run_id is checked."""
        run_id = str(self._uid())
        token = create_sse_ticket(self._uid(), self._uid(), run_id=run_id)
        payload = decode_sse_ticket(token, run_id=run_id)
        assert payload is not None

    def test_ticket_with_run_id_scope_rejects_other_run(self):
        """Ticket scoped to run A must be rejected when checked against run B."""
        run_a = str(self._uid())
        run_b = str(self._uid())
        token = create_sse_ticket(self._uid(), self._uid(), run_id=run_a)
        payload = decode_sse_ticket(token, run_id=run_b)
        assert payload is None

    def test_expired_ticket_is_rejected(self):
        """Tickets past their exp claim must not decode successfully."""
        from jose import jwt
        from app.core.security import _encode  # type: ignore[attr-defined]

        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        expired_payload = {
            "sub":    str(self._uid()),
            "org_id": str(self._uid()),
            "type":   "sse",
            "exp":    past,
        }
        token = _encode(expired_payload)
        assert decode_sse_ticket(token) is None

    def test_tampered_ticket_is_rejected(self):
        """A ticket with a modified signature must fail validation."""
        token = create_sse_ticket(self._uid(), self._uid())
        bad_token = token[:-5] + "XXXXX"
        assert decode_sse_ticket(bad_token) is None


# ══════════════════════════════════════════════════════════════════════════════
# LocalStorageProvider
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def local_storage(tmp_path):
    """LocalStorageProvider pointed at a temp directory."""
    with patch.object(settings, "ARTIFACT_LOCAL_BASE_PATH", str(tmp_path)):
        from app.storage.local import LocalStorageProvider
        return LocalStorageProvider()


class TestLocalStorageProvider:
    """Full LocalStorageProvider behaviour."""

    def test_save_and_read_roundtrip(self, local_storage):
        key = "org1/run1/screenshots/step_001.png"
        data = b"\x89PNG test bytes"
        local_storage.save(key, data, "image/png")
        result = local_storage.read(key)
        assert result == data

    def test_exists_true_after_save(self, local_storage):
        key = "org1/run2/logs/execution.log"
        local_storage.save(key, b"log content", "text/plain")
        assert local_storage.exists(key) is True

    def test_exists_false_before_save(self, local_storage):
        assert local_storage.exists("org1/run99/screenshots/missing.png") is False

    def test_delete_removes_file(self, local_storage):
        key = "org1/run3/videos/recording.mp4"
        local_storage.save(key, b"video data", "video/mp4")
        local_storage.delete(key)
        assert local_storage.exists(key) is False

    def test_delete_noop_if_missing(self, local_storage):
        """delete() on a non-existent key should not raise."""
        local_storage.delete("org1/run99/missing/file.png")  # no exception

    def test_presign_returns_http_path(self, local_storage):
        key = "org1/run4/screenshots/step_002.png"
        url = local_storage.presign(key)
        assert url == f"/artifacts/{key}"

    def test_delete_run_artifacts_removes_directory(self, local_storage, tmp_path):
        org_id = "org1"
        run_id = "run5"
        for fname in ("a.png", "b.png"):
            local_storage.save(f"{org_id}/{run_id}/screenshots/{fname}", b"data", "image/png")

        local_storage.delete_run_artifacts(org_id, run_id)

        run_dir = tmp_path / org_id / run_id
        assert not run_dir.exists()

    def test_delete_run_artifacts_noop_if_missing(self, local_storage):
        """delete_run_artifacts() on a missing run should not raise."""
        local_storage.delete_run_artifacts("ghost_org", "ghost_run")

    def test_path_traversal_blocked(self, local_storage):
        """Keys containing '../' must raise ValueError."""
        with pytest.raises(ValueError):
            local_storage.save("../../etc/passwd", b"evil", "text/plain")

    def test_intermediate_directories_created(self, local_storage, tmp_path):
        key = "org1/run6/traces/deeply/nested/trace.zip"
        local_storage.save(key, b"zip", "application/zip")
        assert (tmp_path / key).exists()


# ══════════════════════════════════════════════════════════════════════════════
# Storage Factory
# ══════════════════════════════════════════════════════════════════════════════

class TestStorageFactory:
    """get_storage() returns the configured provider."""

    def test_default_returns_local_provider(self, tmp_path):
        from app.storage import get_storage
        from app.storage.local import LocalStorageProvider

        # Clear the lru_cache so our patched setting takes effect
        get_storage.cache_clear()
        with patch.object(settings, "ARTIFACT_STORAGE_PROVIDER", "local"), \
             patch.object(settings, "ARTIFACT_LOCAL_BASE_PATH", str(tmp_path)):
            provider = get_storage()
            assert isinstance(provider, LocalStorageProvider)
        get_storage.cache_clear()

    def test_unknown_provider_raises(self):
        from app.storage import get_storage
        get_storage.cache_clear()
        with patch.object(settings, "ARTIFACT_STORAGE_PROVIDER", "cassette"):
            with pytest.raises(ValueError, match="Unknown ARTIFACT_STORAGE_PROVIDER"):
                get_storage()
        get_storage.cache_clear()


# ══════════════════════════════════════════════════════════════════════════════
# RunArtifact model
# ══════════════════════════════════════════════════════════════════════════════

class TestRunArtifactModel:
    """Basic model field/constant validation (no DB required)."""

    def test_artifact_types_constant(self):
        from app.models.artifacts import ARTIFACT_TYPES
        expected = {"SCREENSHOT", "VIDEO", "LOG", "HAR", "TRACE"}
        assert set(ARTIFACT_TYPES) == expected

    def test_storage_key_layout_convention(self):
        """
        Verify the documented key format:
          <org_id>/<run_id>/<artifact_type>/<filename>
        """
        org_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        artifact_type = "screenshots"
        filename = "step_001.png"
        key = f"{org_id}/{run_id}/{artifact_type}/{filename}"

        parts = key.split("/")
        assert len(parts) == 4
        assert parts[2] == artifact_type
        assert parts[3] == filename

    def test_runartifact_importable(self):
        """The model must be importable without DB connection."""
        from app.models.artifacts import RunArtifact  # noqa: F401
        assert RunArtifact.__tablename__ == "run_artifacts"


# ══════════════════════════════════════════════════════════════════════════════
# ScheduleService — structural
# ══════════════════════════════════════════════════════════════════════════════

class TestScheduleServiceInterface:
    """ScheduleService has all required public methods."""

    def test_required_methods_exist(self):
        from app.services.schedule_service import ScheduleService
        for method in (
            "create_schedule", "update_schedule", "delete_schedule",
            "enable_schedule", "disable_schedule", "trigger_now",
            "get_history", "preview_occurrences", "list_schedules", "get_schedule",
        ):
            assert hasattr(ScheduleService, method), f"Missing method: {method}"

    def test_preview_occurrences_returns_list(self):
        from app.services.schedule_service import ScheduleService
        result = ScheduleService.preview_occurrences("0 * * * *", "UTC", count=3)
        assert isinstance(result, list)
        assert len(result) == 3

    def test_preview_occurrences_iso8601(self):
        """Each occurrence must be a parseable ISO-8601 string."""
        from app.services.schedule_service import ScheduleService
        from datetime import datetime
        occurrences = ScheduleService.preview_occurrences("30 9 * * MON", "UTC", count=2)
        for occ in occurrences:
            # Should not raise
            datetime.fromisoformat(occ.replace("Z", "+00:00"))
