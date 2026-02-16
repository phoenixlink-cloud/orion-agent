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
"""ARA Execution Loop — runs tasks from the goal DAG sequentially.

Picks the next ready task, executes it, checks confidence, and decides
whether to continue, checkpoint, re-plan, or stop. Enforces all 5 stop
conditions from ARA-001 §6.

See ARA-001 §9 for full design.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from orion.ara.goal_engine import TaskDAG, TaskStatus
from orion.ara.session import SessionState, SessionStatus

logger = logging.getLogger("orion.ara.execution")

# Stop condition thresholds
CONFIDENCE_COLLAPSE_THRESHOLD = 0.5
CONFIDENCE_COLLAPSE_STREAK = 3
ERROR_THRESHOLD_STREAK = 5


@dataclass
class ExecutionResult:
    """Result of running the execution loop."""

    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0
    stop_reason: str = ""
    total_elapsed_seconds: float = 0.0
    total_cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "tasks_skipped": self.tasks_skipped,
            "stop_reason": self.stop_reason,
            "total_elapsed_seconds": round(self.total_elapsed_seconds, 2),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "errors": self.errors,
        }


class ExecutionLoop:
    """Runs tasks from a TaskDAG, enforcing stop conditions and confidence gating.

    The loop:
    1. Pick next ready task (dependencies met)
    2. Execute via task_executor callback
    3. Update confidence, cost, elapsed time
    4. Check stop conditions
    5. Checkpoint if interval reached
    6. Repeat or stop
    """

    def __init__(
        self,
        session: SessionState,
        dag: TaskDAG,
        task_executor: Callable[..., Any] | None = None,
        task_executor_ref: Any = None,
        on_checkpoint: Callable[[], None] | None = None,
        on_task_complete: Callable[[], None] | None = None,
        on_control_check: Callable[[], None] | None = None,
        checkpoint_interval_minutes: float = 15.0,
    ):
        self._session = session
        self._dag = dag
        self._executor = task_executor or self._default_executor
        self._task_executor_ref = task_executor_ref
        self._on_checkpoint = on_checkpoint
        self._on_task_complete = on_task_complete
        self._on_control_check = on_control_check
        self._checkpoint_interval = checkpoint_interval_minutes * 60
        self._low_confidence_streak = 0
        self._error_streak = 0
        self._last_checkpoint_time = time.time()
        self._stopped = False

    @property
    def session(self) -> SessionState:
        return self._session

    @property
    def dag(self) -> TaskDAG:
        return self._dag

    def stop(self) -> None:
        """Signal the loop to stop after the current task."""
        self._stopped = True

    def _learn_from_outcome(self, task: Any, success: bool) -> None:
        """Feed task outcome to institutional memory (teach-student WRITE path)."""
        ref = self._task_executor_ref
        if ref and hasattr(ref, 'learn_from_task_outcome'):
            ref.learn_from_task_outcome(
                task_id=task.task_id,
                action_type=getattr(task, 'action_type', 'unknown'),
                title=getattr(task, 'title', ''),
                success=success,
                output=getattr(task, 'output', '') or getattr(task, 'error', ''),
                confidence=getattr(task, 'confidence', 0.5),
            )

    async def run(self) -> ExecutionResult:
        """Execute the full loop until completion or stop condition."""
        result = ExecutionResult()
        start_time = time.time()

        # Ensure session is running
        if self._session.status == SessionStatus.CREATED:
            self._session.transition(SessionStatus.RUNNING)

        while not self._stopped:
            # Heartbeat
            self._session.heartbeat()

            # Check session-level stop conditions
            stop_reason = self._session.check_stop_conditions()
            if stop_reason:
                result.stop_reason = stop_reason
                break

            # Check confidence collapse
            if self._low_confidence_streak >= CONFIDENCE_COLLAPSE_STREAK:
                result.stop_reason = (
                    f"confidence_collapse: {self._low_confidence_streak} consecutive "
                    f"tasks below {CONFIDENCE_COLLAPSE_THRESHOLD}"
                )
                break

            # Check error streak
            if self._error_streak >= ERROR_THRESHOLD_STREAK:
                result.stop_reason = (
                    f"error_threshold: {self._error_streak} consecutive failures"
                )
                break

            # Get next ready task
            ready_tasks = self._dag.get_ready_tasks()
            if not ready_tasks:
                if self._dag.pending_tasks > 0:
                    result.stop_reason = "deadlock: pending tasks with unmet dependencies"
                else:
                    result.stop_reason = "goal_complete: all tasks finished"
                break

            task = ready_tasks[0]
            task.status = TaskStatus.RUNNING
            task_start = time.time()

            try:
                # Execute the task
                task_result = await self._executor(task)
                task.actual_minutes = (time.time() - task_start) / 60

                if task_result.get("success", False):
                    task.status = TaskStatus.COMPLETED
                    task.output = task_result.get("output", "")
                    task.confidence = task_result.get("confidence", 1.0)
                    result.tasks_completed += 1
                    self._error_streak = 0

                    # Feed completed task context to executor for next tasks
                    if hasattr(self._executor, '__self__') and hasattr(self._executor.__self__, 'add_task_context'):
                        self._executor.__self__.add_task_context(
                            task.task_id, task.title, task.output,
                        )
                    elif hasattr(self, '_task_executor_ref') and hasattr(self._task_executor_ref, 'add_task_context'):
                        self._task_executor_ref.add_task_context(
                            task.task_id, task.title, task.output,
                        )

                    # Teach-student WRITE path: feed success to institutional memory
                    self._learn_from_outcome(task, success=True)

                    if task.confidence < CONFIDENCE_COLLAPSE_THRESHOLD:
                        self._low_confidence_streak += 1
                    else:
                        self._low_confidence_streak = 0
                else:
                    task.status = TaskStatus.FAILED
                    task.error = task_result.get("error", "Unknown error")
                    result.tasks_failed += 1
                    self._error_streak += 1
                    self._low_confidence_streak = 0
                    result.errors.append(f"{task.task_id}: {task.error}")

                    # Teach-student WRITE path: feed failure to institutional memory
                    self._learn_from_outcome(task, success=False)

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.actual_minutes = (time.time() - task_start) / 60
                result.tasks_failed += 1
                self._error_streak += 1
                result.errors.append(f"{task.task_id}: {e}")

            # Update session cost
            task_cost = task_result.get("cost", 0.0) if "task_result" in dir() else 0.0
            self._session.add_cost(task_cost)
            result.total_cost_usd += task_cost

            # Update session progress
            self._session.progress.total_tasks = self._dag.total_tasks
            self._session.progress.completed_tasks = self._dag.completed_tasks
            self._session.progress.failed_tasks = self._dag.failed_tasks

            # Notify daemon of task completion (status update + save)
            if self._on_task_complete:
                self._on_task_complete()

            # Process control commands (pause/cancel/resume)
            if self._on_control_check:
                self._on_control_check()

            # Checkpoint if interval reached
            now = time.time()
            if (now - self._last_checkpoint_time) >= self._checkpoint_interval:
                if self._on_checkpoint:
                    self._on_checkpoint()
                    self._session.checkpoint_count += 1
                    self._session.last_checkpoint_at = now
                self._last_checkpoint_time = now

        result.total_elapsed_seconds = time.time() - start_time

        # Update session status based on outcome
        if not self._session.is_terminal:
            if result.stop_reason.startswith("goal_complete"):
                self._session.transition(SessionStatus.COMPLETED)
            elif result.stop_reason.startswith(("error_threshold", "confidence_collapse")):
                self._session.error_message = result.stop_reason
                self._session.transition(SessionStatus.FAILED)
            elif self._stopped:
                self._session.transition(SessionStatus.PAUSED)

        logger.info(
            "Execution loop ended: %s (completed=%d, failed=%d)",
            result.stop_reason,
            result.tasks_completed,
            result.tasks_failed,
        )
        return result

    @staticmethod
    async def _default_executor(task: Any) -> dict[str, Any]:
        """Default no-op executor for testing."""
        return {"success": True, "output": f"Executed: {task.title}", "confidence": 0.9}
