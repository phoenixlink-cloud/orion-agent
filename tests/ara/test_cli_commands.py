# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA CLI Commands (ARA-001 §11)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from orion.ara.auth import AuthStore, RoleAuthenticator
from orion.ara.cli_commands import (
    CommandResult,
    cmd_cancel,
    cmd_pause,
    cmd_resume,
    cmd_review,
    cmd_status,
    cmd_work,
    list_available_roles,
)
from orion.ara.daemon import DaemonControl, DaemonStatus
from orion.ara.role_profile import RoleProfile, save_role
from orion.ara.session import SessionState, SessionStatus


@pytest.fixture
def roles_dir(tmp_path: Path) -> Path:
    d = tmp_path / "roles"
    d.mkdir()
    role = RoleProfile(name="test-coder", scope="coding", auth_method="pin")
    save_role(role, d / "test-coder.yaml")
    return d


@pytest.fixture
def control(tmp_path: Path) -> DaemonControl:
    return DaemonControl(state_dir=tmp_path / "daemon")


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sessions"
    d.mkdir()
    return d


class TestCmdWork:
    def test_creates_session(self, roles_dir: Path, control: DaemonControl):
        result = cmd_work(
            role_name="test-coder",
            goal="Add logging",
            roles_dir=roles_dir,
            control=control,
        )
        assert result.success is True
        assert "test-coder" in result.message
        assert result.data["role_name"] == "test-coder"

    def test_rejects_unknown_role(self, roles_dir: Path, control: DaemonControl):
        result = cmd_work(
            role_name="nonexistent",
            goal="test",
            roles_dir=roles_dir,
            control=control,
        )
        assert result.success is False
        assert "not found" in result.message

    def test_rejects_if_session_running(self, roles_dir: Path, control: DaemonControl):
        # Simulate running daemon
        control.write_pid(os.getpid())
        control.write_status(
            DaemonStatus(
                running=True,
                session_id="existing",
                session_status="running",
            )
        )
        result = cmd_work(
            role_name="test-coder",
            goal="test",
            roles_dir=roles_dir,
            control=control,
        )
        assert result.success is False
        assert "already running" in result.message


class TestCmdStatus:
    def test_no_active_session(self, control: DaemonControl):
        result = cmd_status(control=control)
        assert result.success is True
        assert "No active" in result.message

    def test_shows_running_session(self, control: DaemonControl):
        control.write_pid(os.getpid())
        control.write_status(
            DaemonStatus(
                running=True,
                session_id="s1",
                role_name="coder",
                goal="build feature",
                session_status="running",
                tasks_completed=3,
                tasks_total=10,
            )
        )
        result = cmd_status(control=control)
        assert result.success is True
        assert "s1" in result.message


class TestCmdPause:
    def test_sends_pause(self, control: DaemonControl):
        control.write_pid(os.getpid())
        control.write_status(
            DaemonStatus(
                running=True,
                session_id="s1",
                session_status="running",
            )
        )
        result = cmd_pause(control=control)
        assert result.success is True
        assert "Pause" in result.message

    def test_rejects_if_not_running(self, control: DaemonControl):
        result = cmd_pause(control=control)
        assert result.success is False

    def test_rejects_if_not_running_status(self, control: DaemonControl):
        control.write_pid(os.getpid())
        control.write_status(
            DaemonStatus(
                running=True,
                session_id="s1",
                session_status="paused",
            )
        )
        result = cmd_pause(control=control)
        assert result.success is False


class TestCmdResume:
    def test_sends_resume(self, control: DaemonControl):
        control.write_pid(os.getpid())
        control.write_status(
            DaemonStatus(
                running=True,
                session_id="s1",
                session_status="paused",
            )
        )
        result = cmd_resume(control=control)
        assert result.success is True
        assert "Resume" in result.message

    def test_rejects_if_not_paused(self, control: DaemonControl):
        control.write_pid(os.getpid())
        control.write_status(
            DaemonStatus(
                running=True,
                session_id="s1",
                session_status="running",
            )
        )
        result = cmd_resume(control=control)
        assert result.success is False


class TestCmdCancel:
    def test_sends_cancel(self, control: DaemonControl):
        control.write_pid(os.getpid())
        control.write_status(
            DaemonStatus(
                running=True,
                session_id="s1",
                session_status="running",
            )
        )
        result = cmd_cancel(control=control)
        assert result.success is True
        assert "Cancel" in result.message

    def test_rejects_if_no_daemon(self, control: DaemonControl):
        result = cmd_cancel(control=control)
        assert result.success is False


class TestCmdReview:
    def test_review_clean_session(
        self, control: DaemonControl, sessions_dir: Path, roles_dir: Path, tmp_path: Path
    ):
        # Create a completed session with clean sandbox
        session = SessionState(
            session_id="review-test",
            role_name="test-coder",
            goal="test",
            workspace_path=str(tmp_path),
        )
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.COMPLETED)
        session.save(sessions_dir=sessions_dir)

        # Create sandbox dir
        sandbox = sessions_dir / "review-test" / "sandbox"
        sandbox.mkdir(parents=True)
        (sandbox / "clean.py").write_text("x = 1\n")

        # Set up auth
        auth_store = AuthStore(store_path=tmp_path / "auth.json")
        auth_store.set_pin("1234")
        auth = RoleAuthenticator(auth_store=auth_store)

        result = cmd_review(
            session_id="review-test",
            credential="1234",
            control=control,
            authenticator=auth,
            roles_dir=roles_dir,
            sessions_dir=sessions_dir,
        )
        assert result.success is True
        assert "APPROVED" in result.message

    def test_review_blocks_secrets(
        self, control: DaemonControl, sessions_dir: Path, roles_dir: Path, tmp_path: Path
    ):
        session = SessionState(
            session_id="dirty-test",
            role_name="test-coder",
            goal="test",
        )
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.COMPLETED)
        session.save(sessions_dir=sessions_dir)

        sandbox = sessions_dir / "dirty-test" / "sandbox"
        sandbox.mkdir(parents=True)
        (sandbox / "config.py").write_text('KEY = "AKIAIOSFODNN7EXAMPLE"\n')

        auth_store = AuthStore(store_path=tmp_path / "auth.json")
        auth_store.set_pin("1234")
        auth = RoleAuthenticator(auth_store=auth_store)

        result = cmd_review(
            session_id="dirty-test",
            credential="1234",
            control=control,
            authenticator=auth,
            roles_dir=roles_dir,
            sessions_dir=sessions_dir,
        )
        assert result.success is False
        assert "BLOCKED" in result.message

    def test_review_nonexistent_session(self, control: DaemonControl, sessions_dir: Path):
        result = cmd_review(
            session_id="nope",
            control=control,
            sessions_dir=sessions_dir,
        )
        assert result.success is False
        assert "not found" in result.message


class TestListRoles:
    def test_lists_user_roles(self, roles_dir: Path):
        names = list_available_roles(roles_dir)
        assert "test-coder" in names

    def test_includes_starter_roles(self):
        names = list_available_roles(Path("/nonexistent"))
        # Should still find starter templates
        assert len(names) >= 4


class TestCommandResult:
    def test_to_dict(self):
        r = CommandResult(success=True, message="ok", data={"key": "val"})
        d = r.to_dict()
        assert d["success"] is True
        assert d["data"]["key"] == "val"
