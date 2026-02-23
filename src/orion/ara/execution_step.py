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
"""ExecutionStep — multi-command workflow support for Phase 4B.

A single Task can now contain multiple ExecutionSteps, allowing
ordered sequences like:

  1. install_deps: pip install flask
  2. run_command: python app.py
  3. run_tests_sandbox: pytest tests/

The WorkflowRunner executes steps sequentially, stopping on the
first failure (fail-fast) unless ``continue_on_error`` is set.

See Phase 4B.1 specification.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("orion.ara.execution_step")


# ---------------------------------------------------------------------------
# Step status
# ---------------------------------------------------------------------------


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# ExecutionStep dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExecutionStep:
    """A single step in a multi-command workflow.

    Attributes:
        step_id: Unique identifier within the workflow (e.g. "step-1").
        action: Action type — one of ``install_deps``, ``run_command``,
                ``run_tests_sandbox``, ``write_file``.
        command: Shell command to execute (for run_command, install_deps, run_tests_sandbox).
        description: Human-readable description of what this step does.
        timeout: Timeout in seconds for this step.
        continue_on_error: If True, workflow continues even if this step fails.
        status: Current execution status.
        output: Captured stdout after execution.
        error: Captured stderr after execution.
        exit_code: Process exit code (-1 if not yet run).
        duration_seconds: How long the step took.
    """

    step_id: str = ""
    action: str = "run_command"
    command: str = ""
    description: str = ""
    timeout: int = 120
    continue_on_error: bool = False
    status: StepStatus = StepStatus.PENDING
    output: str = ""
    error: str = ""
    exit_code: int = -1
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "command": self.command,
            "description": self.description,
            "timeout": self.timeout,
            "continue_on_error": self.continue_on_error,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionStep:
        return cls(
            step_id=data.get("step_id", ""),
            action=data.get("action", "run_command"),
            command=data.get("command", ""),
            description=data.get("description", ""),
            timeout=int(data.get("timeout", 120)),
            continue_on_error=bool(data.get("continue_on_error", False)),
            status=StepStatus(data.get("status", "pending")),
            output=data.get("output", ""),
            error=data.get("error", ""),
            exit_code=int(data.get("exit_code", -1)),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
        )


# ---------------------------------------------------------------------------
# WorkflowResult
# ---------------------------------------------------------------------------


@dataclass
class WorkflowResult:
    """Result of executing a multi-step workflow."""

    success: bool = False
    steps: list[ExecutionStep] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    completed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0

    @property
    def confidence(self) -> float:
        """Compute overall confidence from step outcomes."""
        if not self.steps:
            return 0.0
        if self.failed_count > 0:
            return 0.3
        return 0.9

    def summary(self) -> str:
        """One-line summary of the workflow result."""
        total = len(self.steps)
        return (
            f"{self.completed_count}/{total} steps completed, "
            f"{self.failed_count} failed, "
            f"{self.skipped_count} skipped "
            f"({self.total_duration_seconds:.1f}s)"
        )


# ---------------------------------------------------------------------------
# Helpers: extract steps from task metadata
# ---------------------------------------------------------------------------


def extract_steps(metadata: dict[str, Any]) -> list[ExecutionStep]:
    """Extract ExecutionSteps from task metadata.

    Looks for ``metadata["execution_steps"]`` — a list of step dicts.
    Falls back to creating a single step from ``metadata["command"]``.

    Args:
        metadata: Task metadata dict.

    Returns:
        List of ExecutionStep objects (may be empty).
    """
    raw_steps = metadata.get("execution_steps", [])
    if raw_steps and isinstance(raw_steps, list):
        steps = []
        for i, raw in enumerate(raw_steps):
            if isinstance(raw, dict):
                step = ExecutionStep.from_dict(raw)
                if not step.step_id:
                    step.step_id = f"step-{i + 1}"
                steps.append(step)
        return steps

    # Fallback: single step from metadata
    command = (
        metadata.get("command") or metadata.get("install_command") or metadata.get("test_command")
    )
    if command:
        action = "run_command"
        if metadata.get("install_command"):
            action = "install_deps"
        elif metadata.get("test_command"):
            action = "run_tests_sandbox"
        return [
            ExecutionStep(
                step_id="step-1",
                action=action,
                command=command,
                description=metadata.get("description", ""),
                timeout=int(metadata.get("timeout", 120)),
            )
        ]

    return []


# ---------------------------------------------------------------------------
# WorkflowRunner
# ---------------------------------------------------------------------------


class WorkflowRunner:
    """Executes a sequence of ExecutionSteps using a session container.

    Supports optional ExecutionFeedbackLoop for error correction on
    ``run_command`` and ``run_tests_sandbox`` steps.

    Usage::

        runner = WorkflowRunner(container=container, feedback=feedback)
        result = await runner.run(steps)
    """

    def __init__(
        self,
        container: Any,
        feedback: Any | None = None,
    ) -> None:
        self._container = container
        self._feedback = feedback

    async def run(self, steps: list[ExecutionStep]) -> WorkflowResult:
        """Execute steps sequentially, returning aggregate result.

        Stops on first failure unless ``step.continue_on_error`` is True.
        """
        result = WorkflowResult(steps=steps)
        start = time.time()

        for step in steps:
            step.status = StepStatus.RUNNING
            step_start = time.time()

            try:
                await self._execute_step(step)
            except Exception as exc:
                step.status = StepStatus.FAILED
                step.error = str(exc)
                step.exit_code = -1
                logger.error("Step %s raised exception: %s", step.step_id, exc)

            step.duration_seconds = time.time() - step_start

            if step.status == StepStatus.COMPLETED:
                result.completed_count += 1
            elif step.status == StepStatus.FAILED:
                result.failed_count += 1
                if not step.continue_on_error:
                    # Skip remaining steps
                    for remaining in steps[steps.index(step) + 1 :]:
                        remaining.status = StepStatus.SKIPPED
                        result.skipped_count += 1
                    break

        result.total_duration_seconds = time.time() - start
        result.success = result.failed_count == 0
        return result

    async def _execute_step(self, step: ExecutionStep) -> None:
        """Execute a single step, updating its fields in-place."""
        if step.action == "install_deps":
            exec_result = await self._container.exec_install(step.command, timeout=step.timeout)
        elif step.action in ("run_command", "run_tests_sandbox"):
            if self._feedback:
                fb_result = await self._feedback.run_with_feedback(
                    step.command, timeout=step.timeout
                )
                step.output = fb_result.final_stdout[:2000]
                step.error = fb_result.final_stderr[:1000]
                step.exit_code = fb_result.final_exit_code
                step.status = StepStatus.COMPLETED if fb_result.success else StepStatus.FAILED
                return
            else:
                exec_result = await self._container.exec(step.command, timeout=step.timeout)
        else:
            # Unknown action — skip
            logger.warning("Unknown step action '%s', skipping", step.action)
            step.status = StepStatus.SKIPPED
            return

        step.output = exec_result.stdout[:2000]
        step.error = exec_result.stderr[:1000]
        step.exit_code = exec_result.exit_code
        step.status = StepStatus.COMPLETED if exec_result.exit_code == 0 else StepStatus.FAILED
