# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Phase 13: Morning Dashboard TUI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orion.ara.dashboard import (
    DashboardData,
    DashboardSection,
    MorningDashboard,
)
from orion.ara.session import SessionState, SessionStatus


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture
def dashboard(sessions_dir: Path) -> MorningDashboard:
    return MorningDashboard(sessions_dir=sessions_dir)


def _create_session(
    sessions_dir: Path,
    session_id: str,
    role: str = "test-role",
    goal: str = "Test goal",
    status: SessionStatus = SessionStatus.COMPLETED,
    cost: float = 0.25,
    elapsed: float = 3600.0,
    tasks: list | None = None,
    file_changes: list | None = None,
) -> None:
    """Create a session with optional plan and diff data."""
    session = SessionState(
        session_id=session_id,
        role_name=role,
        goal=goal,
        status=status,
        cost_usd=cost,
        elapsed_seconds=elapsed,
        max_cost_usd=5.0,
        max_duration_hours=8.0,
    )
    session.save(sessions_dir=sessions_dir)

    session_dir = sessions_dir / session_id

    if tasks is not None:
        (session_dir / "plan.json").write_text(
            json.dumps({"tasks": tasks}), encoding="utf-8",
        )

    if file_changes is not None:
        (session_dir / "diff.json").write_text(
            json.dumps(file_changes), encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# DashboardSection
# ---------------------------------------------------------------------------


class TestDashboardSection:
    def test_render_basic(self):
        s = DashboardSection(title="Test Section", content=["line 1", "line 2"])
        rendered = s.render()
        assert "Test Section" in rendered
        assert "line 1" in rendered
        assert "line 2" in rendered

    def test_render_empty(self):
        s = DashboardSection(title="Empty")
        rendered = s.render()
        assert "Empty" in rendered


# ---------------------------------------------------------------------------
# DashboardData
# ---------------------------------------------------------------------------


class TestDashboardData:
    def test_defaults(self):
        d = DashboardData()
        assert d.session_id == ""
        assert d.tasks == []
        assert d.file_changes == []
        assert d.approval_items == []


# ---------------------------------------------------------------------------
# MorningDashboard.gather_data
# ---------------------------------------------------------------------------


class TestGatherData:
    def test_session_not_found(self, dashboard: MorningDashboard):
        data = dashboard.gather_data("nonexistent")
        assert data.error_message is not None
        assert "not found" in data.error_message

    def test_basic_session(self, dashboard: MorningDashboard, sessions_dir: Path):
        _create_session(sessions_dir, "basic-1", goal="Write tests", cost=0.50, elapsed=7200)
        data = dashboard.gather_data("basic-1")
        assert data.role_name == "test-role"
        assert data.goal == "Write tests"
        assert data.status == "completed"
        assert "$0.50" in data.cost_str
        assert "2h" in data.duration_str

    def test_with_tasks(self, dashboard: MorningDashboard, sessions_dir: Path):
        tasks = [
            {"name": "Write auth", "status": "completed", "confidence": 0.95},
            {"name": "Write tests", "status": "completed", "confidence": 0.88},
            {"name": "Update docs", "status": "pending"},
        ]
        _create_session(sessions_dir, "tasks-1", tasks=tasks)
        data = dashboard.gather_data("tasks-1")
        assert len(data.tasks) == 3
        assert data.confidence_avg == pytest.approx(0.915, abs=0.01)

    def test_with_file_changes(self, dashboard: MorningDashboard, sessions_dir: Path):
        changes = [
            {"path": "src/auth.py", "status": "added", "additions": 50, "deletions": 0},
            {"path": "src/utils.py", "status": "modified", "additions": 10, "deletions": 3},
        ]
        _create_session(sessions_dir, "files-1", file_changes=changes)
        data = dashboard.gather_data("files-1")
        assert len(data.file_changes) == 2

    def test_approval_items(self, dashboard: MorningDashboard, sessions_dir: Path):
        tasks = [
            {"name": "Deploy", "status": "needs_approval"},
            {"name": "Write code", "status": "completed"},
        ]
        _create_session(sessions_dir, "approve-1", tasks=tasks)
        data = dashboard.gather_data("approve-1")
        assert len(data.approval_items) == 1
        assert data.approval_items[0]["name"] == "Deploy"

    def test_sections_built(self, dashboard: MorningDashboard, sessions_dir: Path):
        _create_session(sessions_dir, "sections-1")
        data = dashboard.gather_data("sections-1")
        assert len(data.sections) > 0
        titles = [s.title for s in data.sections]
        assert "Session Overview" in titles
        assert "Budget" in titles
        assert "AEGIS Governance" in titles


# ---------------------------------------------------------------------------
# MorningDashboard.render
# ---------------------------------------------------------------------------


class TestRender:
    def test_render_not_found(self, dashboard: MorningDashboard):
        output = dashboard.render("nope")
        assert "Error" in output

    def test_render_basic(self, dashboard: MorningDashboard, sessions_dir: Path):
        _create_session(sessions_dir, "render-1", goal="Build feature")
        output = dashboard.render("render-1")
        assert "ORION" in output
        assert "Morning Dashboard" in output
        assert "Build feature" in output
        assert "test-role" in output

    def test_render_with_tasks(self, dashboard: MorningDashboard, sessions_dir: Path):
        tasks = [
            {"name": "Task A", "status": "completed", "confidence": 0.9},
            {"name": "Task B", "status": "failed"},
        ]
        _create_session(sessions_dir, "render-2", tasks=tasks)
        output = dashboard.render("render-2")
        assert "Task A" in output
        assert "Task B" in output
        assert "Tasks" in output

    def test_render_with_approval(self, dashboard: MorningDashboard, sessions_dir: Path):
        tasks = [{"name": "Dangerous Op", "status": "needs_approval"}]
        _create_session(sessions_dir, "render-3", tasks=tasks)
        output = dashboard.render("render-3")
        assert "Approval Required" in output
        assert "Dangerous Op" in output

    def test_render_with_files(self, dashboard: MorningDashboard, sessions_dir: Path):
        changes = [
            {"path": "new.py", "status": "added", "additions": 100, "deletions": 0},
        ]
        _create_session(sessions_dir, "render-4", file_changes=changes)
        output = dashboard.render("render-4")
        assert "File Changes" in output
        assert "new.py" in output

    def test_render_actions_bar(self, dashboard: MorningDashboard, sessions_dir: Path):
        _create_session(sessions_dir, "render-5")
        output = dashboard.render("render-5")
        assert "[a]pprove" in output
        assert "[r]eject" in output
        assert "[q]uit" in output

    def test_render_data_directly(self, dashboard: MorningDashboard):
        data = DashboardData(
            session_id="direct-1",
            role_name="coder",
            goal="Test direct render",
            status="completed",
            duration_str="1h 30m",
            cost_str="$0.10",
            sections=[
                DashboardSection(title="Test", content=["hello"], priority=100),
            ],
        )
        output = dashboard.render_data(data)
        assert "ORION" in output
        assert "Morning Dashboard" in output
        assert "Test" in output
        assert "hello" in output


# ---------------------------------------------------------------------------
# MorningDashboard.check_pending_reviews
# ---------------------------------------------------------------------------


class TestPendingReviews:
    def test_no_sessions(self, dashboard: MorningDashboard):
        assert dashboard.check_pending_reviews() == []

    def test_completed_unreviewed(self, dashboard: MorningDashboard, sessions_dir: Path):
        _create_session(sessions_dir, "unreviewed-1", goal="Needs review")
        pending = dashboard.check_pending_reviews()
        assert len(pending) == 1
        assert pending[0]["session_id"] == "unreviewed-1"

    def test_reviewed_excluded(self, dashboard: MorningDashboard, sessions_dir: Path):
        _create_session(sessions_dir, "reviewed-1")
        (sessions_dir / "reviewed-1" / ".reviewed").write_text("done")
        pending = dashboard.check_pending_reviews()
        assert len(pending) == 0

    def test_running_excluded(self, dashboard: MorningDashboard, sessions_dir: Path):
        _create_session(sessions_dir, "running-1", status=SessionStatus.RUNNING)
        pending = dashboard.check_pending_reviews()
        assert len(pending) == 0


# ---------------------------------------------------------------------------
# MorningDashboard.get_startup_message
# ---------------------------------------------------------------------------


class TestStartupMessage:
    def test_no_pending(self, dashboard: MorningDashboard):
        assert dashboard.get_startup_message() is None

    def test_single_pending(self, dashboard: MorningDashboard, sessions_dir: Path):
        _create_session(sessions_dir, "startup-1", goal="Build auth")
        msg = dashboard.get_startup_message()
        assert msg is not None
        assert "orion review" in msg

    def test_multiple_pending(self, dashboard: MorningDashboard, sessions_dir: Path):
        _create_session(sessions_dir, "multi-1", goal="Task A")
        _create_session(sessions_dir, "multi-2", goal="Task B")
        msg = dashboard.get_startup_message()
        assert msg is not None
        assert "2 sessions" in msg
        assert "orion sessions" in msg
