# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA Checkpoint Manager (ARA-001 §10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.ara.checkpoint import CheckpointInfo, CheckpointManager


@pytest.fixture
def cp_manager(tmp_path: Path) -> CheckpointManager:
    return CheckpointManager(
        session_id="test-session",
        checkpoints_dir=tmp_path / "checkpoints",
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    sb = tmp_path / "sandbox"
    sb.mkdir()
    (sb / "main.py").write_text("print('hello')\n")
    (sb / "utils.py").write_text("x = 1\n")
    return sb


class TestCheckpointCreation:
    def test_create_checkpoint(self, cp_manager: CheckpointManager):
        info = cp_manager.create(
            session_state={"status": "running", "elapsed": 100},
            dag_state={"tasks": [], "completed_count": 2},
            description="after task 2",
        )
        assert info.checkpoint_id == "cp-0000"
        assert info.session_id == "test-session"
        assert info.description == "after task 2"

    def test_increments_counter(self, cp_manager: CheckpointManager):
        cp_manager.create({"s": 1}, {"d": 1})
        cp_manager.create({"s": 2}, {"d": 2})
        info = cp_manager.create({"s": 3}, {"d": 3})
        assert info.checkpoint_id == "cp-0002"

    def test_saves_session_and_dag(self, cp_manager: CheckpointManager):
        info = cp_manager.create(
            session_state={"status": "running"},
            dag_state={"tasks": [{"id": "t1"}]},
        )
        cp_dir = info.directory
        assert (cp_dir / "session.json").exists()
        assert (cp_dir / "dag.json").exists()
        assert (cp_dir / "checkpoint.json").exists()

    def test_copies_sandbox(self, cp_manager: CheckpointManager, sandbox: Path):
        info = cp_manager.create(
            session_state={"s": 1},
            dag_state={"d": 1},
            sandbox_path=sandbox,
        )
        ws = info.directory / "workspace"
        assert ws.exists()
        assert (ws / "main.py").exists()
        assert (ws / "utils.py").exists()


class TestCheckpointListing:
    def test_list_empty(self, cp_manager: CheckpointManager):
        assert cp_manager.list_checkpoints() == []
        assert cp_manager.checkpoint_count == 0

    def test_list_checkpoints(self, cp_manager: CheckpointManager):
        cp_manager.create({"s": 1}, {"d": 1})
        cp_manager.create({"s": 2}, {"d": 2})
        cps = cp_manager.list_checkpoints()
        assert len(cps) == 2
        assert cps[0].checkpoint_id == "cp-0000"
        assert cps[1].checkpoint_id == "cp-0001"

    def test_get_latest(self, cp_manager: CheckpointManager):
        cp_manager.create({"s": 1}, {"d": 1})
        cp_manager.create({"s": 2}, {"d": 2}, description="latest")
        latest = cp_manager.get_latest()
        assert latest is not None
        assert latest.checkpoint_id == "cp-0001"

    def test_get_latest_empty(self, cp_manager: CheckpointManager):
        assert cp_manager.get_latest() is None


class TestRollback:
    def test_rollback_restores_state(self, cp_manager: CheckpointManager):
        cp_manager.create(
            session_state={"status": "running", "step": 1},
            dag_state={"tasks": ["t1"]},
        )
        cp_manager.create(
            session_state={"status": "running", "step": 2},
            dag_state={"tasks": ["t1", "t2"]},
        )
        session_data, dag_data, ws = cp_manager.rollback("cp-0000")
        assert session_data["step"] == 1
        assert len(dag_data["tasks"]) == 1

    def test_rollback_with_workspace(self, cp_manager: CheckpointManager, sandbox: Path):
        cp_manager.create({"s": 1}, {"d": 1}, sandbox_path=sandbox)
        _, _, ws = cp_manager.rollback("cp-0000")
        assert ws is not None
        assert (ws / "main.py").exists()

    def test_rollback_nonexistent_raises(self, cp_manager: CheckpointManager):
        with pytest.raises(FileNotFoundError):
            cp_manager.rollback("cp-9999")


class TestDeletion:
    def test_delete_checkpoint(self, cp_manager: CheckpointManager):
        cp_manager.create({"s": 1}, {"d": 1})
        assert cp_manager.delete_checkpoint("cp-0000") is True
        assert cp_manager.checkpoint_count == 0

    def test_delete_nonexistent(self, cp_manager: CheckpointManager):
        assert cp_manager.delete_checkpoint("cp-9999") is False


class TestCheckpointInfo:
    def test_to_dict(self):
        info = CheckpointInfo(
            checkpoint_id="cp-0000",
            session_id="s1",
            created_at=1000.0,
            task_index=0,
            tasks_completed=2,
            description="test",
        )
        d = info.to_dict()
        assert d["checkpoint_id"] == "cp-0000"
        assert d["tasks_completed"] == 2

    def test_from_dict(self):
        data = {
            "checkpoint_id": "cp-0001",
            "session_id": "s1",
            "created_at": 2000.0,
            "task_index": 1,
            "tasks_completed": 5,
        }
        info = CheckpointInfo.from_dict(data)
        assert info.checkpoint_id == "cp-0001"
        assert info.tasks_completed == 5
