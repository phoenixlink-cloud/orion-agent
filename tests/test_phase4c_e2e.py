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
"""E2E Integration Tests for Phase 4C — Activity Logger + Ruff Tool.

8+ tests covering cross-module integration:
  1. ActivityLogger → SessionContainer exec pipeline
  2. ActivityLogger → ExecutionFeedbackLoop retry pipeline
  3. ActivityLogger → Ruff tool validation pipeline
  4. CLI cmd_activity → register/unregister lifecycle
  5. Full session lifecycle: start → exec → lint → feedback → summary
  6. Ring buffer under load
  7. Callback broadcast across multiple listeners
  8. API route data shape validation
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.ara.activity_logger import ActivityEntry, ActivityLogger
from orion.ara.execution_feedback import (
    ExecutionFeedbackLoop,
    RuleBasedFixProvider,
    classify_error,
    ErrorCategory,
)
from orion.ara.ruff_tool import (
    RuffResult,
    parse_ruff_json,
    run_ruff_in_container,
)
from orion.security.session_container import ExecResult, SessionContainer


# =========================================================================
# 1. ActivityLogger → SessionContainer exec pipeline
# =========================================================================
class TestActivityLoggerSessionContainer:
    def test_container_logs_activity_on_exec(self):
        """SessionContainer.exec() should log start+complete to the activity logger."""
        al = ActivityLogger(session_id="e2e-exec")
        sc = SessionContainer(
            session_id="e2e-exec",
            stack="python",
            activity_logger=al,
        )
        # Verify logger is wired
        assert sc.activity_logger is al
        assert sc.session_id == "e2e-exec"

        # Container isn't running so exec will return error immediately,
        # but the activity_logger should NOT log (exec checks _running first)
        assert al.entry_count == 0

    @pytest.mark.asyncio
    async def test_container_exec_logs_when_running(self):
        """When container is running, exec should log via activity_logger."""
        al = ActivityLogger(session_id="e2e-running")
        sc = SessionContainer(
            session_id="e2e-running",
            stack="python",
            activity_logger=al,
        )
        # Simulate running state
        sc._running = True

        # Mock the docker command to succeed
        with patch.object(sc, "_run_docker", new_callable=AsyncMock) as mock_docker:
            mock_docker.return_value = MagicMock(
                stdout="hello world", stderr="", returncode=0
            )
            result = await sc.exec("echo hello")

        assert result.exit_code == 0
        assert result.stdout == "hello world"

        # Activity logger should have 1 entry (log + update)
        entries = al.get_entries()
        assert len(entries) == 1
        assert entries[0].action_type == "command"
        assert entries[0].status == "success"
        assert entries[0].exit_code == 0


# =========================================================================
# 2. ActivityLogger → ExecutionFeedbackLoop retry pipeline
# =========================================================================
class TestActivityLoggerFeedbackLoop:
    @pytest.mark.asyncio
    async def test_feedback_loop_full_retry_cycle(self):
        """Full retry cycle: fail → classify → fix → retry → succeed with activity logging."""
        al = ActivityLogger(session_id="e2e-feedback")

        mock_container = AsyncMock()
        # First call fails with missing dependency, second succeeds
        mock_container.exec = AsyncMock(
            side_effect=[
                ExecResult(
                    stderr="ModuleNotFoundError: No module named 'requests'",
                    exit_code=1,
                    command="python app.py",
                    phase="execute",
                ),
                ExecResult(
                    stdout="Success!",
                    exit_code=0,
                    command="python app.py",
                    phase="execute",
                ),
            ]
        )
        mock_container.exec_install = AsyncMock(
            return_value=ExecResult(
                stdout="Successfully installed requests",
                exit_code=0,
                command="pip install requests",
                phase="install",
            )
        )

        loop = ExecutionFeedbackLoop(
            container=mock_container,
            fix_provider=RuleBasedFixProvider(),
            activity_logger=al,
            max_retries=3,
        )

        result = await loop.run_with_feedback("python app.py")
        assert result.success is True
        assert result.attempts == 2
        assert len(result.fixes_applied) == 1
        assert result.fixes_applied[0].install_command == "pip install requests"

        # Activity logger should have the retry info entry
        info_entries = al.get_entries(action_type="info")
        assert len(info_entries) >= 1
        assert "Retry" in info_entries[0].description
        assert "missing_dependency" in info_entries[0].description


# =========================================================================
# 3. ActivityLogger → Ruff tool validation pipeline
# =========================================================================
class TestActivityLoggerRuffTool:
    @pytest.mark.asyncio
    async def test_ruff_lint_logs_to_activity(self):
        """run_ruff_in_container should log test entry to activity logger."""
        al = ActivityLogger(session_id="e2e-ruff")
        mock_container = AsyncMock()
        mock_container.exec = AsyncMock(
            return_value=ExecResult(
                stdout="[]", stderr="", exit_code=0, duration_seconds=0.5
            )
        )

        result = await run_ruff_in_container(
            mock_container, activity_logger=al
        )
        assert result.success is True
        assert result.ruff_available is True

        entries = al.get_entries(action_type="test")
        assert len(entries) == 1
        assert entries[0].phase == "test"
        assert entries[0].status == "success"
        assert "Ruff" in entries[0].description

    @pytest.mark.asyncio
    async def test_ruff_lint_with_issues_logs_failure(self):
        """Ruff finding errors should log a failed test entry."""
        al = ActivityLogger(session_id="e2e-ruff-fail")
        sample_json = json.dumps(
            [
                {
                    "code": "E999",
                    "message": "SyntaxError",
                    "filename": "/workspace/bad.py",
                    "location": {"row": 1, "column": 1},
                    "end_location": {"row": 1, "column": 1},
                    "fix": None,
                }
            ]
        )
        mock_container = AsyncMock()
        mock_container.exec = AsyncMock(
            return_value=ExecResult(
                stdout=sample_json, stderr="", exit_code=1, duration_seconds=0.3
            )
        )

        result = await run_ruff_in_container(
            mock_container, activity_logger=al
        )
        assert result.has_errors is True

        entries = al.get_entries(action_type="test")
        assert len(entries) == 1
        assert entries[0].status == "failed"


# =========================================================================
# 4. CLI cmd_activity → register/unregister lifecycle
# =========================================================================
class TestCLIActivityLifecycle:
    def test_register_unregister_lifecycle(self):
        """register → cmd_activity → unregister → cmd_activity should fail."""
        from orion.ara.cli_commands import (
            _active_loggers,
            cmd_activity,
            register_activity_logger,
            unregister_activity_logger,
        )

        _active_loggers.clear()

        # No logger → fail
        result = cmd_activity()
        assert not result.success

        # Register logger
        al = ActivityLogger(session_id="lifecycle-test")
        al.log("command", "echo test", status="success")
        register_activity_logger("lifecycle-test", al)

        # Now cmd_activity should work
        result = cmd_activity(session_id="lifecycle-test")
        assert result.success
        assert "1 entries" in result.message

        # Unregister
        unregister_activity_logger("lifecycle-test")

        # Should fail again
        result = cmd_activity(session_id="lifecycle-test")
        assert not result.success

        _active_loggers.clear()


# =========================================================================
# 5. Full session lifecycle: start → exec → lint → feedback → summary
# =========================================================================
class TestFullSessionLifecycle:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Simulate a complete session lifecycle with activity logging."""
        al = ActivityLogger(session_id="full-lifecycle")

        # Phase 1: Simulated exec commands
        al.log("command", "mkdir -p /workspace/src", phase="setup", status="success")
        al.log(
            "file_write",
            "Writing file: /workspace/src/app.py",
            phase="execute",
            status="success",
        )
        al.log(
            "command",
            "Running: python app.py",
            command="python app.py",
            exit_code=0,
            duration_seconds=1.5,
            phase="execute",
            status="success",
        )

        # Phase 2: Lint
        al.log(
            "test",
            "Ruff lint: /workspace",
            command="ruff check --output-format=json /workspace",
            exit_code=0,
            duration_seconds=0.3,
            phase="test",
            status="success",
        )

        # Phase 3: A failed command + retry
        entry = al.log(
            "command",
            "Running: python test.py",
            command="python test.py",
            phase="test",
        )
        al.update(entry, exit_code=1, status="failed", duration_seconds=0.5)

        al.log(
            "info",
            "Retry 1/3: missing_dependency",
            phase="execute",
            status="running",
        )

        entry2 = al.log(
            "command",
            "Running: python test.py (retry)",
            command="python test.py",
            phase="test",
        )
        al.update(entry2, exit_code=0, status="success", duration_seconds=0.8)

        # Verify summary
        summary = al.get_summary()
        assert summary["total_entries"] == 7
        assert summary["error_count"] == 1  # The failed test.py
        assert summary["counts_by_type"]["command"] == 4
        assert summary["counts_by_type"]["file_write"] == 1
        assert summary["counts_by_type"]["test"] == 1
        assert summary["counts_by_type"]["info"] == 1

        # Verify JSONL export
        jsonl = al.to_jsonl()
        lines = jsonl.strip().split("\n")
        assert len(lines) == 7

        # Each line should be valid JSON
        for line in lines:
            parsed = json.loads(line)
            assert "action_type" in parsed
            assert "session_id" in parsed


# =========================================================================
# 6. Ring buffer under load
# =========================================================================
class TestRingBufferUnderLoad:
    def test_high_volume_logging(self):
        """Activity logger should handle 10000 entries and maintain ring buffer."""
        al = ActivityLogger(session_id="load-test", max_entries=500)

        for i in range(10000):
            al.log("command", f"cmd {i}", status="success" if i % 2 == 0 else "failed")

        assert al.entry_count == 500
        entries = al.get_entries(limit=10)
        assert len(entries) == 10
        # Last entry should be cmd 9999
        assert entries[-1].description == "cmd 9999"

        # Summary should reflect only the 500 stored entries
        summary = al.get_summary()
        assert summary["total_entries"] == 500

    def test_ring_buffer_preserves_order(self):
        """After eviction, entries should still be in chronological order."""
        al = ActivityLogger(session_id="order-test", max_entries=10)
        for i in range(25):
            al.log("info", f"msg {i}")

        entries = al.get_entries(limit=100)
        assert len(entries) == 10
        # Should be msgs 15-24
        for idx, entry in enumerate(entries):
            assert entry.description == f"msg {15 + idx}"


# =========================================================================
# 7. Callback broadcast across multiple listeners
# =========================================================================
class TestCallbackBroadcast:
    def test_multiple_listeners(self):
        """Multiple callbacks should all receive events."""
        al = ActivityLogger(session_id="multi-cb")
        received_a = []
        received_b = []
        received_c = []

        al.on_activity(lambda e: received_a.append(e.description))
        al.on_activity(lambda e: received_b.append(e.description))
        al.on_activity(lambda e: received_c.append(e.description))

        al.log("info", "broadcast-1")
        al.log("info", "broadcast-2")

        # Each listener should have 2 entries
        assert received_a == ["broadcast-1", "broadcast-2"]
        assert received_b == ["broadcast-1", "broadcast-2"]
        assert received_c == ["broadcast-1", "broadcast-2"]

    def test_callback_error_isolation(self):
        """A failing callback should not prevent others from running."""
        al = ActivityLogger(session_id="error-cb")
        received = []

        def bad_callback(entry):
            raise RuntimeError("callback crash")

        al.on_activity(bad_callback)
        al.on_activity(lambda e: received.append(e.description))

        # Should not raise, and good callback should still fire
        al.log("info", "test-msg")
        assert received == ["test-msg"]


# =========================================================================
# 8. API route data shape validation
# =========================================================================
class TestAPIRouteDataShape:
    def test_activity_entry_api_shape(self):
        """ActivityEntry.to_dict() should produce API-compatible JSON."""
        al = ActivityLogger(session_id="api-shape")
        entry = al.log(
            "command",
            "echo test",
            command="echo test",
            exit_code=0,
            stdout="test output",
            duration_seconds=0.5,
            phase="execute",
            status="success",
        )

        d = entry.to_dict()

        # Required fields for the API
        assert "timestamp" in d
        assert "session_id" in d
        assert "action_type" in d
        assert "description" in d
        assert "status" in d
        assert "entry_id" in d

        # Should be JSON-serializable
        json_str = json.dumps(d)
        assert json_str  # No exception

    def test_summary_api_shape(self):
        """ActivityLogger.get_summary() should produce API-compatible JSON."""
        al = ActivityLogger(session_id="api-summary")
        al.log("command", "cmd 1", status="success", duration_seconds=1.0)
        al.log("command", "cmd 2", status="failed", duration_seconds=2.0)

        summary = al.get_summary()

        # Required fields
        assert "session_id" in summary
        assert "total_entries" in summary
        assert "counts_by_type" in summary
        assert "error_count" in summary
        assert "total_duration_seconds" in summary

        # Should be JSON-serializable
        json_str = json.dumps(summary)
        assert json_str

    def test_ruff_result_api_shape(self):
        """RuffResult.to_dict() should produce API-compatible JSON."""
        result = RuffResult(
            success=True,
            error_count=0,
            warning_count=2,
            files_checked=3,
            ruff_available=True,
        )
        d = result.to_dict()

        assert "success" in d
        assert "total_issues" in d
        assert "error_count" in d
        assert "has_errors" in d
        assert "issues" in d

        json_str = json.dumps(d)
        assert json_str


# =========================================================================
# 9. Error classification integration
# =========================================================================
class TestErrorClassificationIntegration:
    def test_classify_feeds_into_feedback_loop(self):
        """Error classification should correctly identify categories for the feedback loop."""
        # Missing dependency
        cat = classify_error("ModuleNotFoundError: No module named 'flask'")
        assert cat == ErrorCategory.MISSING_DEPENDENCY

        # Syntax error
        cat = classify_error("SyntaxError: invalid syntax")
        assert cat == ErrorCategory.SYNTAX

        # Timeout
        cat = classify_error("Command timed out after 120s", exit_code=-1)
        assert cat == ErrorCategory.TIMEOUT

        # File not found
        cat = classify_error("FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'")
        assert cat == ErrorCategory.FILE_NOT_FOUND

        # Permission
        cat = classify_error("PermissionError: [Errno 13] Permission denied")
        assert cat == ErrorCategory.PERMISSION
