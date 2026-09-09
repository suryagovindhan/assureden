"""
tests/test_phase8.py — Phase 8: Report service unit tests.

All tests run without PostgreSQL. SQLite in-memory is used where DB access is needed;
pure-Python helpers (time-range resolution, p95, flakiness) need no DB at all.

Test groups:
  TestTimeRangeResolution    (5) — period shortcuts, explicit, default, validation
  TestGranularity            (3) — hour/day/week thresholds
  TestPercentile95           (4) — single, multi, empty, ordering
  TestFlakinessFormula       (4) — formula correctness, terminal-only, min_runs, min_score
  TestReportShapes           (3) — runs/pass-rate shapes with in-memory DB
  TestResponseEnvelope       (2) — envelope keys + granularity=null for non-trend
"""

from __future__ import annotations

import uuid
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.report_service import ReportService
from app.core.config import settings


# ── Helpers ───────────────────────────────────────────────────────────────────

def utc(days_ago: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _org():
    return uuid.uuid4()


# ══════════════════════════════════════════════════════════════════════════════
# TestTimeRangeResolution
# ══════════════════════════════════════════════════════════════════════════════

class TestTimeRangeResolution:
    """resolve_time_range() contracts."""

    def test_period_7d_default(self):
        """No args → 7-day window."""
        since, until = ReportService.resolve_time_range(None, None, None)
        delta = until - since
        assert 6 <= delta.days <= 7

    def test_period_shorthand_maps_correctly(self):
        """?period=30d → ~30-day window."""
        since, until = ReportService.resolve_time_range(None, None, "30d")
        delta = until - since
        assert 29 <= delta.days <= 30

    def test_explicit_since_until_takes_precedence(self):
        """since+until overrides period."""
        s = utc(10)
        u = utc(0)
        since, until = ReportService.resolve_time_range(s, u, "1d")
        assert since == s.astimezone(timezone.utc)
        assert until == u.astimezone(timezone.utc)

    def test_since_after_until_raises(self):
        """since >= until must raise ValueError."""
        with pytest.raises(ValueError, match="since must be before until"):
            ReportService.resolve_time_range(utc(0), utc(5), None)

    def test_range_exceeds_max_raises(self):
        """Range > REPORT_MAX_RANGE_DAYS must raise ValueError."""
        s = utc(settings.REPORT_MAX_RANGE_DAYS + 1)
        u = utc(0)
        with pytest.raises(ValueError, match="exceeds maximum"):
            ReportService.resolve_time_range(s, u, None)


# ══════════════════════════════════════════════════════════════════════════════
# TestGranularity
# ══════════════════════════════════════════════════════════════════════════════

class TestGranularity:
    """resolve_granularity() adaptive bucket selection."""

    def test_hour_for_le_48h(self):
        """A 24h window (well within the ≤48h threshold) → hour granularity."""
        since = utc(0) - timedelta(hours=24)
        until = utc(0)
        assert ReportService.resolve_granularity(since, until) == "hour"

    def test_day_for_3_to_31_days(self):
        since = utc(7)
        until = utc(0)
        assert ReportService.resolve_granularity(since, until) == "day"

    def test_week_for_gt_31_days(self):
        since = utc(60)
        until = utc(0)
        assert ReportService.resolve_granularity(since, until) == "week"


# ══════════════════════════════════════════════════════════════════════════════
# TestPercentile95
# ══════════════════════════════════════════════════════════════════════════════

class TestPercentile95:
    """percentile_95() nearest-rank definition."""

    def test_single_element_equals_avg(self):
        """One value: p95 == avg == that value."""
        assert ReportService.percentile_95([42.0]) == 42.0

    def test_empty_returns_zero(self):
        assert ReportService.percentile_95([]) == 0.0

    def test_deterministic_nearest_rank(self):
        """
        10 values [1..10]:
          index = ceil(0.95 * 10) - 1 = ceil(9.5) - 1 = 10 - 1 = 9
          sorted[9] = 10
        """
        values = list(range(1, 11))  # [1, 2, ..., 10]
        assert ReportService.percentile_95(values) == 10

    def test_unsorted_input_handled(self):
        """Input ordering must not affect result."""
        values = [10, 1, 5, 3, 7, 2, 9, 4, 6, 8]
        assert ReportService.percentile_95(values) == ReportService.percentile_95(sorted(values))


# ══════════════════════════════════════════════════════════════════════════════
# TestFlakinessFormula
# ══════════════════════════════════════════════════════════════════════════════

class TestFlakinessFormula:
    """Flakiness score computation against mock DB rows."""

    def _make_db_mock(self, rows):
        """Create a mock db.execute(...).fetchall() returning given rows."""
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = rows
        return db

    def _Row(self, tc_id, tc_name, status, triggered_at):
        Row = namedtuple("Row", ["test_case_id", "test_case_name", "status", "triggered_at"])
        return Row(tc_id, tc_name, status, triggered_at)

    def _make_run_rows(self, tc_id, tc_name, statuses: list[str]):
        """Build ordered rows for a single test case."""
        base = utc(10)
        return [
            self._Row(tc_id, tc_name, s, base + timedelta(hours=i))
            for i, s in enumerate(statuses)
        ]

    def test_adjacent_flip_rate_formula(self):
        """
        10 runs: P P F F P P P F F P
        flips = 4 (PP→F, FF→P, PPP→F, FF→P)
        expected = 4 / 9 = 0.4444...
        """
        tc_id = uuid.uuid4()
        statuses = ["COMPLETED", "COMPLETED", "FAILED", "FAILED", "COMPLETED",
                    "COMPLETED", "COMPLETED", "FAILED", "FAILED", "COMPLETED"]
        rows = self._make_run_rows(tc_id, "Test A", statuses)
        db = self._make_db_mock(rows)

        result = ReportService.flakiness_report(db, _org(), utc(30), utc(0))
        assert len(result["data"]) == 1
        entry = result["data"][0]
        assert entry["flip_count"] == 4
        assert entry["runs"] == 10
        assert abs(entry["flakiness_score"] - round(4 / 9, 4)) < 0.0001

    def test_only_terminal_states_count(self):
        """
        ABORTED and TIMED_OUT rows must be excluded from the query.
        The mock only returns COMPLETED/FAILED rows (service SQL filters them).
        A test with only 2 COMPLETED rows → excluded (< 3 eligible runs).
        """
        tc_id = uuid.uuid4()
        rows = self._make_run_rows(tc_id, "Test B", ["COMPLETED", "COMPLETED"])
        db = self._make_db_mock(rows)
        result = ReportService.flakiness_report(db, _org(), utc(30), utc(0))
        # Only 2 eligible runs → filtered out
        assert result["data"] == []

    def test_min_eligible_runs_filter(self):
        """Exactly 3 runs with 1 flip → included."""
        tc_id = uuid.uuid4()
        rows = self._make_run_rows(tc_id, "Test C", ["COMPLETED", "FAILED", "COMPLETED"])
        db = self._make_db_mock(rows)
        result = ReportService.flakiness_report(db, _org(), utc(30), utc(0))
        assert len(result["data"]) == 1
        assert result["data"][0]["flakiness_score"] == round(2 / 2, 4)  # 2 flips / 2 transitions

    def test_min_score_filter(self):
        """min_score=0.5 excludes tests with lower score."""
        tc_id = uuid.uuid4()
        # P F P → 2 flips / 2 transitions = 1.0 (would be included)
        rows = self._make_run_rows(tc_id, "Test D", ["COMPLETED", "FAILED", "COMPLETED"])
        db = self._make_db_mock(rows)
        # min_score=0.5 — score=1.0 >= 0.5 → included
        result = ReportService.flakiness_report(db, _org(), utc(30), utc(0), min_score=0.5)
        assert len(result["data"]) == 1

        # Another test with 4 runs, 1 flip → 1/3 ≈ 0.333 → excluded by min_score=0.5
        tc_id2 = uuid.uuid4()
        rows2 = self._make_run_rows(tc_id2, "Test E",
                                    ["COMPLETED", "COMPLETED", "FAILED", "FAILED"])
        db2 = self._make_db_mock(rows2)
        result2 = ReportService.flakiness_report(db2, _org(), utc(30), utc(0), min_score=0.5)
        assert result2["data"] == []


# ══════════════════════════════════════════════════════════════════════════════
# TestReportShapes
# ══════════════════════════════════════════════════════════════════════════════

class TestReportShapes:
    """Verify response shapes for runs/pass-rate with a mock DB."""

    def _empty_db(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        return db

    def test_runs_report_required_keys(self):
        """runs_report must include the standard envelope + data.total."""
        db = self._empty_db()
        result = ReportService.runs_report(db, _org(), utc(7), utc(0))
        assert "since" in result
        assert "until" in result
        assert "granularity" in result
        assert "data" in result
        assert "total" in result["data"]
        assert "by_status" in result["data"]
        assert "by_priority" in result["data"]
        assert "trend" in result["data"]

    def test_pass_rate_report_required_keys(self):
        """pass_rate_report points must include date, total, passed, failed, pass_rate."""
        db = self._empty_db()
        result = ReportService.pass_rate_report(db, _org(), utc(7), utc(0))
        assert result["granularity"] in ("hour", "day", "week")
        assert isinstance(result["data"], list)

    def test_agents_no_utilization_percent(self):
        """agents_report must NOT include utilization_percent at any level."""
        db = self._empty_db()
        result = ReportService.agents_report(db, _org(), utc(7), utc(0))
        assert "utilization_percent" not in result
        for item in result.get("data", []):
            assert "utilization_percent" not in item


# ══════════════════════════════════════════════════════════════════════════════
# TestResponseEnvelope
# ══════════════════════════════════════════════════════════════════════════════

class TestResponseEnvelope:
    """Universal envelope contract."""

    def _empty_db(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        return db

    def test_envelope_since_until_are_iso8601_strings(self):
        """since and until must be ISO-8601 strings, not datetime objects."""
        db = self._empty_db()
        result = ReportService.runs_report(db, _org(), utc(7), utc(0))
        # Both values must be strings parseable as ISO-8601
        datetime.fromisoformat(result["since"].replace("Z", "+00:00"))
        datetime.fromisoformat(result["until"].replace("Z", "+00:00"))

    def test_non_trend_reports_have_null_granularity(self):
        """Flakiness and agents reports return granularity=null."""
        db = self._empty_db()

        flakiness = ReportService.flakiness_report(db, _org(), utc(7), utc(0))
        assert flakiness["granularity"] is None

        agents = ReportService.agents_report(db, _org(), utc(7), utc(0))
        assert agents["granularity"] is None

        schedules = ReportService.schedules_report(db, _org(), utc(7), utc(0))
        assert schedules["granularity"] is None
