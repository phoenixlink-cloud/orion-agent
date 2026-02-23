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
"""Tests for Phase 4 execution wiring in ARATaskExecutor.

Tests TE-01 through TE-08+ as specified in Phase 4A.3.
Validates run_command, install_deps, and run_tests_sandbox action handlers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from orion.ara.task_executor import ARATaskExecutor

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


@dataclass
class FakeTask:
    """Minimal task stub for testing."""

    task_id: str = "test-1"
    title: str = "Test task"
    description: str = "Run a command"
    action_type: str = "run_command"
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    estimated_minutes: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeExecResult:
    """Minimal ExecResult stub."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_seconds: float = 0.1
    command: str = ""
    phase: str = "execute"


@dataclass
class FakeFeedbackResult:
    """Minimal FeedbackResult stub."""

    original_command: str = ""
    success: bool = False
    attempts: int = 1
    final_exit_code: int = -1
    final_stdout: str = ""
    final_stderr: str = ""
    fixes_applied: list = field(default_factory=list)


class FakeContainer:
    """Minimal SessionContainer stub."""

    def __init__(self):
        self._exec_result = FakeExecResult()
        self._install_result = FakeExecResult()
        self.exec_calls: list[str] = []
        self.install_calls: list[str] = []

    async def exec(
        self, command: str, timeout: int = 120, phase: str = "execute"
    ) -> FakeExecResult:
        self.exec_calls.append(command)
        return self._exec_result

    async def exec_install(self, command: str, timeout: int = 300) -> FakeExecResult:
        self.install_calls.append(command)
        return self._install_result


class FakeFeedbackLoop:
    """Minimal ExecutionFeedbackLoop stub."""

    def __init__(self, result: FakeFeedbackResult | None = None):
        self._result = result or FakeFeedbackResult(
            success=True, final_exit_code=0, final_stdout="OK", attempts=1
        )
        self.calls: list[str] = []

    async def run_with_feedback(self, command: str, timeout: int = 120) -> FakeFeedbackResult:
        self.calls.append(command)
        return self._result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    sd = tmp_path / "sandbox"
    sd.mkdir()
    return sd


@pytest.fixture
def container() -> FakeContainer:
    return FakeContainer()


@pytest.fixture
def feedback_loop() -> FakeFeedbackLoop:
    return FakeFeedbackLoop()


# ---------------------------------------------------------------------------
# TE-01: run_command without container returns error
# ---------------------------------------------------------------------------


class TestRunCommandNoContainer:
    """TE-01: run_command fails gracefully without a session container."""

    @pytest.mark.asyncio
    async def test_no_container_returns_error(self, sandbox):
        executor = ARATaskExecutor(sandbox_dir=sandbox)
        task = FakeTask(action_type="run_command", metadata={"command": "echo hi"})
        result = await executor.execute(task)
        assert result["success"] is False
        assert "No session container" in result["error"]


# ---------------------------------------------------------------------------
# TE-02: run_command with container (direct exec)
# ---------------------------------------------------------------------------


class TestRunCommandDirect:
    """TE-02: run_command uses container.exec() when no feedback loop."""

    @pytest.mark.asyncio
    async def test_direct_exec_success(self, sandbox, container):
        container._exec_result = FakeExecResult(exit_code=0, stdout="hello world")
        executor = ARATaskExecutor(sandbox_dir=sandbox, session_container=container)
        task = FakeTask(action_type="run_command", metadata={"command": "echo hello world"})
        result = await executor.execute(task)
        assert result["success"] is True
        assert "hello world" in result["output"]
        assert container.exec_calls == ["echo hello world"]

    @pytest.mark.asyncio
    async def test_direct_exec_failure(self, sandbox, container):
        container._exec_result = FakeExecResult(exit_code=1, stderr="not found")
        executor = ARATaskExecutor(sandbox_dir=sandbox, session_container=container)
        task = FakeTask(action_type="run_command", metadata={"command": "bad_cmd"})
        result = await executor.execute(task)
        assert result["success"] is False
        assert result["confidence"] < 0.5


# ---------------------------------------------------------------------------
# TE-03: run_command with feedback loop
# ---------------------------------------------------------------------------


class TestRunCommandWithFeedback:
    """TE-03: run_command uses feedback loop for error correction."""

    @pytest.mark.asyncio
    async def test_feedback_success(self, sandbox, container):
        fb = FakeFeedbackLoop(
            FakeFeedbackResult(success=True, final_exit_code=0, final_stdout="OK", attempts=1)
        )
        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
            execution_feedback=fb,
        )
        task = FakeTask(action_type="run_command", metadata={"command": "python app.py"})
        result = await executor.execute(task)
        assert result["success"] is True
        assert result["confidence"] == 0.9
        assert fb.calls == ["python app.py"]

    @pytest.mark.asyncio
    async def test_feedback_retry_success(self, sandbox, container):
        """Feedback loop succeeds after retries → lower confidence."""
        fb = FakeFeedbackLoop(
            FakeFeedbackResult(
                success=True,
                final_exit_code=0,
                final_stdout="OK",
                attempts=2,
                fixes_applied=["fix1"],
            )
        )
        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
            execution_feedback=fb,
        )
        task = FakeTask(action_type="run_command", metadata={"command": "python app.py"})
        result = await executor.execute(task)
        assert result["success"] is True
        assert result["confidence"] == 0.7  # Lower due to retries
        assert result["feedback_attempts"] == 2

    @pytest.mark.asyncio
    async def test_feedback_failure(self, sandbox, container):
        fb = FakeFeedbackLoop(
            FakeFeedbackResult(
                success=False,
                final_exit_code=1,
                final_stderr="crash",
                attempts=3,
                fixes_applied=["f1", "f2"],
            )
        )
        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
            execution_feedback=fb,
        )
        task = FakeTask(action_type="run_command", metadata={"command": "python app.py"})
        result = await executor.execute(task)
        assert result["success"] is False
        assert result["confidence"] == 0.2


# ---------------------------------------------------------------------------
# TE-04: install_deps
# ---------------------------------------------------------------------------


class TestInstallDeps:
    """TE-04: install_deps uses container.exec_install()."""

    @pytest.mark.asyncio
    async def test_install_success(self, sandbox, container):
        container._install_result = FakeExecResult(exit_code=0, stdout="Installed flask")
        executor = ARATaskExecutor(sandbox_dir=sandbox, session_container=container)
        task = FakeTask(
            action_type="install_deps",
            metadata={"install_command": "pip install flask"},
        )
        result = await executor.execute(task)
        assert result["success"] is True
        assert container.install_calls == ["pip install flask"]

    @pytest.mark.asyncio
    async def test_install_failure(self, sandbox, container):
        container._install_result = FakeExecResult(exit_code=1, stderr="network error")
        executor = ARATaskExecutor(sandbox_dir=sandbox, session_container=container)
        task = FakeTask(
            action_type="install_deps",
            metadata={"install_command": "pip install broken_pkg"},
        )
        result = await executor.execute(task)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_install_no_container(self, sandbox):
        executor = ARATaskExecutor(sandbox_dir=sandbox)
        task = FakeTask(action_type="install_deps", metadata={"install_command": "pip install x"})
        result = await executor.execute(task)
        assert result["success"] is False
        assert "No session container" in result["error"]


# ---------------------------------------------------------------------------
# TE-05: run_tests_sandbox
# ---------------------------------------------------------------------------


class TestRunTestsSandbox:
    """TE-05: run_tests_sandbox executes tests inside the container."""

    @pytest.mark.asyncio
    async def test_tests_pass(self, sandbox, container):
        container._exec_result = FakeExecResult(exit_code=0, stdout="3 passed in 1.5s")
        executor = ARATaskExecutor(sandbox_dir=sandbox, session_container=container)
        task = FakeTask(
            action_type="run_tests_sandbox",
            metadata={"test_command": "pytest tests/"},
        )
        result = await executor.execute(task)
        assert result["success"] is True
        assert result["confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_tests_fail(self, sandbox, container):
        container._exec_result = FakeExecResult(exit_code=1, stdout="2 passed, 1 failed")
        executor = ARATaskExecutor(sandbox_dir=sandbox, session_container=container)
        task = FakeTask(
            action_type="run_tests_sandbox",
            metadata={"test_command": "pytest tests/"},
        )
        result = await executor.execute(task)
        assert result["success"] is False
        assert result["confidence"] < 0.5

    @pytest.mark.asyncio
    async def test_tests_fallback_no_container(self, sandbox):
        """Falls back to local validation when no container."""
        executor = ARATaskExecutor(sandbox_dir=sandbox)
        task = FakeTask(action_type="run_tests_sandbox")
        result = await executor.execute(task)
        # Falls back to _execute_validate — succeeds (no files to validate)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# TE-06: Command extraction
# ---------------------------------------------------------------------------


class TestExtractCommand:
    """TE-06: _extract_command extracts from metadata or description."""

    def test_from_metadata_command(self):
        task = FakeTask(metadata={"command": "python main.py"})
        assert ARATaskExecutor._extract_command(task) == "python main.py"

    def test_from_metadata_install_command(self):
        task = FakeTask(metadata={"install_command": "pip install flask"})
        assert ARATaskExecutor._extract_command(task) == "pip install flask"

    def test_from_metadata_test_command(self):
        task = FakeTask(metadata={"test_command": "pytest"})
        assert ARATaskExecutor._extract_command(task) == "pytest"

    def test_from_description_fallback(self):
        task = FakeTask(description="echo hello", metadata={})
        assert ARATaskExecutor._extract_command(task) == "echo hello"

    def test_empty_metadata_long_description(self):
        task = FakeTask(description="x" * 600, metadata={})
        assert ARATaskExecutor._extract_command(task) == ""

    def test_priority_order(self):
        """command > install_command > test_command > description."""
        task = FakeTask(
            metadata={
                "command": "CMD",
                "install_command": "INSTALL",
                "test_command": "TEST",
            },
            description="DESC",
        )
        assert ARATaskExecutor._extract_command(task) == "CMD"


# ---------------------------------------------------------------------------
# TE-07: Test output scoring
# ---------------------------------------------------------------------------


class TestScoreTestOutput:
    """TE-07: _score_test_output correctly scores test results."""

    def test_all_passed(self):
        assert ARATaskExecutor._score_test_output("5 passed in 1.0s", True) == 0.95

    def test_passed_and_failed(self):
        assert ARATaskExecutor._score_test_output("3 passed, 1 failed", True) == 0.7

    def test_ok_output(self):
        assert ARATaskExecutor._score_test_output("OK (3 tests)", True) == 0.9

    def test_failure(self):
        assert ARATaskExecutor._score_test_output("FAILED", False) == 0.3

    def test_generic_success(self):
        assert ARATaskExecutor._score_test_output("done", True) == 0.8


# ---------------------------------------------------------------------------
# TE-08: Existing actions still work with new params
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """TE-08: Existing action types work when container/feedback are None."""

    @pytest.mark.asyncio
    async def test_analyze_still_works(self, sandbox):
        """analyze action works without container (no regression)."""
        executor = ARATaskExecutor(sandbox_dir=sandbox)
        task = FakeTask(action_type="analyze", description="Check requirements")
        # Will try to call LLM — mock it
        import unittest.mock as mock

        with mock.patch("orion.ara.task_executor._call_llm", return_value="Analysis complete"):
            result = await executor.execute(task)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_validate_still_works(self, sandbox):
        """validate action works without container."""
        executor = ARATaskExecutor(sandbox_dir=sandbox)
        task = FakeTask(action_type="validate")
        result = await executor.execute(task)
        assert result["success"] is True

    def test_init_backward_compatible(self, sandbox):
        """ARATaskExecutor can be created without new Phase 4 params."""
        executor = ARATaskExecutor(sandbox_dir=sandbox, goal="test")
        assert executor._container is None
        assert executor._feedback is None

    def test_init_with_container(self, sandbox, container):
        """ARATaskExecutor accepts container and feedback params."""
        fb = FakeFeedbackLoop()
        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
            execution_feedback=fb,
        )
        assert executor._container is container
        assert executor._feedback is fb
