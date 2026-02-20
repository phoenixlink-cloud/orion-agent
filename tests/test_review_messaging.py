# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""Tests for Phase 4E.4 — Performance Summary to Messaging.

Covers:
1. format_performance_summary standalone helper
2. _format_review_for_messaging with perf_data kwarg
3. _handle_review integration with PerformanceMetrics engine
4. Edge cases (no metrics, zero executions, missing fields)

Minimum: 6 tests (spec requirement).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from orion.ara.message_bridge import (
    InboundMessage,
    MessageBridge,
    format_performance_summary,
)


# =========================================================================
# Helpers
# =========================================================================


def _perf_dict(
    total: int = 10,
    success_rate: float = 0.9,
    fasr: float = 0.7,
    fix_rate: float = 0.5,
    mean_retries: float = 1.2,
    mean_dur: float = 3.5,
    mttr: float = 5.0,
    errors: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build a performance-metrics dict matching ExecutionMetrics.to_dict()."""
    return {
        "total_executions": total,
        "successful": int(total * success_rate),
        "first_attempt_successes": int(total * fasr),
        "failures_fixed": 2,
        "permanent_failures": 1,
        "success_rate": success_rate,
        "first_attempt_success_rate": fasr,
        "fix_rate": fix_rate,
        "mean_duration_seconds": mean_dur,
        "mean_retries": mean_retries,
        "mean_time_to_resolution": mttr,
        "error_distribution": errors or {},
        "top_fixes": [],
        "stack": "python",
        "session_id": "abc123",
        "window_label": "all",
    }


@dataclass
class _FakeMetrics:
    """Mimics ExecutionMetrics with a to_dict() method."""

    total_executions: int = 0
    _dict: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return self._dict or {"total_executions": self.total_executions}


class _FakePerfEngine:
    """Mimics PerformanceMetrics.compute_metrics()."""

    def __init__(self, metrics: _FakeMetrics | None = None):
        self._metrics = metrics

    def compute_metrics(self, session_id: str = "") -> _FakeMetrics | None:
        return self._metrics


# =========================================================================
# 1. format_performance_summary — standalone helper
# =========================================================================


class TestFormatPerformanceSummary:
    def test_zero_executions_returns_no_data(self):
        result = format_performance_summary({"total_executions": 0})
        assert result == "No execution data."

    def test_basic_fields_present(self):
        perf = _perf_dict()
        result = format_performance_summary(perf)
        assert "Performance:" in result
        assert "Executions: 10" in result
        assert "Success: 90.0%" in result
        assert "First-attempt: 70.0%" in result

    def test_fix_rate_shown_when_nonzero(self):
        perf = _perf_dict(fix_rate=0.5)
        result = format_performance_summary(perf)
        assert "Fix rate: 50.0%" in result

    def test_fix_rate_hidden_when_zero(self):
        perf = _perf_dict(fix_rate=0.0)
        result = format_performance_summary(perf)
        assert "Fix rate" not in result

    def test_retries_shown_when_nonzero(self):
        perf = _perf_dict(mean_retries=2.0)
        result = format_performance_summary(perf)
        assert "Avg retries: 2.0" in result

    def test_retries_hidden_when_zero(self):
        perf = _perf_dict(mean_retries=0.0)
        result = format_performance_summary(perf)
        assert "Avg retries" not in result

    def test_duration_shown_when_nonzero(self):
        perf = _perf_dict(mean_dur=4.2)
        result = format_performance_summary(perf)
        assert "Avg duration: 4.2s" in result

    def test_mttr_shown_when_nonzero(self):
        perf = _perf_dict(mttr=6.3)
        result = format_performance_summary(perf)
        assert "MTTR: 6.3s" in result

    def test_error_distribution_top3(self):
        errors = {"syntax": 5, "import": 3, "timeout": 2, "permission": 1}
        perf = _perf_dict(errors=errors)
        result = format_performance_summary(perf)
        assert "Top errors:" in result
        assert "syntax (5)" in result
        assert "import (3)" in result
        assert "timeout (2)" in result
        # 4th error should NOT appear
        assert "permission" not in result

    def test_empty_error_distribution_no_line(self):
        perf = _perf_dict(errors={})
        result = format_performance_summary(perf)
        assert "Top errors" not in result


# =========================================================================
# 2. _format_review_for_messaging with perf_data
# =========================================================================


class TestFormatReviewWithPerf:
    def test_review_without_perf(self):
        review = {"state": "completed", "goal": "Build API"}
        text = MessageBridge._format_review_for_messaging(review)
        assert "Session Complete" in text
        assert "Performance:" not in text

    def test_review_with_perf(self):
        review = {"state": "completed", "goal": "Build API", "completed_tasks": 5, "total_tasks": 5}
        perf = _perf_dict(total=20, success_rate=0.95, fasr=0.8)
        text = MessageBridge._format_review_for_messaging(review, perf_data=perf)
        assert "Session Complete" in text
        assert "Goal: Build API" in text
        assert "Tasks: 5/5" in text
        assert "Performance:" in text
        assert "Executions: 20" in text
        assert "Success: 95.0%" in text

    def test_none_review_ignores_perf(self):
        text = MessageBridge._format_review_for_messaging(None, perf_data=_perf_dict())
        assert text == "No review data available for this session."

    def test_review_with_empty_perf(self):
        review = {"state": "completed", "goal": "Test"}
        text = MessageBridge._format_review_for_messaging(review, perf_data=None)
        assert "Performance:" not in text


# =========================================================================
# 3. _handle_review integration with PerformanceMetrics
# =========================================================================


class TestHandleReviewIntegration:
    @pytest.mark.asyncio
    async def test_review_includes_performance(self):
        """When a PerformanceMetrics engine is wired, review includes metrics."""
        fake_session = SimpleNamespace(state="completed", goal="Deploy app", status="completed")
        engine = MagicMock()
        engine.get_session.return_value = fake_session

        perf_metrics = _FakePerfEngine(
            _FakeMetrics(total_executions=5, _dict=_perf_dict(total=5, success_rate=1.0, fasr=0.8))
        )

        bridge = MessageBridge(session_engine=engine, performance_metrics=perf_metrics)
        bridge._active_conversations["u1"] = "sess123"

        msg = InboundMessage(platform="telegram", user_id="u1", text="review")
        out = await bridge.handle_message(msg)

        assert "Performance:" in out.text
        assert "Executions: 5" in out.text

    @pytest.mark.asyncio
    async def test_review_without_perf_engine(self):
        """When no PerformanceMetrics engine is available, review works without metrics."""
        fake_session = SimpleNamespace(state="completed", goal="Deploy app", status="completed")
        engine = MagicMock()
        engine.get_session.return_value = fake_session

        bridge = MessageBridge(session_engine=engine)
        bridge._active_conversations["u1"] = "sess123"

        msg = InboundMessage(platform="telegram", user_id="u1", text="review")
        out = await bridge.handle_message(msg)

        assert "Performance:" not in out.text
        assert "Session" in out.text

    @pytest.mark.asyncio
    async def test_review_perf_engine_zero_executions(self):
        """When metrics exist but total_executions == 0, skip perf section."""
        fake_session = SimpleNamespace(state="completed", goal="Test", status="completed")
        engine = MagicMock()
        engine.get_session.return_value = fake_session

        perf_metrics = _FakePerfEngine(_FakeMetrics(total_executions=0))
        bridge = MessageBridge(session_engine=engine, performance_metrics=perf_metrics)
        bridge._active_conversations["u1"] = "sess123"

        msg = InboundMessage(platform="telegram", user_id="u1", text="review")
        out = await bridge.handle_message(msg)

        assert "Performance:" not in out.text

    @pytest.mark.asyncio
    async def test_review_perf_engine_raises(self):
        """If PerformanceMetrics.compute_metrics raises, review still works."""
        fake_session = SimpleNamespace(state="completed", goal="Test", status="completed")
        engine = MagicMock()
        engine.get_session.return_value = fake_session

        perf_engine = MagicMock()
        perf_engine.compute_metrics.side_effect = RuntimeError("boom")

        bridge = MessageBridge(session_engine=engine, performance_metrics=perf_engine)
        bridge._active_conversations["u1"] = "sess123"

        msg = InboundMessage(platform="telegram", user_id="u1", text="review")
        out = await bridge.handle_message(msg)

        # Should still produce a review, just without performance data
        assert "Session" in out.text
        assert "Performance:" not in out.text
