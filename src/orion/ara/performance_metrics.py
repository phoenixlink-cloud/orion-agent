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
"""Performance Metrics Engine — track and analyze execution performance.

This module aggregates execution lessons into quantitative metrics:
- First-attempt success rate (FASR)
- Mean time to resolution (MTTR)
- Error category distribution
- Improvement trends over sliding windows

The metrics power the CLI dashboard (Phase 4D.4) and Web UI panel (4D.5).

See Phase 4D.3 specification.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orion.ara.execution_memory import ExecutionLesson, ExecutionMemory

logger = logging.getLogger("orion.ara.performance_metrics")

# ---------------------------------------------------------------------------
# ExecutionMetrics dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExecutionMetrics:
    """Snapshot of aggregated execution metrics for a given scope."""

    total_executions: int = 0
    successful: int = 0
    first_attempt_successes: int = 0
    failures_fixed: int = 0
    permanent_failures: int = 0

    # Rates (0.0 – 1.0)
    success_rate: float = 0.0
    first_attempt_success_rate: float = 0.0
    fix_rate: float = 0.0  # failures_fixed / (failures_fixed + permanent_failures)

    # Timing
    mean_duration_seconds: float = 0.0
    mean_retries: float = 0.0
    mean_time_to_resolution: float = 0.0

    # Error breakdown: {category_name: count}
    error_distribution: dict[str, int] = field(default_factory=dict)

    # Top fixes: [{fix, count, confidence}]
    top_fixes: list[dict[str, Any]] = field(default_factory=list)

    # Scope metadata
    stack: str = ""
    session_id: str = ""
    window_label: str = ""  # e.g. "last_10", "last_50", "all"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_executions": self.total_executions,
            "successful": self.successful,
            "first_attempt_successes": self.first_attempt_successes,
            "failures_fixed": self.failures_fixed,
            "permanent_failures": self.permanent_failures,
            "success_rate": round(self.success_rate, 4),
            "first_attempt_success_rate": round(self.first_attempt_success_rate, 4),
            "fix_rate": round(self.fix_rate, 4),
            "mean_duration_seconds": round(self.mean_duration_seconds, 2),
            "mean_retries": round(self.mean_retries, 2),
            "mean_time_to_resolution": round(self.mean_time_to_resolution, 2),
            "error_distribution": self.error_distribution,
            "top_fixes": self.top_fixes,
            "stack": self.stack,
            "session_id": self.session_id,
            "window_label": self.window_label,
        }


# ---------------------------------------------------------------------------
# PerformanceTrend dataclass
# ---------------------------------------------------------------------------


@dataclass
class PerformanceTrend:
    """Comparison of two metric windows to detect improvement or regression."""

    metric_name: str = ""
    current_value: float = 0.0
    previous_value: float = 0.0
    delta: float = 0.0
    direction: str = "stable"  # 'improving', 'regressing', 'stable'
    window_current: str = ""
    window_previous: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "current_value": round(self.current_value, 4),
            "previous_value": round(self.previous_value, 4),
            "delta": round(self.delta, 4),
            "direction": self.direction,
            "window_current": self.window_current,
            "window_previous": self.window_previous,
        }


# ---------------------------------------------------------------------------
# PerformanceMetrics — the engine
# ---------------------------------------------------------------------------


class PerformanceMetrics:
    """Aggregates execution lessons into quantitative performance metrics.

    Usage::

        pm = PerformanceMetrics(execution_memory=em)
        snapshot = pm.compute_metrics(stack="python")
        trends = pm.compute_trends(stack="python")
    """

    def __init__(self, execution_memory: ExecutionMemory | None = None) -> None:
        self._memory = execution_memory

    def compute_metrics(
        self,
        stack: str = "",
        session_id: str = "",
        limit: int = 0,
        window_label: str = "all",
    ) -> ExecutionMetrics:
        """Compute aggregated metrics from execution lessons.

        Args:
            stack: Filter by stack (empty = all stacks).
            session_id: Filter by session (empty = all sessions).
            limit: Max lessons to consider (0 = unlimited).
            window_label: Label for this computation window.

        Returns:
            ExecutionMetrics snapshot.
        """
        lessons = self._get_lessons(stack=stack, session_id=session_id, limit=limit)
        return self._aggregate(lessons, stack=stack, session_id=session_id, window_label=window_label)

    def compute_trends(
        self,
        stack: str = "",
        current_window: int = 10,
        previous_window: int = 10,
    ) -> list[PerformanceTrend]:
        """Compare recent performance against earlier performance.

        Splits lessons into two windows:
        - Current: last ``current_window`` lessons
        - Previous: the ``previous_window`` lessons before that

        Returns trends for key metrics.
        """
        lessons = self._get_lessons(stack=stack)
        if len(lessons) < current_window + previous_window:
            # Not enough data for comparison
            return []

        # Lessons are assumed newest-first from query_lessons
        current_lessons = lessons[:current_window]
        previous_lessons = lessons[current_window : current_window + previous_window]

        current = self._aggregate(
            current_lessons, stack=stack, window_label=f"last_{current_window}"
        )
        previous = self._aggregate(
            previous_lessons, stack=stack, window_label=f"prev_{previous_window}"
        )

        trends: list[PerformanceTrend] = []

        # Compare key metrics
        metric_pairs = [
            ("first_attempt_success_rate", current.first_attempt_success_rate, previous.first_attempt_success_rate),
            ("success_rate", current.success_rate, previous.success_rate),
            ("fix_rate", current.fix_rate, previous.fix_rate),
            ("mean_retries", current.mean_retries, previous.mean_retries),
            ("mean_duration_seconds", current.mean_duration_seconds, previous.mean_duration_seconds),
        ]

        for name, cur_val, prev_val in metric_pairs:
            delta = cur_val - prev_val
            # For retries and duration, lower is better
            lower_is_better = name in ("mean_retries", "mean_duration_seconds")
            if abs(delta) < 0.01:
                direction = "stable"
            elif lower_is_better:
                direction = "improving" if delta < 0 else "regressing"
            else:
                direction = "improving" if delta > 0 else "regressing"

            trends.append(
                PerformanceTrend(
                    metric_name=name,
                    current_value=cur_val,
                    previous_value=prev_val,
                    delta=delta,
                    direction=direction,
                    window_current=f"last_{current_window}",
                    window_previous=f"prev_{previous_window}",
                )
            )

        return trends

    def get_error_hotspots(
        self,
        stack: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return the most frequent error categories.

        Returns:
            List of {category, count, percentage} sorted by count desc.
        """
        lessons = self._get_lessons(stack=stack)
        if not lessons:
            return []

        counts: dict[str, int] = {}
        total_errors = 0
        for l in lessons:
            if l.outcome != "success" and l.error_category:
                cat = l.error_category
                counts[cat] = counts.get(cat, 0) + 1
                total_errors += 1

        if not total_errors:
            return []

        hotspots = [
            {
                "category": cat,
                "count": count,
                "percentage": round(count / total_errors * 100, 1),
            }
            for cat, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        ]
        return hotspots[:limit]

    def get_stack_comparison(self) -> list[dict[str, Any]]:
        """Compare performance across all stacks.

        Returns:
            List of {stack, total, success_rate, fasr, mean_retries}.
        """
        if not self._memory:
            return []

        # Get all lessons and group by stack
        all_lessons = self._get_lessons()
        stacks: dict[str, list] = {}
        for l in all_lessons:
            stacks.setdefault(l.stack, []).append(l)

        result = []
        for stack_name, lessons in sorted(stacks.items()):
            m = self._aggregate(lessons, stack=stack_name)
            result.append({
                "stack": stack_name,
                "total": m.total_executions,
                "success_rate": round(m.success_rate, 4),
                "first_attempt_success_rate": round(m.first_attempt_success_rate, 4),
                "mean_retries": round(m.mean_retries, 2),
            })

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_lessons(
        self,
        stack: str = "",
        session_id: str = "",
        limit: int = 0,
    ) -> list:
        """Retrieve lessons from ExecutionMemory."""
        if not self._memory:
            return []

        kwargs: dict[str, Any] = {}
        if stack:
            kwargs["stack"] = stack
        if limit:
            kwargs["limit"] = limit

        lessons = self._memory.query_lessons(**kwargs)

        # Filter by session if specified
        if session_id:
            lessons = [l for l in lessons if l.session_id == session_id]

        return lessons

    def _aggregate(
        self,
        lessons: list,
        stack: str = "",
        session_id: str = "",
        window_label: str = "",
    ) -> ExecutionMetrics:
        """Aggregate a list of ExecutionLessons into ExecutionMetrics."""
        metrics = ExecutionMetrics(
            stack=stack,
            session_id=session_id,
            window_label=window_label,
        )

        if not lessons:
            return metrics

        metrics.total_executions = len(lessons)

        durations: list[float] = []
        retries_list: list[int] = []
        fix_counts: dict[str, int] = {}

        for l in lessons:
            if l.outcome == "success":
                metrics.successful += 1
                if l.first_attempt_success:
                    metrics.first_attempt_successes += 1
            elif l.outcome == "failure_fixed":
                metrics.successful += 1
                metrics.failures_fixed += 1
            elif l.outcome == "failure_permanent":
                metrics.permanent_failures += 1

            if l.duration_seconds and l.duration_seconds > 0:
                durations.append(l.duration_seconds)

            retries_list.append(l.retries)

            if l.error_category:
                metrics.error_distribution[l.error_category] = (
                    metrics.error_distribution.get(l.error_category, 0) + 1
                )

            if l.fix_applied:
                fix_counts[l.fix_applied] = fix_counts.get(l.fix_applied, 0) + 1

        # Rates
        total = metrics.total_executions
        metrics.success_rate = metrics.successful / total if total else 0.0
        metrics.first_attempt_success_rate = (
            metrics.first_attempt_successes / total if total else 0.0
        )
        failures_total = metrics.failures_fixed + metrics.permanent_failures
        metrics.fix_rate = (
            metrics.failures_fixed / failures_total if failures_total else 0.0
        )

        # Timing
        if durations:
            metrics.mean_duration_seconds = statistics.mean(durations)
        if retries_list:
            metrics.mean_retries = statistics.mean(retries_list)

        # MTTR: mean duration of fixed failures
        fixed_durations = [
            l.duration_seconds
            for l in lessons
            if l.outcome == "failure_fixed" and l.duration_seconds > 0
        ]
        if fixed_durations:
            metrics.mean_time_to_resolution = statistics.mean(fixed_durations)

        # Top fixes
        metrics.top_fixes = [
            {"fix": fix, "count": count}
            for fix, count in sorted(fix_counts.items(), key=lambda x: x[1], reverse=True)
        ][:5]

        return metrics
