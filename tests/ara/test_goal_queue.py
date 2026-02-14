# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Phase 14: GoalQueue — multi-goal queuing with priority interrupts."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.ara.goal_queue import GoalQueue, QueuedGoal


@pytest.fixture
def queue_path(tmp_path: Path) -> Path:
    return tmp_path / "queue.json"


@pytest.fixture
def queue(queue_path: Path) -> GoalQueue:
    return GoalQueue(path=queue_path)


class TestQueuedGoal:
    def test_defaults(self):
        g = QueuedGoal(description="Test", role_name="coder")
        assert g.status == "queued"
        assert g.priority == "normal"
        assert g.depends_on is None
        assert len(g.goal_id) == 12

    def test_roundtrip(self):
        g = QueuedGoal(description="Test", role_name="coder", priority="urgent")
        d = g.to_dict()
        g2 = QueuedGoal.from_dict(d)
        assert g2.description == "Test"
        assert g2.priority == "urgent"


class TestEnqueueDequeue:
    def test_enqueue_and_dequeue(self, queue: GoalQueue):
        queue.enqueue(QueuedGoal(description="First", role_name="coder"))
        queue.enqueue(QueuedGoal(description="Second", role_name="coder"))
        assert queue.size == 2
        assert queue.pending_count == 2

        g = queue.dequeue()
        assert g is not None
        assert g.description == "First"
        assert g.status == "active"
        assert queue.pending_count == 1

    def test_dequeue_empty(self, queue: GoalQueue):
        assert queue.dequeue() is None

    def test_fifo_order(self, queue: GoalQueue):
        queue.enqueue(QueuedGoal(description="A", role_name="r"))
        queue.enqueue(QueuedGoal(description="B", role_name="r"))
        queue.enqueue(QueuedGoal(description="C", role_name="r"))

        assert queue.dequeue().description == "A"
        assert queue.dequeue().description == "B"
        assert queue.dequeue().description == "C"
        assert queue.dequeue() is None

    def test_urgent_priority(self, queue: GoalQueue):
        queue.enqueue(QueuedGoal(description="Normal", role_name="r"))
        queue.enqueue(QueuedGoal(description="Urgent", role_name="r", priority="urgent"))
        queue.enqueue(QueuedGoal(description="Normal2", role_name="r"))

        g = queue.dequeue()
        assert g.description == "Urgent"


class TestDependencies:
    def test_dependency_blocks(self, queue: GoalQueue):
        g1 = QueuedGoal(goal_id="g1", description="First", role_name="r")
        g2 = QueuedGoal(goal_id="g2", description="Second", role_name="r", depends_on="g1")
        queue.enqueue(g1)
        queue.enqueue(g2)

        # Dequeue g1
        got = queue.dequeue()
        assert got.goal_id == "g1"

        # g2 should be blocked (g1 not completed)
        got2 = queue.dequeue()
        assert got2 is None

        # Complete g1, then g2 should be available
        queue.complete("g1")
        got3 = queue.dequeue()
        assert got3 is not None
        assert got3.goal_id == "g2"


class TestInterrupt:
    def test_interrupt_pauses_active(self, queue: GoalQueue):
        queue.enqueue(QueuedGoal(goal_id="current", description="Current work", role_name="r"))
        queue.dequeue()  # Activate "current"

        urgent = QueuedGoal(description="Urgent fix", role_name="r")
        paused_id = queue.interrupt(urgent)
        assert paused_id == "current"

        # Urgent should be active
        active = [g for g in queue.list_goals() if g.status == "active"]
        assert len(active) == 1
        assert active[0].description == "Urgent fix"

    def test_interrupt_no_active(self, queue: GoalQueue):
        urgent = QueuedGoal(description="Urgent", role_name="r")
        paused_id = queue.interrupt(urgent)
        assert paused_id is None

    def test_resume_after_interrupt(self, queue: GoalQueue):
        queue.enqueue(QueuedGoal(goal_id="original", description="Original", role_name="r"))
        queue.dequeue()  # Activate

        urgent = QueuedGoal(goal_id="urgent-1", description="Urgent", role_name="r")
        queue.interrupt(urgent)
        queue.complete("urgent-1")

        resumed = queue.resume_paused()
        assert resumed is not None
        assert resumed.goal_id == "original"
        assert resumed.status == "active"


class TestCompleteAndFail:
    def test_complete(self, queue: GoalQueue):
        queue.enqueue(QueuedGoal(goal_id="c1", description="Complete me", role_name="r"))
        queue.dequeue()
        assert queue.complete("c1") is True

        goals = queue.list_goals()
        assert goals[0].status == "completed"

    def test_complete_unknown(self, queue: GoalQueue):
        assert queue.complete("unknown") is False

    def test_fail(self, queue: GoalQueue):
        queue.enqueue(QueuedGoal(goal_id="f1", description="Fail me", role_name="r"))
        queue.dequeue()
        assert queue.fail("f1") is True

        goals = queue.list_goals()
        assert goals[0].status == "failed"


class TestReorder:
    def test_reorder(self, queue: GoalQueue):
        queue.enqueue(QueuedGoal(description="A", role_name="r"))
        queue.enqueue(QueuedGoal(description="B", role_name="r"))
        queue.enqueue(QueuedGoal(description="C", role_name="r"))

        assert queue.reorder(2, 0) is True
        queued = queue.list_queued()
        assert queued[0].description == "C"

    def test_reorder_out_of_bounds(self, queue: GoalQueue):
        queue.enqueue(QueuedGoal(description="A", role_name="r"))
        assert queue.reorder(0, 5) is False
        assert queue.reorder(-1, 0) is False


class TestPersistence:
    def test_persistence(self, queue_path: Path):
        q1 = GoalQueue(path=queue_path)
        q1.enqueue(QueuedGoal(description="Persist me", role_name="r"))

        q2 = GoalQueue(path=queue_path)
        assert q2.size == 1
        assert q2.list_goals()[0].description == "Persist me"


class TestClear:
    def test_clear(self, queue: GoalQueue):
        queue.enqueue(QueuedGoal(description="A", role_name="r"))
        queue.enqueue(QueuedGoal(description="B", role_name="r"))
        removed = queue.clear()
        assert removed == 2
        assert queue.size == 0
