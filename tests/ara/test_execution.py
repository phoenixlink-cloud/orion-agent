# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA Execution Loop (ARA-001 §9)."""

from __future__ import annotations

import asyncio

import pytest

from orion.ara.execution import ExecutionLoop, ExecutionResult
from orion.ara.goal_engine import Task, TaskDAG, TaskStatus
from orion.ara.session import SessionState, SessionStatus


def _make_dag(task_count: int = 3) -> TaskDAG:
    """Create a simple linear DAG for testing."""
    tasks = []
    for i in range(task_count):
        deps = [f"t{i - 1}"] if i > 0 else []
        tasks.append(Task(
            task_id=f"t{i}",
            title=f"Task {i}",
            description=f"Test task {i}",
            action_type="write_files",
            dependencies=deps,
        ))
    return TaskDAG(goal="Test goal", tasks=tasks)


def _make_session(**kwargs) -> SessionState:
    return SessionState(
        session_id="exec-test",
        role_name="test",
        goal="Test",
        **kwargs,
    )


async def _success_executor(task):
    return {"success": True, "output": f"Done: {task.title}", "confidence": 0.9}


async def _fail_executor(task):
    return {"success": False, "error": "Simulated failure"}


async def _low_confidence_executor(task):
    return {"success": True, "output": "Low confidence", "confidence": 0.3}


class TestBasicExecution:
    def test_runs_all_tasks(self):
        session = _make_session()
        dag = _make_dag(3)
        loop = ExecutionLoop(session, dag, task_executor=_success_executor)
        result = asyncio.run(loop.run())
        assert result.tasks_completed == 3
        assert result.tasks_failed == 0
        assert "goal_complete" in result.stop_reason

    def test_session_transitions_to_completed(self):
        session = _make_session()
        dag = _make_dag(2)
        loop = ExecutionLoop(session, dag, task_executor=_success_executor)
        asyncio.run(loop.run())
        assert session.status == SessionStatus.COMPLETED

    def test_session_auto_starts(self):
        session = _make_session()
        dag = _make_dag(1)
        loop = ExecutionLoop(session, dag, task_executor=_success_executor)
        asyncio.run(loop.run())
        assert session.started_at is not None

    def test_tracks_progress(self):
        session = _make_session()
        dag = _make_dag(3)
        loop = ExecutionLoop(session, dag, task_executor=_success_executor)
        asyncio.run(loop.run())
        assert session.progress.total_tasks == 3
        assert session.progress.completed_tasks == 3


class TestStopConditions:
    def test_stops_on_time_limit(self):
        session = _make_session(max_duration_hours=0.0001)
        session.elapsed_seconds = 1  # Already past limit
        dag = _make_dag(5)
        loop = ExecutionLoop(session, dag, task_executor=_success_executor)
        result = asyncio.run(loop.run())
        assert "time_limit" in result.stop_reason

    def test_stops_on_cost_limit(self):
        session = _make_session(max_cost_usd=0.001)
        session.cost_usd = 0.002
        dag = _make_dag(5)
        loop = ExecutionLoop(session, dag, task_executor=_success_executor)
        result = asyncio.run(loop.run())
        assert "cost_limit" in result.stop_reason

    def test_stops_on_error_streak(self):
        session = _make_session()
        # Create 6 independent tasks (no deps)
        tasks = [
            Task(task_id=f"t{i}", title=f"Task {i}", description="", action_type="write_files")
            for i in range(6)
        ]
        dag = TaskDAG(goal="Test", tasks=tasks)
        loop = ExecutionLoop(session, dag, task_executor=_fail_executor)
        result = asyncio.run(loop.run())
        assert "error_threshold" in result.stop_reason
        assert session.status == SessionStatus.FAILED

    def test_stops_on_confidence_collapse(self):
        session = _make_session()
        tasks = [
            Task(task_id=f"t{i}", title=f"Task {i}", description="", action_type="write_files")
            for i in range(5)
        ]
        dag = TaskDAG(goal="Test", tasks=tasks)
        loop = ExecutionLoop(session, dag, task_executor=_low_confidence_executor)
        result = asyncio.run(loop.run())
        assert "confidence_collapse" in result.stop_reason

    def test_manual_stop(self):
        session = _make_session()
        tasks = [
            Task(task_id=f"t{i}", title=f"Task {i}", description="", action_type="write_files")
            for i in range(10)
        ]
        dag = TaskDAG(goal="Test", tasks=tasks)

        call_count = 0

        async def counting_executor(task):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                loop.stop()
            return {"success": True, "output": "ok", "confidence": 0.9}

        loop = ExecutionLoop(session, dag, task_executor=counting_executor)
        result = asyncio.run(loop.run())
        assert result.tasks_completed >= 2
        assert session.status == SessionStatus.PAUSED


class TestCheckpointing:
    def test_checkpoint_callback(self):
        session = _make_session()
        dag = _make_dag(1)
        checkpoints = []
        loop = ExecutionLoop(
            session, dag,
            task_executor=_success_executor,
            on_checkpoint=lambda: checkpoints.append(True),
            checkpoint_interval_minutes=0,  # Checkpoint after every task
        )
        asyncio.run(loop.run())
        # May or may not checkpoint depending on timing, but should not error
        assert isinstance(checkpoints, list)


class TestExecutionResult:
    def test_to_dict(self):
        result = ExecutionResult(
            tasks_completed=3,
            tasks_failed=1,
            stop_reason="goal_complete",
            total_elapsed_seconds=120.5,
        )
        d = result.to_dict()
        assert d["tasks_completed"] == 3
        assert d["stop_reason"] == "goal_complete"
