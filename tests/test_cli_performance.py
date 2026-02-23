# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for CLI Performance Dashboard — /performance command rendering.

Phase 4D.4: 8 tests covering:
- CP-01: /performance with no data
- CP-02: /performance overview rendering
- CP-03: /performance trends rendering
- CP-04: /performance hotspots rendering
- CP-05: /performance stacks rendering
- CP-06: /performance detail (all panels)
- CP-07: /performance unknown subcommand → usage
- CP-08: /performance wired into commands.py
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orion.ara.execution_memory import ExecutionLesson, ExecutionMemory
from orion.ara.performance_metrics import PerformanceMetrics
from orion.cli.cli_performance import (
    _render_hotspots,
    _render_overview,
    _render_stacks,
    _render_trends,
    handle_performance_command,
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


def _console() -> MagicMock:
    c = MagicMock()
    c.print_info = MagicMock()
    c.print_error = MagicMock()
    c._print = MagicMock()
    return c


# ===========================================================================
# Tests
# ===========================================================================


class TestNoData:
    """CP-01: No data available → informational message."""

    def test_no_data_message(self):
        console = _console()
        pm = PerformanceMetrics(execution_memory=_mock_memory([]))
        _render_overview(pm, console)
        console.print_info.assert_called()
        # Should mention "No executions"
        calls = [str(c) for c in console.print_info.call_args_list]
        assert any("No executions" in c for c in calls)


class TestOverview:
    """CP-02: Overview renders key metrics."""

    def test_overview_rendering(self):
        lessons = [
            _lesson(outcome="success", first_attempt=True, duration=1.5),
            _lesson(outcome="failure_fixed", first_attempt=False, fix_applied="pip install x", duration=3.0),
            _lesson(outcome="failure_permanent", first_attempt=False, duration=5.0),
        ]
        console = _console()
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        _render_overview(pm, console)

        # Should print the dashboard header and stats
        all_output = " ".join(str(c) for c in console._print.call_args_list)
        assert "Total executions" in all_output
        assert "Success rate" in all_output
        assert "Mean duration" in all_output


class TestTrends:
    """CP-03: Trends rendering with sufficient data."""

    def test_trends_rendering(self):
        # 20 lessons: first 10 all success, next 10 half failures
        current = [_lesson(outcome="success", first_attempt=True) for _ in range(10)]
        previous = [_lesson(outcome="success", first_attempt=True) for _ in range(5)]
        previous += [_lesson(outcome="failure_permanent", first_attempt=False) for _ in range(5)]
        lessons = current + previous

        console = _console()
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        _render_trends(pm, console)

        all_output = " ".join(str(c) for c in console._print.call_args_list)
        # Should contain trend arrows or metric names
        assert "Success Rate" in all_output or "First Attempt" in all_output

    def test_trends_insufficient_data(self):
        """Not enough data → informational message."""
        lessons = [_lesson() for _ in range(5)]
        console = _console()
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        _render_trends(pm, console)

        calls = [str(c) for c in console.print_info.call_args_list]
        assert any("Not enough data" in c for c in calls)


class TestHotspots:
    """CP-04: Hotspots rendering."""

    def test_hotspots_rendering(self):
        lessons = [
            _lesson(outcome="failure_fixed", error_category="missing_dependency", fix_applied="x"),
            _lesson(outcome="failure_fixed", error_category="missing_dependency", fix_applied="y"),
            _lesson(outcome="failure_permanent", error_category="runtime"),
        ]
        console = _console()
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        _render_hotspots(pm, console)

        all_output = " ".join(str(c) for c in console._print.call_args_list)
        assert "missing_dependency" in all_output


class TestStacks:
    """CP-05: Stack comparison rendering."""

    def test_stacks_rendering(self):
        lessons = [
            _lesson(stack="python", outcome="success"),
            _lesson(stack="node", outcome="failure_permanent", first_attempt=False),
        ]
        console = _console()
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))
        _render_stacks(pm, console)

        all_output = " ".join(str(c) for c in console._print.call_args_list)
        assert "python" in all_output
        assert "node" in all_output


class TestDetail:
    """CP-06: /performance detail renders all panels."""

    def test_detail_calls_all_renderers(self):
        lessons = [_lesson() for _ in range(25)]
        console = _console()
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))

        with patch("orion.cli.cli_performance._get_performance_metrics", return_value=pm):
            handle_performance_command(["/performance", "detail"], console)

        # Should have printed many lines covering all sections
        assert console._print.call_count > 5


class TestUnknownSubcommand:
    """CP-07: Unknown subcommand → usage info."""

    def test_unknown_subcommand_shows_usage(self):
        console = _console()
        lessons = [_lesson()]
        pm = PerformanceMetrics(execution_memory=_mock_memory(lessons))

        with patch("orion.cli.cli_performance._get_performance_metrics", return_value=pm):
            handle_performance_command(["/performance", "foobar"], console)

        calls = [str(c) for c in console.print_info.call_args_list]
        assert any("Usage" in c for c in calls)


class TestCommandsWiring:
    """CP-08: /performance is wired into commands.py."""

    def test_performance_command_routed(self):
        from orion.cli.commands import handle_command

        console = _console()

        with patch("orion.cli.cli_performance._get_performance_metrics", return_value=None):
            result = handle_command("/performance", console, ".", "safe")

        assert result == {}
        # Should have printed the "not available" message
        console.print_info.assert_called()
