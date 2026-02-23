# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Performance API Routes — Web UI endpoints.

Phase 4D.5: 6 tests covering:
- AP-01: GET /api/performance — overview metrics
- AP-02: GET /api/performance — no data returns null
- AP-03: GET /api/performance/trends — trend data
- AP-04: GET /api/performance/hotspots — hotspot data
- AP-05: GET /api/performance/stacks — stack comparison
- AP-06: Router registered in server.py
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orion.ara.execution_memory import ExecutionLesson, ExecutionMemory
from orion.ara.performance_metrics import PerformanceMetrics

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
            result = [lsn for lsn in result if lsn.stack == stack]
        if limit:
            result = result[:limit]
        return result

    mem.query_lessons.side_effect = _query
    return mem


def _pm_with_data(lessons: list[ExecutionLesson]) -> PerformanceMetrics:
    return PerformanceMetrics(execution_memory=_mock_memory(lessons))


# ===========================================================================
# Tests
# ===========================================================================


class TestGetMetrics:
    """AP-01: GET /api/performance returns metrics snapshot."""

    @pytest.mark.asyncio
    async def test_metrics_with_data(self):
        from orion.api.routes.performance import get_metrics

        lessons = [
            _lesson(outcome="success", first_attempt=True),
            _lesson(outcome="failure_fixed", first_attempt=False, fix_applied="pip install x"),
            _lesson(outcome="failure_permanent", first_attempt=False),
        ]
        pm = _pm_with_data(lessons)

        with patch("orion.api.routes.performance._get_performance_metrics", return_value=pm):
            result = await get_metrics(stack="", session_id="", limit=0)

        assert result["success"] is True
        assert result["data"]["total_executions"] == 3
        assert result["data"]["successful"] == 2


class TestGetMetricsNoData:
    """AP-02: GET /api/performance with no data returns null."""

    @pytest.mark.asyncio
    async def test_no_data(self):
        from orion.api.routes.performance import get_metrics

        with patch("orion.api.routes.performance._get_performance_metrics", return_value=None):
            result = await get_metrics(stack="", session_id="", limit=0)

        assert result["success"] is True
        assert result["data"] is None


class TestGetTrends:
    """AP-03: GET /api/performance/trends returns trend data."""

    @pytest.mark.asyncio
    async def test_trends_with_data(self):
        from orion.api.routes.performance import get_trends

        current = [_lesson(outcome="success", first_attempt=True) for _ in range(10)]
        previous = [_lesson(outcome="failure_permanent", first_attempt=False) for _ in range(10)]
        pm = _pm_with_data(current + previous)

        with patch("orion.api.routes.performance._get_performance_metrics", return_value=pm):
            result = await get_trends(stack="", current_window=10, previous_window=10)

        assert result["success"] is True
        assert len(result["data"]) > 0
        assert result["data"][0]["metric_name"] == "first_attempt_success_rate"


class TestGetHotspots:
    """AP-04: GET /api/performance/hotspots returns error hotspots."""

    @pytest.mark.asyncio
    async def test_hotspots(self):
        from orion.api.routes.performance import get_hotspots

        lessons = [
            _lesson(outcome="failure_fixed", error_category="missing_dependency", fix_applied="x"),
            _lesson(outcome="failure_fixed", error_category="missing_dependency", fix_applied="y"),
            _lesson(outcome="failure_permanent", error_category="runtime"),
        ]
        pm = _pm_with_data(lessons)

        with patch("orion.api.routes.performance._get_performance_metrics", return_value=pm):
            result = await get_hotspots(stack="", limit=5)

        assert result["success"] is True
        assert len(result["data"]) == 2
        assert result["data"][0]["category"] == "missing_dependency"


class TestGetStacks:
    """AP-05: GET /api/performance/stacks returns per-stack comparison."""

    @pytest.mark.asyncio
    async def test_stacks(self):
        from orion.api.routes.performance import get_stacks

        lessons = [
            _lesson(stack="python", outcome="success"),
            _lesson(stack="node", outcome="failure_permanent", first_attempt=False),
        ]
        pm = _pm_with_data(lessons)

        with patch("orion.api.routes.performance._get_performance_metrics", return_value=pm):
            result = await get_stacks()

        assert result["success"] is True
        assert len(result["data"]) == 2


class TestRouterRegistered:
    """AP-06: Performance router is registered in server.py."""

    def test_router_in_server(self):
        from orion.api.routes.performance import router

        assert router.prefix == "/api/performance"
        # Check that all expected routes exist
        route_paths = [r.path for r in router.routes]
        assert "/api/performance" in route_paths
        assert "/api/performance/trends" in route_paths
        assert "/api/performance/hotspots" in route_paths
        assert "/api/performance/stacks" in route_paths
