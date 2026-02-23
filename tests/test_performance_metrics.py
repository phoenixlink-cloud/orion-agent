# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for PerformanceMetrics — aggregation, trends, hotspots, comparisons.

Phase 4D.3: 17 tests covering:
- Empty metrics (PM-01)
- Success rate calculation (PM-02)
- First-attempt success rate (PM-03)
- Fix rate (PM-04)
- Mean retries (PM-05)
- Mean duration (PM-06)
- Error distribution (PM-07)
- Top fixes (PM-08)
- Stack filter (PM-09)
- Session filter (PM-10)
- Window/limit (PM-11)
- Trends improving (PM-12)
- Trends regressing (PM-13)
- Trends stable (PM-14)
- Error hotspots (PM-15)
- Stack comparison (PM-16)
- ExecutionMetrics.to_dict (PM-17)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orion.ara.execution_memory import ExecutionLesson, ExecutionMemory
from orion.ara.performance_metrics import (
    ExecutionMetrics,
    PerformanceMetrics,
    PerformanceTrend,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lesson(
    *,
    outcome: str = "success",
    first_attempt: bool = True,
    stack: str = "python",
    retries: int = 0,
    duration: float = 2.0,
    error_category: str = "",
    fix_applied: str | None = None,
    session_id: str = "s1",
) -> ExecutionLesson:
    return ExecutionLesson(
        command="python app.py",
        outcome=outcome,
        first_attempt_success=first_attempt,
        stack=stack,
        retries=retries,
        duration_seconds=duration,
        error_category=error_category,
        fix_applied=fix_applied,
        confidence=0.9 if outcome == "success" else 0.7,
        session_id=session_id,
    )


def _mock_memory(lessons: list[ExecutionLesson]) -> MagicMock:
    mem = MagicMock(spec=ExecutionMemory)

    def _query(stack: str = "", limit: int = 0, **kw):
        result = lessons
        if stack:
            result = [l for l in result if l.stack == stack]
        if limit:
            result = result[:limit]
        return result

    mem.query_lessons.side_effect = _query
    return mem


# ===========================================================================
# Tests
# ===========================================================================


class TestEmptyMetrics:
    """PM-01: No lessons → zero metrics."""

    def test_empty_returns_zeroes(self):
        pm = PerformanceMetrics(execution_memory=None)
        m = pm.compute_metrics()
        assert m.total_executions == 0
        assert m.success_rate == 0.0
        assert m.first_attempt_success_rate == 0.0

    def test_empty_memory_returns_zeroes(self):
        mem = _mock_memory([])
        pm = PerformanceMetrics(execution_memory=mem)
        m = pm.compute_metrics()
        assert m.total_executions == 0


class TestSuccessRate:
    """PM-02: Success rate calculation."""

    def test_success_rate(self):
        lessons = [
            _lesson(outcome="success"),
            _lesson(outcome="success"),
            _lesson(outcome="failure_fixed", first_attempt=False, fix_applied="pip install x"),
            _lesson(outcome="failure_permanent", first_attempt=False),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        m = pm.compute_metrics()

        # 2 success + 1 failure_fixed = 3 successful out of 4
        assert m.total_executions == 4
        assert m.successful == 3
        assert m.success_rate == pytest.approx(0.75, abs=0.01)


class TestFASR:
    """PM-03: First-attempt success rate."""

    def test_first_attempt_success_rate(self):
        lessons = [
            _lesson(outcome="success", first_attempt=True),
            _lesson(outcome="success", first_attempt=False),
            _lesson(outcome="failure_fixed", first_attempt=False, fix_applied="fix"),
            _lesson(outcome="failure_permanent", first_attempt=False),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        m = pm.compute_metrics()

        # 1 first-attempt success out of 4
        assert m.first_attempt_success_rate == pytest.approx(0.25, abs=0.01)


class TestFixRate:
    """PM-04: Fix rate = failures_fixed / (failures_fixed + permanent_failures)."""

    def test_fix_rate(self):
        lessons = [
            _lesson(outcome="failure_fixed", first_attempt=False, fix_applied="fix1"),
            _lesson(outcome="failure_fixed", first_attempt=False, fix_applied="fix2"),
            _lesson(outcome="failure_permanent", first_attempt=False),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        m = pm.compute_metrics()

        # 2 fixed / (2 fixed + 1 permanent) = 0.667
        assert m.fix_rate == pytest.approx(0.667, abs=0.01)


class TestMeanRetries:
    """PM-05: Mean retries across lessons."""

    def test_mean_retries(self):
        lessons = [
            _lesson(retries=0),
            _lesson(retries=2),
            _lesson(retries=4),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        m = pm.compute_metrics()
        assert m.mean_retries == pytest.approx(2.0, abs=0.01)


class TestMeanDuration:
    """PM-06: Mean duration seconds."""

    def test_mean_duration(self):
        lessons = [
            _lesson(duration=1.0),
            _lesson(duration=3.0),
            _lesson(duration=5.0),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        m = pm.compute_metrics()
        assert m.mean_duration_seconds == pytest.approx(3.0, abs=0.01)


class TestErrorDistribution:
    """PM-07: Error category breakdown."""

    def test_error_distribution(self):
        lessons = [
            _lesson(outcome="failure_fixed", error_category="missing_dependency", fix_applied="x"),
            _lesson(outcome="failure_fixed", error_category="missing_dependency", fix_applied="y"),
            _lesson(outcome="failure_permanent", error_category="runtime"),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        m = pm.compute_metrics()

        assert m.error_distribution["missing_dependency"] == 2
        assert m.error_distribution["runtime"] == 1


class TestTopFixes:
    """PM-08: Top fixes ranked by count."""

    def test_top_fixes(self):
        lessons = [
            _lesson(outcome="failure_fixed", fix_applied="pip install flask"),
            _lesson(outcome="failure_fixed", fix_applied="pip install flask"),
            _lesson(outcome="failure_fixed", fix_applied="pip install requests"),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        m = pm.compute_metrics()

        assert len(m.top_fixes) == 2
        assert m.top_fixes[0]["fix"] == "pip install flask"
        assert m.top_fixes[0]["count"] == 2


class TestStackFilter:
    """PM-09: Filter metrics by stack."""

    def test_stack_filter(self):
        lessons = [
            _lesson(stack="python"),
            _lesson(stack="python"),
            _lesson(stack="node"),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        m = pm.compute_metrics(stack="python")
        assert m.total_executions == 2


class TestSessionFilter:
    """PM-10: Filter metrics by session_id."""

    def test_session_filter(self):
        lessons = [
            _lesson(session_id="s1"),
            _lesson(session_id="s1"),
            _lesson(session_id="s2"),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        m = pm.compute_metrics(session_id="s1")
        assert m.total_executions == 2


class TestWindowLimit:
    """PM-11: Limit the number of lessons considered."""

    def test_limit(self):
        lessons = [_lesson() for _ in range(20)]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        m = pm.compute_metrics(limit=5, window_label="last_5")
        assert m.total_executions == 5
        assert m.window_label == "last_5"


class TestTrendsImproving:
    """PM-12: Trends show improvement when FASR increases."""

    def test_improving_trend(self):
        # Current window: all first-attempt successes
        current = [_lesson(outcome="success", first_attempt=True) for _ in range(10)]
        # Previous window: half failures
        previous = [_lesson(outcome="success", first_attempt=True) for _ in range(5)]
        previous += [_lesson(outcome="failure_permanent", first_attempt=False) for _ in range(5)]

        all_lessons = current + previous
        pm = PerformanceMetrics(execution_memory=_mock_memory(all_lessons))
        trends = pm.compute_trends(current_window=10, previous_window=10)

        fasr_trend = next(t for t in trends if t.metric_name == "first_attempt_success_rate")
        assert fasr_trend.direction == "improving"
        assert fasr_trend.delta > 0


class TestTrendsRegressing:
    """PM-13: Trends show regression when success rate drops."""

    def test_regressing_trend(self):
        # Current window: mostly failures
        current = [_lesson(outcome="failure_permanent", first_attempt=False) for _ in range(8)]
        current += [_lesson(outcome="success", first_attempt=True) for _ in range(2)]
        # Previous window: all successes
        previous = [_lesson(outcome="success", first_attempt=True) for _ in range(10)]

        all_lessons = current + previous
        pm = PerformanceMetrics(execution_memory=_mock_memory(all_lessons))
        trends = pm.compute_trends(current_window=10, previous_window=10)

        sr_trend = next(t for t in trends if t.metric_name == "success_rate")
        assert sr_trend.direction == "regressing"
        assert sr_trend.delta < 0


class TestTrendsStable:
    """PM-14: Trends show stable when no change."""

    def test_stable_trend(self):
        lessons = [_lesson(outcome="success", first_attempt=True) for _ in range(20)]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        trends = pm.compute_trends(current_window=10, previous_window=10)

        fasr_trend = next(t for t in trends if t.metric_name == "first_attempt_success_rate")
        assert fasr_trend.direction == "stable"


class TestErrorHotspots:
    """PM-15: Error hotspots ranked by frequency."""

    def test_hotspots(self):
        lessons = [
            _lesson(outcome="failure_fixed", error_category="missing_dependency", fix_applied="x"),
            _lesson(outcome="failure_fixed", error_category="missing_dependency", fix_applied="y"),
            _lesson(outcome="failure_fixed", error_category="missing_dependency", fix_applied="z"),
            _lesson(outcome="failure_permanent", error_category="runtime"),
            _lesson(outcome="failure_permanent", error_category="syntax"),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        hotspots = pm.get_error_hotspots()

        assert len(hotspots) == 3
        assert hotspots[0]["category"] == "missing_dependency"
        assert hotspots[0]["count"] == 3
        assert hotspots[0]["percentage"] == 60.0


class TestStackComparison:
    """PM-16: Compare performance across stacks."""

    def test_stack_comparison(self):
        lessons = [
            _lesson(stack="python", outcome="success", first_attempt=True),
            _lesson(stack="python", outcome="success", first_attempt=True),
            _lesson(stack="node", outcome="failure_permanent", first_attempt=False),
        ]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        comparison = pm.get_stack_comparison()

        assert len(comparison) == 2
        py = next(c for c in comparison if c["stack"] == "python")
        node = next(c for c in comparison if c["stack"] == "node")
        assert py["success_rate"] == 1.0
        assert node["success_rate"] == 0.0


class TestMetricsToDict:
    """PM-17: ExecutionMetrics.to_dict serialization."""

    def test_to_dict_keys(self):
        m = ExecutionMetrics(
            total_executions=10,
            successful=8,
            success_rate=0.8,
            first_attempt_success_rate=0.6,
            stack="python",
            window_label="last_10",
        )
        d = m.to_dict()
        assert d["total_executions"] == 10
        assert d["success_rate"] == 0.8
        assert d["stack"] == "python"
        assert "error_distribution" in d
        assert "top_fixes" in d

    def test_trend_to_dict(self):
        t = PerformanceTrend(
            metric_name="success_rate",
            current_value=0.9,
            previous_value=0.7,
            delta=0.2,
            direction="improving",
        )
        d = t.to_dict()
        assert d["metric_name"] == "success_rate"
        assert d["delta"] == 0.2
        assert d["direction"] == "improving"
