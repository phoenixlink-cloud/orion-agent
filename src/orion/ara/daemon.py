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
"""ARA Daemon — background process manager for autonomous sessions.

Runs ARA sessions in the background, manages lifecycle, and provides
a control interface for CLI commands (status, pause, resume, cancel).

See ARA-001 §11 for full design.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from orion.ara.checkpoint import CheckpointManager
from orion.ara.execution import ExecutionLoop
from orion.ara.feedback_store import FeedbackStore, SessionOutcome, TaskOutcome
from orion.ara.goal_engine import TaskDAG
from orion.ara.role_profile import RoleProfile
from orion.ara.session import SessionState, SessionStatus

logger = logging.getLogger("orion.ara.daemon")

DAEMON_STATE_DIR = Path.home() / ".orion" / "daemon"
DAEMON_PID_FILE = DAEMON_STATE_DIR / "daemon.pid"
DAEMON_CONTROL_FILE = DAEMON_STATE_DIR / "control.json"


@dataclass
class DaemonStatus:
    """Current status of the ARA daemon."""

    running: bool = False
    pid: int | None = None
    session_id: str | None = None
    role_name: str | None = None
    goal: str | None = None
    session_status: str | None = None
    elapsed_seconds: float = 0.0
    tasks_completed: int = 0
    tasks_total: int = 0
    cost_usd: float = 0.0
    checkpoint_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "pid": self.pid,
            "session_id": self.session_id,
            "role_name": self.role_name,
            "goal": self.goal,
            "session_status": self.session_status,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "tasks_completed": self.tasks_completed,
            "tasks_total": self.tasks_total,
            "cost_usd": round(self.cost_usd, 4),
            "checkpoint_count": self.checkpoint_count,
            "error": self.error,
        }

    def summary(self) -> str:
        if not self.running:
            return "Daemon: not running"
        pct = f"{self.tasks_completed}/{self.tasks_total}" if self.tasks_total > 0 else "0/0"
        hours = self.elapsed_seconds / 3600
        return (
            f"Session: {self.session_id} ({self.session_status})\n"
            f"Role: {self.role_name} | Goal: {self.goal}\n"
            f"Progress: {pct} tasks | {hours:.1f}h elapsed | ${self.cost_usd:.4f}\n"
            f"Checkpoints: {self.checkpoint_count}"
        )


class DaemonControl:
    """File-based control interface for the daemon.

    Uses a JSON control file for signaling between CLI and daemon process.
    Commands: pause, resume, cancel, none.
    """

    def __init__(self, state_dir: Path | None = None):
        self._dir = state_dir or DAEMON_STATE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._control_file = self._dir / "control.json"
        self._status_file = self._dir / "status.json"
        self._pid_file = self._dir / "daemon.pid"

    def write_pid(self, pid: int) -> None:
        self._pid_file.write_text(str(pid), encoding="utf-8")

    def read_pid(self) -> int | None:
        if not self._pid_file.exists():
            return None
        try:
            return int(self._pid_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            return None

    def clear_pid(self) -> None:
        if self._pid_file.exists():
            self._pid_file.unlink(missing_ok=True)

    def send_command(self, command: str) -> None:
        """Send a control command to the daemon."""
        data = {"command": command, "timestamp": time.time()}
        self._control_file.write_text(json.dumps(data), encoding="utf-8")
        logger.info("Sent daemon command: %s", command)

    def read_command(self) -> str | None:
        """Read and consume the pending control command."""
        if not self._control_file.exists():
            return None
        try:
            data = json.loads(self._control_file.read_text(encoding="utf-8"))
            self._control_file.unlink(missing_ok=True)
            return data.get("command")
        except (json.JSONDecodeError, OSError):
            return None

    def write_status(self, status: DaemonStatus) -> None:
        """Write current daemon status."""
        self._status_file.write_text(json.dumps(status.to_dict(), indent=2), encoding="utf-8")

    def read_status(self) -> DaemonStatus:
        """Read current daemon status."""
        if not self._status_file.exists():
            return DaemonStatus(running=False)
        try:
            data = json.loads(self._status_file.read_text(encoding="utf-8"))
            return DaemonStatus(
                **{k: v for k, v in data.items() if k in DaemonStatus.__dataclass_fields__}
            )
        except (json.JSONDecodeError, OSError):
            return DaemonStatus(running=False)

    def is_daemon_alive(self) -> bool:
        """Check if the daemon process is still running."""
        pid = self.read_pid()
        if pid is None:
            return False
        try:
            if os.name == "nt":
                # Windows: use kernel32 OpenProcess
                import ctypes

                process_query_limited = 0x1000
                handle = ctypes.windll.kernel32.OpenProcess(process_query_limited, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, PermissionError):
            return False

    def cleanup(self) -> None:
        """Clean up all daemon state files."""
        for f in (self._pid_file, self._control_file, self._status_file):
            if f.exists():
                f.unlink(missing_ok=True)


class ARADaemon:
    """Background daemon that runs an ARA session.

    Integrates session state, goal engine, execution loop, and checkpoint manager.
    Polls for control commands between tasks.
    """

    def __init__(
        self,
        session: SessionState,
        role: RoleProfile,
        dag: TaskDAG,
        control: DaemonControl | None = None,
        task_executor: Callable[..., Any] | None = None,
        task_executor_ref: Any = None,
        checkpoint_dir: Path | None = None,
    ):
        self._session = session
        self._role = role
        self._dag = dag
        self._control = control or DaemonControl()
        self._executor = task_executor
        self._executor_ref = task_executor_ref
        self._checkpoint_mgr = CheckpointManager(
            session_id=session.session_id,
            checkpoints_dir=checkpoint_dir,
        )
        self._loop: ExecutionLoop | None = None

    @property
    def session(self) -> SessionState:
        return self._session

    def _update_status(self) -> None:
        """Write current status to the control file."""
        status = DaemonStatus(
            running=self._session.is_active,
            pid=os.getpid(),
            session_id=self._session.session_id,
            role_name=self._session.role_name,
            goal=self._session.goal,
            session_status=self._session.status.value,
            elapsed_seconds=self._session.elapsed_seconds,
            tasks_completed=self._session.progress.completed_tasks,
            tasks_total=self._session.progress.total_tasks,
            cost_usd=self._session.cost_usd,
            checkpoint_count=self._session.checkpoint_count,
        )
        self._control.write_status(status)

    def _create_checkpoint(self) -> None:
        """Create a checkpoint of current state."""
        self._checkpoint_mgr.create(
            session_state=self._session.to_dict(),
            dag_state=self._dag.to_dict(),
            description=f"auto-cp after task {self._session.progress.completed_tasks}",
        )
        self._session.checkpoint_count += 1
        self._session.last_checkpoint_at = time.time()
        logger.info("Daemon checkpoint created: #%d", self._session.checkpoint_count)

    def _process_control_command(self) -> None:
        """Check for and process any pending control command."""
        cmd = self._control.read_command()
        if cmd is None:
            return

        logger.info("Daemon received command: %s", cmd)
        if cmd == "pause":
            if self._loop and self._session.status == SessionStatus.RUNNING:
                self._loop.stop()
                self._create_checkpoint()
                logger.info("Daemon pausing session")
        elif cmd == "cancel":
            if self._loop:
                self._loop.stop()
                self._session.transition(SessionStatus.CANCELLED)
                logger.info("Daemon cancelling session")
        elif cmd == "resume":
            # Resume is handled by re-running the execution loop
            logger.info("Daemon resume acknowledged")

    def _on_task_complete(self) -> None:
        """Called after each task — update status, save session."""
        self._update_status()
        self._session.save()

    def _on_control_check(self) -> None:
        """Called between tasks — process pending control commands."""
        self._process_control_command()

    def _write_notification(self, event: str, message: str) -> None:
        """Write a notification file for the CLI/web to pick up."""
        notif_dir = self._control._dir / "notifications"
        notif_dir.mkdir(parents=True, exist_ok=True)
        notif = {
            "event": event,
            "session_id": self._session.session_id,
            "role_name": self._session.role_name,
            "message": message,
            "timestamp": time.time(),
            "read": False,
        }
        notif_file = notif_dir / f"{event}_{int(time.time())}.json"
        notif_file.write_text(json.dumps(notif, indent=2), encoding="utf-8")
        logger.info("Notification written: %s — %s", event, message)

    def _record_feedback(self, result) -> None:
        """Record task and session outcomes to FeedbackStore."""
        try:
            store = FeedbackStore()

            # Record each task outcome
            for task in self._dag.tasks:
                store.record_task(
                    TaskOutcome(
                        task_id=task.task_id,
                        session_id=self._session.session_id,
                        action_type=task.action_type,
                        success=(task.status.value == "completed"),
                        confidence=task.confidence,
                        duration_seconds=task.actual_minutes * 60,
                        error=task.error or None,
                    )
                )

            # Record session outcome
            store.record_session(
                SessionOutcome(
                    session_id=self._session.session_id,
                    role_name=self._session.role_name,
                    goal=self._session.goal,
                    status=self._session.status.value,
                    tasks_completed=result.tasks_completed,
                    tasks_failed=result.tasks_failed,
                    total_duration_seconds=result.total_elapsed_seconds,
                    total_cost_usd=result.total_cost_usd,
                )
            )
            logger.info("Feedback recorded: %d tasks, 1 session", len(self._dag.tasks))
        except Exception as e:
            logger.warning("Failed to record feedback: %s", e)

    async def run(self) -> None:
        """Run the daemon execution loop."""
        self._control.write_pid(os.getpid())
        self._update_status()

        try:
            self._loop = ExecutionLoop(
                session=self._session,
                dag=self._dag,
                task_executor=self._executor,
                task_executor_ref=self._executor_ref,
                on_checkpoint=self._create_checkpoint,
                on_task_complete=self._on_task_complete,
                on_control_check=self._on_control_check,
                checkpoint_interval_minutes=self._role.auto_checkpoint_interval_minutes,
            )

            result = await self._loop.run()

            # Save final state
            self._session.save()
            self._update_status()

            # Record feedback to FeedbackStore
            self._record_feedback(result)

            # Write completion notification
            if self._role.notifications.on_complete:
                if self._session.status == SessionStatus.COMPLETED:
                    self._write_notification(
                        "session_complete",
                        f"Session {self._session.session_id[:12]} completed. "
                        f"{result.tasks_completed}/{self._dag.total_tasks} tasks done. "
                        f"Run '/review' to approve and promote files.",
                    )
                elif (
                    self._session.status == SessionStatus.FAILED
                    and self._role.notifications.on_error
                ):
                    self._write_notification(
                        "session_failed",
                        f"Session {self._session.session_id[:12]} failed: {result.stop_reason}",
                    )

            logger.info(
                "Daemon session ended: %s (completed=%d, failed=%d)",
                result.stop_reason,
                result.tasks_completed,
                result.tasks_failed,
            )

        except Exception as e:
            logger.error("Daemon error: %s", e)
            if not self._session.is_terminal:
                self._session.error_message = str(e)
                self._session.transition(SessionStatus.FAILED)
            self._update_status()
            if self._role.notifications.on_error:
                self._write_notification(
                    "session_error",
                    f"Session {self._session.session_id[:12]} error: {e}",
                )

        finally:
            self._control.clear_pid()
