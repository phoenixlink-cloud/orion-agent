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
"""Phase 4B End-to-End Integration Tests.

Tests 4B-E2E-01 through 4B-E2E-04 validating the full Phase 4B pipeline:
  multi-step workflows + registry whitelist + configurable resource profiles

Docker is fully mocked — these tests exercise cross-module integration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from orion.ara.execution_config import load_execution_settings
from orion.ara.execution_feedback import (
    ExecutionFeedbackLoop,
    RuleBasedFixProvider,
)
from orion.ara.execution_step import (
    ExecutionStep,
    WorkflowRunner,
    extract_steps,
)
from orion.ara.task_executor import ARATaskExecutor
from orion.security.registry_whitelist import (
    get_install_phase_domains,
    get_registry_domains,
)
from orion.security.sandbox_config import get_profile, ResourceProfile
from orion.security.session_container import ExecResult
from orion.security.stack_detector import detect_stack


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------


class FakeContainer:
    """Container stub for E2E tests."""

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
# 4B-E2E-01: Config → Profile → Workflow full pipeline
# ---------------------------------------------------------------------------


class TestConfigProfileWorkflow:
    """4B-E2E-01: Config enables execution, profile resolved, workflow runs."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, tmp_path: Path):
        # 1. Config: enable execution with heavy profile
        settings_dir = tmp_path / ".orion"
        settings_dir.mkdir()
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
        ara_settings.write_text(
            json.dumps(
                {"execution": {"resource_profiles": {"heavy": {"memory": "8g", "cpus": "6"}}}}
            )
        )

        # 2. Resolve config
        cfg = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert cfg.enabled is True
        assert cfg.resource_profile == "heavy"

        # 3. Resolve profile with user override
        profile = get_profile("heavy", ara_settings)
        assert profile.memory == "8g"
        assert profile.cpus == "6"
        docker_args = profile.to_docker_args()
        assert "--memory=8g" in docker_args

        # 4. Detect stack
        project = tmp_path / "project"
        project.mkdir()
        (project / "requirements.txt").write_text("flask\nrequests\n")
        stack = detect_stack(project)
        assert stack == "python"

        # 5. Get registry domains for install phase
        domains = get_registry_domains(stack)
        assert "pypi.org" in domains

        # 6. Multi-step workflow
        container = FakeContainer()
        container.install_results = [
            ExecResult(exit_code=0, stdout="installed flask", command="pip install flask"),
        ]
        container.exec_results = [
            ExecResult(exit_code=0, stdout="Running", command="python app.py"),
            ExecResult(exit_code=0, stdout="5 passed", command="pytest"),
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


# ---------------------------------------------------------------------------
# 4B-E2E-02: Multi-step workflow through executor with registry isolation
# ---------------------------------------------------------------------------


class TestWorkflowExecutorRegistryIsolation:
    """4B-E2E-02: Executor runs workflow; registries are stack-specific."""

    @pytest.mark.asyncio
    async def test_node_workflow_with_registry(self, tmp_path: Path):
        # Stack detection
        project = tmp_path / "project"
        project.mkdir()
        (project / "package.json").write_text('{"name":"app"}\n')
        stack = detect_stack(project)
        assert stack == "node"

        # Registry check: Node registries, no Python
        domains = get_registry_domains(stack)
        assert "registry.npmjs.org" in domains
        assert "pypi.org" not in domains

        # Workflow execution
        container = FakeContainer()
        container.install_results = [
            ExecResult(exit_code=0, stdout="added 50 packages", command="npm install"),
        ]
        container.exec_results = [
            ExecResult(exit_code=0, stdout="listening on 3000", command="node server.js"),
        ]

        executor = ARATaskExecutor(
            sandbox_dir=tmp_path / "sandbox",
            session_container=container,
        )

        @dataclass
        class WorkflowTask:
            task_id: str = "node-wf"
            title: str = "Setup Node app"
            description: str = ""
            action_type: str = "run_command"
            metadata: dict = field(
                default_factory=lambda: {
                    "execution_steps": [
                        {"action": "install_deps", "command": "npm install"},
                        {"action": "run_command", "command": "node server.js"},
                    ]
                }
            )

        result = await executor.execute(WorkflowTask())
        assert result["success"] is True
        assert result["completed_steps"] == 2
        assert container.install_calls == ["npm install"]
        assert container.exec_calls == ["node server.js"]


# ---------------------------------------------------------------------------
# 4B-E2E-03: Profile + Registry + Extras from settings
# ---------------------------------------------------------------------------


class TestProfileRegistryExtras:
    """4B-E2E-03: User overrides for profiles and extra registries combine."""

    def test_combined_config(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps(
                {
                    "execution": {
                        "resource_profiles": {"standard": {"memory": "4g", "pids": 512}},
                        "extra_registries": ["private.pypi.corp.dev"],
                    }
                }
            )
        )

        # Profile with override
        profile = get_profile("standard", settings)
        assert profile.memory == "4g"
        assert profile.pids == 512
        assert profile.cpus == "2"  # Default preserved

        # Install-phase domains include extra
        domains = get_install_phase_domains("python", settings)
        assert "pypi.org" in domains
        assert "private.pypi.corp.dev" in domains
        assert "github.com" in domains

        # Node stack doesn't get Python registries
        node_domains = get_install_phase_domains("node", settings)
        assert "registry.npmjs.org" in node_domains
        assert "pypi.org" not in node_domains
        # But extra is shared
        assert "private.pypi.corp.dev" in node_domains


# ---------------------------------------------------------------------------
# 4B-E2E-04: Workflow fail-fast + feedback retry pipeline
# ---------------------------------------------------------------------------


class TestWorkflowFailFastFeedback:
    """4B-E2E-04: Multi-step workflow with feedback-driven retry."""

    @pytest.mark.asyncio
    async def test_workflow_with_feedback_retry(self, tmp_path: Path):
        container = FakeContainer()
        # Step 1 (install): succeeds
        container.install_results = [
            ExecResult(exit_code=0, stdout="installed", command="pip install flask"),
        ]
        # Step 2 (run_command via feedback): fail → fix → succeed
        container.exec_results = [
            # First attempt: fail with missing dep
            ExecResult(
                exit_code=1,
                stderr="ModuleNotFoundError: No module named 'requests'",
                command="python app.py",
            ),
            # Fix: install requests
            ExecResult(exit_code=0, stdout="installed requests", command="pip install requests"),
            # Retry: succeed
            ExecResult(exit_code=0, stdout="Server started", command="python app.py"),
        ]

        feedback = ExecutionFeedbackLoop(
            container=container,
            fix_provider=RuleBasedFixProvider(),
            max_retries=3,
        )

        steps = [
            ExecutionStep(step_id="s1", action="install_deps", command="pip install flask"),
            ExecutionStep(step_id="s2", action="run_command", command="python app.py"),
        ]

        runner = WorkflowRunner(container=container, feedback=feedback)
        result = await runner.run(steps)

        assert result.success is True
        assert result.completed_count == 2
        assert result.failed_count == 0
        # Install was called separately for step 1
        assert "pip install flask" in container.install_calls
