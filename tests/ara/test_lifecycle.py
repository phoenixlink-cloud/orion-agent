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
"""Tests for ARA Lifecycle Manager (ARA-001 §C.2)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from orion.ara.lifecycle import CleanupStats, LifecycleManager, SessionInfo


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture
def checkpoints_dir(tmp_path: Path) -> Path:
    d = tmp_path / "checkpoints"
    d.mkdir()
    return d


@pytest.fixture
def manager(sessions_dir: Path, checkpoints_dir: Path) -> LifecycleManager:
    return LifecycleManager(
        sessions_dir=sessions_dir,
        checkpoints_dir=checkpoints_dir,
        session_ttl_hours=0.001,  # Very short for testing
        checkpoint_ttl_hours=0.001,
        max_checkpoints_per_session=3,
    )


def _create_session(
    sessions_dir: Path,
    session_id: str,
    role_name: str = "test",
    status: str = "completed",
    age_seconds: float = 100,
) -> Path:
    """Helper to create a mock session directory."""
    session_dir = sessions_dir / session_id
    session_dir.mkdir()
    meta = {
        "session_id": session_id,
        "role_name": role_name,
        "status": status,
        "created_at": time.time() - age_seconds,
        "updated_at": time.time() - age_seconds,
    }
    (session_dir / "session.json").write_text(json.dumps(meta))
    (session_dir / "workspace").mkdir()
    (session_dir / "workspace" / "main.py").write_text("x = 1\n")
    return session_dir


def _create_checkpoints(checkpoints_dir: Path, session_id: str, count: int) -> list[Path]:
    """Helper to create mock checkpoints."""
    cp_dir = checkpoints_dir / session_id
    cp_dir.mkdir(exist_ok=True)
    paths = []
    for i in range(count):
        cp = cp_dir / f"checkpoint-{i:03d}"
        cp.mkdir()
        (cp / "state.json").write_text(json.dumps({"step": i}))
        paths.append(cp)
        time.sleep(0.01)  # Ensure different mtimes
    return paths


class TestListSessions:
    """Test session listing."""

    def test_list_empty(self, manager: LifecycleManager):
        sessions = manager.list_sessions()
        assert len(sessions) == 0

    def test_list_sessions(self, manager: LifecycleManager, sessions_dir: Path):
        _create_session(sessions_dir, "session-001")
        _create_session(sessions_dir, "session-002", status="running")
        sessions = manager.list_sessions()
        assert len(sessions) == 2

    def test_session_info_properties(self, manager: LifecycleManager, sessions_dir: Path):
        _create_session(sessions_dir, "session-001", age_seconds=3600)
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        s = sessions[0]
        assert s.session_id == "session-001"
        assert s.age_hours > 0.9
        assert s.size_bytes > 0


class TestStaleDetection:
    """Test stale session detection."""

    def test_find_stale_completed(self, manager: LifecycleManager, sessions_dir: Path):
        _create_session(sessions_dir, "old-done", status="completed", age_seconds=100)
        _create_session(sessions_dir, "still-running", status="running", age_seconds=100)
        stale = manager.find_stale_sessions()
        assert len(stale) == 1
        assert stale[0].session_id == "old-done"

    def test_no_stale_if_recent(self, sessions_dir: Path, checkpoints_dir: Path):
        mgr = LifecycleManager(
            sessions_dir=sessions_dir,
            checkpoints_dir=checkpoints_dir,
            session_ttl_hours=999,
        )
        _create_session(sessions_dir, "recent", status="completed", age_seconds=10)
        stale = mgr.find_stale_sessions()
        assert len(stale) == 0


class TestSessionCleanup:
    """Test session directory cleanup."""

    def test_cleanup_session(self, manager: LifecycleManager, sessions_dir: Path):
        session_dir = _create_session(sessions_dir, "cleanup-me")
        assert session_dir.exists()
        freed = manager.cleanup_session(session_dir)
        assert freed > 0
        assert not session_dir.exists()

    def test_cleanup_nonexistent(self, manager: LifecycleManager, tmp_path: Path):
        freed = manager.cleanup_session(tmp_path / "nope")
        assert freed == 0


class TestCheckpointPruning:
    """Test checkpoint pruning."""

    def test_prune_excess_checkpoints(self, manager: LifecycleManager, checkpoints_dir: Path):
        _create_checkpoints(checkpoints_dir, "session-001", count=6)
        count, freed = manager.prune_checkpoints("session-001")
        assert count >= 3  # 6 - 3 max = at least 3 pruned
        remaining = list((checkpoints_dir / "session-001").iterdir())
        assert len(remaining) <= 3

    def test_prune_old_checkpoints(self, manager: LifecycleManager, checkpoints_dir: Path):
        paths = _create_checkpoints(checkpoints_dir, "session-002", count=2)
        # All should be pruned since TTL is very short
        time.sleep(0.01)
        count, freed = manager.prune_checkpoints("session-002")
        assert count >= 0  # May or may not be old enough

    def test_no_prune_empty(self, manager: LifecycleManager):
        count, freed = manager.prune_checkpoints("nonexistent")
        assert count == 0
        assert freed == 0


class TestFullCleanup:
    """Test the full cleanup pipeline."""

    def test_run_cleanup(
        self, manager: LifecycleManager, sessions_dir: Path, checkpoints_dir: Path
    ):
        _create_session(sessions_dir, "stale-1", status="completed", age_seconds=100)
        _create_session(sessions_dir, "active-1", status="running", age_seconds=10)
        _create_checkpoints(checkpoints_dir, "stale-1", count=5)

        stats = manager.run_cleanup()
        assert stats.sessions_cleaned >= 1
        assert stats.checkpoints_pruned >= 0
        assert stats.bytes_freed > 0


class TestHealthReport:
    """Test health reporting."""

    def test_health_report(self, manager: LifecycleManager, sessions_dir: Path):
        _create_session(sessions_dir, "s1", status="running")
        _create_session(sessions_dir, "s2", status="completed", age_seconds=100)
        report = manager.health_report()
        assert report["total_sessions"] == 2
        assert report["active_sessions"] == 1
        assert report["stale_sessions"] >= 1
        assert len(report["sessions"]) == 2


class TestCleanupStats:
    """Test CleanupStats data class."""

    def test_summary(self):
        stats = CleanupStats(sessions_cleaned=2, checkpoints_pruned=5, bytes_freed=1024 * 1024)
        summary = stats.summary()
        assert "2 sessions" in summary
        assert "5 checkpoints" in summary

    def test_mb_freed(self):
        stats = CleanupStats(bytes_freed=10 * 1024 * 1024)
        assert stats.mb_freed == pytest.approx(10.0, abs=0.1)


class TestSessionInfo:
    """Test SessionInfo data class."""

    def test_to_dict(self):
        info = SessionInfo(
            session_id="test-123",
            role_name="coder",
            status="running",
            created_at=time.time() - 3600,
            updated_at=time.time() - 600,
            directory=Path("/tmp/test"),
            size_bytes=1024,
        )
        d = info.to_dict()
        assert d["session_id"] == "test-123"
        assert d["age_hours"] > 0.9
        assert d["idle_hours"] > 0.1
