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
"""ARA Feedback Store — outcome recording and confidence calibration.

Records task outcomes, user feedback, and calibrates confidence scores
for future task estimation.

See ARA-001 Appendix C.3 for full design.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.ara.feedback_store")

FEEDBACK_DIR = Path.home() / ".orion" / "feedback"


@dataclass
class TaskOutcome:
    """Recorded outcome of a single task execution."""

    task_id: str
    session_id: str
    action_type: str
    success: bool
    confidence: float = 0.0
    duration_seconds: float = 0.0
    error: str | None = None
    user_rating: int | None = None  # 1-5 scale
    user_comment: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "action_type": self.action_type,
            "success": self.success,
            "confidence": self.confidence,
            "duration_seconds": round(self.duration_seconds, 3),
            "error": self.error,
            "user_rating": self.user_rating,
            "user_comment": self.user_comment,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskOutcome:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SessionOutcome:
    """Aggregated outcome of a full session."""

    session_id: str
    role_name: str
    goal: str
    status: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_duration_seconds: float = 0.0
    total_cost_usd: float = 0.0
    user_rating: int | None = None
    user_comment: str | None = None
    promoted: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "role_name": self.role_name,
            "goal": self.goal,
            "status": self.status,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "total_duration_seconds": round(self.total_duration_seconds, 3),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "user_rating": self.user_rating,
            "user_comment": self.user_comment,
            "promoted": self.promoted,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionOutcome:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ConfidenceStats:
    """Calibration statistics for confidence scoring."""

    action_type: str
    total_tasks: int = 0
    successful_tasks: int = 0
    avg_confidence: float = 0.0
    avg_duration: float = 0.0
    accuracy: float = 0.0  # How often high-confidence tasks actually succeed

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "avg_confidence": round(self.avg_confidence, 4),
            "avg_duration": round(self.avg_duration, 3),
            "accuracy": round(self.accuracy, 4),
        }


class FeedbackStore:
    """Persistent store for task and session outcomes.

    Used for:
    - Confidence calibration (are high-confidence predictions actually correct?)
    - Duration estimation (how long do similar tasks take?)
    - Role performance tracking
    - Learning from user feedback
    """

    def __init__(self, store_dir: Path | None = None):
        self._dir = store_dir or FEEDBACK_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._tasks_file = self._dir / "task_outcomes.jsonl"
        self._sessions_file = self._dir / "session_outcomes.jsonl"

    def record_task(self, outcome: TaskOutcome) -> None:
        """Record a single task outcome."""
        with self._tasks_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(outcome.to_dict()) + "\n")
        logger.debug("Recorded task outcome: %s (%s)", outcome.task_id, outcome.action_type)

    def record_session(self, outcome: SessionOutcome) -> None:
        """Record a session outcome."""
        with self._sessions_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(outcome.to_dict()) + "\n")
        logger.info("Recorded session outcome: %s (%s)", outcome.session_id, outcome.status)

    def add_user_feedback(
        self,
        session_id: str,
        rating: int,
        comment: str | None = None,
    ) -> bool:
        """Add user feedback to a session outcome."""
        outcomes = self.get_session_outcomes()
        updated = False
        for o in outcomes:
            if o.session_id == session_id:
                o.user_rating = rating
                o.user_comment = comment
                updated = True
                break

        if updated:
            self._rewrite_sessions(outcomes)
        return updated

    def get_task_outcomes(
        self,
        session_id: str | None = None,
        action_type: str | None = None,
        limit: int = 1000,
    ) -> list[TaskOutcome]:
        """Retrieve task outcomes, optionally filtered."""
        outcomes = self._read_tasks()
        if session_id:
            outcomes = [o for o in outcomes if o.session_id == session_id]
        if action_type:
            outcomes = [o for o in outcomes if o.action_type == action_type]
        return outcomes[-limit:]

    def get_session_outcomes(
        self,
        role_name: str | None = None,
        limit: int = 100,
    ) -> list[SessionOutcome]:
        """Retrieve session outcomes, optionally filtered by role."""
        outcomes = self._read_sessions()
        if role_name:
            outcomes = [o for o in outcomes if o.role_name == role_name]
        return outcomes[-limit:]

    def get_confidence_stats(self, action_type: str | None = None) -> list[ConfidenceStats]:
        """Calculate confidence calibration statistics by action type."""
        outcomes = self._read_tasks()
        if action_type:
            outcomes = [o for o in outcomes if o.action_type == action_type]

        # Group by action_type
        by_type: dict[str, list[TaskOutcome]] = {}
        for o in outcomes:
            by_type.setdefault(o.action_type, []).append(o)

        stats = []
        for atype, tasks in sorted(by_type.items()):
            total = len(tasks)
            successful = sum(1 for t in tasks if t.success)
            avg_conf = sum(t.confidence for t in tasks) / total if total > 0 else 0
            avg_dur = sum(t.duration_seconds for t in tasks) / total if total > 0 else 0

            # Accuracy: of tasks with confidence > 0.7, how many succeeded?
            high_conf = [t for t in tasks if t.confidence > 0.7]
            accuracy = (
                sum(1 for t in high_conf if t.success) / len(high_conf)
                if high_conf else 0
            )

            stats.append(ConfidenceStats(
                action_type=atype,
                total_tasks=total,
                successful_tasks=successful,
                avg_confidence=avg_conf,
                avg_duration=avg_dur,
                accuracy=accuracy,
            ))

        return stats

    def estimate_duration(self, action_type: str) -> float | None:
        """Estimate task duration based on historical data."""
        outcomes = [o for o in self._read_tasks() if o.action_type == action_type and o.success]
        if not outcomes:
            return None
        return sum(o.duration_seconds for o in outcomes) / len(outcomes)

    @property
    def task_count(self) -> int:
        return len(self._read_tasks())

    @property
    def session_count(self) -> int:
        return len(self._read_sessions())

    def _read_tasks(self) -> list[TaskOutcome]:
        if not self._tasks_file.exists():
            return []
        results = []
        for line in self._tasks_file.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    results.append(TaskOutcome.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    pass
        return results

    def _read_sessions(self) -> list[SessionOutcome]:
        if not self._sessions_file.exists():
            return []
        results = []
        for line in self._sessions_file.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    results.append(SessionOutcome.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    pass
        return results

    def _rewrite_sessions(self, outcomes: list[SessionOutcome]) -> None:
        with self._sessions_file.open("w", encoding="utf-8") as f:
            for o in outcomes:
                f.write(json.dumps(o.to_dict()) + "\n")
