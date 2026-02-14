# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA Session State (ARA-001 §6)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from orion.ara.session import (
    InvalidTransitionError,
    SessionState,
    SessionStatus,
    TaskProgress,
)


@pytest.fixture
def session() -> SessionState:
    return SessionState(
        session_id="test-001",
        role_name="night-coder",
        goal="Add unit tests for auth module",
        workspace_path="/tmp/workspace",
        max_cost_usd=5.0,
        max_duration_hours=8.0,
    )


class TestSessionCreation:
    def test_default_state(self, session: SessionState):
        assert session.status == SessionStatus.CREATED
        assert session.session_id == "test-001"
        assert session.is_terminal is False
        assert session.is_active is False

    def test_auto_generated_id(self):
        s = SessionState(role_name="test", goal="test")
        assert len(s.session_id) == 12

    def test_serialization_roundtrip(self, session: SessionState):
        data = session.to_dict()
        restored = SessionState.from_dict(data)
        assert restored.session_id == session.session_id
        assert restored.role_name == session.role_name
        assert restored.goal == session.goal
        assert restored.status == session.status


class TestStateTransitions:
    def test_created_to_running(self, session: SessionState):
        session.transition(SessionStatus.RUNNING)
        assert session.status == SessionStatus.RUNNING
        assert session.started_at is not None

    def test_running_to_paused(self, session: SessionState):
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.PAUSED)
        assert session.status == SessionStatus.PAUSED

    def test_paused_to_running(self, session: SessionState):
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.PAUSED)
        session.transition(SessionStatus.RUNNING)
        assert session.status == SessionStatus.RUNNING

    def test_running_to_completed(self, session: SessionState):
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.COMPLETED)
        assert session.is_terminal is True
        assert session.completed_at is not None

    def test_running_to_failed(self, session: SessionState):
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.FAILED)
        assert session.is_terminal is True

    def test_running_to_cancelled(self, session: SessionState):
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.CANCELLED)
        assert session.is_terminal is True

    def test_invalid_transition_raises(self, session: SessionState):
        with pytest.raises(InvalidTransitionError):
            session.transition(SessionStatus.COMPLETED)

    def test_terminal_cannot_transition(self, session: SessionState):
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.COMPLETED)
        with pytest.raises(InvalidTransitionError):
            session.transition(SessionStatus.RUNNING)


class TestHeartbeat:
    def test_heartbeat_updates_time(self, session: SessionState):
        session.transition(SessionStatus.RUNNING)
        old_hb = session.last_heartbeat
        time.sleep(0.01)
        session.heartbeat()
        assert session.last_heartbeat > old_hb

    def test_heartbeat_tracks_elapsed(self, session: SessionState):
        session.transition(SessionStatus.RUNNING)
        time.sleep(0.05)
        session.heartbeat()
        assert session.elapsed_seconds > 0


class TestStopConditions:
    def test_no_stop_initially(self, session: SessionState):
        assert session.check_stop_conditions() is None

    def test_time_limit(self, session: SessionState):
        session.elapsed_seconds = 8 * 3600 + 1
        reason = session.check_stop_conditions()
        assert reason is not None
        assert "time_limit" in reason

    def test_cost_limit(self, session: SessionState):
        session.cost_usd = 5.01
        reason = session.check_stop_conditions()
        assert reason is not None
        assert "cost_limit" in reason

    def test_goal_complete(self, session: SessionState):
        session.progress = TaskProgress(total_tasks=3, completed_tasks=3)
        reason = session.check_stop_conditions()
        assert reason is not None
        assert "goal_complete" in reason


class TestPersistence:
    def test_save_and_load(self, session: SessionState, tmp_path: Path):
        session.save(sessions_dir=tmp_path)
        loaded = SessionState.load("test-001", sessions_dir=tmp_path)
        assert loaded.session_id == "test-001"
        assert loaded.role_name == "night-coder"

    def test_load_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            SessionState.load("nonexistent", sessions_dir=tmp_path)


class TestTaskProgress:
    def test_completion_pct(self):
        p = TaskProgress(total_tasks=10, completed_tasks=5)
        assert p.completion_pct == 50.0

    def test_pending(self):
        p = TaskProgress(total_tasks=10, completed_tasks=3, failed_tasks=2, skipped_tasks=1)
        assert p.pending_tasks == 4

    def test_zero_tasks(self):
        p = TaskProgress()
        assert p.completion_pct == 0.0

    def test_roundtrip(self):
        p = TaskProgress(total_tasks=5, completed_tasks=2, failed_tasks=1)
        restored = TaskProgress.from_dict(p.to_dict())
        assert restored.total_tasks == 5
        assert restored.completed_tasks == 2
