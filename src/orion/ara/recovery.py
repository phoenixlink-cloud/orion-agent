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
"""ARA Recovery — failure detection, heartbeat monitoring, and auto-retry.

Detects interrupted sessions (stale heartbeat), handles transient failures
with configurable retry logic, and manages OOM/crash recovery.

See ARA-001 §C.1 for full design.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from orion.ara.session import SessionState, SessionStatus

logger = logging.getLogger("orion.ara.recovery")

# Heartbeat staleness threshold
HEARTBEAT_STALE_SECONDS = 120  # 2 minutes without heartbeat = stale

# Auto-retry defaults
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 5.0
DEFAULT_RETRY_BACKOFF_MULTIPLIER = 2.0


@dataclass
class RecoveryAction:
    """Describes a recovery action to take."""

    action: str  # "resume", "rollback", "abort", "retry", "none"
    reason: str
    checkpoint_id: str | None = None
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "checkpoint_id": self.checkpoint_id,
            "retry_count": self.retry_count,
        }


@dataclass
class RetryPolicy:
    """Configurable retry policy for transient failures."""

    max_retries: int = DEFAULT_MAX_RETRIES
    delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS
    backoff_multiplier: float = DEFAULT_RETRY_BACKOFF_MULTIPLIER
    retryable_errors: list[str] = field(
        default_factory=lambda: [
            "timeout",
            "connection",
            "rate_limit",
            "temporary",
            "transient",
        ]
    )

    def is_retryable(self, error: str) -> bool:
        """Check if an error message indicates a retryable failure."""
        error_lower = error.lower()
        return any(pattern in error_lower for pattern in self.retryable_errors)

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt (exponential backoff)."""
        return self.delay_seconds * (self.backoff_multiplier**attempt)


class RecoveryManager:
    """Manages failure detection and recovery for ARA sessions."""

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        heartbeat_stale_seconds: float = HEARTBEAT_STALE_SECONDS,
    ):
        self._retry_policy = retry_policy or RetryPolicy()
        self._heartbeat_stale = heartbeat_stale_seconds
        self._retry_counts: dict[str, int] = {}  # task_id -> retry count

    def is_session_stale(self, session: SessionState) -> bool:
        """Check if a session's heartbeat is stale (possibly crashed)."""
        if session.is_terminal:
            return False
        if session.status != SessionStatus.RUNNING:
            return False
        return (time.time() - session.last_heartbeat) > self._heartbeat_stale

    def diagnose(self, session: SessionState, last_error: str | None = None) -> RecoveryAction:
        """Diagnose a session and recommend a recovery action.

        Decision tree:
        1. If session is stale → resume from last checkpoint
        2. If last error is retryable and retries remain → retry
        3. If last error is not retryable → rollback to checkpoint
        4. If no checkpoint available → abort
        """
        # Check for stale heartbeat (crash detection)
        if self.is_session_stale(session):
            if session.checkpoint_count > 0:
                return RecoveryAction(
                    action="resume",
                    reason=f"Stale heartbeat detected ({self._heartbeat_stale}s). Resuming from last checkpoint.",
                )
            return RecoveryAction(
                action="abort",
                reason="Stale heartbeat detected. No checkpoint available for recovery.",
            )

        # Check if error is retryable
        if last_error and self._retry_policy.is_retryable(last_error):
            task_retries = max(self._retry_counts.values()) if self._retry_counts else 0
            if task_retries < self._retry_policy.max_retries:
                return RecoveryAction(
                    action="retry",
                    reason=f"Retryable error: {last_error}",
                    retry_count=task_retries + 1,
                )

        # Non-retryable error with checkpoint → rollback
        if last_error and session.checkpoint_count > 0:
            return RecoveryAction(
                action="rollback",
                reason=f"Non-retryable error: {last_error}. Rolling back to last checkpoint.",
            )

        # Non-retryable error without checkpoint → abort
        if last_error:
            return RecoveryAction(
                action="abort",
                reason=f"Non-retryable error with no checkpoint: {last_error}",
            )

        return RecoveryAction(action="none", reason="No recovery needed")

    def record_retry(self, task_id: str) -> int:
        """Record a retry attempt for a task. Returns the new retry count."""
        count = self._retry_counts.get(task_id, 0) + 1
        self._retry_counts[task_id] = count
        logger.info("Retry %d for task %s", count, task_id)
        return count

    def get_retry_count(self, task_id: str) -> int:
        """Get the current retry count for a task."""
        return self._retry_counts.get(task_id, 0)

    def can_retry(self, task_id: str) -> bool:
        """Check if a task can be retried."""
        return self.get_retry_count(task_id) < self._retry_policy.max_retries

    def get_retry_delay(self, task_id: str) -> float:
        """Get the delay before the next retry for a task."""
        attempt = self.get_retry_count(task_id)
        return self._retry_policy.get_delay(attempt)

    def reset_retries(self, task_id: str | None = None) -> None:
        """Reset retry counts. If task_id is None, reset all."""
        if task_id:
            self._retry_counts.pop(task_id, None)
        else:
            self._retry_counts.clear()
