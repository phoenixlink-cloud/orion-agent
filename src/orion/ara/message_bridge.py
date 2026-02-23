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
"""ARA Message Bridge — routes incoming messages from messaging platforms to ARA sessions.

This is NOT a messaging adapter — those already exist in src/orion/integrations/.
This module:
1. Receives a normalized message from any platform adapter
2. Determines if it's a new task, a correction, or a status query
3. Routes to the appropriate ARA action (create session, update, query)
4. Sends responses back through the same platform adapter

See Phase 4E.1 specification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("orion.ara.message_bridge")


# ---------------------------------------------------------------------------
# Normalized message dataclasses
# ---------------------------------------------------------------------------


@dataclass
class InboundMessage:
    """Normalized message from any messaging platform."""

    platform: str  # 'telegram', 'discord', 'slack', etc.
    user_id: str  # Platform-specific user identifier
    text: str  # Message text content
    thread_id: str | None = None  # For threaded conversations
    reply_to: str | None = None  # If replying to a specific message
    metadata: dict[str, Any] = field(default_factory=dict)  # Platform-specific extras


@dataclass
class OutboundMessage:
    """Normalized response to send back via a messaging platform."""

    text: str
    platform: str
    recipient_id: str
    session_id: str | None = None
    thread_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Intent constants
# ---------------------------------------------------------------------------

INTENT_NEW_TASK = "new_task"
INTENT_CORRECTION = "correction"
INTENT_STATUS = "status"
INTENT_CANCEL = "cancel"
INTENT_REVIEW = "review"
INTENT_UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# MessageBridge
# ---------------------------------------------------------------------------


class MessageBridge:
    """Bridges incoming messages from messaging platforms to ARA sessions.

    This is NOT a messaging adapter — those already exist in src/orion/integrations/.
    This module:
    1. Receives a normalized message from any platform adapter
    2. Determines if it's a new task, a correction, or a status query
    3. Routes to the appropriate ARA action (create session, update, query)
    4. Sends responses back through the same platform adapter
    """

    def __init__(
        self,
        session_engine: Any = None,
        goal_engine: Any = None,
        notification_manager: Any = None,
        performance_metrics: Any = None,
    ):
        """
        Args:
            session_engine: The existing ARA SessionEngine for creating/managing sessions.
            goal_engine: The existing GoalEngine for task decomposition.
            notification_manager: The existing notification manager for sending responses.
            performance_metrics: Optional PerformanceMetrics engine for review summaries.
        """
        self._session_engine = session_engine
        self._goal_engine = goal_engine
        self._notification_manager = notification_manager
        self._performance_metrics = performance_metrics
        self._active_conversations: dict[str, str] = {}  # platform_user_id → session_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def active_conversations(self) -> dict[str, str]:
        """Return a copy of the active conversation map."""
        return dict(self._active_conversations)

    async def handle_message(self, message: InboundMessage) -> OutboundMessage:
        """Handle an incoming message from any messaging platform.

        Determines intent:
        - New task: "Build a Flask API" → create ARA session
        - Correction: "Use PostgreSQL instead" → update running session
        - Status query: "How's it going?" → return session status
        - Cancel: "Stop" / "Cancel" → cancel running session
        - Review: "Show me the results" → return session review

        Returns an OutboundMessage to send back via the same platform.
        """
        intent = self.classify_intent(message)
        logger.info(
            "Message from %s/%s classified as '%s': %.60s",
            message.platform,
            message.user_id,
            intent,
            message.text,
        )

        if intent == INTENT_NEW_TASK:
            return await self._handle_new_task(message)
        elif intent == INTENT_CORRECTION:
            return await self._handle_correction(message)
        elif intent == INTENT_STATUS:
            return await self._handle_status_query(message)
        elif intent == INTENT_CANCEL:
            return await self._handle_cancel(message)
        elif intent == INTENT_REVIEW:
            return await self._handle_review(message)
        else:
            return OutboundMessage(
                text=(
                    "I'm not sure what you'd like me to do. "
                    "Try sending a task like 'Build a Flask API with auth' "
                    "or ask 'What's the status?'"
                ),
                platform=message.platform,
                recipient_id=message.user_id,
            )

    # ------------------------------------------------------------------
    # Intent classification
    # ------------------------------------------------------------------

    def classify_intent(self, message: InboundMessage) -> str:
        """Classify the intent of an incoming message.

        Uses simple keyword matching first, falls back to default.
        This is intentionally simple — the LLM does the real understanding
        when creating the ARA session.
        """
        text_lower = message.text.lower().strip()

        if not text_lower:
            return INTENT_UNKNOWN

        # Cancel patterns
        cancel_keywords = {"stop", "cancel", "abort", "quit", "halt"}
        if text_lower in cancel_keywords:
            return INTENT_CANCEL

        # Status patterns
        status_keywords = {
            "status",
            "progress",
            "how's it going",
            "update",
            "what's happening",
        }
        if text_lower in status_keywords:
            return INTENT_STATUS
        if text_lower.startswith("status") or text_lower.startswith("progress"):
            return INTENT_STATUS

        # Review patterns
        review_keywords = {
            "review",
            "results",
            "show me",
            "what did you build",
            "done?",
        }
        if text_lower in review_keywords:
            return INTENT_REVIEW
        if text_lower.startswith("review") or text_lower.startswith("show"):
            return INTENT_REVIEW

        # Correction patterns — only if there's an active session
        active_session = self._active_conversations.get(message.user_id)
        if active_session:
            correction_prefixes = (
                "instead",
                "actually",
                "change",
                "use",
                "switch to",
                "no,",
                "wait,",
                "but ",
            )
            if any(text_lower.startswith(p) for p in correction_prefixes):
                return INTENT_CORRECTION

        # Default: treat as new task
        return INTENT_NEW_TASK

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_new_task(self, message: InboundMessage) -> OutboundMessage:
        """Create a new ARA session from a messaging task."""
        # Check if user already has an active session
        existing = self._active_conversations.get(message.user_id)
        if existing and self._session_engine:
            status = self._get_session_status(existing)
            if status and self._is_session_running(status):
                return OutboundMessage(
                    text=(
                        f"You already have an active session ({existing[:8]}). "
                        "Send 'status' to check progress or 'cancel' to stop it "
                        "before starting a new task."
                    ),
                    platform=message.platform,
                    recipient_id=message.user_id,
                )

        # Create ARA session
        session_id = await self._create_session(message)

        if session_id:
            self._active_conversations[message.user_id] = session_id

            # Wire messaging notifications so session events reach the user
            if self._notification_manager and hasattr(
                self._notification_manager, "enable_messaging"
            ):
                self._notification_manager.enable_messaging(
                    platform=message.platform,
                    channel=message.user_id,
                )

            return OutboundMessage(
                text=(
                    f"Task received. Session {session_id[:8]} started.\n\n"
                    f"Goal: {message.text}\n\n"
                    "I'll send updates as I work. Send 'status' anytime to check progress."
                ),
                platform=message.platform,
                recipient_id=message.user_id,
                session_id=session_id,
            )
        else:
            return OutboundMessage(
                text="Failed to create session. Please try again.",
                platform=message.platform,
                recipient_id=message.user_id,
            )

    async def _handle_correction(self, message: InboundMessage) -> OutboundMessage:
        """Send a correction to a running session."""
        session_id = self._active_conversations.get(message.user_id)
        if not session_id:
            return OutboundMessage(
                text="No active session to update. Send a new task to get started.",
                platform=message.platform,
                recipient_id=message.user_id,
            )

        # Inject correction into the session's context
        await self._inject_correction(session_id, message.text)

        truncated = message.text[:100]
        return OutboundMessage(
            text=f'Correction received. Adjusting approach: "{truncated}"',
            platform=message.platform,
            recipient_id=message.user_id,
            session_id=session_id,
        )

    async def _handle_status_query(self, message: InboundMessage) -> OutboundMessage:
        """Return current session status."""
        session_id = self._active_conversations.get(message.user_id)
        if not session_id:
            return OutboundMessage(
                text="No active session. Send a task to get started.",
                platform=message.platform,
                recipient_id=message.user_id,
            )

        status = self._get_session_status(session_id)
        if not status:
            return OutboundMessage(
                text="Session not found. It may have expired.",
                platform=message.platform,
                recipient_id=message.user_id,
            )

        text = self._format_status_for_messaging(status)
        return OutboundMessage(
            text=text,
            platform=message.platform,
            recipient_id=message.user_id,
            session_id=session_id,
        )

    async def _handle_cancel(self, message: InboundMessage) -> OutboundMessage:
        """Cancel a running session."""
        session_id = self._active_conversations.get(message.user_id)
        if not session_id:
            return OutboundMessage(
                text="No active session to cancel.",
                platform=message.platform,
                recipient_id=message.user_id,
            )

        cancelled = await self._cancel_session(session_id)
        if cancelled:
            self._active_conversations.pop(message.user_id, None)
            return OutboundMessage(
                text=f"Session {session_id[:8]} cancelled.",
                platform=message.platform,
                recipient_id=message.user_id,
                session_id=session_id,
            )
        else:
            return OutboundMessage(
                text=f"Could not cancel session {session_id[:8]}. It may have already completed.",
                platform=message.platform,
                recipient_id=message.user_id,
                session_id=session_id,
            )

    async def _handle_review(self, message: InboundMessage) -> OutboundMessage:
        """Return a concise review of the last completed session.

        Includes performance metrics (FASR, success rate, MTTR, error
        hotspots) when a PerformanceMetrics engine is available.
        """
        session_id = self._active_conversations.get(message.user_id)
        if not session_id:
            return OutboundMessage(
                text="No recent session to review.",
                platform=message.platform,
                recipient_id=message.user_id,
            )

        review = self._get_session_review(session_id)

        # Enrich review with performance metrics when available
        perf_data: dict[str, Any] | None = None
        if self._performance_metrics:
            try:
                metrics = self._performance_metrics.compute_metrics(session_id=session_id)
                perf_data = metrics.to_dict() if metrics and metrics.total_executions > 0 else None
            except Exception as exc:
                logger.debug("Could not fetch performance metrics: %s", exc)

        text = self._format_review_for_messaging(review, perf_data=perf_data)
        return OutboundMessage(
            text=text,
            platform=message.platform,
            recipient_id=message.user_id,
            session_id=session_id,
        )

    # ------------------------------------------------------------------
    # Session engine helpers (adapt to whatever engine interface exists)
    # ------------------------------------------------------------------

    async def _create_session(self, message: InboundMessage) -> str | None:
        """Create a session via the session engine.  Returns session_id or None."""
        if not self._session_engine:
            return None

        try:
            if hasattr(self._session_engine, "create_session"):
                result = self._session_engine.create_session(
                    goal=message.text,
                    role="night-coder",
                    source_platform=message.platform,
                    source_user_id=message.user_id,
                )
                # Handle both sync and async
                if hasattr(result, "__await__"):
                    result = await result
                return getattr(result, "session_id", None) or (
                    result if isinstance(result, str) else None
                )

            # Fallback: engine might be a simple dict-returning callable
            if callable(self._session_engine):
                result = self._session_engine(message.text)
                if hasattr(result, "__await__"):
                    result = await result
                return result
        except Exception as exc:
            logger.error("Failed to create session: %s", exc)

        return None

    def _get_session_status(self, session_id: str) -> Any:
        """Retrieve session status from the engine."""
        if not self._session_engine:
            return None
        try:
            if hasattr(self._session_engine, "get_status"):
                return self._session_engine.get_status(session_id)
            if hasattr(self._session_engine, "get_session"):
                return self._session_engine.get_session(session_id)
        except Exception:
            pass
        return None

    @staticmethod
    def _is_session_running(status: Any) -> bool:
        """Check if a session status represents a running session."""
        state = getattr(status, "state", None) or getattr(status, "status", None)
        if state is None:
            return False
        state_str = str(state).lower()
        return state_str in ("running", "paused")

    async def _inject_correction(self, session_id: str, correction_text: str) -> None:
        """Inject a mid-execution correction into the session."""
        if not self._session_engine:
            return
        try:
            if hasattr(self._session_engine, "inject_correction"):
                result = self._session_engine.inject_correction(session_id, correction_text)
                if hasattr(result, "__await__"):
                    await result
        except Exception as exc:
            logger.warning("Correction injection failed: %s", exc)

    async def _cancel_session(self, session_id: str) -> bool:
        """Cancel a running session.  Returns True on success."""
        if not self._session_engine:
            return False
        try:
            if hasattr(self._session_engine, "cancel_session"):
                result = self._session_engine.cancel_session(session_id)
                if hasattr(result, "__await__"):
                    result = await result
                return bool(result) if result is not None else True
            if hasattr(self._session_engine, "cancel"):
                result = self._session_engine.cancel(session_id)
                if hasattr(result, "__await__"):
                    result = await result
                return True
        except Exception as exc:
            logger.warning("Session cancel failed: %s", exc)
        return False

    def _get_session_review(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve review/summary data for a session."""
        if not self._session_engine:
            return None
        try:
            if hasattr(self._session_engine, "get_review"):
                return self._session_engine.get_review(session_id)
            if hasattr(self._session_engine, "get_session"):
                sess = self._session_engine.get_session(session_id)
                if sess:
                    return {
                        "session_id": session_id,
                        "state": getattr(sess, "state", getattr(sess, "status", "unknown")),
                        "goal": getattr(sess, "goal", ""),
                    }
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_status_for_messaging(status: Any) -> str:
        """Format session status for messaging (concise, emoji-friendly)."""
        state_emoji = {
            "created": "🔄",
            "running": "⚡",
            "paused": "⏸",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫",
        }
        raw_state = getattr(status, "state", None) or getattr(status, "status", None) or "unknown"
        state_str = str(raw_state).lower()
        emoji = state_emoji.get(state_str, "❓")

        lines = [f"{emoji} Session: {state_str.upper()}"]

        # Progress info
        progress = getattr(status, "progress", None)
        if progress:
            completed = getattr(progress, "completed_tasks", None)
            total = getattr(progress, "total_tasks", None)
            if completed is not None and total is not None:
                lines.append(f"Tasks: {completed}/{total}")

        if hasattr(status, "checkpoint_count") and status.checkpoint_count:
            lines.append(f"Checkpoints: {status.checkpoint_count}")

        elapsed = getattr(status, "elapsed_seconds", None)
        if elapsed and elapsed > 0:
            minutes = int(elapsed / 60)
            if minutes > 0:
                lines.append(f"Elapsed: {minutes}m")

        return "\n".join(lines)

    @staticmethod
    def _format_review_for_messaging(
        review: dict[str, Any] | None,
        *,
        perf_data: dict[str, Any] | None = None,
    ) -> str:
        """Format session review for messaging.

        Args:
            review: Session-level review dict (state, goal, tasks, duration, files).
            perf_data: Optional performance-metrics dict from
                ``ExecutionMetrics.to_dict()``.
        """
        if not review:
            return "No review data available for this session."

        lines: list[str] = []
        state = review.get("state", review.get("status", "unknown"))
        goal = review.get("goal", "")

        state_str = str(state).lower()
        if state_str == "completed":
            lines.append("Session Complete")
        elif state_str == "failed":
            lines.append("Session Failed")
        else:
            lines.append(f"Session: {state_str.upper()}")

        if goal:
            lines.append(f"Goal: {goal}")

        # Task progress
        completed = review.get("completed_tasks") or review.get("tasks_completed")
        total = review.get("total_tasks") or review.get("tasks_total")
        if completed is not None and total is not None:
            lines.append(f"Tasks: {completed}/{total}")

        # Duration
        duration = review.get("duration") or review.get("elapsed")
        if duration:
            lines.append(f"Duration: {duration}")

        # Files
        files = review.get("files_changed")
        if files:
            lines.append(f"Files changed: {files}")

        # Performance metrics section
        if perf_data:
            lines.append("")
            lines.append(format_performance_summary(perf_data))

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone formatting helper (usable outside MessageBridge)
# ---------------------------------------------------------------------------


def format_performance_summary(perf: dict[str, Any]) -> str:
    """Format an ``ExecutionMetrics.to_dict()`` payload for messaging.

    Produces a concise, human-readable performance block suitable for
    Telegram, Discord, Slack, etc.
    """
    total = perf.get("total_executions", 0)
    if total == 0:
        return "No execution data."

    success_pct = round(perf.get("success_rate", 0) * 100, 1)
    fasr_pct = round(perf.get("first_attempt_success_rate", 0) * 100, 1)
    fix_pct = round(perf.get("fix_rate", 0) * 100, 1)
    mean_retries = round(perf.get("mean_retries", 0), 1)
    mean_dur = round(perf.get("mean_duration_seconds", 0), 1)
    mttr = round(perf.get("mean_time_to_resolution", 0), 1)

    lines = [
        "Performance:",
        f"  Executions: {total}",
        f"  Success: {success_pct}%",
        f"  First-attempt: {fasr_pct}%",
    ]

    if fix_pct > 0:
        lines.append(f"  Fix rate: {fix_pct}%")
    if mean_retries > 0:
        lines.append(f"  Avg retries: {mean_retries}")
    if mean_dur > 0:
        lines.append(f"  Avg duration: {mean_dur}s")
    if mttr > 0:
        lines.append(f"  MTTR: {mttr}s")

    # Top error categories (max 3)
    errors = perf.get("error_distribution", {})
    if errors:
        top3 = sorted(errors.items(), key=lambda x: x[1], reverse=True)[:3]
        lines.append("  Top errors: " + ", ".join(f"{cat} ({n})" for cat, n in top3))

    return "\n".join(lines)
