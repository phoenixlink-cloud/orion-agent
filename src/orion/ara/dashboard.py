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
"""Morning Dashboard — CLI TUI for reviewing ARA session results.

Provides a structured text-based dashboard for reviewing completed
autonomous sessions, including task lists, file changes, cost/time
budget, AEGIS status, and approval queue.

See ARA-001 §9 for design.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orion.ara.session import SessionState, SessionStatus

logger = logging.getLogger("orion.ara.dashboard")

SESSIONS_DIR = Path.home() / ".orion" / "sessions"


@dataclass
class DashboardSection:
    """A single section of the dashboard display."""

    title: str
    content: list[str] = field(default_factory=list)
    priority: int = 0  # Higher = shown first

    def render(self) -> str:
        lines = [f"{'─' * 60}", f"  {self.title}", f"{'─' * 60}"]
        lines.extend(f"  {line}" for line in self.content)
        return "\n".join(lines)


@dataclass
class DashboardData:
    """All data needed to render the dashboard."""

    session_id: str = ""
    role_name: str = ""
    goal: str = ""
    status: str = ""
    duration_str: str = ""
    cost_str: str = ""
    tasks: list[dict[str, Any]] = field(default_factory=list)
    file_changes: list[dict[str, Any]] = field(default_factory=list)
    approval_items: list[dict[str, Any]] = field(default_factory=list)
    confidence_avg: float = 0.0
    aegis_status: str = "active"
    checkpoints: int = 0
    error_message: str | None = None
    sections: list[DashboardSection] = field(default_factory=list)


class MorningDashboard:
    """Interactive terminal dashboard for reviewing ARA session results.

    Usage::

        dashboard = MorningDashboard()
        output = dashboard.render(session_id="abc123")
        print(output)

        # Or render from session data directly
        data = dashboard.gather_data(session_id="abc123")
        output = dashboard.render_data(data)
    """

    def __init__(self, sessions_dir: Path | None = None):
        self._sessions_dir = sessions_dir or SESSIONS_DIR

    def gather_data(self, session_id: str) -> DashboardData:
        """Gather all dashboard data for a session."""
        data = DashboardData(session_id=session_id)

        try:
            session = SessionState.load(session_id, sessions_dir=self._sessions_dir)
        except FileNotFoundError:
            data.error_message = f"Session {session_id} not found."
            return data

        data.role_name = session.role_name
        data.goal = session.goal
        data.status = session.status.value
        data.cost_str = f"${session.cost_usd:.4f}"
        data.checkpoints = session.checkpoint_count
        data.error_message = session.error_message

        # Duration
        elapsed = session.elapsed_seconds
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        data.duration_str = f"{hours}h {minutes}m"

        # Tasks from plan.json
        plan_file = self._sessions_dir / session_id / "plan.json"
        if plan_file.exists():
            try:
                plan = json.loads(plan_file.read_text(encoding="utf-8"))
                data.tasks = plan.get("tasks", [])
            except Exception:
                pass

        # File changes from diff.json
        diff_file = self._sessions_dir / session_id / "diff.json"
        if diff_file.exists():
            try:
                data.file_changes = json.loads(diff_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Approval items (tasks needing consent)
        data.approval_items = [
            t for t in data.tasks
            if t.get("status") == "needs_approval"
        ]

        # Confidence average
        confidences = [
            t.get("confidence", 0)
            for t in data.tasks
            if t.get("confidence") is not None and t.get("confidence") > 0
        ]
        if confidences:
            data.confidence_avg = sum(confidences) / len(confidences)

        # Build sections
        data.sections = self._build_sections(data)

        return data

    def _build_sections(self, data: DashboardData) -> list[DashboardSection]:
        """Build all dashboard sections from data."""
        sections: list[DashboardSection] = []

        # 1. Session Header
        header = DashboardSection(title="Session Overview", priority=100)
        header.content = [
            f"Session:  {data.session_id[:12]}",
            f"Role:     {data.role_name}",
            f"Goal:     {data.goal}",
            f"Status:   {data.status.upper()}",
            f"Duration: {data.duration_str}",
            f"Cost:     {data.cost_str}",
            f"Checkpoints: {data.checkpoints}",
        ]
        if data.error_message:
            header.content.append(f"Error:    {data.error_message}")
        sections.append(header)

        # 2. Approval Queue (highest priority if items exist)
        if data.approval_items:
            approval = DashboardSection(title="Approval Required", priority=200)
            approval.content = [
                f"  {len(data.approval_items)} item(s) need your decision:",
                "",
            ]
            for item in data.approval_items:
                name = item.get("name", item.get("action", "unknown"))
                approval.content.append(f"  [!] {name}")
            sections.append(approval)

        # 3. Task List
        if data.tasks:
            tasks = DashboardSection(title="Tasks", priority=90)
            completed = sum(1 for t in data.tasks if t.get("status") == "completed")
            failed = sum(1 for t in data.tasks if t.get("status") == "failed")
            pending = sum(1 for t in data.tasks if t.get("status") in ("pending", "needs_approval"))
            tasks.content = [
                f"Total: {len(data.tasks)}  |  Completed: {completed}  |  "
                f"Failed: {failed}  |  Pending: {pending}",
                "",
            ]
            for i, task in enumerate(data.tasks, 1):
                status = task.get("status", "?")
                name = task.get("name", task.get("action", "unknown"))
                conf = task.get("confidence")
                icon = {"completed": "+", "failed": "x", "pending": ".", "needs_approval": "!"}
                marker = icon.get(status, "?")
                conf_str = f" ({conf:.0%})" if conf else ""
                tasks.content.append(f"  [{marker}] {i}. {name}{conf_str}")
            sections.append(tasks)

        # 4. File Changes
        if data.file_changes:
            files = DashboardSection(title="File Changes", priority=80)
            added = sum(1 for f in data.file_changes if f.get("status") == "added")
            modified = sum(1 for f in data.file_changes if f.get("status") == "modified")
            deleted = sum(1 for f in data.file_changes if f.get("status") == "deleted")
            files.content = [
                f"Added: {added}  |  Modified: {modified}  |  Deleted: {deleted}",
                "",
            ]
            for fc in data.file_changes[:20]:
                status = fc.get("status", "?")[0].upper()
                path = fc.get("path", "?")
                adds = fc.get("additions", 0)
                dels = fc.get("deletions", 0)
                files.content.append(f"  [{status}] {path}  +{adds} -{dels}")
            if len(data.file_changes) > 20:
                files.content.append(f"  ... and {len(data.file_changes) - 20} more")
            sections.append(files)

        # 5. Cost / Time Budget
        budget = DashboardSection(title="Budget", priority=70)
        budget.content = [
            f"Cost:     {data.cost_str}",
            f"Duration: {data.duration_str}",
        ]
        if data.confidence_avg > 0:
            budget.content.append(f"Avg Confidence: {data.confidence_avg:.0%}")
        sections.append(budget)

        # 6. AEGIS Status
        aegis = DashboardSection(title="AEGIS Governance", priority=60)
        aegis.content = [
            f"Status: {data.aegis_status.upper()}",
            "All actions validated against role authority.",
        ]
        sections.append(aegis)

        # Sort by priority (highest first)
        sections.sort(key=lambda s: s.priority, reverse=True)
        return sections

    def render(self, session_id: str) -> str:
        """Gather data and render the full dashboard for a session."""
        data = self.gather_data(session_id)
        return self.render_data(data)

    def render_data(self, data: DashboardData) -> str:
        """Render the dashboard from pre-gathered data."""
        if data.error_message and not data.role_name:
            return f"\n  Error: {data.error_message}\n"

        lines = [
            "",
            "=" * 60,
            "  ORION — Morning Dashboard",
            "=" * 60,
            "",
        ]

        for section in data.sections:
            lines.append(section.render())
            lines.append("")

        lines.extend([
            "=" * 60,
            "  Actions: [a]pprove  [r]eject  [d]iff  [l]og  [q]uit",
            "=" * 60,
            "",
        ])

        return "\n".join(lines)

    def check_pending_reviews(self) -> list[dict[str, Any]]:
        """Check for completed sessions that haven't been reviewed.

        Returns a list of session summaries needing review.
        """
        if not self._sessions_dir.exists():
            return []

        pending: list[dict[str, Any]] = []
        for session_dir in sorted(self._sessions_dir.iterdir()):
            if not session_dir.is_dir():
                continue
            session_file = session_dir / "session.json"
            if not session_file.exists():
                continue

            try:
                session = SessionState.load(
                    session_dir.name, sessions_dir=self._sessions_dir,
                )
            except Exception:
                continue

            if session.status == SessionStatus.COMPLETED:
                reviewed_marker = session_dir / ".reviewed"
                if not reviewed_marker.exists():
                    pending.append({
                        "session_id": session.session_id,
                        "role": session.role_name,
                        "goal": session.goal[:60],
                        "tasks": session.progress.completed_tasks,
                    })

        return pending

    def get_startup_message(self) -> str | None:
        """Get the REPL startup notification about pending reviews.

        Returns None if no sessions need review.
        """
        pending = self.check_pending_reviews()
        if not pending:
            return None

        if len(pending) == 1:
            p = pending[0]
            return (
                f"Orion completed {p['tasks']} tasks "
                f"(\"{p['goal']}\").\n"
                f"Run `orion review` to inspect and approve."
            )

        total_tasks = sum(p["tasks"] for p in pending)
        return (
            f"Orion completed {total_tasks} tasks across "
            f"{len(pending)} sessions.\n"
            f"Run `orion sessions` to view, then `orion review` to approve."
        )
