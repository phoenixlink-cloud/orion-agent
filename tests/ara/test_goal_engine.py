# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA Goal Engine (ARA-001 §8)."""

from __future__ import annotations

import asyncio

import pytest

from orion.ara.goal_engine import (
    DAGValidationError,
    GoalEngine,
    MockLLMProvider,
    Task,
    TaskDAG,
    TaskStatus,
)


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def engine(mock_llm: MockLLMProvider) -> GoalEngine:
    return GoalEngine(llm_provider=mock_llm)


class TestTaskDAG:
    def test_create_dag(self):
        dag = TaskDAG(
            goal="test",
            tasks=[
                Task(task_id="t1", title="A", description="", action_type="read_files"),
                Task(
                    task_id="t2",
                    title="B",
                    description="",
                    action_type="write_files",
                    dependencies=["t1"],
                ),
            ],
        )
        assert dag.total_tasks == 2
        assert dag.pending_tasks == 2

    def test_get_ready_tasks(self):
        dag = TaskDAG(
            goal="test",
            tasks=[
                Task(task_id="t1", title="A", description="", action_type="read_files"),
                Task(
                    task_id="t2",
                    title="B",
                    description="",
                    action_type="write_files",
                    dependencies=["t1"],
                ),
            ],
        )
        ready = dag.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "t1"

    def test_ready_after_completion(self):
        dag = TaskDAG(
            goal="test",
            tasks=[
                Task(
                    task_id="t1",
                    title="A",
                    description="",
                    action_type="read_files",
                    status=TaskStatus.COMPLETED,
                ),
                Task(
                    task_id="t2",
                    title="B",
                    description="",
                    action_type="write_files",
                    dependencies=["t1"],
                ),
            ],
        )
        ready = dag.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "t2"

    def test_validate_valid_dag(self):
        dag = TaskDAG(
            goal="test",
            tasks=[
                Task(task_id="t1", title="A", description="", action_type="read_files"),
                Task(
                    task_id="t2",
                    title="B",
                    description="",
                    action_type="write_files",
                    dependencies=["t1"],
                ),
            ],
        )
        errors = dag.validate_dag()
        assert len(errors) == 0

    def test_validate_missing_dependency(self):
        dag = TaskDAG(
            goal="test",
            tasks=[
                Task(
                    task_id="t1",
                    title="A",
                    description="",
                    action_type="read_files",
                    dependencies=["missing"],
                ),
            ],
        )
        errors = dag.validate_dag()
        assert len(errors) >= 1
        assert "unknown task" in errors[0].lower()

    def test_validate_duplicate_ids(self):
        dag = TaskDAG(
            goal="test",
            tasks=[
                Task(task_id="t1", title="A", description="", action_type="read_files"),
                Task(task_id="t1", title="B", description="", action_type="write_files"),
            ],
        )
        errors = dag.validate_dag()
        assert len(errors) >= 1

    def test_serialization_roundtrip(self):
        dag = TaskDAG(
            goal="build feature",
            tasks=[
                Task(task_id="t1", title="A", description="desc", action_type="read_files"),
            ],
        )
        data = dag.to_dict()
        restored = TaskDAG.from_dict(data)
        assert restored.goal == dag.goal
        assert len(restored.tasks) == 1
        assert restored.tasks[0].task_id == "t1"

    def test_get_task_by_id(self):
        dag = TaskDAG(
            goal="test",
            tasks=[Task(task_id="t1", title="A", description="", action_type="read_files")],
        )
        assert dag.get_task("t1") is not None
        assert dag.get_task("missing") is None


class TestMockLLMProvider:
    def test_default_decomposition(self, mock_llm: MockLLMProvider):
        tasks = asyncio.run(mock_llm.decompose_goal("any goal"))
        assert len(tasks) == 3
        assert tasks[0]["task_id"] == "task-1"

    def test_custom_responses(self):
        custom = MockLLMProvider(
            responses={
                "custom goal": [
                    {
                        "task_id": "c1",
                        "title": "Custom",
                        "description": "",
                        "action_type": "read_files",
                    }
                ],
            }
        )
        tasks = asyncio.run(custom.decompose_goal("custom goal"))
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == "c1"

    def test_replan(self, mock_llm: MockLLMProvider):
        remaining = [
            {"task_id": "r1", "title": "Remaining", "description": "", "action_type": "write_files"}
        ]
        result = asyncio.run(mock_llm.replan("goal", remaining=remaining))
        assert len(result) >= 1

    def test_tracks_call_count(self, mock_llm: MockLLMProvider):
        asyncio.run(mock_llm.decompose_goal("a"))
        asyncio.run(mock_llm.decompose_goal("b"))
        assert mock_llm._call_count == 2


class TestGoalEngine:
    def test_decompose(self, engine: GoalEngine):
        dag = asyncio.run(engine.decompose("Add tests for auth"))
        assert dag.total_tasks == 3
        assert dag.goal == "Add tests for auth"

    def test_decompose_invalid_raises(self):
        bad_llm = MockLLMProvider(
            responses={
                "bad": [
                    {
                        "task_id": "t1",
                        "title": "A",
                        "description": "",
                        "action_type": "x",
                        "dependencies": ["missing"],
                    }
                ],
            }
        )
        engine = GoalEngine(llm_provider=bad_llm)
        with pytest.raises(DAGValidationError):
            asyncio.run(engine.decompose("bad"))

    def test_replan(self, engine: GoalEngine):
        dag = asyncio.run(engine.decompose("Refactor module"))
        dag.tasks[0].status = TaskStatus.COMPLETED
        dag.tasks[1].status = TaskStatus.FAILED
        new_dag = asyncio.run(engine.replan(dag))
        assert new_dag.total_tasks >= 1

    def test_validate_actions(self, engine: GoalEngine):
        dag = asyncio.run(engine.decompose("test"))
        violations = engine.validate_actions(dag, ["read_files", "write_files"])
        # "run_tests" is in default mock tasks but not in allowed list
        assert "run_tests" in violations

    def test_validate_actions_empty_allowlist(self, engine: GoalEngine):
        dag = asyncio.run(engine.decompose("test"))
        violations = engine.validate_actions(dag, [])
        assert len(violations) == 0
