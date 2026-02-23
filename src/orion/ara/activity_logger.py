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
"""Docker Activity Logger — real-time log of every action Orion takes inside Docker.

Design philosophy: Orion is an employee. Docker is the employee's workstation.
AEGIS is the company security policy. The activity logger is how the manager
(user) sees what the employee is doing at their workstation, in real time.

This module captures and broadcasts all Docker session activity via:
  - In-memory ring buffer (capped at ``max_entries``)
  - Registered callbacks (for WebSocket / CLI streaming)
  - JSONL export (for audit persistence)

See Phase 4C.1 specification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("orion.ara.activity_logger")

# Maximum characters kept for stdout/stderr in an entry
_MAX_OUTPUT_CHARS = 2000


# ---------------------------------------------------------------------------
# ActivityEntry dataclass
# ---------------------------------------------------------------------------


@dataclass
class ActivityEntry:
    """Single logged activity inside Docker."""

    timestamp: str = ""
    session_id: str = ""
    action_type: str = (
        ""  # 'command', 'file_write', 'file_read', 'install', 'test', 'error', 'info'
    )
    description: str = ""
    command: str | None = None
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    duration_seconds: float | None = None
    phase: str = ""  # 'install', 'execute', 'test', 'promote', 'setup'
    status: str = "running"  # 'running', 'success', 'failed', 'skipped'
    entry_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON export."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActivityEntry:
        """Deserialize from dict."""
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# ActivityLogger
# ---------------------------------------------------------------------------


class ActivityLogger:
    """Captures and broadcasts Docker session activity.

    Usage::

        logger = ActivityLogger(session_id="abc123")
        logger.on_activity(my_callback)

        entry = logger.log("command", "Running: python app.py", command="python app.py")
        logger.update(entry, exit_code=0, status="success", duration_seconds=1.2)
    """

    def __init__(self, session_id: str, max_entries: int = 1000) -> None:
        self.session_id = session_id
        self._entries: list[ActivityEntry] = []
        self._callbacks: list[Callable[[ActivityEntry], None]] = []
        self._max_entries = max_entries
        self._next_id = 1

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def log(
        self,
        action_type: str,
        description: str,
        *,
        command: str | None = None,
        exit_code: int | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        duration_seconds: float | None = None,
        phase: str = "",
        status: str = "running",
    ) -> ActivityEntry:
        """Log an activity. Auto-timestamps. Calls all registered callbacks."""
        # Truncate output fields
        if stdout and len(stdout) > _MAX_OUTPUT_CHARS:
            stdout = stdout[:_MAX_OUTPUT_CHARS] + "... (truncated)"
        if stderr and len(stderr) > _MAX_OUTPUT_CHARS:
            stderr = stderr[:_MAX_OUTPUT_CHARS] + "... (truncated)"

        entry = ActivityEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=self.session_id,
            action_type=action_type,
            description=description,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            phase=phase,
            status=status,
            entry_id=self._next_id,
        )
        self._next_id += 1

        self._entries.append(entry)
        # Ring buffer eviction
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

        self._fire_callbacks(entry)
        return entry

    def update(self, entry: ActivityEntry, **kwargs: Any) -> ActivityEntry:
        """Update a running entry (e.g., set exit_code, status, duration).

        Truncates stdout/stderr if provided.
        """
        for k, v in kwargs.items():
            if k in ("stdout", "stderr") and isinstance(v, str) and len(v) > _MAX_OUTPUT_CHARS:
                v = v[:_MAX_OUTPUT_CHARS] + "... (truncated)"
            if hasattr(entry, k):
                setattr(entry, k, v)

        self._fire_callbacks(entry)
        return entry

    # ------------------------------------------------------------------
    # Callbacks (real-time broadcast)
    # ------------------------------------------------------------------

    def on_activity(self, callback: Callable[[ActivityEntry], None]) -> None:
        """Register a callback for real-time activity events."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[ActivityEntry], None]) -> None:
        """Remove a previously registered callback."""
        self._callbacks = [cb for cb in self._callbacks if cb is not callback]

    def _fire_callbacks(self, entry: ActivityEntry) -> None:
        """Invoke all registered callbacks. Errors are logged, not raised."""
        for cb in self._callbacks:
            try:
                cb(entry)
            except Exception as exc:
                logger.debug("Activity callback error: %s", exc)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_entries(
        self,
        limit: int = 50,
        action_type: str | None = None,
    ) -> list[ActivityEntry]:
        """Get recent entries, optionally filtered by action_type."""
        entries = self._entries
        if action_type:
            entries = [e for e in entries if e.action_type == action_type]
        return entries[-limit:]

    @property
    def entry_count(self) -> int:
        """Total entries currently stored."""
        return len(self._entries)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_summary(self) -> dict[str, Any]:
        """Get session activity summary: counts by type, total duration, error count."""
        counts: dict[str, int] = {}
        error_count = 0
        total_duration = 0.0

        for entry in self._entries:
            counts[entry.action_type] = counts.get(entry.action_type, 0) + 1
            if entry.status == "failed":
                error_count += 1
            if entry.duration_seconds is not None:
                total_duration += entry.duration_seconds

        return {
            "session_id": self.session_id,
            "total_entries": len(self._entries),
            "counts_by_type": counts,
            "error_count": error_count,
            "total_duration_seconds": round(total_duration, 3),
        }

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_jsonl(self) -> str:
        """Export all entries as JSONL (for audit persistence)."""
        lines = []
        for entry in self._entries:
            lines.append(json.dumps(entry.to_dict(), default=str))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _default_log_dir() -> Path:
        """Default directory for activity log files."""
        return Path.home() / ".orion" / "activity_logs"

    def save_to_file(self, directory: str | Path | None = None) -> Path:
        """Persist current entries as a JSONL file.

        Args:
            directory: Target directory. Defaults to ``~/.orion/activity_logs``.

        Returns:
            Path to the written file.
        """
        log_dir = Path(directory) if directory else self._default_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        filepath = log_dir / f"{self.session_id}.jsonl"

        jsonl = self.to_jsonl()
        filepath.write_text(jsonl, encoding="utf-8")
        logger.info("Activity log saved: %s (%d entries)", filepath, self.entry_count)
        return filepath

    @classmethod
    def load_from_file(cls, session_id: str, directory: str | Path | None = None) -> ActivityLogger:
        """Load an ActivityLogger from a persisted JSONL file.

        Args:
            session_id: Session ID (determines filename).
            directory: Directory containing log files. Defaults to ``~/.orion/activity_logs``.

        Returns:
            ActivityLogger with loaded entries.

        Raises:
            FileNotFoundError: If the JSONL file does not exist.
        """
        log_dir = Path(directory) if directory else cls._default_log_dir()
        filepath = log_dir / f"{session_id}.jsonl"

        if not filepath.exists():
            raise FileNotFoundError(f"Activity log not found: {filepath}")

        text = filepath.read_text(encoding="utf-8").strip()
        al = cls(session_id=session_id)

        if text:
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    data = json.loads(line)
                    entry = ActivityEntry.from_dict(data)
                    al._entries.append(entry)
                    if entry.entry_id >= al._next_id:
                        al._next_id = entry.entry_id + 1

        logger.info("Activity log loaded: %s (%d entries)", filepath, al.entry_count)
        return al

    @staticmethod
    def list_sessions(directory: str | Path | None = None) -> list[dict[str, Any]]:
        """List all persisted activity log sessions.

        Args:
            directory: Directory containing log files. Defaults to ``~/.orion/activity_logs``.

        Returns:
            List of dicts with ``session_id``, ``file_path``, ``size_bytes``, ``modified``.
        """
        log_dir = Path(directory) if directory else ActivityLogger._default_log_dir()
        if not log_dir.exists():
            return []

        sessions = []
        for filepath in sorted(log_dir.glob("*.jsonl")):
            stat = filepath.stat()
            sessions.append(
                {
                    "session_id": filepath.stem,
                    "file_path": str(filepath),
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
        return sessions


# ---------------------------------------------------------------------------
# ActivityMessagingSummary — Phase 4E.3
# ---------------------------------------------------------------------------


class ActivityMessagingSummary:
    """Streams activity summaries to a messaging platform.

    Registers as a callback on an :class:`ActivityLogger` and sends concise
    summaries when:
      - The execution *phase* changes (e.g. install → execute → test)
      - An error (``status == "failed"``) occurs
      - A configurable number of entries have accumulated without a send

    This avoids spamming the user with per-command messages while still
    keeping them informed of meaningful progress.
    """

    def __init__(
        self,
        notification_manager: Any = None,
        platform: str = "",
        channel: str = "",
        *,
        batch_threshold: int = 10,
    ) -> None:
        """
        Args:
            notification_manager: The existing NotificationManager (with messaging enabled).
            platform: Messaging platform name (for direct send fallback).
            channel: Channel / user ID on the platform.
            batch_threshold: Send a summary after this many unsent entries even
                without a phase change.
        """
        self._notification_manager = notification_manager
        self._platform = platform
        self._channel = channel
        self._batch_threshold = max(1, batch_threshold)

        self._current_phase: str = ""
        self._pending: list[ActivityEntry] = []
        self._sent_summaries: list[dict[str, Any]] = []
        self._bound_callback: Callable[[ActivityEntry], None] | None = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def sent_summaries(self) -> list[dict[str, Any]]:
        """Return copies of all summaries that have been sent."""
        return list(self._sent_summaries)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def attach(self, activity_logger: ActivityLogger) -> None:
        """Register this summary streamer as a callback on the logger."""
        self._bound_callback = self.on_activity
        activity_logger.on_activity(self._bound_callback)

    def detach(self, activity_logger: ActivityLogger) -> None:
        """Remove this summary streamer from the logger's callbacks."""
        if self._bound_callback is not None:
            activity_logger.remove_callback(self._bound_callback)
            self._bound_callback = None

    # ------------------------------------------------------------------
    # Callback (registered on ActivityLogger)
    # ------------------------------------------------------------------

    def on_activity(self, entry: ActivityEntry) -> None:
        """Called for every activity entry. Decides whether to send a summary."""
        phase_changed = entry.phase and entry.phase != self._current_phase
        is_error = entry.status == "failed"

        self._pending.append(entry)

        if phase_changed:
            # Summarise the *previous* phase that just ended
            if self._current_phase:
                self._send_summary(self._current_phase, self._pending[:-1])
                self._pending = [entry]
            self._current_phase = entry.phase

        if is_error:
            self._send_summary(
                entry.phase or self._current_phase or "unknown",
                self._pending,
                error=True,
            )
            self._pending = []

        elif len(self._pending) >= self._batch_threshold:
            self._send_summary(
                self._current_phase or "progress",
                self._pending,
            )
            self._pending = []

    # ------------------------------------------------------------------
    # Summary formatting & sending
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_phase(phase: str, entries: list[ActivityEntry], *, error: bool = False) -> str:
        """Build a concise, messaging-friendly summary string."""
        if not entries:
            return f"Phase '{phase}' completed (no entries)."

        total = len(entries)
        succeeded = sum(1 for e in entries if e.status == "success")
        failed = sum(1 for e in entries if e.status == "failed")
        running = total - succeeded - failed

        total_dur = sum(e.duration_seconds or 0.0 for e in entries)

        lines: list[str] = []
        if error:
            lines.append(f"Error in phase: {phase}")
        else:
            lines.append(f"Phase: {phase}")

        lines.append(f"Actions: {total} ({succeeded} ok, {failed} failed, {running} other)")

        if total_dur > 0:
            lines.append(f"Duration: {total_dur:.1f}s")

        # Show the last failed entry's description if this is an error summary
        if error:
            last_fail = next((e for e in reversed(entries) if e.status == "failed"), None)
            if last_fail:
                lines.append(f"Last error: {last_fail.description[:120]}")

        return "\n".join(lines)

    def _send_summary(
        self,
        phase: str,
        entries: list[ActivityEntry],
        *,
        error: bool = False,
    ) -> None:
        """Format and dispatch a summary to the messaging platform."""
        text = self._summarize_phase(phase, entries, error=error)

        summary_record: dict[str, Any] = {
            "phase": phase,
            "entry_count": len(entries),
            "error": error,
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Try NotificationManager first (it already has the messaging provider)
        sent = False
        if self._notification_manager:
            try:
                if hasattr(self._notification_manager, "notify"):
                    sent = self._notification_manager.notify(
                        "checkpoint_created",
                        {
                            "session_id": entries[0].session_id if entries else "",
                            "checkpoint_number": phase,
                        },
                    )
            except Exception as exc:
                logger.debug("Notification manager send failed: %s", exc)

        # Fallback: direct messaging provider send
        if not sent and self._platform and self._channel:
            try:
                from orion.integrations.messaging import get_messaging_provider

                provider = get_messaging_provider(self._platform)
                if provider:
                    import asyncio

                    coro = provider.send_message(self._channel, text)
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(coro)
                        sent = True
                    except RuntimeError:
                        asyncio.run(coro)
                        sent = True
            except Exception as exc:
                logger.debug("Direct messaging send failed: %s", exc)

        summary_record["sent"] = sent
        self._sent_summaries.append(summary_record)
        logger.info(
            "Activity summary for phase '%s' (%d entries, error=%s)", phase, len(entries), error
        )
