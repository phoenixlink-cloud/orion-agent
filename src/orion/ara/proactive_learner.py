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
"""Proactive Learner — apply past execution lessons BEFORE running commands.

Before Orion executes a task, this module:
1. Queries ``ExecutionMemory`` for relevant past lessons
2. Identifies likely errors based on stack, command, and task description
3. Returns a list of ``ProactiveFix`` objects — pre-emptive actions that
   should be applied BEFORE the main command runs

Example: if Orion has learned that Flask apps need ``pip install flask``,
the proactive learner will suggest that install BEFORE running the app —
preventing the ``ModuleNotFoundError`` entirely.

See Phase 4D.2 specification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orion.ara.execution_memory import ExecutionMemory

logger = logging.getLogger("orion.ara.proactive_learner")

# ---------------------------------------------------------------------------
# ProactiveFix dataclass
# ---------------------------------------------------------------------------


@dataclass
class ProactiveFix:
    """A pre-emptive fix suggested by past experience."""

    fix_type: str  # 'install_dependency', 'create_file', 'run_command'
    command: str = ""
    description: str = ""
    confidence: float = 0.5
    source_lesson_id: str = ""
    times_proven: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fix_type": self.fix_type,
            "command": self.command,
            "description": self.description,
            "confidence": self.confidence,
            "source_lesson_id": self.source_lesson_id,
            "times_proven": self.times_proven,
        }


# ---------------------------------------------------------------------------
# ProactiveLearner
# ---------------------------------------------------------------------------


class ProactiveLearner:
    """Queries execution memory to suggest pre-emptive fixes.

    Usage::

        learner = ProactiveLearner(execution_memory=em)
        fixes = learner.suggest_fixes("python", "Build a Flask REST API", "python app.py")

        for fix in fixes:
            if fix.confidence >= 0.7:
                await container.exec_install(fix.command)
    """

    def __init__(
        self,
        execution_memory: ExecutionMemory | None = None,
        min_confidence: float = 0.7,
    ) -> None:
        self._memory = execution_memory
        self._min_confidence = min_confidence

    def suggest_fixes(
        self,
        stack: str,
        task_description: str,
        command: str = "",
    ) -> list[ProactiveFix]:
        """Suggest pre-emptive fixes based on past execution lessons.

        Args:
            stack: The language/runtime stack (python, node, etc.)
            task_description: What the task is trying to accomplish
            command: The command that will be executed (optional)

        Returns:
            List of ProactiveFix sorted by confidence descending.
        """
        if not self._memory:
            return []

        fixes: list[ProactiveFix] = []

        # Strategy 1: Known dependency fixes for this stack
        fixes.extend(self._suggest_dependency_fixes(stack, task_description))

        # Strategy 2: Known fixes for common error patterns
        fixes.extend(self._suggest_error_prevention(stack, command))

        # Strategy 3: Dependency map lookup
        fixes.extend(self._suggest_from_dependency_map(stack, task_description))

        # Deduplicate by command
        seen_commands: set[str] = set()
        unique: list[ProactiveFix] = []
        for fix in fixes:
            key = fix.command.strip().lower()
            if key and key not in seen_commands:
                seen_commands.add(key)
                unique.append(fix)

        # Filter by confidence threshold and sort
        result = [f for f in unique if f.confidence >= self._min_confidence]
        result.sort(key=lambda f: f.confidence, reverse=True)
        return result

    def get_task_context(
        self,
        stack: str,
        task_description: str,
    ) -> str:
        """Build a context string from past lessons for LLM prompt injection.

        Returns a human-readable summary of relevant past experience that
        can be injected into the system prompt to inform the LLM.
        """
        if not self._memory:
            return ""

        lessons = self._memory.query_lessons(stack=stack, limit=10)
        if not lessons:
            return ""

        # Filter to high-confidence lessons
        relevant = [lsn for lsn in lessons if lsn.confidence >= 0.6]
        if not relevant:
            return ""

        lines = [
            "## EXECUTION EXPERIENCE",
            f"(From {len(relevant)} past executions with {stack} stack)\n",
        ]

        successes = [lsn for lsn in relevant if lsn.outcome == "success"]
        fixed = [lsn for lsn in relevant if lsn.outcome == "failure_fixed"]
        failed = [lsn for lsn in relevant if lsn.outcome == "failure_permanent"]

        if fixed:
            lines.append("**Common issues and fixes:**")
            for lsn in fixed[:5]:
                lines.append(
                    f"- '{lsn.command}' failed with {lsn.error_category}, "
                    f"fixed by: {lsn.fix_applied}"
                )

        if failed:
            lines.append("\n**Known problematic patterns:**")
            for lsn in failed[:3]:
                lines.append(
                    f"- '{lsn.command}' fails permanently with "
                    f"{lsn.error_category}: avoid this approach"
                )

        if successes:
            lines.append(f"\n**{len(successes)} commands succeeded on first attempt.**")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private strategies
    # ------------------------------------------------------------------

    def _suggest_dependency_fixes(self, stack: str, task_description: str) -> list[ProactiveFix]:
        """Strategy 1: Query known fixes for missing_dependency errors."""
        fixes: list[ProactiveFix] = []
        known = self._memory.get_known_fixes("missing_dependency", stack)

        task_lower = task_description.lower()
        for entry in known:
            fix_cmd = entry["fix"]
            # Check if the fix is relevant to the current task
            packages = _extract_package_names(fix_cmd)
            for pkg in packages:
                if pkg.lower() in task_lower:
                    fixes.append(
                        ProactiveFix(
                            fix_type="install_dependency",
                            command=fix_cmd,
                            description=(
                                f"Pre-install {pkg} (learned from "
                                f"{entry['times_applied']} past executions)"
                            ),
                            confidence=entry["confidence"],
                            source_lesson_id=entry["lesson_id"],
                            times_proven=entry["times_applied"],
                        )
                    )
                    break  # One fix per entry

        return fixes

    def _suggest_error_prevention(self, stack: str, command: str) -> list[ProactiveFix]:
        """Strategy 2: Match command patterns to past failures."""
        if not command:
            return []

        fixes: list[ProactiveFix] = []
        # Look for lessons with matching commands
        lessons = self._memory.query_lessons(
            stack=stack, command_pattern=command.split()[0] if command else ""
        )

        for lesson in lessons:
            if lesson.outcome == "failure_fixed" and lesson.fix_applied:
                fixes.append(
                    ProactiveFix(
                        fix_type="run_command",
                        command=lesson.fix_applied,
                        description=(f"Pre-apply fix for '{lesson.command}': {lesson.fix_applied}"),
                        confidence=lesson.confidence * 0.9,  # Slightly lower
                        source_lesson_id=lesson.lesson_id,
                    )
                )

        return fixes

    def _suggest_from_dependency_map(self, stack: str, task_description: str) -> list[ProactiveFix]:
        """Strategy 3: Use the dependency map to find required packages."""
        fixes: list[ProactiveFix] = []
        dep_map = self._memory.get_dependency_map(stack)

        task_lower = task_description.lower()
        for keyword, packages in dep_map.items():
            if keyword in task_lower:
                for pkg in packages:
                    install_cmd = _build_install_command(stack, pkg)
                    if install_cmd:
                        fixes.append(
                            ProactiveFix(
                                fix_type="install_dependency",
                                command=install_cmd,
                                description=(
                                    f"Install {pkg} (dependency map: '{keyword}' → {pkg})"
                                ),
                                confidence=0.75,
                            )
                        )

        return fixes


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _extract_package_names(install_cmd: str) -> list[str]:
    """Extract package names from an install command."""
    packages: list[str] = []
    for prefix in ("pip install", "npm install", "go get", "cargo add"):
        if prefix in install_cmd:
            parts = install_cmd.split(prefix)[-1].strip().split()
            packages.extend(p for p in parts if not p.startswith("-"))
            break
    return packages


def _build_install_command(stack: str, package: str) -> str:
    """Build an install command for the given stack and package."""
    installers = {
        "python": f"pip install {package}",
        "node": f"npm install {package}",
        "go": f"go get {package}",
        "rust": f"cargo add {package}",
    }
    return installers.get(stack, "")
