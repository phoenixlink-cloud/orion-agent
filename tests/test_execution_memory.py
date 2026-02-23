# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ExecutionMemory — lesson capture, query, dependency map, known fixes.

Phase 4D.1: 18 tests covering:
- Lesson creation from FeedbackResult (EM-01 to EM-03)
- Confidence calculation (EM-04)
- Tag extraction (EM-05 to EM-07)
- Memory pattern format (EM-08)
- Lesson text generation (EM-09 to EM-11)
- Query filtering (EM-12 to EM-13)
- Fallback storage (EM-14 to EM-15)
- Dependency map (EM-16)
- Known fixes ranking (EM-17)
- Promotion threshold (EM-18)
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orion.ara.execution_feedback import ErrorCategory, FeedbackResult, FixAction
from orion.ara.execution_memory import ExecutionLesson, ExecutionMemory


# ---------------------------------------------------------------------------
# Helpers — mock FeedbackResult factory
# ---------------------------------------------------------------------------


def _make_feedback(
    *,
    command: str = "python app.py",
    success: bool = True,
    attempts: int = 1,
    error_category: ErrorCategory = ErrorCategory.UNKNOWN,
    fixes: list[FixAction] | None = None,
    duration: float = 2.5,
    stderr: str = "",
    stdout: str = "",
) -> FeedbackResult:
    return FeedbackResult(
        original_command=command,
        success=success,
        attempts=attempts,
        final_exit_code=0 if success else 1,
        final_stdout=stdout,
        final_stderr=stderr,
        error_category=error_category,
        fixes_applied=fixes or [],
        total_duration_seconds=duration,
    )


# ===========================================================================
# Tests
# ===========================================================================


class TestLessonCapture:
    """EM-01 to EM-03: Lesson creation from various FeedbackResult outcomes."""

    def test_lesson_from_first_attempt_success(self):
        """EM-01: First-attempt success → outcome='success', confidence=0.9."""
        em = ExecutionMemory()
        fb = _make_feedback(success=True, attempts=1)
        lesson = em.capture_lesson(fb, "Build Flask API", "python", "sess-1")

        assert lesson.outcome == "success"
        assert lesson.first_attempt_success is True
        assert lesson.confidence == 0.9
        assert lesson.retries == 0
        assert lesson.stack == "python"
        assert lesson.session_id == "sess-1"
        assert lesson.command == "python app.py"

    def test_lesson_from_failure_fixed(self):
        """EM-02: Failure that was fixed → outcome='failure_fixed', fix_applied populated."""
        fix = FixAction(
            description="Install flask",
            install_command="pip install flask",
            category=ErrorCategory.MISSING_DEPENDENCY,
            confidence=0.8,
        )
        fb = _make_feedback(
            success=True,
            attempts=2,
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            fixes=[fix],
            stderr="ModuleNotFoundError: No module named 'flask'",
        )
        em = ExecutionMemory()
        lesson = em.capture_lesson(fb, "Run Flask app", "python", "sess-2")

        assert lesson.outcome == "failure_fixed"
        assert lesson.fix_applied == "pip install flask"
        assert lesson.retries == 1
        assert lesson.error_category == "missing_dependency"
        assert lesson.first_attempt_success is False

    def test_lesson_from_permanent_failure(self):
        """EM-03: Permanent failure → outcome='failure_permanent', confidence=0.5."""
        fb = _make_feedback(
            success=False,
            attempts=4,
            error_category=ErrorCategory.RUNTIME,
            stderr="RuntimeError: something broke",
        )
        em = ExecutionMemory()
        lesson = em.capture_lesson(fb, "Run broken code", "python", "sess-3")

        assert lesson.outcome == "failure_permanent"
        assert lesson.confidence == 0.5
        assert lesson.retries == 3
        assert lesson.fix_applied is None


class TestConfidence:
    """EM-04: Confidence decreases with retries."""

    def test_confidence_decreases_with_retries(self):
        em = ExecutionMemory()

        # 1 retry → attempts=2
        fb1 = _make_feedback(success=True, attempts=2)
        l1 = em.capture_lesson(fb1, "t", "python", "s")

        # 3 retries → attempts=4
        fb3 = _make_feedback(success=True, attempts=4)
        l3 = em.capture_lesson(fb3, "t", "python", "s")

        # Confidence should decrease with more retries
        assert l1.confidence > l3.confidence
        # 2 attempts: 0.85 - 0.05 = 0.80
        assert l1.confidence == pytest.approx(0.80, abs=0.01)
        # 4 attempts: 0.85 - 0.15 = 0.70
        assert l3.confidence == pytest.approx(0.70, abs=0.01)


class TestTags:
    """EM-05 to EM-07: Tag extraction."""

    def test_tags_include_stack(self):
        """EM-05: Tags always include the stack name."""
        em = ExecutionMemory()
        fb = _make_feedback()
        lesson = em.capture_lesson(fb, "test", "node", "s")
        assert "node" in lesson.tags

    def test_tags_extract_pip_packages(self):
        """EM-06: pip install packages appear in tags."""
        fix = FixAction(
            install_command="pip install flask requests",
            category=ErrorCategory.MISSING_DEPENDENCY,
        )
        fb = _make_feedback(
            success=True,
            attempts=2,
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            fixes=[fix],
        )
        em = ExecutionMemory()
        lesson = em.capture_lesson(fb, "test", "python", "s")
        assert "flask" in lesson.tags
        assert "requests" in lesson.tags

    def test_tags_extract_npm_packages(self):
        """EM-07: npm install packages appear in tags."""
        fix = FixAction(
            install_command="npm install express",
            category=ErrorCategory.MISSING_DEPENDENCY,
        )
        fb = _make_feedback(
            success=True,
            attempts=2,
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            fixes=[fix],
        )
        em = ExecutionMemory()
        lesson = em.capture_lesson(fb, "test", "node", "s")
        assert "express" in lesson.tags


class TestMemoryPattern:
    """EM-08: Pattern dict format."""

    def test_to_memory_pattern_format(self):
        """EM-08: Pattern has correct keys for memory system."""
        em = ExecutionMemory()
        fb = _make_feedback()
        lesson = em.capture_lesson(fb, "test", "python", "s")
        pattern = lesson.to_memory_pattern()

        assert "id" in pattern
        assert "content" in pattern
        assert "category" in pattern
        assert pattern["category"] == "execution-lesson"
        assert "confidence" in pattern
        assert "tags" in pattern
        assert "metadata" in pattern
        assert "stack" in pattern["metadata"]
        assert "command" in pattern["metadata"]
        assert "outcome" in pattern["metadata"]


class TestLessonText:
    """EM-09 to EM-11: Human-readable lesson text."""

    def test_lesson_text_success(self):
        """EM-09: Success text mentions first attempt."""
        lesson = ExecutionLesson(
            command="python app.py",
            outcome="success",
            first_attempt_success=True,
            stack="python",
        )
        text = lesson._generate_lesson_text()
        assert "succeeded on first attempt" in text
        assert "python" in text

    def test_lesson_text_fixed(self):
        """EM-10: Fixed failure text mentions error and fix."""
        lesson = ExecutionLesson(
            command="python app.py",
            outcome="failure_fixed",
            error_category="missing_dependency",
            error_message="No module named 'flask'",
            fix_applied="pip install flask",
            retries=1,
            stack="python",
        )
        text = lesson._generate_lesson_text()
        assert "failed with missing_dependency" in text
        assert "pip install flask" in text.lower() or "pip install flask" in text

    def test_lesson_text_permanent_failure(self):
        """EM-11: Permanent failure text mentions no fix found."""
        lesson = ExecutionLesson(
            command="python app.py",
            outcome="failure_permanent",
            error_category="runtime",
            error_message="RuntimeError: fatal",
            retries=3,
            stack="python",
        )
        text = lesson._generate_lesson_text()
        assert "permanently" in text
        assert "No fix found" in text


class TestQuery:
    """EM-12 to EM-13: Query filtering."""

    def _populate(self, em: ExecutionMemory):
        """Populate with diverse lessons."""
        fb_py = _make_feedback(
            command="python app.py",
            success=True,
            attempts=2,
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            fixes=[FixAction(install_command="pip install flask")],
        )
        em.capture_lesson(fb_py, "Flask app", "python", "s1")

        fb_node = _make_feedback(
            command="node server.js",
            success=True,
            attempts=2,
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            fixes=[FixAction(install_command="npm install express")],
        )
        em.capture_lesson(fb_node, "Node server", "node", "s2")

        fb_runtime = _make_feedback(
            command="python test.py",
            success=False,
            attempts=3,
            error_category=ErrorCategory.RUNTIME,
            stderr="AssertionError",
        )
        em.capture_lesson(fb_runtime, "Run tests", "python", "s3")

    def test_query_by_stack(self):
        """EM-12: query_lessons(stack='python') filters correctly."""
        em = ExecutionMemory()
        self._populate(em)
        results = em.query_lessons(stack="python")
        assert len(results) == 2
        assert all(l.stack == "python" for l in results)

    def test_query_by_error_category(self):
        """EM-13: query_lessons(error_category='missing_dependency') works."""
        em = ExecutionMemory()
        self._populate(em)
        results = em.query_lessons(error_category="missing_dependency")
        assert len(results) == 2
        assert all(l.error_category == "missing_dependency" for l in results)


class TestFallbackStorage:
    """EM-14 to EM-15: JSON fallback when memory engine unavailable."""

    def test_fallback_storage(self):
        """EM-14: Without memory_engine, lessons persist to JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fallback = Path(tmpdir) / "lessons.json"
            em = ExecutionMemory()
            em._fallback_path = fallback

            fb = _make_feedback()
            em.capture_lesson(fb, "test", "python", "s")

            assert fallback.exists()
            data = json.loads(fallback.read_text(encoding="utf-8"))
            assert len(data) == 1
            assert data[0]["category"] == "execution-lesson"

    def test_fallback_ring_buffer(self):
        """EM-15: JSON fallback keeps max 1000 lessons."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fallback = Path(tmpdir) / "lessons.json"
            em = ExecutionMemory()
            em._fallback_path = fallback

            # Pre-seed with 999 entries
            seed = [{"id": str(i), "content": f"lesson-{i}"} for i in range(999)]
            fallback.write_text(json.dumps(seed), encoding="utf-8")

            # Add 2 more → should trigger trim to 1000
            fb = _make_feedback()
            em.capture_lesson(fb, "test1", "python", "s")
            em.capture_lesson(fb, "test2", "python", "s")

            data = json.loads(fallback.read_text(encoding="utf-8"))
            assert len(data) == 1000


class TestDependencyMap:
    """EM-16: Dependency map from lessons."""

    def test_dependency_map_from_lessons(self):
        """EM-16: get_dependency_map builds correct map from past fixes."""
        em = ExecutionMemory()

        # Simulate: "Build Flask API" failed, fixed with pip install flask
        fix = FixAction(install_command="pip install flask")
        fb = _make_feedback(
            success=True,
            attempts=2,
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            fixes=[fix],
        )
        em.capture_lesson(fb, "Build Flask API", "python", "s")

        dep_map = em.get_dependency_map("python")
        assert "flask" in dep_map
        assert "flask" in dep_map["flask"]


class TestKnownFixes:
    """EM-17: Known fixes ranked by confidence * times_applied."""

    def test_known_fixes_ranked(self):
        """EM-17: get_known_fixes returns fixes sorted by confidence."""
        em = ExecutionMemory()

        # Add multiple lessons with the same fix
        for _ in range(3):
            fix = FixAction(install_command="pip install flask")
            fb = _make_feedback(
                success=True,
                attempts=2,
                error_category=ErrorCategory.MISSING_DEPENDENCY,
                fixes=[fix],
            )
            em.capture_lesson(fb, "Flask app", "python", "s")

        # Add one lesson with a different fix
        fix2 = FixAction(install_command="pip install requests")
        fb2 = _make_feedback(
            success=True,
            attempts=2,
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            fixes=[fix2],
        )
        em.capture_lesson(fb2, "HTTP client", "python", "s")

        fixes = em.get_known_fixes("missing_dependency", "python")
        assert len(fixes) == 2
        # flask should be first (3x applied)
        assert fixes[0]["fix"] == "pip install flask"
        assert fixes[0]["times_applied"] == 3
        assert fixes[1]["fix"] == "pip install requests"
        assert fixes[1]["times_applied"] == 1


class TestPromotion:
    """EM-18: Lessons with confidence ≥0.85 and 3+ similar → promote."""

    def test_promotion_threshold(self):
        """EM-18: High-confidence recurring lessons are promoted to Tier 3."""
        mock_engine = MagicMock()
        em = ExecutionMemory(memory_engine=mock_engine)

        # Create 4 similar lessons with same error_category + stack
        # First 3 build up the count
        for i in range(3):
            fix = FixAction(install_command="pip install flask")
            fb = _make_feedback(
                success=True,
                attempts=1,  # first-attempt success → confidence=0.9
                error_category=ErrorCategory.MISSING_DEPENDENCY,
                fixes=[fix],
            )
            em.capture_lesson(fb, f"Flask task {i}", "python", "s")

        # Check that remember was called with tier=2 for the first 3
        tier2_calls = [
            c for c in mock_engine.remember.call_args_list
            if c.kwargs.get("tier") == 2 or (c.args and len(c.args) > 1 and c.args[1] == 2)
        ]
        assert len(tier2_calls) >= 3

        # The 4th lesson (confidence=0.9 ≥ 0.85, similar count ≥ 3)
        # should trigger a tier=3 promotion call
        fix = FixAction(install_command="pip install flask")
        fb = _make_feedback(
            success=True,
            attempts=1,
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            fixes=[fix],
        )
        em.capture_lesson(fb, "Flask task 4", "python", "s")

        # Should now have at least one tier=3 call
        tier3_calls = [
            c for c in mock_engine.remember.call_args_list
            if c.kwargs.get("tier") == 3
        ]
        assert len(tier3_calls) >= 1


class TestSerialization:
    """Additional serialization tests for ExecutionLesson."""

    def test_to_dict_roundtrip(self):
        lesson = ExecutionLesson(
            lesson_id="test-123",
            timestamp="2025-01-01T00:00:00Z",
            session_id="sess-1",
            task_description="Build Flask API",
            stack="python",
            command="python app.py",
            outcome="success",
            confidence=0.9,
            tags=["python", "flask"],
        )
        d = lesson.to_dict()
        restored = ExecutionLesson.from_dict(d)
        assert restored.lesson_id == lesson.lesson_id
        assert restored.stack == lesson.stack
        assert restored.tags == lesson.tags

    def test_from_dict_ignores_extra_keys(self):
        d = {
            "lesson_id": "x",
            "stack": "node",
            "unknown_field": "ignored",
        }
        lesson = ExecutionLesson.from_dict(d)
        assert lesson.lesson_id == "x"
        assert lesson.stack == "node"


class TestFeedbackLoopIntegration:
    """Verify ExecutionFeedbackLoop accepts execution_memory parameter."""

    def test_feedback_loop_accepts_execution_memory(self):
        from orion.ara.execution_feedback import ExecutionFeedbackLoop

        mock_container = MagicMock()
        mock_memory = MagicMock()

        loop = ExecutionFeedbackLoop(
            container=mock_container,
            execution_memory=mock_memory,
        )
        assert loop.execution_memory is mock_memory


class TestTaskExecutorIntegration:
    """Verify ARATaskExecutor accepts execution_memory parameter."""

    def test_task_executor_accepts_execution_memory(self):
        from orion.ara.task_executor import ARATaskExecutor

        mock_memory = MagicMock()
        executor = ARATaskExecutor(execution_memory=mock_memory)
        assert executor._execution_memory is mock_memory
