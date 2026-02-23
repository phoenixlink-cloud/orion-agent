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
"""Phase 4A End-to-End Integration Tests.

Tests E2E-01 through E2E-08 validating the full pipeline:
  config → stack detection → container → executor → feedback

Docker is fully mocked — these tests exercise cross-module integration
without requiring a running Docker daemon.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from orion.ara.execution_config import ExecutionSettings, load_execution_settings
from orion.ara.execution_feedback import (
    ErrorCategory,
    ExecutionFeedbackLoop,
    FeedbackResult,
    FixAction,
    RuleBasedFixProvider,
    classify_error,
)
from orion.ara.task_executor import ARATaskExecutor
from orion.security.session_container import ExecResult, SessionContainer
from orion.security.stack_detector import detect_stack, detect_stack_from_goal, image_name


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------


@dataclass
class FakeTask:
    task_id: str = "e2e-1"
    title: str = "E2E test task"
    description: str = ""
    action_type: str = "run_command"
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    estimated_minutes: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class FakeContainer:
    """Container stub that tracks calls and returns configurable results."""

    def __init__(self) -> None:
        self.exec_results: list[ExecResult] = []
        self._exec_index = 0
        self.install_results: list[ExecResult] = []
        self._install_index = 0
        self.exec_calls: list[str] = []
        self.install_calls: list[str] = []
        self._running = True

    @property
    def is_running(self) -> bool:
        return self._running

    async def exec(self, command: str, timeout: int = 120, phase: str = "execute") -> ExecResult:
        self.exec_calls.append(command)
        if self._exec_index < len(self.exec_results):
            result = self.exec_results[self._exec_index]
            self._exec_index += 1
            return result
        return ExecResult(exit_code=0, stdout="OK", command=command)

    async def exec_install(self, command: str, timeout: int = 300) -> ExecResult:
        self.install_calls.append(command)
        if self._install_index < len(self.install_results):
            result = self.install_results[self._install_index]
            self._install_index += 1
            return result
        return ExecResult(exit_code=0, stdout="installed", command=command)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    sd = tmp_path / "sandbox"
    sd.mkdir()
    return sd


@pytest.fixture
def settings_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".orion"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# E2E-01: Config → Stack → Image pipeline
# ---------------------------------------------------------------------------


class TestConfigStackImagePipeline:
    """E2E-01: Settings enable execution, stack detected, correct image chosen."""

    def test_full_config_to_image(self, tmp_path: Path, settings_dir: Path):
        # 1. Write config enabling execution
        global_settings = settings_dir / "settings.json"
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": True,
                    "ara_resource_profile": "heavy",
                }
            )
        )
        ara_settings = settings_dir / "ara_settings.json"

        # 2. Load and verify config
        cfg = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert cfg.enabled is True
        assert cfg.resource_profile == "heavy"

        # 3. Detect stack from workspace
        workspace = tmp_path / "project"
        workspace.mkdir()
        (workspace / "requirements.txt").write_text("flask\n")
        stack = detect_stack(workspace)
        assert stack == "python"

        # 4. Get correct image name
        img = image_name(stack)
        assert img == "orion-stack-python:latest"

    def test_goal_based_stack_to_image(self):
        stack = detect_stack_from_goal("Build a REST API with Express and Node.js")
        assert stack == "node"
        assert image_name(stack) == "orion-stack-node:latest"


# ---------------------------------------------------------------------------
# E2E-02: Config disabled → executor refuses run_command
# ---------------------------------------------------------------------------


class TestConfigDisabledBlocksExecution:
    """E2E-02: When execution is disabled in config, executor has no container."""

    @pytest.mark.asyncio
    async def test_disabled_config_no_container(self, sandbox: Path, settings_dir: Path):
        # Config says disabled
        global_settings = settings_dir / "settings.json"
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": False,
                }
            )
        )
        cfg = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=settings_dir / "ara_settings.json",
        )
        assert cfg.enabled is False

        # Executor created without container (as orchestrator would do)
        executor = ARATaskExecutor(sandbox_dir=sandbox)
        task = FakeTask(action_type="run_command", metadata={"command": "echo hi"})
        result = await executor.execute(task)
        assert result["success"] is False
        assert "No session container" in result["error"]


# ---------------------------------------------------------------------------
# E2E-03: Container → Feedback → Success on first try
# ---------------------------------------------------------------------------


class TestContainerFeedbackSuccess:
    """E2E-03: Command succeeds on first attempt via feedback loop."""

    @pytest.mark.asyncio
    async def test_success_first_try(self, sandbox: Path):
        container = FakeContainer()
        container.exec_results = [
            ExecResult(exit_code=0, stdout="Hello World", command="python app.py"),
        ]

        feedback = ExecutionFeedbackLoop(
            container=container,
            fix_provider=RuleBasedFixProvider(),
            max_retries=3,
        )

        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
            execution_feedback=feedback,
        )
        task = FakeTask(
            action_type="run_command",
            metadata={"command": "python app.py"},
        )
        result = await executor.execute(task)

        assert result["success"] is True
        assert "Hello World" in result["output"]
        assert result["confidence"] == 0.9
        assert result["feedback_attempts"] == 1


# ---------------------------------------------------------------------------
# E2E-04: Container → Feedback → Retry → Success
# ---------------------------------------------------------------------------


class TestContainerFeedbackRetry:
    """E2E-04: Command fails, feedback loop fixes it, retry succeeds."""

    @pytest.mark.asyncio
    async def test_retry_after_missing_dep(self, sandbox: Path):
        container = FakeContainer()
        # First exec: fail with missing dep
        # Second exec: install command
        # Third exec: retry succeeds
        container.exec_results = [
            ExecResult(
                exit_code=1,
                stderr="ModuleNotFoundError: No module named 'flask'",
                command="python app.py",
            ),
            ExecResult(exit_code=0, stdout="installed flask", command="pip install flask"),
            ExecResult(exit_code=0, stdout="Server running", command="python app.py"),
        ]

        feedback = ExecutionFeedbackLoop(
            container=container,
            fix_provider=RuleBasedFixProvider(),
            max_retries=3,
        )

        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
            execution_feedback=feedback,
        )
        task = FakeTask(
            action_type="run_command",
            metadata={"command": "python app.py"},
        )
        result = await executor.execute(task)

        assert result["success"] is True
        assert result["confidence"] == 0.7  # Lower due to retries
        assert result["feedback_attempts"] >= 2


# ---------------------------------------------------------------------------
# E2E-05: Error classification → Fix suggestion pipeline
# ---------------------------------------------------------------------------


class TestErrorClassificationFixPipeline:
    """E2E-05: classify_error → RuleBasedFixProvider → correct fix."""

    @pytest.mark.asyncio
    async def test_python_missing_module(self):
        stderr = "ModuleNotFoundError: No module named 'requests'"
        category = classify_error(stderr)
        assert category == ErrorCategory.MISSING_DEPENDENCY

        provider = RuleBasedFixProvider()
        fix = await provider.suggest_fix(
            command="python scraper.py",
            stderr=stderr,
            stdout="",
            error_category=category,
            previous_fixes=[],
        )
        assert fix.install_command == "pip install requests"
        assert fix.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_node_missing_module(self):
        stderr = "Error: Cannot find module 'express'"
        category = classify_error(stderr)
        assert category == ErrorCategory.MISSING_DEPENDENCY

        provider = RuleBasedFixProvider()
        fix = await provider.suggest_fix(
            command="node server.js",
            stderr=stderr,
            stdout="",
            error_category=category,
            previous_fixes=[],
        )
        assert fix.install_command == "npm install express"

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        stderr = "FileNotFoundError: No such file or directory: 'config.json'"
        category = classify_error(stderr)
        assert category == ErrorCategory.FILE_NOT_FOUND

        provider = RuleBasedFixProvider()
        fix = await provider.suggest_fix(
            command="python app.py",
            stderr=stderr,
            stdout="",
            error_category=category,
            previous_fixes=[],
        )
        assert fix.file_path is not None


# ---------------------------------------------------------------------------
# E2E-06: Install action through executor
# ---------------------------------------------------------------------------


class TestInstallThroughExecutor:
    """E2E-06: install_deps flows through container.exec_install()."""

    @pytest.mark.asyncio
    async def test_install_flow(self, sandbox: Path):
        container = FakeContainer()
        container.install_results = [
            ExecResult(
                exit_code=0,
                stdout="Successfully installed flask-2.3.0",
                command="pip install flask",
            ),
        ]

        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
        )
        task = FakeTask(
            action_type="install_deps",
            metadata={"install_command": "pip install flask"},
        )
        result = await executor.execute(task)

        assert result["success"] is True
        assert "flask" in result["output"]
        assert container.install_calls == ["pip install flask"]


# ---------------------------------------------------------------------------
# E2E-07: Test runner through executor
# ---------------------------------------------------------------------------


class TestRunTestsThroughExecutor:
    """E2E-07: run_tests_sandbox runs tests and scores output."""

    @pytest.mark.asyncio
    async def test_all_pass(self, sandbox: Path):
        container = FakeContainer()
        container.exec_results = [
            ExecResult(exit_code=0, stdout="5 passed in 2.1s", command="pytest"),
        ]

        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
        )
        task = FakeTask(
            action_type="run_tests_sandbox",
            metadata={"test_command": "pytest tests/"},
        )
        result = await executor.execute(task)

        assert result["success"] is True
        assert result["confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_some_fail(self, sandbox: Path):
        container = FakeContainer()
        container.exec_results = [
            ExecResult(
                exit_code=1, stdout="3 passed, 2 failed", stderr="AssertionError", command="pytest"
            ),
        ]

        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
        )
        task = FakeTask(
            action_type="run_tests_sandbox",
            metadata={"test_command": "pytest tests/"},
        )
        result = await executor.execute(task)

        assert result["success"] is False
        assert result["confidence"] < 0.5


# ---------------------------------------------------------------------------
# E2E-08: Full pipeline — config + stack + executor + feedback
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """E2E-08: Complete pipeline from config to execution result."""

    @pytest.mark.asyncio
    async def test_end_to_end(self, tmp_path: Path, sandbox: Path):
        # 1. Config
        settings_dir = tmp_path / ".orion"
        settings_dir.mkdir()
        global_settings = settings_dir / "settings.json"
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": True,
                    "ara_resource_profile": "standard",
                }
            )
        )
        cfg = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=settings_dir / "ara_settings.json",
        )
        assert cfg.enabled is True

        # 2. Stack detection
        project = tmp_path / "project"
        project.mkdir()
        (project / "package.json").write_text('{"name": "app"}\n')
        stack = detect_stack(project)
        assert stack == "node"

        # 3. Container + feedback
        container = FakeContainer()
        container.exec_results = [
            ExecResult(exit_code=0, stdout="Server started on port 3000", command="node app.js"),
        ]

        feedback = ExecutionFeedbackLoop(
            container=container,
            fix_provider=RuleBasedFixProvider(),
            max_retries=cfg.max_feedback_retries,
        )

        # 4. Executor
        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
            execution_feedback=feedback,
        )

        # 5. Execute
        task = FakeTask(
            action_type="run_command",
            metadata={"command": "node app.js"},
        )
        result = await executor.execute(task)

        assert result["success"] is True
        assert "Server started" in result["output"]
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_end_to_end_with_retry(self, tmp_path: Path, sandbox: Path):
        """Full pipeline: command fails, feedback fixes, retry succeeds."""
        settings_dir = tmp_path / ".orion"
        settings_dir.mkdir()
        global_settings = settings_dir / "settings.json"
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": True,
                }
            )
        )
        cfg = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=settings_dir / "ara_settings.json",
        )

        container = FakeContainer()
        container.exec_results = [
            # 1st: fail
            ExecResult(exit_code=1, stderr="No module named 'pandas'", command="python analyze.py"),
            # 2nd: install fix
            ExecResult(exit_code=0, stdout="installed", command="pip install pandas"),
            # 3rd: retry succeeds
            ExecResult(exit_code=0, stdout="Analysis complete", command="python analyze.py"),
        ]

        feedback = ExecutionFeedbackLoop(
            container=container,
            fix_provider=RuleBasedFixProvider(),
            max_retries=cfg.max_feedback_retries,
        )

        executor = ARATaskExecutor(
            sandbox_dir=sandbox,
            session_container=container,
            execution_feedback=feedback,
        )

        task = FakeTask(
            action_type="run_command",
            metadata={"command": "python analyze.py"},
        )
        result = await executor.execute(task)

        assert result["success"] is True
        assert result["feedback_attempts"] >= 2
        assert result["confidence"] == 0.7  # Lowered due to retry
