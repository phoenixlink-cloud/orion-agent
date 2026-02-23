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
"""ARA Session State — core state machine for autonomous sessions.

Manages session lifecycle: created → running → paused → completed/failed/cancelled.
Tracks heartbeat, elapsed time, cost, and task progress.

See ARA-001 §6 for full design.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.ara.session")

SESSIONS_DIR = Path.home() / ".orion" / "sessions"


class SessionStatus(str, Enum):
    """Session lifecycle states."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid state transitions
VALID_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATED: {SessionStatus.RUNNING, SessionStatus.CANCELLED},
    SessionStatus.RUNNING: {
        SessionStatus.PAUSED,
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.CANCELLED,
    },
    SessionStatus.PAUSED: {SessionStatus.RUNNING, SessionStatus.CANCELLED},
    SessionStatus.COMPLETED: set(),
    SessionStatus.FAILED: set(),
    SessionStatus.CANCELLED: set(),
}


@dataclass
class TaskProgress:
    """Track task completion within a session."""

    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0

    @property
    def pending_tasks(self) -> int:
        return self.total_tasks - self.completed_tasks - self.failed_tasks - self.skipped_tasks

    @property
    def completion_pct(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total_tasks,
            "completed": self.completed_tasks,
            "failed": self.failed_tasks,
            "skipped": self.skipped_tasks,
            "pending": self.pending_tasks,
            "completion_pct": round(self.completion_pct, 1),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskProgress:
        return cls(
            total_tasks=data.get("total", 0),
            completed_tasks=data.get("completed", 0),
            failed_tasks=data.get("failed", 0),
            skipped_tasks=data.get("skipped", 0),
        )


@dataclass
class SessionState:
    """Core state for an ARA autonomous session."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    role_name: str = ""
    goal: str = ""
    workspace_path: str = ""
    status: SessionStatus = SessionStatus.CREATED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    last_heartbeat: float = field(default_factory=time.time)
    heartbeat_interval: int = 30
    elapsed_seconds: float = 0.0
    cost_usd: float = 0.0
    max_cost_usd: float = 5.0
    max_duration_hours: float = 8.0
    checkpoint_count: int = 0
    last_checkpoint_at: float | None = None
    error_message: str | None = None
    progress: TaskProgress = field(default_factory=TaskProgress)
    source_platform: str | None = None  # Phase 4E: originating messaging platform
    source_user_id: str | None = None  # Phase 4E: originating user on that platform
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        )

    @property
    def is_active(self) -> bool:
        return self.status in (SessionStatus.RUNNING, SessionStatus.PAUSED)

    @property
    def elapsed_hours(self) -> float:
        return self.elapsed_seconds / 3600

    def transition(self, new_status: SessionStatus) -> None:
        """Transition to a new state. Raises ValueError on invalid transition."""
        valid = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            raise InvalidTransitionError(
                f"Cannot transition from {self.status.value} to {new_status.value}. "
                f"Valid: {', '.join(s.value for s in valid) or 'none'}"
            )
        old = self.status
        self.status = new_status
        self.updated_at = time.time()

        if new_status == SessionStatus.RUNNING and self.started_at is None:
            self.started_at = time.time()
        elif new_status in (SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED):
            self.completed_at = time.time()

        logger.info("Session %s: %s → %s", self.session_id, old.value, new_status.value)

    def heartbeat(self) -> None:
        """Update heartbeat timestamp and elapsed time."""
        now = time.time()
        if self.status == SessionStatus.RUNNING:
            self.elapsed_seconds += now - self.last_heartbeat
        self.last_heartbeat = now
        self.updated_at = now

    def add_cost(self, amount: float) -> None:
        """Add cost to the session."""
        self.cost_usd += amount
        self.updated_at = time.time()

    def check_stop_conditions(self) -> str | None:
        """Check if any stop condition is met. Returns reason or None."""
        if self.elapsed_hours >= self.max_duration_hours:
            return f"time_limit: {self.elapsed_hours:.1f}h >= {self.max_duration_hours}h"
        if self.cost_usd >= self.max_cost_usd:
            return f"cost_limit: ${self.cost_usd:.2f} >= ${self.max_cost_usd:.2f}"
        if self.progress.total_tasks > 0 and self.progress.pending_tasks == 0:
            return "goal_complete: all tasks finished"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "role_name": self.role_name,
            "goal": self.goal,
            "workspace_path": self.workspace_path,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "last_heartbeat": self.last_heartbeat,
            "elapsed_seconds": self.elapsed_seconds,
            "cost_usd": self.cost_usd,
            "max_cost_usd": self.max_cost_usd,
            "max_duration_hours": self.max_duration_hours,
            "checkpoint_count": self.checkpoint_count,
            "last_checkpoint_at": self.last_checkpoint_at,
            "error_message": self.error_message,
            "progress": self.progress.to_dict(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        progress_data = data.get("progress", {})
        return cls(
            session_id=data.get("session_id", uuid.uuid4().hex[:12]),
            role_name=data.get("role_name", ""),
            goal=data.get("goal", ""),
            workspace_path=data.get("workspace_path", ""),
            status=SessionStatus(data.get("status", "created")),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            last_heartbeat=data.get("last_heartbeat", time.time()),
            elapsed_seconds=data.get("elapsed_seconds", 0.0),
            cost_usd=data.get("cost_usd", 0.0),
            max_cost_usd=data.get("max_cost_usd", 5.0),
            max_duration_hours=data.get("max_duration_hours", 8.0),
            checkpoint_count=data.get("checkpoint_count", 0),
            last_checkpoint_at=data.get("last_checkpoint_at"),
            error_message=data.get("error_message"),
            progress=TaskProgress.from_dict(progress_data),
            metadata=data.get("metadata", {}),
        )

    def save(self, sessions_dir: Path | None = None) -> Path:
        """Persist session state to disk."""
        base = sessions_dir or SESSIONS_DIR
        session_dir = base / self.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / "session.json"
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, session_id: str, sessions_dir: Path | None = None) -> SessionState:
        """Load session state from disk."""
        base = sessions_dir or SESSIONS_DIR
        path = base / session_id / "session.json"
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


class InvalidTransitionError(ValueError):
    """Raised when an invalid state transition is attempted."""
