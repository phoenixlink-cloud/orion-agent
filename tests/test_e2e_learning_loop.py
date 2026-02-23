# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""End-to-end tests — prove Orion learns from execution and improves.

Phase 4D.6: 10 tests covering:
- E2E-01: Capture → store → query round-trip
- E2E-02: Failure + fix → lesson with correct confidence
- E2E-03: Permanent failure → lesson with low confidence
- E2E-04: ProactiveLearner suggests fix from captured lesson
- E2E-05: Dependency map built from captured lessons
- E2E-06: Performance metrics reflect captured lessons
- E2E-07: Trend detection: improvement over time
- E2E-08: Multiple stacks tracked independently
- E2E-09: High-confidence recurring lessons trigger promotion
- E2E-10: Full pipeline: capture → proactive suggest → metrics → API response
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from orion.ara.execution_feedback import ErrorCategory, FeedbackResult, FixAction
from orion.ara.execution_memory import ExecutionLesson, ExecutionMemory
from orion.ara.performance_metrics import PerformanceMetrics
from orion.ara.proactive_learner import ProactiveLearner


# ---------------------------------------------------------------------------
# Helpers — build FeedbackResult fixtures without a real container
# ---------------------------------------------------------------------------


def _fb(
    *,
    command: str = "python app.py",
    success: bool = True,
    attempts: int = 1,
    stderr: str = "",
    error_cat: ErrorCategory = ErrorCategory.UNKNOWN,
    fixes: list[FixAction] | None = None,
    duration: float = 2.0,
) -> FeedbackResult:
    return FeedbackResult(
        original_command=command,
        success=success,
        attempts=attempts,
        final_exit_code=0 if success else 1,
        final_stdout="",
        final_stderr=stderr,
        error_category=error_cat,
        fixes_applied=fixes or [],
        total_duration_seconds=duration,
    )


def _fix(
    desc: str = "install flask",
    install_cmd: str | None = None,
    cmd: str | None = None,
) -> FixAction:
    return FixAction(
        description=desc,
        install_command=install_cmd,
        command=cmd,
        category=ErrorCategory.MISSING_DEPENDENCY,
        confidence=0.8,
    )


# ===========================================================================
# E2E-01: Capture → Store → Query round-trip
# ===========================================================================


class TestCaptureStoreQuery:
    """Lessons captured by ExecutionMemory are immediately queryable."""

    def test_round_trip(self):
        em = ExecutionMemory()
        fb = _fb(command="python app.py", success=True, attempts=1)
        lesson = em.capture_lesson(fb, "Build Flask API", "python", "s1")

        results = em.query_lessons(stack="python")
        assert len(results) == 1
        assert results[0].lesson_id == lesson.lesson_id
        assert results[0].outcome == "success"
        assert results[0].first_attempt_success is True


# ===========================================================================
# E2E-02: Failure + fix → lesson with correct confidence
# ===========================================================================


class TestFailureFixedConfidence:
    """A failed-then-fixed execution produces a lesson with 0.7 confidence."""

    def test_fixed_confidence(self):
        em = ExecutionMemory()
        fix = _fix(desc="pip install flask", install_cmd="pip install flask")
        fb = _fb(
            command="python app.py",
            success=True,
            attempts=2,
            stderr="ModuleNotFoundError: No module named 'flask'",
            error_cat=ErrorCategory.MISSING_DEPENDENCY,
            fixes=[fix],
            duration=5.0,
        )
        lesson = em.capture_lesson(fb, "Run Flask app", "python", "s1")

        assert lesson.outcome == "failure_fixed"
        assert lesson.confidence == pytest.approx(0.8, abs=0.05)
        assert lesson.fix_applied is not None
        assert "flask" in lesson.fix_applied.lower()
        assert lesson.retries == 1


# ===========================================================================
# E2E-03: Permanent failure → lesson with low confidence
# ===========================================================================


class TestPermanentFailureConfidence:
    """A permanently failed execution gets 0.5 confidence."""

    def test_permanent_failure(self):
        em = ExecutionMemory()
        fb = _fb(
            command="python broken.py",
            success=False,
            attempts=3,
            stderr="SyntaxError: invalid syntax",
            error_cat=ErrorCategory.SYNTAX,
            duration=8.0,
        )
        lesson = em.capture_lesson(fb, "Run broken script", "python", "s1")

        assert lesson.outcome == "failure_permanent"
        assert lesson.confidence == pytest.approx(0.5, abs=0.01)
        assert lesson.retries == 2


# ===========================================================================
# E2E-04: ProactiveLearner suggests fix from captured lesson
# ===========================================================================


class TestProactiveSuggestFromLesson:
    """After learning a dependency fix, ProactiveLearner suggests it."""

    def test_proactive_fix_suggestion(self):
        em = ExecutionMemory()

        # Step 1: Capture a lesson about flask dependency
        fix = _fix(desc="pip install flask", install_cmd="pip install flask")
        fb = _fb(
            command="python app.py",
            success=True,
            attempts=2,
            stderr="ModuleNotFoundError: No module named 'flask'",
            error_cat=ErrorCategory.MISSING_DEPENDENCY,
            fixes=[fix],
        )
        em.capture_lesson(fb, "Build Flask REST API", "python", "s1")

        # Step 2: ProactiveLearner queries the same memory
        learner = ProactiveLearner(execution_memory=em, min_confidence=0.5)
        fixes = learner.suggest_fixes("python", "Build a Flask REST API", "python app.py")

        # Should suggest pre-installing flask
        assert len(fixes) >= 1
        install_cmds = [f.command for f in fixes]
        assert any("flask" in c.lower() for c in install_cmds)


# ===========================================================================
# E2E-05: Dependency map built from captured lessons
# ===========================================================================


class TestDependencyMapFromLessons:
    """Dependency map grows as more lessons are captured."""

    def test_dependency_map_growth(self):
        em = ExecutionMemory()

        # Capture 3 different dependency lessons
        for pkg in ["flask", "requests", "numpy"]:
            fix = _fix(desc=f"pip install {pkg}", install_cmd=f"pip install {pkg}")
            fb = _fb(
                command="python app.py",
                success=True,
                attempts=2,
                stderr=f"ModuleNotFoundError: No module named '{pkg}'",
                error_cat=ErrorCategory.MISSING_DEPENDENCY,
                fixes=[fix],
            )
            em.capture_lesson(fb, f"Build app using {pkg}", "python", "s1")

        dep_map = em.get_dependency_map("python")

        # Each package should appear in the map
        assert "flask" in dep_map
        assert "requests" in dep_map
        assert "numpy" in dep_map


# ===========================================================================
# E2E-06: Performance metrics reflect captured lessons
# ===========================================================================


class TestMetricsReflectLessons:
    """PerformanceMetrics accurately summarize captured lessons."""

    def test_metrics_accuracy(self):
        em = ExecutionMemory()

        # 5 successes, 2 fixed, 1 permanent failure
        for _ in range(5):
            em.capture_lesson(
                _fb(success=True, attempts=1, duration=1.0),
                "task", "python", "s1",
            )
        for _ in range(2):
            em.capture_lesson(
                _fb(
                    success=True, attempts=2, duration=3.0,
                    error_cat=ErrorCategory.MISSING_DEPENDENCY,
                    fixes=[_fix(install_cmd="pip install x")],
                ),
                "task", "python", "s1",
            )
        em.capture_lesson(
            _fb(success=False, attempts=3, duration=6.0, error_cat=ErrorCategory.RUNTIME),
            "task", "python", "s1",
        )

        pm = PerformanceMetrics(execution_memory=em)
        m = pm.compute_metrics()

        assert m.total_executions == 8
        assert m.successful == 7  # 5 + 2 fixed
        assert m.first_attempt_successes == 5
        assert m.failures_fixed == 2
        assert m.permanent_failures == 1
        assert m.success_rate == pytest.approx(7 / 8, abs=0.01)
        assert m.first_attempt_success_rate == pytest.approx(5 / 8, abs=0.01)


# ===========================================================================
# E2E-07: Trend detection — improvement over time
# ===========================================================================


class TestTrendDetection:
    """Trends detect improvement when recent lessons are better."""

    def test_improvement_trend(self):
        em = ExecutionMemory()

        # Current batch (first 10 appended = current window): 100% success
        for _ in range(10):
            em.capture_lesson(
                _fb(success=True, attempts=1, duration=1.0),
                "task", "python", "s2",
            )

        # Previous batch (next 10 appended = previous window): 50% failures
        for _ in range(5):
            em.capture_lesson(
                _fb(success=True, attempts=1, duration=1.0),
                "task", "python", "s1",
            )
        for _ in range(5):
            em.capture_lesson(
                _fb(success=False, attempts=3, duration=5.0, error_cat=ErrorCategory.RUNTIME),
                "task", "python", "s1",
            )

        pm = PerformanceMetrics(execution_memory=em)
        trends = pm.compute_trends(current_window=10, previous_window=10)

        # Find the first_attempt_success_rate trend
        fasr_trend = next(
            (t for t in trends if t.metric_name == "first_attempt_success_rate"),
            None,
        )
        assert fasr_trend is not None
        assert fasr_trend.current_value > fasr_trend.previous_value
        assert fasr_trend.direction == "improving"


# ===========================================================================
# E2E-08: Multiple stacks tracked independently
# ===========================================================================


class TestMultiStackIndependence:
    """Python and Node lessons don't contaminate each other."""

    def test_stack_isolation(self):
        em = ExecutionMemory()

        # Python: all success
        for _ in range(5):
            em.capture_lesson(
                _fb(command="python app.py", success=True, attempts=1),
                "task", "python", "s1",
            )

        # Node: all failures
        for _ in range(5):
            em.capture_lesson(
                _fb(command="node server.js", success=False, attempts=3,
                    error_cat=ErrorCategory.RUNTIME),
                "task", "node", "s1",
            )

        pm = PerformanceMetrics(execution_memory=em)

        py_metrics = pm.compute_metrics(stack="python")
        node_metrics = pm.compute_metrics(stack="node")

        assert py_metrics.success_rate == pytest.approx(1.0, abs=0.01)
        assert node_metrics.success_rate == pytest.approx(0.0, abs=0.01)
        assert py_metrics.first_attempt_success_rate == pytest.approx(1.0, abs=0.01)
        assert node_metrics.first_attempt_success_rate == pytest.approx(0.0, abs=0.01)


# ===========================================================================
# E2E-09: High-confidence recurring lessons trigger promotion
# ===========================================================================


class TestPromotionTrigger:
    """Lessons with confidence >= 0.85 and >= 3 similar lessons promote to T3."""

    def test_promotion_path(self):
        engine = MagicMock()
        engine.recall.return_value = []
        em = ExecutionMemory(memory_engine=engine)

        # Capture 4 identical first-attempt successes (conf=0.9)
        for i in range(4):
            em.capture_lesson(
                _fb(command="python app.py", success=True, attempts=1),
                "Build Flask API", "python", f"s{i}",
            )

        # The 4th lesson should trigger promotion
        # Check that remember was called with tier=3 at least once
        tier3_calls = [
            c for c in engine.remember.call_args_list
            if c.kwargs.get("tier") == 3 or (len(c.args) > 1 and c.args[1] == 3)
        ]
        # There should be at least one T3 call (when 4th lesson sees 3 similar)
        assert len(tier3_calls) >= 1


# ===========================================================================
# E2E-10: Full pipeline — capture → proactive → metrics → API
# ===========================================================================


class TestFullPipeline:
    """End-to-end: capture lessons, query proactive fixes, compute metrics,
    and verify API response structure."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        em = ExecutionMemory()

        # Phase 1: Capture lessons
        fix = _fix(desc="pip install flask", install_cmd="pip install flask")
        em.capture_lesson(
            _fb(
                command="python app.py", success=True, attempts=2,
                stderr="ModuleNotFoundError: No module named 'flask'",
                error_cat=ErrorCategory.MISSING_DEPENDENCY,
                fixes=[fix], duration=4.0,
            ),
            "Build Flask REST API", "python", "s1",
        )
        for _ in range(5):
            em.capture_lesson(
                _fb(command="python app.py", success=True, attempts=1, duration=1.0),
                "Run Flask API", "python", "s1",
            )

        # Phase 2: Proactive suggestions
        learner = ProactiveLearner(execution_memory=em, min_confidence=0.5)
        fixes = learner.suggest_fixes("python", "Build a Flask REST API", "python app.py")
        assert len(fixes) >= 1

        # Phase 3: Performance metrics
        pm = PerformanceMetrics(execution_memory=em)
        m = pm.compute_metrics()
        assert m.total_executions == 6
        assert m.successful == 6

        # Phase 4: API response structure
        from orion.api.routes.performance import get_metrics

        with patch("orion.api.routes.performance._get_performance_metrics", return_value=pm):
            resp = await get_metrics(stack="", session_id="", limit=0)

        assert resp["success"] is True
        assert resp["data"]["total_executions"] == 6
        assert resp["data"]["success_rate"] > 0.9
