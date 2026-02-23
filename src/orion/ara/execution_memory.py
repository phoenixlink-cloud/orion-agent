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
"""Execution Memory — lesson capture and retrieval for the execution pipeline.

After every execution (success or failure), this module extracts a structured
lesson and stores it in the 3-tier memory system.  Before every execution, the
proactive learner (Phase 4D.2) queries this module for relevant past lessons.

Design philosophy: Orion is an employee.  The execution memory is how the
employee remembers what they learned on the job.  "Last time I tried to run a
Flask app, I had to install flask first."

This module bridges the execution pipeline (Phase 4A) with the memory system
(src/orion/core/memory/) without creating a parallel store.  It uses
``MemoryEngine.remember()`` / ``MemoryEngine.recall()`` for Tier 2/3 storage
and falls back to a local JSON file when no MemoryEngine is available.

See Phase 4D.1 specification.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orion.ara.execution_feedback import FeedbackResult
    from orion.core.memory.engine import MemoryEngine

logger = logging.getLogger("orion.ara.execution_memory")

# ---------------------------------------------------------------------------
# ExecutionLesson dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExecutionLesson:
    """A lesson learned from a single execution attempt."""

    lesson_id: str = ""
    timestamp: str = ""
    session_id: str = ""
    task_description: str = ""
    stack: str = ""  # python, node, go, rust, base
    command: str = ""
    outcome: str = ""  # 'success', 'failure_fixed', 'failure_permanent'
    error_category: str | None = None
    error_message: str | None = None
    fix_applied: str | None = None
    retries: int = 0
    duration_seconds: float = 0.0
    first_attempt_success: bool = False
    confidence: float = 0.5
    tags: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionLesson:
        """Deserialize from dict."""
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)

    # ------------------------------------------------------------------
    # Memory integration
    # ------------------------------------------------------------------

    def to_memory_pattern(self) -> dict[str, Any]:
        """Convert to the format expected by the memory system's pattern store."""
        content = self._generate_lesson_text()
        return {
            "id": self.lesson_id,
            "content": content,
            "category": "execution-lesson",
            "subcategory": self.error_category or "success",
            "confidence": self.confidence,
            "tags": self.tags,
            "metadata": {
                "stack": self.stack,
                "command": self.command,
                "outcome": self.outcome,
                "fix_applied": self.fix_applied,
                "retries": self.retries,
                "first_attempt_success": self.first_attempt_success,
                "error_category": self.error_category,
                "session_id": self.session_id,
                "task_description": self.task_description[:300],
            },
        }

    def _generate_lesson_text(self) -> str:
        """Generate human-readable lesson text for memory storage."""
        if self.outcome == "success" and self.first_attempt_success:
            return (
                f"Command '{self.command}' succeeded on first attempt "
                f"for {self.stack} stack."
            )
        elif self.outcome == "failure_fixed":
            err = (self.error_message or "")[:200]
            return (
                f"Command '{self.command}' failed with {self.error_category}: "
                f"'{err}'. Fixed by: {self.fix_applied}. "
                f"Took {self.retries} retries."
            )
        elif self.outcome == "failure_permanent":
            err = (self.error_message or "")[:200]
            return (
                f"Command '{self.command}' failed permanently with "
                f"{self.error_category}: '{err}'. "
                f"No fix found after {self.retries} attempts."
            )
        return f"Execution of '{self.command}': {self.outcome}"


# ---------------------------------------------------------------------------
# ExecutionMemory
# ---------------------------------------------------------------------------


class ExecutionMemory:
    """Bridges the execution pipeline with the 3-tier memory system.

    Usage::

        em = ExecutionMemory(memory_engine=engine, project_id="my-project")

        # After execution
        lesson = em.capture_lesson(feedback_result, "Build Flask API", "python", "sess-1")

        # Before next execution (used by ProactiveLearner)
        lessons = em.query_lessons(stack="python", error_category="missing_dependency")
        dep_map = em.get_dependency_map("python")
        fixes = em.get_known_fixes("missing_dependency", "python")
    """

    def __init__(
        self,
        memory_engine: MemoryEngine | None = None,
        project_id: str | None = None,
    ) -> None:
        self._memory_engine = memory_engine
        self._project_id = project_id
        self._lessons: list[ExecutionLesson] = []
        self._fallback_path = Path.home() / ".orion" / "execution_lessons.json"

    # ------------------------------------------------------------------
    # Core: Capture
    # ------------------------------------------------------------------

    def capture_lesson(
        self,
        feedback_result: FeedbackResult,
        task_description: str,
        stack: str,
        session_id: str,
    ) -> ExecutionLesson:
        """Extract a lesson from a FeedbackResult and store it.

        Called AFTER every execution, whether it succeeded or failed.
        """
        # Determine the fix that was applied (if any)
        fix_applied = self._extract_fix(feedback_result)

        # Determine last error message
        last_error = feedback_result.final_stderr or ""
        if not last_error and feedback_result.fixes_applied:
            last_error = feedback_result.fixes_applied[-1].description

        lesson = ExecutionLesson(
            lesson_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            task_description=task_description,
            stack=stack,
            command=feedback_result.original_command,
            outcome=self._determine_outcome(feedback_result),
            error_category=(
                feedback_result.error_category.value
                if feedback_result.error_category
                else None
            ),
            error_message=last_error[:500] if last_error else None,
            fix_applied=fix_applied,
            retries=feedback_result.attempts - 1,
            duration_seconds=feedback_result.total_duration_seconds,
            first_attempt_success=(
                feedback_result.success and feedback_result.attempts == 1
            ),
            confidence=self._calculate_confidence(feedback_result),
            tags=self._extract_tags(feedback_result, stack),
        )

        self._lessons.append(lesson)
        self._store_in_memory(lesson)
        return lesson

    # ------------------------------------------------------------------
    # Core: Query
    # ------------------------------------------------------------------

    def query_lessons(
        self,
        stack: str | None = None,
        error_category: str | None = None,
        command_pattern: str | None = None,
        limit: int = 20,
    ) -> list[ExecutionLesson]:
        """Query stored execution lessons.

        Searches both in-memory lessons and the memory engine.
        Used by ProactiveLearner (4D.2) to find relevant past experience.
        """
        results = list(self._lessons)

        # Also query memory engine for persisted lessons
        if self._memory_engine:
            query = " ".join(
                filter(None, [stack, error_category, command_pattern])
            )
            if query:
                memories = self._memory_engine.recall(
                    query,
                    max_results=limit * 2,
                    min_confidence=0.3,
                    categories=["execution-lesson"],
                )
                for mem in memories:
                    meta = mem.metadata or {}
                    if meta.get("stack") or meta.get("command"):
                        lesson = ExecutionLesson(
                            lesson_id=mem.id,
                            timestamp=mem.created_at,
                            stack=meta.get("stack", ""),
                            command=meta.get("command", ""),
                            outcome=meta.get("outcome", ""),
                            error_category=meta.get("error_category"),
                            fix_applied=meta.get("fix_applied"),
                            retries=meta.get("retries", 0),
                            first_attempt_success=meta.get(
                                "first_attempt_success", False
                            ),
                            confidence=mem.confidence,
                            tags=list(meta.get("tags", [])),
                            task_description=meta.get("task_description", ""),
                            session_id=meta.get("session_id", ""),
                        )
                        # Avoid duplicates (same lesson_id)
                        if not any(
                            l.lesson_id == lesson.lesson_id for l in results
                        ):
                            results.append(lesson)

        # Apply filters
        if stack:
            results = [l for l in results if l.stack == stack]
        if error_category:
            results = [l for l in results if l.error_category == error_category]
        if command_pattern:
            pattern_lower = command_pattern.lower()
            results = [
                l for l in results if pattern_lower in l.command.lower()
            ]

        return results[-limit:]

    def get_dependency_map(self, stack: str) -> dict[str, list[str]]:
        """Build a dependency map from past lessons.

        Returns:
            {"flask": ["flask"], "express": ["express"]}

        When Orion sees a task mentioning "flask", it knows to install it.
        Built from past execution lessons where missing dependencies were fixed.
        """
        dep_map: dict[str, list[str]] = {}

        for lesson in self._lessons:
            if lesson.stack != stack:
                continue
            if lesson.outcome != "failure_fixed":
                continue
            if lesson.error_category != "missing_dependency":
                continue
            if not lesson.fix_applied:
                continue

            # Extract package names from install commands
            packages = self._extract_packages_from_command(lesson.fix_applied)
            for pkg in packages:
                if pkg not in dep_map:
                    dep_map[pkg] = []
                if pkg not in dep_map[pkg]:
                    dep_map[pkg].append(pkg)

            # Map task keywords to dependencies
            task_lower = lesson.task_description.lower()
            for pkg in packages:
                # Look for framework/library names in the task description
                for word in task_lower.split():
                    word = word.strip(".,;:!?()[]{}\"'")
                    if len(word) >= 3 and word.isalpha():
                        if word not in dep_map:
                            dep_map[word] = []
                        if pkg not in dep_map[word]:
                            dep_map[word].append(pkg)

        return dep_map

    def get_known_fixes(
        self, error_category: str, stack: str
    ) -> list[dict[str, Any]]:
        """Get fixes that have worked for this error_category + stack combo.

        Returns:
            [{"fix": "pip install flask", "confidence": 0.95,
              "times_applied": 12, "lesson_id": "..."}]
        """
        fix_counts: dict[str, dict[str, Any]] = {}

        for lesson in self._lessons:
            if lesson.stack != stack:
                continue
            if lesson.error_category != error_category:
                continue
            if not lesson.fix_applied:
                continue
            if lesson.outcome != "failure_fixed":
                continue

            fix = lesson.fix_applied
            if fix not in fix_counts:
                fix_counts[fix] = {
                    "fix": fix,
                    "confidence": lesson.confidence,
                    "times_applied": 0,
                    "lesson_id": lesson.lesson_id,
                }
            fix_counts[fix]["times_applied"] += 1
            # Update confidence to the max seen
            fix_counts[fix]["confidence"] = max(
                fix_counts[fix]["confidence"], lesson.confidence
            )

        # Sort by times_applied * confidence (most reliable first)
        results = list(fix_counts.values())
        results.sort(
            key=lambda x: x["times_applied"] * x["confidence"], reverse=True
        )
        return results

    # ------------------------------------------------------------------
    # Memory storage
    # ------------------------------------------------------------------

    def _store_in_memory(self, lesson: ExecutionLesson) -> None:
        """Store lesson in the 3-tier memory system."""
        pattern = lesson.to_memory_pattern()

        if self._memory_engine:
            # Store in Tier 2 (Project Memory) first
            self._memory_engine.remember(
                content=pattern["content"],
                tier=2,
                category="execution-lesson",
                confidence=lesson.confidence,
                source="execution_memory",
                metadata=pattern["metadata"],
            )

            # If high confidence and recurring, promote to Tier 3
            if lesson.confidence >= 0.85:
                similar = self._find_similar_lessons(lesson)
                if len(similar) >= 3:
                    self._memory_engine.remember(
                        content=pattern["content"],
                        tier=3,
                        category="execution-lesson",
                        confidence=lesson.confidence,
                        source="execution_memory_promoted",
                        metadata=pattern["metadata"],
                    )
                    logger.info(
                        "Lesson promoted to Tier 3: %s (confidence=%.2f, "
                        "similar=%d)",
                        lesson.lesson_id,
                        lesson.confidence,
                        len(similar),
                    )
        else:
            # Fallback: store to local JSON file
            self._store_fallback(lesson)

    def _store_fallback(self, lesson: ExecutionLesson) -> None:
        """Store to local JSON when memory engine is unavailable."""
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        lessons: list[dict] = []
        if self._fallback_path.exists():
            try:
                lessons = json.loads(
                    self._fallback_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                lessons = []
        lessons.append(lesson.to_memory_pattern())
        # Ring buffer: keep last 1000
        if len(lessons) > 1000:
            lessons = lessons[-1000:]
        self._fallback_path.write_text(
            json.dumps(lessons, indent=2, default=str), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_outcome(feedback_result: FeedbackResult) -> str:
        """Determine the outcome category from a FeedbackResult."""
        if feedback_result.success and feedback_result.attempts == 1:
            return "success"
        elif feedback_result.success:
            return "failure_fixed"
        else:
            return "failure_permanent"

    @staticmethod
    def _calculate_confidence(feedback_result: FeedbackResult) -> float:
        """Calculate confidence score for the lesson.

        Higher confidence for:
        - First-attempt successes (0.9)
        - Failures that were fixed (0.8 - decreasing with retries)
        - Permanent failures get lower confidence (0.5)
        """
        if feedback_result.success and feedback_result.attempts == 1:
            return 0.9
        elif feedback_result.success:
            return max(0.6, 0.85 - (feedback_result.attempts - 1) * 0.05)
        else:
            return 0.5

    @staticmethod
    def _extract_tags(feedback_result: FeedbackResult, stack: str) -> list[str]:
        """Extract searchable tags from the execution result."""
        tags = [stack]
        if feedback_result.error_category:
            tags.append(feedback_result.error_category.value)

        # Extract package names from install commands in fixes
        for fix in feedback_result.fixes_applied:
            if fix.install_command:
                pkgs = _extract_packages_from_install(fix.install_command)
                tags.extend(pkgs)

        # Extract from the original command too
        cmd = feedback_result.original_command or ""
        if "pip install" in cmd:
            pkgs = cmd.split("pip install")[-1].strip().split()
            tags.extend(p for p in pkgs if not p.startswith("-"))
        if "npm install" in cmd:
            pkgs = cmd.split("npm install")[-1].strip().split()
            tags.extend(p for p in pkgs if not p.startswith("-"))

        return tags

    @staticmethod
    def _extract_fix(feedback_result: FeedbackResult) -> str | None:
        """Extract the fix that worked from a FeedbackResult."""
        if not feedback_result.success or not feedback_result.fixes_applied:
            return None
        # The last fix applied before success is the one that worked
        last_fix = feedback_result.fixes_applied[-1]
        if last_fix.install_command:
            return last_fix.install_command
        if last_fix.command:
            return last_fix.command
        if last_fix.description:
            return last_fix.description
        return None

    def _find_similar_lessons(self, lesson: ExecutionLesson) -> list[ExecutionLesson]:
        """Find past lessons with the same error_category + stack + similar command."""
        return [
            l
            for l in self._lessons
            if l.error_category == lesson.error_category
            and l.stack == lesson.stack
            and l.lesson_id != lesson.lesson_id
        ]

    @staticmethod
    def _extract_packages_from_command(cmd: str) -> list[str]:
        """Extract package names from an install command string."""
        return _extract_packages_from_install(cmd)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _extract_packages_from_install(cmd: str) -> list[str]:
    """Extract package names from pip/npm install commands."""
    packages: list[str] = []
    if "pip install" in cmd:
        parts = cmd.split("pip install")[-1].strip().split()
        packages.extend(p for p in parts if not p.startswith("-"))
    elif "npm install" in cmd:
        parts = cmd.split("npm install")[-1].strip().split()
        packages.extend(p for p in parts if not p.startswith("-"))
    elif "go get" in cmd:
        parts = cmd.split("go get")[-1].strip().split()
        packages.extend(p for p in parts if not p.startswith("-"))
    elif "cargo add" in cmd:
        parts = cmd.split("cargo add")[-1].strip().split()
        packages.extend(p for p in parts if not p.startswith("-"))
    return packages
