# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA Daemon (ARA-001 §11)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from orion.ara.daemon import ARADaemon, DaemonControl, DaemonStatus
from orion.ara.goal_engine import Task, TaskDAG
from orion.ara.role_profile import RoleProfile
from orion.ara.session import SessionState, SessionStatus


def _make_session(**kwargs) -> SessionState:
    return SessionState(
        session_id="daemon-test",
        role_name="test",
        goal="Test daemon",
        **kwargs,
    )


def _make_role(**kwargs) -> RoleProfile:
    return RoleProfile(name="test-role", scope="coding", **kwargs)


def _make_dag(count: int = 3) -> TaskDAG:
    tasks = []
    for i in range(count):
        deps = [f"t{i - 1}"] if i > 0 else []
        tasks.append(Task(
            task_id=f"t{i}", title=f"Task {i}",
            description="", action_type="write_files",
            dependencies=deps,
        ))
    return TaskDAG(goal="Test", tasks=tasks)


async def _success_executor(task):
    return {"success": True, "output": f"Done: {task.title}", "confidence": 0.9}


class TestDaemonControl:
    def test_write_and_read_pid(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        ctrl.write_pid(12345)
        assert ctrl.read_pid() == 12345

    def test_read_pid_missing(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        assert ctrl.read_pid() is None

    def test_clear_pid(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        ctrl.write_pid(12345)
        ctrl.clear_pid()
        assert ctrl.read_pid() is None

    def test_send_and_read_command(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        ctrl.send_command("pause")
        cmd = ctrl.read_command()
        assert cmd == "pause"

    def test_read_command_consumes(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        ctrl.send_command("cancel")
        ctrl.read_command()
        assert ctrl.read_command() is None

    def test_read_command_empty(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        assert ctrl.read_command() is None

    def test_write_and_read_status(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        status = DaemonStatus(
            running=True,
            pid=999,
            session_id="s1",
            role_name="coder",
            goal="build",
            session_status="running",
        )
        ctrl.write_status(status)
        read_back = ctrl.read_status()
        assert read_back.running is True
        assert read_back.session_id == "s1"

    def test_read_status_missing(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        status = ctrl.read_status()
        assert status.running is False

    def test_is_daemon_alive_self(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        ctrl.write_pid(os.getpid())
        assert ctrl.is_daemon_alive() is True

    def test_is_daemon_alive_dead(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        ctrl.write_pid(99999999)
        assert ctrl.is_daemon_alive() is False

    def test_cleanup(self, tmp_path: Path):
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        ctrl.write_pid(123)
        ctrl.send_command("test")
        ctrl.write_status(DaemonStatus(running=True))
        ctrl.cleanup()
        assert ctrl.read_pid() is None
        assert ctrl.read_command() is None


class TestDaemonStatus:
    def test_to_dict(self):
        status = DaemonStatus(
            running=True, pid=123, session_id="s1",
            tasks_completed=5, tasks_total=10,
        )
        d = status.to_dict()
        assert d["running"] is True
        assert d["tasks_completed"] == 5

    def test_summary_running(self):
        status = DaemonStatus(
            running=True, session_id="s1", role_name="coder",
            goal="test", session_status="running",
            tasks_completed=2, tasks_total=5,
        )
        s = status.summary()
        assert "s1" in s
        assert "2/5" in s

    def test_summary_not_running(self):
        status = DaemonStatus(running=False)
        assert "not running" in status.summary()


class TestARADaemon:
    def test_runs_to_completion(self, tmp_path: Path):
        session = _make_session()
        role = _make_role()
        dag = _make_dag(3)
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")

        daemon = ARADaemon(
            session=session, role=role, dag=dag,
            control=ctrl, task_executor=_success_executor,
            checkpoint_dir=tmp_path / "checkpoints",
        )
        asyncio.run(daemon.run())
        assert session.status == SessionStatus.COMPLETED
        assert session.progress.completed_tasks == 3

    def test_writes_status(self, tmp_path: Path):
        session = _make_session()
        role = _make_role()
        dag = _make_dag(1)
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")

        daemon = ARADaemon(
            session=session, role=role, dag=dag,
            control=ctrl, task_executor=_success_executor,
            checkpoint_dir=tmp_path / "checkpoints",
        )
        asyncio.run(daemon.run())
        status = ctrl.read_status()
        assert status.session_id == "daemon-test"

    def test_handles_executor_failure(self, tmp_path: Path):
        async def failing_executor(task):
            return {"success": False, "error": "boom"}

        session = _make_session()
        role = _make_role()
        # 6 independent tasks to trigger error streak
        tasks = [
            Task(task_id=f"t{i}", title=f"T{i}", description="", action_type="write_files")
            for i in range(6)
        ]
        dag = TaskDAG(goal="fail", tasks=tasks)
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")

        daemon = ARADaemon(
            session=session, role=role, dag=dag,
            control=ctrl, task_executor=failing_executor,
            checkpoint_dir=tmp_path / "checkpoints",
        )
        asyncio.run(daemon.run())
        assert session.status == SessionStatus.FAILED

    def test_clears_pid_on_exit(self, tmp_path: Path):
        session = _make_session()
        role = _make_role()
        dag = _make_dag(1)
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")

        daemon = ARADaemon(
            session=session, role=role, dag=dag,
            control=ctrl, task_executor=_success_executor,
            checkpoint_dir=tmp_path / "checkpoints",
        )
        asyncio.run(daemon.run())
        assert ctrl.read_pid() is None
