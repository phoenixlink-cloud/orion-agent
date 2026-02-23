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
"""Tests for ExecutionStep and WorkflowRunner (Phase 4B.1).

Tests WF-01 through WF-06+ validating multi-command workflow execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from orion.ara.execution_step import (
    ExecutionStep,
    StepStatus,
    WorkflowResult,
    WorkflowRunner,
    extract_steps,
)
from orion.security.session_container import ExecResult

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class FakeContainer:
    """Container stub for workflow tests."""

    def __init__(self) -> None:
        self.exec_results: list[ExecResult] = []
        self._exec_index = 0
        self.install_results: list[ExecResult] = []
        self._install_index = 0
        self.exec_calls: list[str] = []
        self.install_calls: list[str] = []

    async def exec(self, command: str, timeout: int = 120, phase: str = "execute") -> ExecResult:
        self.exec_calls.append(command)
        if self._exec_index < len(self.exec_results):
            r = self.exec_results[self._exec_index]
            self._exec_index += 1
            return r
        return ExecResult(exit_code=0, stdout="OK", command=command)

    async def exec_install(self, command: str, timeout: int = 300) -> ExecResult:
        self.install_calls.append(command)
        if self._install_index < len(self.install_results):
            r = self.install_results[self._install_index]
            self._install_index += 1
            return r
        return ExecResult(exit_code=0, stdout="installed", command=command)


# ---------------------------------------------------------------------------
# WF-01: ExecutionStep dataclass
# ---------------------------------------------------------------------------


class TestExecutionStep:
    """WF-01: ExecutionStep serialization and deserialization."""

    def test_defaults(self):
        step = ExecutionStep()
        assert step.status == StepStatus.PENDING
        assert step.action == "run_command"
        assert step.exit_code == -1

    def test_to_dict(self):
        step = ExecutionStep(step_id="s1", action="install_deps", command="pip install flask")
        d = step.to_dict()
        assert d["step_id"] == "s1"
        assert d["action"] == "install_deps"
        assert d["command"] == "pip install flask"
        assert d["status"] == "pending"

    def test_from_dict(self):
        step = ExecutionStep.from_dict(
            {
                "step_id": "s2",
                "action": "run_command",
                "command": "python app.py",
                "timeout": 60,
                "continue_on_error": True,
            }
        )
        assert step.step_id == "s2"
        assert step.timeout == 60
        assert step.continue_on_error is True

    def test_roundtrip(self):
        original = ExecutionStep(
            step_id="s3",
            action="run_tests_sandbox",
            command="pytest",
            description="Run tests",
            timeout=180,
        )
        restored = ExecutionStep.from_dict(original.to_dict())
        assert restored.step_id == original.step_id
        assert restored.action == original.action
        assert restored.command == original.command
        assert restored.timeout == original.timeout


# ---------------------------------------------------------------------------
# WF-02: extract_steps from metadata
# ---------------------------------------------------------------------------


class TestExtractSteps:
    """WF-02: extract_steps correctly parses metadata."""

    def test_multi_step_metadata(self):
        metadata = {
            "execution_steps": [
                {"action": "install_deps", "command": "pip install flask"},
                {"action": "run_command", "command": "python app.py"},
                {"action": "run_tests_sandbox", "command": "pytest"},
            ]
        }
        steps = extract_steps(metadata)
        assert len(steps) == 3
        assert steps[0].action == "install_deps"
        assert steps[1].action == "run_command"
        assert steps[2].action == "run_tests_sandbox"

    def test_auto_assigns_step_ids(self):
        metadata = {
            "execution_steps": [
                {"action": "run_command", "command": "echo hello"},
                {"action": "run_command", "command": "echo world"},
            ]
        }
        steps = extract_steps(metadata)
        assert steps[0].step_id == "step-1"
        assert steps[1].step_id == "step-2"

    def test_preserves_existing_step_ids(self):
        metadata = {
            "execution_steps": [
                {"step_id": "custom-1", "action": "run_command", "command": "echo hi"},
            ]
        }
        steps = extract_steps(metadata)
        assert steps[0].step_id == "custom-1"

    def test_fallback_to_single_command(self):
        metadata = {"command": "python app.py"}
        steps = extract_steps(metadata)
        assert len(steps) == 1
        assert steps[0].action == "run_command"
        assert steps[0].command == "python app.py"

    def test_fallback_install_command(self):
        metadata = {"install_command": "pip install flask"}
        steps = extract_steps(metadata)
        assert len(steps) == 1
        assert steps[0].action == "install_deps"

    def test_fallback_test_command(self):
        metadata = {"test_command": "pytest tests/"}
        steps = extract_steps(metadata)
        assert len(steps) == 1
        assert steps[0].action == "run_tests_sandbox"

    def test_empty_metadata(self):
        steps = extract_steps({})
        assert steps == []

    def test_invalid_steps_ignored(self):
        metadata = {"execution_steps": ["not a dict", 42, None]}
        steps = extract_steps(metadata)
        assert steps == []


# ---------------------------------------------------------------------------
# WF-03: WorkflowRunner — all steps succeed
# ---------------------------------------------------------------------------


class TestWorkflowRunnerSuccess:
    """WF-03: WorkflowRunner completes all steps successfully."""

    @pytest.mark.asyncio
    async def test_all_steps_pass(self):
        container = FakeContainer()
        container.install_results = [
            ExecResult(exit_code=0, stdout="installed flask", command="pip install flask"),
        ]
        container.exec_results = [
            ExecResult(exit_code=0, stdout="Server started", command="python app.py"),
            ExecResult(exit_code=0, stdout="3 passed", command="pytest"),
        ]

        steps = [
            ExecutionStep(step_id="s1", action="install_deps", command="pip install flask"),
            ExecutionStep(step_id="s2", action="run_command", command="python app.py"),
            ExecutionStep(step_id="s3", action="run_tests_sandbox", command="pytest"),
        ]

        runner = WorkflowRunner(container=container)
        result = await runner.run(steps)

        assert result.success is True
        assert result.completed_count == 3
        assert result.failed_count == 0
        assert result.skipped_count == 0
        assert result.confidence == 0.9
        assert container.install_calls == ["pip install flask"]
        assert container.exec_calls == ["python app.py", "pytest"]


# ---------------------------------------------------------------------------
# WF-04: WorkflowRunner — fail-fast behavior
# ---------------------------------------------------------------------------


class TestWorkflowRunnerFailFast:
    """WF-04: WorkflowRunner stops on first failure."""

    @pytest.mark.asyncio
    async def test_fail_fast_skips_remaining(self):
        container = FakeContainer()
        container.exec_results = [
            ExecResult(exit_code=1, stderr="Error: syntax", command="python app.py"),
        ]

        steps = [
            ExecutionStep(step_id="s1", action="run_command", command="python app.py"),
            ExecutionStep(step_id="s2", action="run_command", command="echo done"),
            ExecutionStep(step_id="s3", action="run_command", command="echo final"),
        ]

        runner = WorkflowRunner(container=container)
        result = await runner.run(steps)

        assert result.success is False
        assert result.completed_count == 0
        assert result.failed_count == 1
        assert result.skipped_count == 2
        assert steps[0].status == StepStatus.FAILED
        assert steps[1].status == StepStatus.SKIPPED
        assert steps[2].status == StepStatus.SKIPPED


# ---------------------------------------------------------------------------
# WF-05: WorkflowRunner — continue_on_error
# ---------------------------------------------------------------------------


class TestWorkflowRunnerContinueOnError:
    """WF-05: Steps with continue_on_error don't stop the workflow."""

    @pytest.mark.asyncio
    async def test_continue_after_optional_failure(self):
        container = FakeContainer()
        container.exec_results = [
            ExecResult(exit_code=1, stderr="lint warnings", command="flake8"),
            ExecResult(exit_code=0, stdout="OK", command="python app.py"),
        ]

        steps = [
            ExecutionStep(
                step_id="s1",
                action="run_command",
                command="flake8",
                continue_on_error=True,
            ),
            ExecutionStep(step_id="s2", action="run_command", command="python app.py"),
        ]

        runner = WorkflowRunner(container=container)
        result = await runner.run(steps)

        assert result.success is False  # Overall fails because one step failed
        assert result.completed_count == 1
        assert result.failed_count == 1
        assert result.skipped_count == 0
        assert steps[0].status == StepStatus.FAILED
        assert steps[1].status == StepStatus.COMPLETED


# ---------------------------------------------------------------------------
# WF-06: WorkflowRunner — with feedback loop
# ---------------------------------------------------------------------------


class TestWorkflowRunnerWithFeedback:
    """WF-06: WorkflowRunner uses feedback loop for run_command steps."""

    @pytest.mark.asyncio
    async def test_feedback_integration(self):
        from orion.ara.execution_feedback import (
            ExecutionFeedbackLoop,
            RuleBasedFixProvider,
        )

        container = FakeContainer()
        container.exec_results = [
            ExecResult(exit_code=0, stdout="Hello", command="python app.py"),
        ]

        feedback = ExecutionFeedbackLoop(
            container=container,
            fix_provider=RuleBasedFixProvider(),
            max_retries=2,
        )

        steps = [
            ExecutionStep(step_id="s1", action="run_command", command="python app.py"),
        ]

        runner = WorkflowRunner(container=container, feedback=feedback)
        result = await runner.run(steps)

        assert result.success is True
        assert result.completed_count == 1
        assert steps[0].output == "Hello"


# ---------------------------------------------------------------------------
# WF-07: WorkflowResult
# ---------------------------------------------------------------------------


class TestWorkflowResult:
    """WF-07: WorkflowResult properties and summary."""

    def test_empty_result(self):
        r = WorkflowResult()
        assert r.confidence == 0.0
        assert "0/0" in r.summary()

    def test_all_pass_confidence(self):
        r = WorkflowResult(
            success=True,
            completed_count=3,
            failed_count=0,
            steps=[ExecutionStep(), ExecutionStep(), ExecutionStep()],
        )
        assert r.confidence == 0.9

    def test_with_failures_confidence(self):
        r = WorkflowResult(
            success=False,
            completed_count=1,
            failed_count=1,
            steps=[ExecutionStep(), ExecutionStep()],
        )
        assert r.confidence == 0.3

    def test_summary_format(self):
        r = WorkflowResult(
            success=False,
            completed_count=2,
            failed_count=1,
            skipped_count=1,
            total_duration_seconds=5.5,
            steps=[ExecutionStep()] * 4,
        )
        s = r.summary()
        assert "2/4" in s
        assert "1 failed" in s
        assert "1 skipped" in s
        assert "5.5s" in s


# ---------------------------------------------------------------------------
# WF-08: Executor workflow integration
# ---------------------------------------------------------------------------


class TestExecutorWorkflowIntegration:
    """WF-08: ARATaskExecutor routes to _execute_workflow for multi-step tasks."""

    @pytest.mark.asyncio
    async def test_executor_routes_to_workflow(self, tmp_path):
        from orion.ara.task_executor import ARATaskExecutor

        container = FakeContainer()
        container.install_results = [
            ExecResult(exit_code=0, stdout="installed", command="pip install flask"),
        ]
        container.exec_results = [
            ExecResult(exit_code=0, stdout="running", command="python app.py"),
        ]

        executor = ARATaskExecutor(
            sandbox_dir=tmp_path / "sandbox",
            session_container=container,
        )

        @dataclass
        class MultiStepTask:
            task_id: str = "wf-1"
            title: str = "Setup and run"
            description: str = ""
            action_type: str = "run_command"
            metadata: dict = field(
                default_factory=lambda: {
                    "execution_steps": [
                        {"action": "install_deps", "command": "pip install flask"},
                        {"action": "run_command", "command": "python app.py"},
                    ]
                }
            )

        task = MultiStepTask()
        result = await executor.execute(task)

        assert result["success"] is True
        assert result["completed_steps"] == 2
        assert result["failed_steps"] == 0
        assert "workflow_steps" in result
