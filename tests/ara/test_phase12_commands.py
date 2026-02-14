# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Phase 12: CLI Commands + Setup Wizard."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orion.ara import cli_commands
from orion.ara.cli_commands import (
    cmd_auth_switch,
    cmd_plan_review,
    cmd_rollback,
    cmd_sessions,
    cmd_sessions_cleanup,
    cmd_settings_ara,
    cmd_setup,
)
from orion.ara.daemon import DaemonControl, DaemonStatus
from orion.ara.session import SessionState, SessionStatus


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sessions"
    d.mkdir()
    return d


def _make_session(
    sessions_dir: Path,
    session_id: str,
    role: str = "test-role",
    goal: str = "Test goal",
    status: SessionStatus = SessionStatus.COMPLETED,
    cost: float = 0.5,
) -> SessionState:
    """Helper to create a persisted session."""
    session = SessionState(
        session_id=session_id,
        role_name=role,
        goal=goal,
        workspace_path=str(sessions_dir.parent),
        status=status,
        cost_usd=cost,
        max_cost_usd=10.0,
        max_duration_hours=8.0,
    )
    session.save(sessions_dir=sessions_dir)
    return session


def _mock_control(session_id: str = "test-sess") -> DaemonControl:
    ctrl = MagicMock(spec=DaemonControl)
    ctrl.is_daemon_alive.return_value = False
    status = DaemonStatus(
        running=False,
        pid=None,
        session_id=session_id,
        session_status="completed",
    )
    ctrl.read_status.return_value = status
    return ctrl


# ---------------------------------------------------------------------------
# cmd_sessions
# ---------------------------------------------------------------------------


class TestCmdSessions:
    def test_no_sessions(self, sessions_dir: Path):
        result = cmd_sessions(sessions_dir=sessions_dir)
        assert result.success
        assert result.data["sessions"] == []

    def test_lists_sessions(self, sessions_dir: Path):
        _make_session(sessions_dir, "s1", goal="First task", status=SessionStatus.COMPLETED)
        _make_session(sessions_dir, "s2", goal="Second task", status=SessionStatus.RUNNING)
        result = cmd_sessions(sessions_dir=sessions_dir)
        assert result.success
        assert len(result.data["sessions"]) == 2
        ids = [s["session_id"] for s in result.data["sessions"]]
        assert "s1" in ids
        assert "s2" in ids

    def test_shows_status_and_cost(self, sessions_dir: Path):
        _make_session(sessions_dir, "s3", cost=1.2345, status=SessionStatus.FAILED)
        result = cmd_sessions(sessions_dir=sessions_dir)
        s = result.data["sessions"][0]
        assert s["status"] == "failed"
        assert s["cost_usd"] == 1.2345

    def test_nonexistent_dir(self, tmp_path: Path):
        result = cmd_sessions(sessions_dir=tmp_path / "nope")
        assert result.success
        assert result.data["sessions"] == []


# ---------------------------------------------------------------------------
# cmd_sessions_cleanup
# ---------------------------------------------------------------------------


class TestCmdSessionsCleanup:
    def test_cleanup_empty(self, sessions_dir: Path):
        result = cmd_sessions_cleanup(sessions_dir=sessions_dir)
        assert result.success

    def test_cleanup_old_sessions(self, sessions_dir: Path):
        _make_session(sessions_dir, "old-1", status=SessionStatus.COMPLETED)
        # Make the session file appear old
        state_file = sessions_dir / "old-1" / "session.json"
        import os
        old_time = time.time() - (31 * 86400)
        os.utime(state_file, (old_time, old_time))

        result = cmd_sessions_cleanup(max_age_days=30, sessions_dir=sessions_dir)
        assert result.success
        assert result.data["cleaned"] == 1
        assert not (sessions_dir / "old-1").exists()

    def test_keeps_recent_sessions(self, sessions_dir: Path):
        _make_session(sessions_dir, "recent-1", status=SessionStatus.COMPLETED)
        result = cmd_sessions_cleanup(max_age_days=30, sessions_dir=sessions_dir)
        assert result.data["cleaned"] == 0
        assert (sessions_dir / "recent-1").exists()

    def test_prunes_checkpoints(self, sessions_dir: Path):
        _make_session(sessions_dir, "cp-test", status=SessionStatus.RUNNING)
        cp_dir = sessions_dir / "cp-test" / "checkpoints"
        cp_dir.mkdir()
        for i in range(6):
            (cp_dir / f"cp-{i:03d}").write_text(f"checkpoint {i}")

        result = cmd_sessions_cleanup(sessions_dir=sessions_dir)
        assert result.data["pruned_checkpoints"] == 3
        remaining = list(cp_dir.iterdir())
        assert len(remaining) == 3


# ---------------------------------------------------------------------------
# cmd_rollback
# ---------------------------------------------------------------------------


class TestCmdRollback:
    def test_rollback_no_session(self):
        ctrl = _mock_control("")
        result = cmd_rollback("cp-001", control=ctrl)
        assert not result.success

    def test_rollback_session_not_found(self, sessions_dir: Path):
        ctrl = _mock_control("nonexistent")
        result = cmd_rollback(
            "cp-001", session_id="nonexistent",
            sessions_dir=sessions_dir, control=ctrl,
        )
        assert not result.success


# ---------------------------------------------------------------------------
# cmd_plan_review
# ---------------------------------------------------------------------------


class TestCmdPlanReview:
    def test_no_session(self):
        ctrl = _mock_control("")
        result = cmd_plan_review(control=ctrl)
        assert not result.success

    def test_no_plan_file(self, sessions_dir: Path):
        _make_session(sessions_dir, "no-plan")
        result = cmd_plan_review(session_id="no-plan", sessions_dir=sessions_dir, control=_mock_control())
        assert not result.success
        assert "No plan found" in result.message

    def test_shows_plan(self, sessions_dir: Path):
        _make_session(sessions_dir, "with-plan")
        plan = {
            "tasks": [
                {"name": "Write auth module", "status": "completed", "depends_on": []},
                {"name": "Write tests", "status": "pending", "depends_on": ["Write auth module"]},
                {"name": "Update docs", "status": "pending", "depends_on": []},
            ]
        }
        (sessions_dir / "with-plan" / "plan.json").write_text(json.dumps(plan))

        result = cmd_plan_review(session_id="with-plan", sessions_dir=sessions_dir, control=_mock_control())
        assert result.success
        assert "Write auth module" in result.message
        assert "Write tests" in result.message
        assert "Total tasks: 3" in result.message

    def test_empty_plan(self, sessions_dir: Path):
        _make_session(sessions_dir, "empty-plan")
        (sessions_dir / "empty-plan" / "plan.json").write_text(json.dumps({"tasks": []}))
        result = cmd_plan_review(session_id="empty-plan", sessions_dir=sessions_dir, control=_mock_control())
        assert result.success
        assert "empty" in result.message.lower()


# ---------------------------------------------------------------------------
# cmd_settings_ara
# ---------------------------------------------------------------------------


class TestCmdSettingsAra:
    def test_view_defaults(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        result = cmd_settings_ara(settings_path=path)
        assert result.success
        assert "default_role" in result.data
        assert "notifications" in result.data
        assert "session_defaults" in result.data
        assert "replan_interval_tasks" in result.data
        assert path.exists()

    def test_update_settings(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        cmd_settings_ara(settings_path=path)  # init

        result = cmd_settings_ara(
            settings={"default_role": "night-coder", "replan_interval_tasks": 10},
            settings_path=path,
        )
        assert result.success
        assert result.data["default_role"] == "night-coder"
        assert result.data["replan_interval_tasks"] == 10

    def test_update_nested(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        cmd_settings_ara(settings_path=path)

        result = cmd_settings_ara(
            settings={"notifications": {"email_enabled": True, "email_recipient": "me@test.com"}},
            settings_path=path,
        )
        assert result.data["notifications"]["email_enabled"] is True
        assert result.data["notifications"]["email_recipient"] == "me@test.com"
        # Other notification defaults preserved
        assert "desktop_enabled" in result.data["notifications"]

    def test_persistence(self, tmp_path: Path):
        path = tmp_path / "settings.json"
        cmd_settings_ara(settings={"default_role": "custom"}, settings_path=path)

        result = cmd_settings_ara(settings_path=path)
        assert result.data["default_role"] == "custom"


# ---------------------------------------------------------------------------
# cmd_auth_switch
# ---------------------------------------------------------------------------


class TestCmdAuthSwitch:
    def test_invalid_method(self):
        result = cmd_auth_switch("biometric", "1234")
        assert not result.success
        assert "Invalid" in result.message

    def test_bad_credential(self):
        auth = MagicMock()
        auth.verify.return_value = False
        result = cmd_auth_switch("totp", "wrong", authenticator=auth)
        assert not result.success
        assert "verification failed" in result.message

    def test_successful_switch(self):
        auth = MagicMock()
        auth.verify.return_value = True
        result = cmd_auth_switch("totp", "correct-pin", authenticator=auth)
        assert result.success
        assert result.data["new_method"] == "totp"
        assert result.data["verified"] is True


# ---------------------------------------------------------------------------
# cmd_setup
# ---------------------------------------------------------------------------


class TestCmdSetup:
    def test_setup_basic(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        roles_dir = tmp_path / "roles"
        roles_dir.mkdir()
        empty_starter = tmp_path / "no_starters"
        empty_starter.mkdir()
        monkeypatch.setattr(cli_commands, "STARTER_ROLES_DIR", empty_starter)

        result = cmd_setup(roles_dir=roles_dir, skip_docker_check=True)
        # Setup may not be fully "ok" without roles/auth, but should still return data
        assert "checks" in result.data
        assert "dry_run_scenarios" in result.data
        assert len(result.data["dry_run_scenarios"]) == 6

    def test_setup_checks_docker(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        roles_dir = tmp_path / "roles"
        roles_dir.mkdir()
        empty_starter = tmp_path / "no_starters"
        empty_starter.mkdir()
        monkeypatch.setattr(cli_commands, "STARTER_ROLES_DIR", empty_starter)

        result = cmd_setup(roles_dir=roles_dir, skip_docker_check=False)
        docker_check = next(c for c in result.data["checks"] if c["name"] == "Docker")
        # Docker may or may not be installed in test env
        assert docker_check["status"] in ("ok", "missing")

    def test_setup_reports_aegis(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        roles_dir = tmp_path / "roles"
        roles_dir.mkdir()
        empty_starter = tmp_path / "no_starters"
        empty_starter.mkdir()
        monkeypatch.setattr(cli_commands, "STARTER_ROLES_DIR", empty_starter)

        result = cmd_setup(roles_dir=roles_dir, skip_docker_check=True)
        aegis_check = next(c for c in result.data["checks"] if c["name"] == "AEGIS governance")
        assert aegis_check["status"] == "ok"

    def test_setup_with_roles(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from orion.ara.role_profile import RoleProfile, save_role

        roles_dir = tmp_path / "roles"
        roles_dir.mkdir()
        empty_starter = tmp_path / "no_starters"
        empty_starter.mkdir()
        monkeypatch.setattr(cli_commands, "STARTER_ROLES_DIR", empty_starter)

        role = RoleProfile(name="test-role", scope="coding")
        save_role(role, roles_dir / "test-role.yaml")

        result = cmd_setup(roles_dir=roles_dir, skip_docker_check=True)
        assert "test-role" in result.data["roles_available"]
        roles_check = next(c for c in result.data["checks"] if c["name"] == "Roles")
        assert roles_check["status"] == "ok"
