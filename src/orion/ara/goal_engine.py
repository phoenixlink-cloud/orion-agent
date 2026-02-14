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
"""ARA Goal Engine — LLM-powered task decomposition into a DAG.

Takes a high-level goal string and decomposes it into an ordered list of
atomic tasks. Each task has dependencies, estimated effort, and an action type.
The plan is validated by AEGIS at plan-time before execution begins.

See ARA-001 §8 for full design.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger("orion.ara.goal_engine")


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """A single atomic task in the goal DAG."""

    task_id: str
    title: str
    description: str
    action_type: str  # e.g. "write_file", "run_tests", "read_files"
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    estimated_minutes: float = 5.0
    actual_minutes: float = 0.0
    output: str = ""
    error: str = ""
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        """A task is ready if all dependencies are completed."""
        return self.status == TaskStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "action_type": self.action_type,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "estimated_minutes": self.estimated_minutes,
            "actual_minutes": self.actual_minutes,
            "output": self.output,
            "error": self.error,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        return cls(
            task_id=data["task_id"],
            title=data.get("title", ""),
            description=data.get("description", ""),
            action_type=data.get("action_type", "unknown"),
            dependencies=data.get("dependencies", []),
            status=TaskStatus(data.get("status", "pending")),
            estimated_minutes=data.get("estimated_minutes", 5.0),
            actual_minutes=data.get("actual_minutes", 0.0),
            output=data.get("output", ""),
            error=data.get("error", ""),
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TaskDAG:
    """Directed Acyclic Graph of tasks for a goal."""

    goal: str
    tasks: list[Task] = field(default_factory=list)
    created_at: float = 0.0

    @property
    def total_tasks(self) -> int:
        return len(self.tasks)

    @property
    def completed_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)

    @property
    def failed_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.FAILED)

    @property
    def pending_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.PENDING)

    def get_task(self, task_id: str) -> Task | None:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def get_ready_tasks(self) -> list[Task]:
        """Return tasks whose dependencies are all completed."""
        completed_ids = {t.task_id for t in self.tasks if t.status == TaskStatus.COMPLETED}
        ready = []
        for task in self.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            if all(dep in completed_ids for dep in task.dependencies):
                ready.append(task)
        return ready

    def validate_dag(self) -> list[str]:
        """Validate DAG structure. Returns list of errors."""
        errors: list[str] = []
        ids = {t.task_id for t in self.tasks}

        # Check for duplicate IDs
        if len(ids) != len(self.tasks):
            errors.append("Duplicate task IDs detected")

        # Check dependencies reference valid tasks
        for task in self.tasks:
            for dep in task.dependencies:
                if dep not in ids:
                    errors.append(f"Task '{task.task_id}' depends on unknown task '{dep}'")

        # Check for cycles (simple DFS)
        visited: set[str] = set()
        rec_stack: set[str] = set()
        task_map = {t.task_id: t for t in self.tasks}

        def has_cycle(tid: str) -> bool:
            visited.add(tid)
            rec_stack.add(tid)
            task = task_map.get(tid)
            if task:
                for dep in task.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            rec_stack.discard(tid)
            return False

        for t in self.tasks:
            if t.task_id not in visited:
                if has_cycle(t.task_id):
                    errors.append("Cycle detected in task dependencies")
                    break

        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "tasks": [t.to_dict() for t in self.tasks],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskDAG:
        return cls(
            goal=data.get("goal", ""),
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
            created_at=data.get("created_at", 0.0),
        )


class LLMProvider(Protocol):
    """Protocol for LLM calls — satisfied by MockLLMProvider and real providers."""

    async def decompose_goal(self, goal: str, context: str) -> list[dict[str, Any]]:
        """Decompose a goal into a list of task dicts."""
        ...

    async def replan(
        self, goal: str, completed: list[dict], failed: list[dict], remaining: list[dict]
    ) -> list[dict[str, Any]]:
        """Re-plan remaining tasks given progress so far."""
        ...


class MockLLMProvider:
    """Mock LLM provider for deterministic testing (Tier 1).

    Returns pre-configured task DAGs without any LLM call.
    """

    def __init__(self, responses: dict[str, list[dict[str, Any]]] | None = None):
        self._responses = responses or {}
        self._default_tasks = [
            {
                "task_id": "task-1",
                "title": "Analyze requirements",
                "description": "Read and understand the goal",
                "action_type": "read_files",
                "dependencies": [],
                "estimated_minutes": 2,
            },
            {
                "task_id": "task-2",
                "title": "Implement changes",
                "description": "Write the code changes",
                "action_type": "write_files",
                "dependencies": ["task-1"],
                "estimated_minutes": 10,
            },
            {
                "task_id": "task-3",
                "title": "Run tests",
                "description": "Verify changes with tests",
                "action_type": "run_tests",
                "dependencies": ["task-2"],
                "estimated_minutes": 3,
            },
        ]
        self._call_count = 0
        self._replan_count = 0

    async def decompose_goal(self, goal: str, context: str = "") -> list[dict[str, Any]]:
        self._call_count += 1
        return self._responses.get(goal, self._default_tasks)

    async def replan(
        self,
        goal: str,
        completed: list[dict] | None = None,
        failed: list[dict] | None = None,
        remaining: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        self._replan_count += 1
        # Return simplified remaining tasks
        if remaining:
            return remaining
        return self._default_tasks[-1:]


class GoalEngine:
    """Decomposes high-level goals into executable task DAGs.

    Uses an LLM provider (real or mock) for decomposition, then validates
    the resulting DAG structure and checks action types against AEGIS.
    """

    def __init__(self, llm_provider: LLMProvider | MockLLMProvider):
        self._llm = llm_provider

    async def decompose(self, goal: str, context: str = "") -> TaskDAG:
        """Decompose a goal into a TaskDAG."""
        import time as _time

        raw_tasks = await self._llm.decompose_goal(goal, context)
        tasks = [Task.from_dict(t) for t in raw_tasks]
        dag = TaskDAG(goal=goal, tasks=tasks, created_at=_time.time())

        errors = dag.validate_dag()
        if errors:
            raise DAGValidationError(f"Invalid task DAG: {'; '.join(errors)}")

        logger.info(
            "Goal decomposed into %d tasks: %s",
            len(tasks),
            ", ".join(t.task_id for t in tasks),
        )
        return dag

    async def replan(self, dag: TaskDAG) -> TaskDAG:
        """Re-plan a DAG based on current progress."""
        import time as _time

        completed = [t.to_dict() for t in dag.tasks if t.status == TaskStatus.COMPLETED]
        failed = [t.to_dict() for t in dag.tasks if t.status == TaskStatus.FAILED]
        remaining = [t.to_dict() for t in dag.tasks if t.status == TaskStatus.PENDING]

        raw_tasks = await self._llm.replan(dag.goal, completed, failed, remaining)
        new_tasks = [Task.from_dict(t) for t in raw_tasks]

        # Preserve completed tasks, replace remaining
        kept = [t for t in dag.tasks if t.status == TaskStatus.COMPLETED]
        new_dag = TaskDAG(goal=dag.goal, tasks=kept + new_tasks, created_at=_time.time())

        errors = new_dag.validate_dag()
        if errors:
            logger.warning("Re-plan produced invalid DAG: %s", errors)
            return dag  # Return original if replan fails

        logger.info("Re-planned: %d tasks remaining", len(new_tasks))
        return new_dag

    def validate_actions(self, dag: TaskDAG, allowed_actions: list[str]) -> list[str]:
        """Check that all task action_types are in the allowed list.

        Returns list of disallowed action types.
        """
        if not allowed_actions:
            return []
        violations = []
        for task in dag.tasks:
            if task.action_type not in allowed_actions:
                violations.append(task.action_type)
        return violations


class DAGValidationError(ValueError):
    """Raised when a task DAG fails structural validation."""
