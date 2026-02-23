# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ProactiveLearner — pre-emptive fix suggestions from past lessons.

Phase 4D.2: 14 tests covering:
- No memory → empty suggestions (PL-01)
- Dependency fix from known_fixes (PL-02)
- Error prevention from command pattern (PL-03)
- Dependency map suggestions (PL-04)
- Confidence threshold filtering (PL-05)
- Deduplication (PL-06)
- Sorting by confidence (PL-07)
- Task context generation (PL-08)
- Empty task context when no lessons (PL-09)
- ProactiveFix.to_dict (PL-10)
- Package extraction from pip (PL-11)
- Package extraction from npm (PL-12)
- Build install command per stack (PL-13)
- ARATaskExecutor auto-creates proactive learner (PL-14)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from orion.ara.execution_memory import ExecutionLesson, ExecutionMemory
from orion.ara.proactive_learner import (
    ProactiveFix,
    ProactiveLearner,
    _build_install_command,
    _extract_package_names,
)


# ---------------------------------------------------------------------------
# Helpers — mock ExecutionMemory
# ---------------------------------------------------------------------------


def _mock_memory(
    *,
    known_fixes: list[dict] | None = None,
    lessons: list[ExecutionLesson] | None = None,
    dep_map: dict[str, set[str]] | None = None,
) -> MagicMock:
    """Create a mock ExecutionMemory with controllable returns."""
    mem = MagicMock(spec=ExecutionMemory)
    mem.get_known_fixes.return_value = known_fixes or []
    mem.query_lessons.return_value = lessons or []
    mem.get_dependency_map.return_value = dep_map or {}
    return mem


# ===========================================================================
# Tests
# ===========================================================================


class TestNoMemory:
    """PL-01: Without ExecutionMemory, returns empty list."""

    def test_no_memory_returns_empty(self):
        learner = ProactiveLearner(execution_memory=None)
        fixes = learner.suggest_fixes("python", "Build Flask API", "python app.py")
        assert fixes == []


class TestDependencyFix:
    """PL-02: Known dependency fixes matched against task description."""

    def test_dependency_fix_from_known_fixes(self):
        mem = _mock_memory(
            known_fixes=[
                {
                    "fix": "pip install flask",
                    "times_applied": 3,
                    "confidence": 0.85,
                    "lesson_id": "L-001",
                },
            ]
        )
        learner = ProactiveLearner(execution_memory=mem)
        fixes = learner.suggest_fixes("python", "Build Flask REST API")

        assert len(fixes) >= 1
        flask_fix = [f for f in fixes if "flask" in f.command]
        assert len(flask_fix) == 1
        assert flask_fix[0].fix_type == "install_dependency"
        assert flask_fix[0].times_proven == 3


class TestErrorPrevention:
    """PL-03: Match command pattern to past failure_fixed lessons."""

    def test_error_prevention_from_command_pattern(self):
        lesson = ExecutionLesson(
            lesson_id="L-010",
            command="python app.py",
            outcome="failure_fixed",
            fix_applied="pip install flask",
            confidence=0.8,
            stack="python",
            error_category="missing_dependency",
        )
        mem = _mock_memory(lessons=[lesson])
        learner = ProactiveLearner(execution_memory=mem)
        fixes = learner.suggest_fixes("python", "Run my app", "python app.py")

        # Should suggest the fix that was applied before
        assert len(fixes) >= 1
        assert any("flask" in f.command for f in fixes)


class TestDependencyMapSuggestion:
    """PL-04: Suggestions from dependency map."""

    def test_dependency_map_fix(self):
        mem = _mock_memory(
            dep_map={"flask": {"flask"}, "express": {"express"}},
        )
        learner = ProactiveLearner(execution_memory=mem)
        fixes = learner.suggest_fixes("python", "Build a Flask API")

        assert len(fixes) >= 1
        assert any("flask" in f.command for f in fixes)


class TestConfidenceThreshold:
    """PL-05: Fixes below min_confidence are filtered out."""

    def test_low_confidence_filtered(self):
        mem = _mock_memory(
            known_fixes=[
                {
                    "fix": "pip install flask",
                    "times_applied": 1,
                    "confidence": 0.4,  # Below threshold
                    "lesson_id": "L-002",
                },
            ]
        )
        learner = ProactiveLearner(execution_memory=mem, min_confidence=0.7)
        fixes = learner.suggest_fixes("python", "Build Flask app")
        assert fixes == []

    def test_high_confidence_passes(self):
        mem = _mock_memory(
            known_fixes=[
                {
                    "fix": "pip install flask",
                    "times_applied": 3,
                    "confidence": 0.9,
                    "lesson_id": "L-003",
                },
            ]
        )
        learner = ProactiveLearner(execution_memory=mem, min_confidence=0.7)
        fixes = learner.suggest_fixes("python", "Build Flask app")
        assert len(fixes) >= 1


class TestDeduplication:
    """PL-06: Duplicate commands are deduplicated."""

    def test_deduplication(self):
        # Same fix from different strategies
        mem = _mock_memory(
            known_fixes=[
                {
                    "fix": "pip install flask",
                    "times_applied": 3,
                    "confidence": 0.9,
                    "lesson_id": "L-004",
                },
            ],
            dep_map={"flask": {"flask"}},
        )
        learner = ProactiveLearner(execution_memory=mem)
        fixes = learner.suggest_fixes("python", "Build Flask API")

        flask_fixes = [f for f in fixes if "flask" in f.command.lower()]
        assert len(flask_fixes) == 1  # Deduplicated


class TestSorting:
    """PL-07: Results sorted by confidence descending."""

    def test_sorted_by_confidence(self):
        mem = _mock_memory(
            known_fixes=[
                {
                    "fix": "pip install flask",
                    "times_applied": 3,
                    "confidence": 0.85,
                    "lesson_id": "L-005",
                },
                {
                    "fix": "pip install requests",
                    "times_applied": 5,
                    "confidence": 0.95,
                    "lesson_id": "L-006",
                },
            ]
        )
        learner = ProactiveLearner(execution_memory=mem)
        fixes = learner.suggest_fixes("python", "Build Flask app with requests")

        assert len(fixes) == 2
        assert fixes[0].confidence >= fixes[1].confidence


class TestTaskContext:
    """PL-08 to PL-09: Task context generation."""

    def test_task_context_with_lessons(self):
        """PL-08: Context string includes relevant lessons."""
        lessons = [
            ExecutionLesson(
                command="python app.py",
                outcome="failure_fixed",
                error_category="missing_dependency",
                fix_applied="pip install flask",
                confidence=0.8,
                stack="python",
            ),
            ExecutionLesson(
                command="python test.py",
                outcome="success",
                first_attempt_success=True,
                confidence=0.9,
                stack="python",
            ),
        ]
        mem = _mock_memory(lessons=lessons)
        learner = ProactiveLearner(execution_memory=mem)
        ctx = learner.get_task_context("python", "Build Flask API")

        assert "EXECUTION EXPERIENCE" in ctx
        assert "flask" in ctx.lower()
        assert "succeeded" in ctx.lower()

    def test_task_context_empty_when_no_lessons(self):
        """PL-09: Empty string when no lessons exist."""
        mem = _mock_memory(lessons=[])
        learner = ProactiveLearner(execution_memory=mem)
        ctx = learner.get_task_context("python", "Build something")
        assert ctx == ""


class TestProactiveFixDict:
    """PL-10: ProactiveFix.to_dict serialization."""

    def test_to_dict(self):
        fix = ProactiveFix(
            fix_type="install_dependency",
            command="pip install flask",
            description="Pre-install flask",
            confidence=0.85,
            source_lesson_id="L-001",
            times_proven=3,
        )
        d = fix.to_dict()
        assert d["fix_type"] == "install_dependency"
        assert d["command"] == "pip install flask"
        assert d["confidence"] == 0.85
        assert d["times_proven"] == 3


class TestPackageExtraction:
    """PL-11 to PL-12: Package name extraction from install commands."""

    def test_extract_pip_packages(self):
        """PL-11: pip install command parsing."""
        pkgs = _extract_package_names("pip install flask requests gunicorn")
        assert pkgs == ["flask", "requests", "gunicorn"]

    def test_extract_npm_packages(self):
        """PL-12: npm install command parsing."""
        pkgs = _extract_package_names("npm install express cors")
        assert pkgs == ["express", "cors"]


class TestBuildInstallCommand:
    """PL-13: Build install command per stack."""

    def test_build_install_python(self):
        assert _build_install_command("python", "flask") == "pip install flask"

    def test_build_install_node(self):
        assert _build_install_command("node", "express") == "npm install express"

    def test_build_install_unknown(self):
        assert _build_install_command("unknown_stack", "pkg") == ""


class TestTaskExecutorIntegration:
    """PL-14: ARATaskExecutor auto-creates ProactiveLearner."""

    def test_executor_creates_proactive_learner(self):
        from orion.ara.task_executor import ARATaskExecutor

        mock_memory = MagicMock(spec=ExecutionMemory)
        executor = ARATaskExecutor(execution_memory=mock_memory)
        assert executor._proactive_learner is not None

    def test_executor_no_learner_without_memory(self):
        from orion.ara.task_executor import ARATaskExecutor

        executor = ARATaskExecutor(execution_memory=None)
        assert executor._proactive_learner is None
