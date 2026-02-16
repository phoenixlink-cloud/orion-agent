# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA Feedback Store (ARA-001 Appendix C.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.ara.feedback_store import (
    ConfidenceStats,
    FeedbackStore,
    SessionOutcome,
    TaskOutcome,
)


@pytest.fixture
def store(tmp_path: Path) -> FeedbackStore:
    return FeedbackStore(store_dir=tmp_path / "feedback")


class TestTaskOutcome:
    def test_to_dict(self):
        o = TaskOutcome(
            task_id="t1",
            session_id="s1",
            action_type="write_files",
            success=True,
            confidence=0.9,
            duration_seconds=5.5,
        )
        d = o.to_dict()
        assert d["task_id"] == "t1"
        assert d["confidence"] == 0.9

    def test_roundtrip(self):
        o = TaskOutcome(
            task_id="t1",
            session_id="s1",
            action_type="read_files",
            success=False,
            error="timeout",
        )
        restored = TaskOutcome.from_dict(o.to_dict())
        assert restored.task_id == o.task_id
        assert restored.error == "timeout"


class TestSessionOutcome:
    def test_to_dict(self):
        o = SessionOutcome(
            session_id="s1",
            role_name="coder",
            goal="build",
            status="completed",
            tasks_completed=5,
            total_cost_usd=0.05,
        )
        d = o.to_dict()
        assert d["session_id"] == "s1"
        assert d["tasks_completed"] == 5

    def test_roundtrip(self):
        o = SessionOutcome(
            session_id="s1",
            role_name="coder",
            goal="test",
            status="failed",
            promoted=False,
        )
        restored = SessionOutcome.from_dict(o.to_dict())
        assert restored.session_id == o.session_id
        assert restored.promoted is False


class TestRecordAndRetrieve:
    def test_record_task(self, store: FeedbackStore):
        store.record_task(
            TaskOutcome(
                task_id="t1",
                session_id="s1",
                action_type="write_files",
                success=True,
                confidence=0.85,
            )
        )
        assert store.task_count == 1

    def test_record_multiple_tasks(self, store: FeedbackStore):
        for i in range(5):
            store.record_task(
                TaskOutcome(
                    task_id=f"t{i}",
                    session_id="s1",
                    action_type="write_files",
                    success=True,
                    confidence=0.8,
                )
            )
        assert store.task_count == 5

    def test_record_session(self, store: FeedbackStore):
        store.record_session(
            SessionOutcome(
                session_id="s1",
                role_name="coder",
                goal="build",
                status="completed",
                tasks_completed=3,
            )
        )
        assert store.session_count == 1

    def test_filter_tasks_by_session(self, store: FeedbackStore):
        store.record_task(
            TaskOutcome(
                task_id="t1",
                session_id="s1",
                action_type="write_files",
                success=True,
            )
        )
        store.record_task(
            TaskOutcome(
                task_id="t2",
                session_id="s2",
                action_type="read_files",
                success=True,
            )
        )
        results = store.get_task_outcomes(session_id="s1")
        assert len(results) == 1
        assert results[0].session_id == "s1"

    def test_filter_tasks_by_action(self, store: FeedbackStore):
        store.record_task(
            TaskOutcome(
                task_id="t1",
                session_id="s1",
                action_type="write_files",
                success=True,
            )
        )
        store.record_task(
            TaskOutcome(
                task_id="t2",
                session_id="s1",
                action_type="run_tests",
                success=True,
            )
        )
        results = store.get_task_outcomes(action_type="run_tests")
        assert len(results) == 1

    def test_filter_sessions_by_role(self, store: FeedbackStore):
        store.record_session(
            SessionOutcome(
                session_id="s1",
                role_name="coder",
                goal="a",
                status="completed",
            )
        )
        store.record_session(
            SessionOutcome(
                session_id="s2",
                role_name="researcher",
                goal="b",
                status="completed",
            )
        )
        results = store.get_session_outcomes(role_name="coder")
        assert len(results) == 1


class TestUserFeedback:
    def test_add_feedback(self, store: FeedbackStore):
        store.record_session(
            SessionOutcome(
                session_id="s1",
                role_name="coder",
                goal="build",
                status="completed",
            )
        )
        updated = store.add_user_feedback("s1", rating=4, comment="Good work")
        assert updated is True
        sessions = store.get_session_outcomes()
        assert sessions[0].user_rating == 4
        assert sessions[0].user_comment == "Good work"

    def test_feedback_nonexistent_session(self, store: FeedbackStore):
        updated = store.add_user_feedback("nonexistent", rating=3)
        assert updated is False


class TestConfidenceStats:
    def test_stats_by_action_type(self, store: FeedbackStore):
        for i in range(10):
            store.record_task(
                TaskOutcome(
                    task_id=f"t{i}",
                    session_id="s1",
                    action_type="write_files",
                    success=i < 8,
                    confidence=0.8,
                    duration_seconds=5.0,
                )
            )
        stats = store.get_confidence_stats()
        assert len(stats) == 1
        assert stats[0].action_type == "write_files"
        assert stats[0].total_tasks == 10
        assert stats[0].successful_tasks == 8

    def test_accuracy_calculation(self, store: FeedbackStore):
        # All high-confidence tasks succeed
        for i in range(5):
            store.record_task(
                TaskOutcome(
                    task_id=f"t{i}",
                    session_id="s1",
                    action_type="write_files",
                    success=True,
                    confidence=0.9,
                )
            )
        stats = store.get_confidence_stats()
        assert stats[0].accuracy == 1.0

    def test_filter_stats_by_action(self, store: FeedbackStore):
        store.record_task(
            TaskOutcome(
                task_id="t1",
                session_id="s1",
                action_type="write_files",
                success=True,
                confidence=0.9,
            )
        )
        store.record_task(
            TaskOutcome(
                task_id="t2",
                session_id="s1",
                action_type="run_tests",
                success=True,
                confidence=0.7,
            )
        )
        stats = store.get_confidence_stats(action_type="run_tests")
        assert len(stats) == 1
        assert stats[0].action_type == "run_tests"

    def test_to_dict(self):
        s = ConfidenceStats(
            action_type="write_files",
            total_tasks=10,
            successful_tasks=8,
            avg_confidence=0.85,
        )
        d = s.to_dict()
        assert d["action_type"] == "write_files"
        assert d["total_tasks"] == 10


class TestDurationEstimation:
    def test_estimate_duration(self, store: FeedbackStore):
        for dur in [5.0, 10.0, 15.0]:
            store.record_task(
                TaskOutcome(
                    task_id=f"t{dur}",
                    session_id="s1",
                    action_type="write_files",
                    success=True,
                    duration_seconds=dur,
                )
            )
        est = store.estimate_duration("write_files")
        assert est == 10.0

    def test_estimate_no_data(self, store: FeedbackStore):
        assert store.estimate_duration("unknown") is None

    def test_estimate_ignores_failures(self, store: FeedbackStore):
        store.record_task(
            TaskOutcome(
                task_id="t1",
                session_id="s1",
                action_type="write_files",
                success=True,
                duration_seconds=10.0,
            )
        )
        store.record_task(
            TaskOutcome(
                task_id="t2",
                session_id="s1",
                action_type="write_files",
                success=False,
                duration_seconds=100.0,
            )
        )
        est = store.estimate_duration("write_files")
        assert est == 10.0


class TestEmptyStore:
    def test_empty_task_count(self, store: FeedbackStore):
        assert store.task_count == 0

    def test_empty_session_count(self, store: FeedbackStore):
        assert store.session_count == 0

    def test_empty_stats(self, store: FeedbackStore):
        assert store.get_confidence_stats() == []
