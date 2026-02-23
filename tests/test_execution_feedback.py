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
"""Tests for ExecutionFeedbackLoop — LLM-driven error correction.

Tests EF-01 through EF-10+ as specified in Phase 4A.2.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.ara.execution_feedback import (
    ErrorCategory,
    ExecutionFeedbackLoop,
    FeedbackResult,
    FixAction,
    LLMFixProvider,
    RuleBasedFixProvider,
    classify_error,
)

# ---------------------------------------------------------------------------
# Minimal ExecResult stub (avoids importing Docker-dependent module in tests)
# ---------------------------------------------------------------------------


@dataclass
class FakeExecResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_seconds: float = 0.1
    command: str = ""
    phase: str = "execute"


# ---------------------------------------------------------------------------
# Fake container
# ---------------------------------------------------------------------------


class FakeSessionContainer:
    """Minimal stub for SessionContainer used in unit tests."""

    def __init__(self):
        self._exec_results: list[FakeExecResult] = []
        self._exec_call_count = 0
        self._install_results: list[FakeExecResult] = []
        self._install_call_count = 0
        self._written_files: dict[str, str] = {}

    def queue_exec(self, *results: FakeExecResult) -> None:
        """Queue exec results to be returned in order."""
        self._exec_results.extend(results)

    def queue_install(self, *results: FakeExecResult) -> None:
        """Queue install results to be returned in order."""
        self._install_results.extend(results)

    async def exec(
        self, command: str, timeout: int = 120, phase: str = "execute"
    ) -> FakeExecResult:
        self._exec_call_count += 1
        if self._exec_results:
            return self._exec_results.pop(0)
        return FakeExecResult(exit_code=0, command=command, phase=phase)

    async def exec_install(self, command: str, timeout: int = 300) -> FakeExecResult:
        self._install_call_count += 1
        if self._install_results:
            return self._install_results.pop(0)
        return FakeExecResult(exit_code=0, command=command, phase="install")

    async def write_file(self, path: str, content: str) -> bool:
        self._written_files[path] = content
        return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def container() -> FakeSessionContainer:
    return FakeSessionContainer()


@pytest.fixture
def rule_provider() -> RuleBasedFixProvider:
    return RuleBasedFixProvider()


# ---------------------------------------------------------------------------
# EF-01: Error classification
# ---------------------------------------------------------------------------


class TestErrorClassification:
    """EF-01: classify_error correctly categorizes errors."""

    def test_syntax_error_python(self):
        assert classify_error("SyntaxError: invalid syntax") == ErrorCategory.SYNTAX

    def test_indentation_error(self):
        assert classify_error("IndentationError: unexpected indent") == ErrorCategory.SYNTAX

    def test_missing_module_python(self):
        assert (
            classify_error("ModuleNotFoundError: No module named 'flask'")
            == ErrorCategory.MISSING_DEPENDENCY
        )

    def test_import_error(self):
        assert (
            classify_error("ImportError: cannot import name 'foo'")
            == ErrorCategory.MISSING_DEPENDENCY
        )

    def test_node_module_missing(self):
        assert classify_error("Cannot find module 'express'") == ErrorCategory.MISSING_DEPENDENCY

    def test_command_not_found(self):
        assert classify_error("rustc: command not found") == ErrorCategory.MISSING_DEPENDENCY

    def test_file_not_found(self):
        assert (
            classify_error("FileNotFoundError: [Errno 2] No such file or directory: 'app.py'")
            == ErrorCategory.FILE_NOT_FOUND
        )

    def test_no_such_file(self):
        assert classify_error("ls: No such file or directory") == ErrorCategory.FILE_NOT_FOUND

    def test_permission_denied(self):
        assert classify_error("Permission denied") == ErrorCategory.PERMISSION

    def test_timeout(self):
        assert classify_error("Command timed out after 30s", exit_code=-1) == ErrorCategory.TIMEOUT

    def test_generic_runtime(self):
        assert (
            classify_error("Traceback (most recent call last):\n  ValueError: bad input")
            == ErrorCategory.RUNTIME
        )

    def test_unknown_error(self):
        assert classify_error("") == ErrorCategory.UNKNOWN


# ---------------------------------------------------------------------------
# EF-02: Rule-based fix provider
# ---------------------------------------------------------------------------


class TestRuleBasedFixProvider:
    """EF-02: RuleBasedFixProvider suggests correct fixes."""

    @pytest.mark.asyncio
    async def test_fix_missing_python_module(self, rule_provider):
        fix = await rule_provider.suggest_fix(
            command="python app.py",
            stderr="ModuleNotFoundError: No module named 'flask'",
            stdout="",
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            previous_fixes=[],
        )
        assert fix.install_command == "pip install flask"
        assert fix.confidence >= 0.5

    @pytest.mark.asyncio
    async def test_fix_missing_node_module(self, rule_provider):
        fix = await rule_provider.suggest_fix(
            command="node app.js",
            stderr="Error: Cannot find module 'express'",
            stdout="",
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            previous_fixes=[],
        )
        assert fix.install_command == "npm install express"

    @pytest.mark.asyncio
    async def test_fix_command_not_found(self, rule_provider):
        fix = await rule_provider.suggest_fix(
            command="rustc main.rs",
            stderr="rustc: command not found",
            stdout="",
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            previous_fixes=[],
        )
        assert "rustc" in fix.description
        assert fix.confidence < 0.5  # Low confidence — can't auto-install

    @pytest.mark.asyncio
    async def test_fix_file_not_found(self, rule_provider):
        fix = await rule_provider.suggest_fix(
            command="python app.py",
            stderr="FileNotFoundError: [Errno 2] No such file or directory: '/workspace/config.json'",
            stdout="",
            error_category=ErrorCategory.FILE_NOT_FOUND,
            previous_fixes=[],
        )
        assert fix.file_path is not None
        assert "config.json" in fix.file_path

    @pytest.mark.asyncio
    async def test_fix_permission_no_autofix(self, rule_provider):
        fix = await rule_provider.suggest_fix(
            command="cat /etc/shadow",
            stderr="Permission denied",
            stdout="",
            error_category=ErrorCategory.PERMISSION,
            previous_fixes=[],
        )
        assert fix.confidence <= 0.1

    @pytest.mark.asyncio
    async def test_fix_timeout_no_autofix(self, rule_provider):
        fix = await rule_provider.suggest_fix(
            command="sleep 999",
            stderr="Command timed out after 30s",
            stdout="",
            error_category=ErrorCategory.TIMEOUT,
            previous_fixes=[],
        )
        assert fix.confidence <= 0.1


# ---------------------------------------------------------------------------
# EF-03: Feedback loop — success on first try
# ---------------------------------------------------------------------------


class TestFeedbackLoopSuccess:
    """EF-03: Feedback loop returns immediately on success."""

    @pytest.mark.asyncio
    async def test_success_no_retry(self, container):
        container.queue_exec(FakeExecResult(exit_code=0, stdout="OK"))
        loop = ExecutionFeedbackLoop(container, max_retries=3)

        result = await loop.run_with_feedback("echo hello")

        assert result.success is True
        assert result.attempts == 1
        assert result.final_exit_code == 0
        assert len(result.fixes_applied) == 0


# ---------------------------------------------------------------------------
# EF-04: Feedback loop — retry with install fix
# ---------------------------------------------------------------------------


class TestFeedbackLoopRetryInstall:
    """EF-04: Feedback loop installs dependency and retries."""

    @pytest.mark.asyncio
    async def test_install_then_succeed(self, container):
        # First attempt: missing module
        container.queue_exec(
            FakeExecResult(
                exit_code=1,
                stderr="ModuleNotFoundError: No module named 'requests'",
            )
        )
        # Install succeeds (via exec_install)
        container.queue_install(
            FakeExecResult(exit_code=0, stdout="Successfully installed requests")
        )
        # Retry succeeds
        container.queue_exec(FakeExecResult(exit_code=0, stdout="OK"))

        loop = ExecutionFeedbackLoop(container, fix_provider=RuleBasedFixProvider(), max_retries=3)
        result = await loop.run_with_feedback("python app.py")

        assert result.success is True
        assert result.attempts == 2
        assert len(result.fixes_applied) == 1
        assert result.fixes_applied[0].install_command == "pip install requests"


# ---------------------------------------------------------------------------
# EF-05: Feedback loop — max retries exhausted
# ---------------------------------------------------------------------------


class TestFeedbackLoopMaxRetries:
    """EF-05: Feedback loop stops after max_retries."""

    @pytest.mark.asyncio
    async def test_exhausts_retries(self, container):
        # All attempts fail with the same error
        for _ in range(5):
            container.queue_exec(
                FakeExecResult(
                    exit_code=1,
                    stderr="ModuleNotFoundError: No module named 'nonexistent_pkg_xyz'",
                )
            )
        # Install always succeeds but module still not importable
        for _ in range(5):
            container.queue_install(FakeExecResult(exit_code=0))

        loop = ExecutionFeedbackLoop(container, fix_provider=RuleBasedFixProvider(), max_retries=2)
        result = await loop.run_with_feedback("python app.py")

        assert result.success is False
        assert result.attempts == 3  # 1 initial + 2 retries
        assert len(result.fixes_applied) == 2


# ---------------------------------------------------------------------------
# EF-06: Feedback loop — low confidence stops retries
# ---------------------------------------------------------------------------


class TestFeedbackLoopLowConfidence:
    """EF-06: Low-confidence fix stops the retry loop early."""

    @pytest.mark.asyncio
    async def test_low_confidence_stops_early(self, container):
        container.queue_exec(FakeExecResult(exit_code=1, stderr="Permission denied"))

        loop = ExecutionFeedbackLoop(container, fix_provider=RuleBasedFixProvider(), max_retries=5)
        result = await loop.run_with_feedback("cat /etc/shadow")

        assert result.success is False
        # Should stop after 1 fix attempt due to low confidence
        assert result.attempts == 1
        assert len(result.fixes_applied) == 1
        assert result.fixes_applied[0].confidence <= 0.1


# ---------------------------------------------------------------------------
# EF-07: Fix action apply — install + command + file write
# ---------------------------------------------------------------------------


class TestApplyFix:
    """EF-07: _apply_fix correctly applies all fix types."""

    @pytest.mark.asyncio
    async def test_apply_install_fix(self, container):
        loop = ExecutionFeedbackLoop(container)
        fix = FixAction(
            description="Install flask",
            install_command="pip install flask",
            confidence=0.8,
        )
        applied = await loop._apply_fix(fix)
        assert applied is True
        assert container._install_call_count == 1

    @pytest.mark.asyncio
    async def test_apply_command_fix(self, container):
        loop = ExecutionFeedbackLoop(container)
        fix = FixAction(
            description="Create directory",
            command="mkdir -p /workspace/src",
            confidence=0.7,
        )
        applied = await loop._apply_fix(fix)
        assert applied is True
        assert container._exec_call_count == 1

    @pytest.mark.asyncio
    async def test_apply_file_write_fix(self, container):
        loop = ExecutionFeedbackLoop(container)
        fix = FixAction(
            description="Create config",
            file_path="/workspace/config.json",
            file_content="{}",
            confidence=0.6,
        )
        applied = await loop._apply_fix(fix)
        assert applied is True
        assert "/workspace/config.json" in container._written_files

    @pytest.mark.asyncio
    async def test_apply_info_only_fix(self, container):
        loop = ExecutionFeedbackLoop(container)
        fix = FixAction(
            description="Cannot auto-fix this",
            confidence=0.0,
        )
        applied = await loop._apply_fix(fix)
        assert applied is False


# ---------------------------------------------------------------------------
# EF-08: LLM fix provider parse
# ---------------------------------------------------------------------------


class TestLLMFixProviderParse:
    """EF-08: LLMFixProvider._parse_llm_response correctly parses output."""

    def test_parse_full_response(self):
        response = (
            "DESCRIPTION: Install missing flask module\n"
            "INSTALL: pip install flask\n"
            "COMMAND: NONE\n"
            "CONFIDENCE: 0.9\n"
        )
        fix = LLMFixProvider._parse_llm_response(response, ErrorCategory.MISSING_DEPENDENCY)
        assert fix.description == "Install missing flask module"
        assert fix.install_command == "pip install flask"
        assert fix.command is None
        assert fix.confidence == 0.9

    def test_parse_command_response(self):
        response = (
            "DESCRIPTION: Create missing directory\n"
            "INSTALL: NONE\n"
            "COMMAND: mkdir -p /workspace/data\n"
            "CONFIDENCE: 0.85\n"
        )
        fix = LLMFixProvider._parse_llm_response(response, ErrorCategory.FILE_NOT_FOUND)
        assert fix.command == "mkdir -p /workspace/data"
        assert fix.install_command is None

    def test_parse_empty_response(self):
        fix = LLMFixProvider._parse_llm_response("", ErrorCategory.UNKNOWN)
        assert fix.description == "LLM suggested fix (could not parse description)"
        assert fix.confidence == 0.5  # default


# ---------------------------------------------------------------------------
# EF-09: Feedback history tracking
# ---------------------------------------------------------------------------


class TestFeedbackHistory:
    """EF-09: Feedback loop tracks history correctly."""

    @pytest.mark.asyncio
    async def test_history_populated(self, container):
        container.queue_exec(FakeExecResult(exit_code=0, stdout="OK"))
        container.queue_exec(FakeExecResult(exit_code=0, stdout="OK2"))

        loop = ExecutionFeedbackLoop(container, max_retries=1)
        await loop.run_with_feedback("echo 1")
        await loop.run_with_feedback("echo 2")

        assert len(loop.history) == 2
        assert loop.history[0].original_command == "echo 1"
        assert loop.history[1].original_command == "echo 2"


# ---------------------------------------------------------------------------
# EF-10: FeedbackResult dataclass
# ---------------------------------------------------------------------------


class TestFeedbackResultDataclass:
    """EF-10: FeedbackResult holds all expected fields."""

    def test_default_values(self):
        r = FeedbackResult()
        assert r.success is False
        assert r.attempts == 0
        assert r.final_exit_code == -1
        assert r.error_category == ErrorCategory.UNKNOWN
        assert r.fixes_applied == []
        assert r.total_duration_seconds == 0.0

    def test_custom_values(self):
        r = FeedbackResult(
            original_command="python app.py",
            success=True,
            attempts=2,
            final_exit_code=0,
            error_category=ErrorCategory.MISSING_DEPENDENCY,
            fixes_applied=[FixAction(description="test")],
        )
        assert r.attempts == 2
        assert len(r.fixes_applied) == 1


# ---------------------------------------------------------------------------
# EF-11: FixAction dataclass
# ---------------------------------------------------------------------------


class TestFixActionDataclass:
    """EF-11: FixAction holds all expected fields."""

    def test_defaults(self):
        f = FixAction()
        assert f.description == ""
        assert f.command is None
        assert f.file_path is None
        assert f.file_content is None
        assert f.install_command is None
        assert f.confidence == 0.5

    def test_install_fix(self):
        f = FixAction(
            description="Install flask",
            install_command="pip install flask",
            category=ErrorCategory.MISSING_DEPENDENCY,
            confidence=0.8,
        )
        assert f.install_command == "pip install flask"
        assert f.category == ErrorCategory.MISSING_DEPENDENCY
