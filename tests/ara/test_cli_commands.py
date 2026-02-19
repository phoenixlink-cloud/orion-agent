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
    _resolve_workspace,
    _scan_workspace,
    cmd_cancel,
    cmd_pause,
    cmd_resume,
    cmd_review,
    cmd_status,
    cmd_work,
    cmd_workspace_clear,
    cmd_workspace_list,
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
    def test_creates_session(self, roles_dir: Path, control: DaemonControl, tmp_path: Path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        result = cmd_work(
            role_name="test-coder",
            goal="Add logging",
            workspace_path=str(ws),
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


# ═══════════════════════════════════════════════════════════════════════
# Workspace decision feature tests
# ═══════════════════════════════════════════════════════════════════════


class TestScanWorkspace:
    def test_empty_dir(self, tmp_path: Path):
        assert _scan_workspace(tmp_path) == []

    def test_nonexistent_dir(self, tmp_path: Path):
        assert _scan_workspace(tmp_path / "nope") == []

    def test_finds_files(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("print(1)")
        (tmp_path / "README.md").write_text("# hi")
        files = _scan_workspace(tmp_path)
        assert "main.py" in files
        assert "README.md" in files

    def test_skips_hidden_and_git(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("x")
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.py").write_text("x = 1")
        files = _scan_workspace(tmp_path)
        assert "visible.py" in files
        assert not any(".git" in f for f in files)

    def test_skips_node_modules(self, tmp_path: Path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}")
        (tmp_path / "app.js").write_text("const x = 1")
        files = _scan_workspace(tmp_path)
        assert "app.js" in files
        assert not any("node_modules" in f for f in files)

    def test_caps_at_50(self, tmp_path: Path):
        for i in range(60):
            (tmp_path / f"file_{i:03d}.txt").write_text(f"{i}")
        files = _scan_workspace(tmp_path)
        assert len(files) == 50


class TestResolveWorkspace:
    def test_fallback_to_cwd(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # No settings.json → fall back to cwd
        ws = _resolve_workspace()
        assert ws == Path.cwd()

    def test_reads_from_settings(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        orion_dir = tmp_path / ".orion"
        orion_dir.mkdir()
        settings = {"default_workspace": str(tmp_path / "my_workspace")}
        (orion_dir / "settings.json").write_text(json.dumps(settings))
        ws = _resolve_workspace()
        assert ws == tmp_path / "my_workspace"

    def test_reads_workspace_key_fallback(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        orion_dir = tmp_path / ".orion"
        orion_dir.mkdir()
        settings = {"workspace": str(tmp_path / "alt")}
        (orion_dir / "settings.json").write_text(json.dumps(settings))
        ws = _resolve_workspace()
        assert ws == tmp_path / "alt"


class TestCmdWorkspaceList:
    def test_empty_workspace(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        orion_dir = tmp_path / ".orion"
        orion_dir.mkdir()
        ws = tmp_path / "ws"
        ws.mkdir()
        (orion_dir / "settings.json").write_text(json.dumps({"default_workspace": str(ws)}))
        result = cmd_workspace_list()
        assert result.success is True
        assert result.data["files"] == []

    def test_lists_files(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        orion_dir = tmp_path / ".orion"
        orion_dir.mkdir()
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "index.py").write_text("x = 1")
        (ws / "lib.py").write_text("y = 2")
        (orion_dir / "settings.json").write_text(json.dumps({"default_workspace": str(ws)}))
        result = cmd_workspace_list()
        assert result.success is True
        assert len(result.data["files"]) == 2
        assert "index.py" in result.data["files"]

    def test_nonexistent_workspace(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        orion_dir = tmp_path / ".orion"
        orion_dir.mkdir()
        (orion_dir / "settings.json").write_text(
            json.dumps({"default_workspace": str(tmp_path / "nonexistent")})
        )
        result = cmd_workspace_list()
        assert result.success is True
        assert result.data["files"] == []


class TestCmdWorkspaceClear:
    def test_clears_files(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        orion_dir = tmp_path / ".orion"
        orion_dir.mkdir()
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "a.py").write_text("a")
        (ws / "b.py").write_text("b")
        (orion_dir / "settings.json").write_text(json.dumps({"default_workspace": str(ws)}))
        result = cmd_workspace_clear()
        assert result.success is True
        assert result.data["removed"] == 2
        assert not (ws / "a.py").exists()
        assert not (ws / "b.py").exists()

    def test_preserves_hidden_dirs(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        orion_dir = tmp_path / ".orion"
        orion_dir.mkdir()
        ws = tmp_path / "ws"
        ws.mkdir()
        git_dir = ws / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("gitconfig")
        (ws / "code.py").write_text("x = 1")
        (orion_dir / "settings.json").write_text(json.dumps({"default_workspace": str(ws)}))
        result = cmd_workspace_clear()
        assert result.data["removed"] == 1
        assert (git_dir / "config").exists()

    def test_nonexistent_workspace(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        orion_dir = tmp_path / ".orion"
        orion_dir.mkdir()
        (orion_dir / "settings.json").write_text(
            json.dumps({"default_workspace": str(tmp_path / "gone")})
        )
        result = cmd_workspace_clear()
        assert result.success is True
        assert result.data["removed"] == 0


class TestCmdWorkProjectMode:
    """Tests for cmd_work project_mode parameter (auto / new / continue)."""

    def test_auto_returns_needs_decision_when_files_exist(
        self, roles_dir: Path, control: DaemonControl, tmp_path: Path
    ):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "existing.py").write_text("old code")
        result = cmd_work(
            role_name="test-coder",
            goal="Refactor",
            workspace_path=str(ws),
            roles_dir=roles_dir,
            control=control,
            project_mode="auto",
        )
        assert result.success is False
        assert result.data is not None
        assert result.data["needs_decision"] is True
        assert "existing.py" in result.data["workspace_files"]

    def test_auto_proceeds_on_empty_workspace(
        self, roles_dir: Path, control: DaemonControl, tmp_path: Path
    ):
        ws = tmp_path / "workspace"
        ws.mkdir()
        result = cmd_work(
            role_name="test-coder",
            goal="Build app",
            workspace_path=str(ws),
            roles_dir=roles_dir,
            control=control,
            project_mode="auto",
        )
        assert result.success is True

    def test_new_skips_decision(self, roles_dir: Path, control: DaemonControl, tmp_path: Path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "old.py").write_text("old")
        result = cmd_work(
            role_name="test-coder",
            goal="Start fresh",
            workspace_path=str(ws),
            roles_dir=roles_dir,
            control=control,
            project_mode="new",
        )
        assert result.success is True
        assert result.data.get("needs_decision") is not True

    def test_continue_skips_decision(self, roles_dir: Path, control: DaemonControl, tmp_path: Path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "app.py").write_text("existing app")
        result = cmd_work(
            role_name="test-coder",
            goal="Add feature",
            workspace_path=str(ws),
            roles_dir=roles_dir,
            control=control,
            project_mode="continue",
        )
        assert result.success is True
        assert result.data["project_mode"] == "continue"
