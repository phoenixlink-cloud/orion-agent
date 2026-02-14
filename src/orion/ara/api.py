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
"""ARA API — REST + WebSocket interface for dashboard integration.

Provides a lightweight API layer for the ARA dashboard to query session
status, control sessions, and receive real-time updates.

See ARA-001 §13 / Appendix C.12 for full design.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from orion.ara.cli_commands import (
    cmd_cancel,
    cmd_pause,
    cmd_resume,
    cmd_status,
    cmd_work,
)
from orion.ara.daemon import DaemonControl
from orion.ara.feedback_store import FeedbackStore

logger = logging.getLogger("orion.ara.api")


@dataclass
class APIResponse:
    """Standardized API response."""

    status: int
    data: dict[str, Any] | None = None
    error: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status,
            "timestamp": self.timestamp,
        }
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass
class WSMessage:
    """WebSocket message format."""

    event: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str) -> WSMessage:
        data = json.loads(raw)
        return cls(
            event=data.get("event", "unknown"),
            data=data.get("data", {}),
            timestamp=data.get("timestamp", time.time()),
        )


class ARARouter:
    """REST-style API router for ARA operations.

    Maps API endpoints to ARA CLI commands and data queries.
    Designed for integration with any HTTP framework (FastAPI, Flask, etc.)
    or for direct programmatic use.
    """

    def __init__(
        self,
        control: DaemonControl | None = None,
        feedback_store: FeedbackStore | None = None,
    ):
        self._control = control or DaemonControl()
        self._feedback = feedback_store

        self._routes: dict[str, Callable[..., APIResponse]] = {
            "GET /api/ara/status": self.get_status,
            "POST /api/ara/work": self.post_work,
            "POST /api/ara/pause": self.post_pause,
            "POST /api/ara/resume": self.post_resume,
            "POST /api/ara/cancel": self.post_cancel,
            "GET /api/ara/feedback/stats": self.get_feedback_stats,
            "GET /api/ara/feedback/sessions": self.get_feedback_sessions,
            "POST /api/ara/feedback": self.post_feedback,
        }

    @property
    def routes(self) -> dict[str, Callable[..., APIResponse]]:
        return dict(self._routes)

    def handle(self, method: str, path: str, body: dict[str, Any] | None = None) -> APIResponse:
        """Route a request to the appropriate handler."""
        key = f"{method.upper()} {path}"
        handler = self._routes.get(key)
        if handler is None:
            return APIResponse(status=404, error=f"Not found: {key}")
        try:
            if body and method.upper() in ("POST", "PUT", "PATCH"):
                return handler(**body)
            return handler()
        except Exception as e:
            logger.error("API error on %s: %s", key, e)
            return APIResponse(status=500, error=str(e))

    def get_status(self) -> APIResponse:
        """GET /api/ara/status — Current session status."""
        result = cmd_status(control=self._control)
        return APIResponse(
            status=200,
            data=result.data,
        )

    def post_work(self, role_name: str = "", goal: str = "", **kwargs: Any) -> APIResponse:
        """POST /api/ara/work — Start a new session."""
        if not role_name or not goal:
            return APIResponse(status=400, error="role_name and goal are required")

        result = cmd_work(role_name=role_name, goal=goal, control=self._control, **kwargs)
        return APIResponse(
            status=201 if result.success else 409,
            data=result.data,
            error=None if result.success else result.message,
        )

    def post_pause(self) -> APIResponse:
        """POST /api/ara/pause — Pause running session."""
        result = cmd_pause(control=self._control)
        return APIResponse(
            status=200 if result.success else 409,
            data=result.data,
            error=None if result.success else result.message,
        )

    def post_resume(self) -> APIResponse:
        """POST /api/ara/resume — Resume paused session."""
        result = cmd_resume(control=self._control)
        return APIResponse(
            status=200 if result.success else 409,
            data=result.data,
            error=None if result.success else result.message,
        )

    def post_cancel(self) -> APIResponse:
        """POST /api/ara/cancel — Cancel running session."""
        result = cmd_cancel(control=self._control)
        return APIResponse(
            status=200 if result.success else 409,
            data=result.data,
            error=None if result.success else result.message,
        )

    def get_feedback_stats(self) -> APIResponse:
        """GET /api/ara/feedback/stats — Confidence calibration stats."""
        if not self._feedback:
            return APIResponse(status=503, error="Feedback store not configured")
        stats = self._feedback.get_confidence_stats()
        return APIResponse(
            status=200,
            data={"stats": [s.to_dict() for s in stats]},
        )

    def get_feedback_sessions(self, role_name: str | None = None, **kwargs: Any) -> APIResponse:
        """GET /api/ara/feedback/sessions — Session outcomes."""
        if not self._feedback:
            return APIResponse(status=503, error="Feedback store not configured")
        outcomes = self._feedback.get_session_outcomes(role_name=role_name)
        return APIResponse(
            status=200,
            data={"sessions": [o.to_dict() for o in outcomes]},
        )

    def post_feedback(
        self, session_id: str = "", rating: int = 0, comment: str | None = None, **kwargs: Any
    ) -> APIResponse:
        """POST /api/ara/feedback — Submit user feedback for a session."""
        if not self._feedback:
            return APIResponse(status=503, error="Feedback store not configured")
        if not session_id or not (1 <= rating <= 5):
            return APIResponse(status=400, error="session_id and rating (1-5) required")

        updated = self._feedback.add_user_feedback(session_id, rating, comment)
        if updated:
            return APIResponse(status=200, data={"session_id": session_id, "rating": rating})
        return APIResponse(status=404, error=f"Session {session_id} not found")


class WSChannel:
    """WebSocket channel for real-time ARA updates.

    Manages subscribers and broadcasts session events.
    Designed for integration with any WebSocket framework.
    """

    def __init__(self):
        self._subscribers: list[Callable[[str], None]] = []
        self._event_log: list[WSMessage] = []
        self._max_log: int = 100

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def event_log(self) -> list[WSMessage]:
        return list(self._event_log)

    def subscribe(self, callback: Callable[[str], None]) -> None:
        """Add a subscriber that receives JSON-encoded messages."""
        self._subscribers.append(callback)
        logger.debug("WS subscriber added (total: %d)", len(self._subscribers))

    def unsubscribe(self, callback: Callable[[str], None]) -> None:
        """Remove a subscriber."""
        self._subscribers = [s for s in self._subscribers if s is not callback]

    def broadcast(self, event: str, data: dict[str, Any] | None = None) -> int:
        """Broadcast an event to all subscribers.

        Returns the number of subscribers that received the message.
        """
        msg = WSMessage(event=event, data=data or {})
        json_msg = msg.to_json()

        # Log event
        self._event_log.append(msg)
        if len(self._event_log) > self._max_log:
            self._event_log = self._event_log[-self._max_log:]

        delivered = 0
        for sub in self._subscribers:
            try:
                sub(json_msg)
                delivered += 1
            except Exception as e:
                logger.warning("WS broadcast failed for subscriber: %s", e)

        logger.debug("WS broadcast '%s' to %d/%d subscribers", event, delivered, len(self._subscribers))
        return delivered

    def emit_session_update(self, session_data: dict[str, Any]) -> int:
        """Broadcast a session status update."""
        return self.broadcast("session_update", session_data)

    def emit_task_complete(self, task_data: dict[str, Any]) -> int:
        """Broadcast a task completion event."""
        return self.broadcast("task_complete", task_data)

    def emit_checkpoint(self, checkpoint_data: dict[str, Any]) -> int:
        """Broadcast a checkpoint event."""
        return self.broadcast("checkpoint", checkpoint_data)

    def emit_error(self, error_data: dict[str, Any]) -> int:
        """Broadcast an error event."""
        return self.broadcast("error", error_data)
