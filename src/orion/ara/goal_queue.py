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
"""Goal Queue — multi-goal queuing with priority interrupts.

Allows users to queue multiple goals for sequential execution.
Supports priority interrupts where an urgent goal checkpoints and
pauses the current goal, runs to completion, then resumes the previous.

See ARA-001 Appendix C.5 for design.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.ara.goal_queue")

DEFAULT_QUEUE_PATH = Path.home() / ".orion" / "goal_queue.json"


@dataclass
class QueuedGoal:
    """A goal waiting in the queue."""

    goal_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    role_name: str = ""
    priority: str = "normal"  # "normal" | "urgent"
    depends_on: str | None = None  # goal_id of prerequisite
    added_at: float = field(default_factory=time.time)
    status: str = "queued"  # "queued" | "active" | "paused" | "completed" | "failed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueuedGoal:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class GoalQueue:
    """FIFO goal queue with priority interrupt support.

    Usage::

        queue = GoalQueue()
        queue.enqueue(QueuedGoal(description="Write auth", role_name="coder"))
        queue.enqueue(QueuedGoal(description="Fix bug", role_name="coder", priority="urgent"))

        next_goal = queue.dequeue()  # Returns urgent goal first
        queue.complete(next_goal.goal_id)
    """

    def __init__(self, path: Path | None = None):
        self._path = path or DEFAULT_QUEUE_PATH
        self._goals: list[QueuedGoal] = []
        self._paused_goals: list[QueuedGoal] = []
        self._load()

    def _load(self) -> None:
        """Load queue state from disk."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._goals = [QueuedGoal.from_dict(g) for g in data.get("goals", [])]
            self._paused_goals = [QueuedGoal.from_dict(g) for g in data.get("paused", [])]
        except Exception as e:
            logger.warning("Failed to load goal queue: %s", e)

    def _save(self) -> None:
        """Persist queue state to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "goals": [g.to_dict() for g in self._goals],
            "paused": [g.to_dict() for g in self._paused_goals],
        }
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def enqueue(self, goal: QueuedGoal) -> None:
        """Add a goal to the queue."""
        self._goals.append(goal)
        self._save()
        logger.info("Enqueued goal: %s (%s)", goal.description[:40], goal.priority)

    def dequeue(self) -> QueuedGoal | None:
        """Get the next goal to execute.

        Priority: urgent goals first, then FIFO order.
        Respects dependencies (skips goals whose prerequisite isn't completed).
        """
        completed_ids = {g.goal_id for g in self._goals if g.status == "completed"}

        # Try urgent first
        for goal in self._goals:
            if goal.status != "queued":
                continue
            if goal.priority == "urgent":
                if goal.depends_on and goal.depends_on not in completed_ids:
                    continue
                goal.status = "active"
                self._save()
                return goal

        # Then normal FIFO
        for goal in self._goals:
            if goal.status != "queued":
                continue
            if goal.depends_on and goal.depends_on not in completed_ids:
                continue
            goal.status = "active"
            self._save()
            return goal

        return None

    def interrupt(self, urgent_goal: QueuedGoal) -> str | None:
        """Priority interrupt: pause current active goal, start urgent.

        Returns the paused goal_id, or None if nothing was active.
        """
        paused_id = None
        for goal in self._goals:
            if goal.status == "active":
                goal.status = "paused"
                self._paused_goals.append(goal)
                paused_id = goal.goal_id
                break

        urgent_goal.priority = "urgent"
        urgent_goal.status = "active"
        self._goals.append(urgent_goal)
        self._save()
        return paused_id

    def complete(self, goal_id: str) -> bool:
        """Mark a goal as completed."""
        for goal in self._goals:
            if goal.goal_id == goal_id:
                goal.status = "completed"
                self._save()
                return True
        return False

    def fail(self, goal_id: str) -> bool:
        """Mark a goal as failed."""
        for goal in self._goals:
            if goal.goal_id == goal_id:
                goal.status = "failed"
                self._save()
                return True
        return False

    def resume_paused(self) -> QueuedGoal | None:
        """Resume the most recently paused goal (after an interrupt completes)."""
        if not self._paused_goals:
            return None
        goal = self._paused_goals.pop()
        for g in self._goals:
            if g.goal_id == goal.goal_id:
                g.status = "active"
                self._save()
                return g
        return None

    def reorder(self, from_pos: int, to_pos: int) -> bool:
        """Move a queued goal from one position to another (0-indexed among queued)."""
        queued = [g for g in self._goals if g.status == "queued"]
        if from_pos < 0 or from_pos >= len(queued) or to_pos < 0 or to_pos >= len(queued):
            return False
        goal = queued[from_pos]
        self._goals.remove(goal)
        # Find insertion point
        queued_remaining = [g for g in self._goals if g.status == "queued"]
        if to_pos >= len(queued_remaining):
            self._goals.append(goal)
        else:
            target = queued_remaining[to_pos]
            idx = self._goals.index(target)
            self._goals.insert(idx, goal)
        self._save()
        return True

    def list_goals(self) -> list[QueuedGoal]:
        """Return all goals in queue order."""
        return list(self._goals)

    def list_queued(self) -> list[QueuedGoal]:
        """Return only queued (pending) goals."""
        return [g for g in self._goals if g.status == "queued"]

    @property
    def size(self) -> int:
        """Number of goals in the queue (all statuses)."""
        return len(self._goals)

    @property
    def pending_count(self) -> int:
        """Number of queued goals waiting to execute."""
        return sum(1 for g in self._goals if g.status == "queued")

    def clear(self) -> int:
        """Remove all queued goals. Returns count removed."""
        count = len(self._goals)
        self._goals.clear()
        self._paused_goals.clear()
        self._save()
        return count
