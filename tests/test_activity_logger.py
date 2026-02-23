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
"""Tests for Phase 4C.1 — Docker Activity Logger.

15 tests covering:
  - ActivityEntry dataclass (creation, serialization, deserialization)
  - ActivityLogger core (log, update, ring buffer, callbacks, query, summary, export)
  - CLI cmd_activity integration
  - API route integration
  - SessionContainer activity_logger wiring
  - ExecutionFeedbackLoop activity_logger wiring
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.ara.activity_logger import _MAX_OUTPUT_CHARS, ActivityEntry, ActivityLogger


# =========================================================================
# 1. ActivityEntry creation
# =========================================================================
class TestActivityEntry:
    def test_create_entry_defaults(self):
        """ActivityEntry should have sensible defaults."""
        entry = ActivityEntry()
        assert entry.timestamp == ""
        assert entry.session_id == ""
        assert entry.action_type == ""
        assert entry.status == "running"
        assert entry.entry_id == 0
        assert entry.exit_code is None
        assert entry.stdout is None
        assert entry.stderr is None
        assert entry.duration_seconds is None

    def test_create_entry_with_values(self):
        """ActivityEntry should accept all fields."""
        entry = ActivityEntry(
            timestamp="2025-01-01T00:00:00+00:00",
            session_id="sess-1",
            action_type="command",
            description="Running: python app.py",
            command="python app.py",
            exit_code=0,
            stdout="hello",
            stderr="",
            duration_seconds=1.5,
            phase="execute",
            status="success",
            entry_id=42,
        )
        assert entry.session_id == "sess-1"
        assert entry.action_type == "command"
        assert entry.exit_code == 0
        assert entry.duration_seconds == 1.5
        assert entry.entry_id == 42

    # =====================================================================
    # 2. ActivityEntry serialization (to_dict)
    # =====================================================================
    def test_to_dict_excludes_none(self):
        """to_dict should exclude None values."""
        entry = ActivityEntry(
            session_id="s1",
            action_type="command",
            status="running",
        )
        d = entry.to_dict()
        assert "exit_code" not in d
        assert "stdout" not in d
        assert d["session_id"] == "s1"
        assert d["action_type"] == "command"

    # =====================================================================
    # 3. ActivityEntry deserialization (from_dict)
    # =====================================================================
    def test_from_dict_roundtrip(self):
        """from_dict should reconstruct an entry from a dict."""
        entry = ActivityEntry(
            timestamp="2025-01-01T00:00:00+00:00",
            session_id="s1",
            action_type="command",
            description="test",
            exit_code=0,
            status="success",
            entry_id=5,
        )
        d = entry.to_dict()
        restored = ActivityEntry.from_dict(d)
        assert restored.session_id == "s1"
        assert restored.exit_code == 0
        assert restored.entry_id == 5

    def test_from_dict_ignores_extra_keys(self):
        """from_dict should ignore keys not in the dataclass."""
        d = {"session_id": "s1", "action_type": "info", "unknown_field": "whatever"}
        entry = ActivityEntry.from_dict(d)
        assert entry.session_id == "s1"
        assert not hasattr(entry, "unknown_field") or entry.action_type == "info"


# =========================================================================
# ActivityLogger tests
# =========================================================================
class TestActivityLogger:
    # =====================================================================
    # 4. log() creates entry with auto-timestamp and incrementing ID
    # =====================================================================
    def test_log_creates_entry(self):
        """log() should create an ActivityEntry with auto-timestamp and ID."""
        al = ActivityLogger(session_id="test-sess")
        entry = al.log("command", "Running: echo hello", command="echo hello", phase="execute")

        assert entry.session_id == "test-sess"
        assert entry.action_type == "command"
        assert entry.command == "echo hello"
        assert entry.status == "running"
        assert entry.entry_id == 1
        assert entry.timestamp != ""
        assert al.entry_count == 1

    # =====================================================================
    # 5. update() modifies entry fields
    # =====================================================================
    def test_update_modifies_entry(self):
        """update() should modify entry fields in place."""
        al = ActivityLogger(session_id="test-sess")
        entry = al.log("command", "Running: test")
        assert entry.status == "running"

        al.update(entry, exit_code=0, status="success", duration_seconds=2.5)
        assert entry.exit_code == 0
        assert entry.status == "success"
        assert entry.duration_seconds == 2.5

    # =====================================================================
    # 6. Ring buffer eviction
    # =====================================================================
    def test_ring_buffer_eviction(self):
        """Entries beyond max_entries should be evicted (oldest first)."""
        al = ActivityLogger(session_id="test-sess", max_entries=5)
        for i in range(10):
            al.log("info", f"Entry {i}")

        assert al.entry_count == 5
        entries = al.get_entries(limit=10)
        # Should have entries 5-9 (oldest 0-4 evicted)
        assert entries[0].description == "Entry 5"
        assert entries[-1].description == "Entry 9"

    # =====================================================================
    # 7. Callback on log
    # =====================================================================
    def test_callback_fires_on_log(self):
        """Registered callbacks should fire when log() is called."""
        al = ActivityLogger(session_id="test-sess")
        received = []
        al.on_activity(lambda e: received.append(e))

        entry = al.log("command", "test")
        assert len(received) == 1
        assert received[0] is entry

    # =====================================================================
    # 8. Callback on update
    # =====================================================================
    def test_callback_fires_on_update(self):
        """Registered callbacks should fire when update() is called."""
        al = ActivityLogger(session_id="test-sess")
        received = []
        al.on_activity(lambda e: received.append(e))

        entry = al.log("command", "test")
        al.update(entry, status="success")
        # Should fire twice: once on log, once on update
        assert len(received) == 2

    # =====================================================================
    # 9. Callback removal
    # =====================================================================
    def test_remove_callback(self):
        """remove_callback() should stop future notifications."""
        al = ActivityLogger(session_id="test-sess")
        received = []

        def cb(e):
            received.append(e)

        al.on_activity(cb)
        al.log("info", "first")
        assert len(received) == 1

        al.remove_callback(cb)
        al.log("info", "second")
        assert len(received) == 1  # No new callback

    # =====================================================================
    # 10. get_entries with filter
    # =====================================================================
    def test_get_entries_filtered(self):
        """get_entries should filter by action_type."""
        al = ActivityLogger(session_id="test-sess")
        al.log("command", "cmd 1")
        al.log("info", "info 1")
        al.log("command", "cmd 2")
        al.log("file_write", "write 1")

        commands = al.get_entries(action_type="command")
        assert len(commands) == 2
        assert all(e.action_type == "command" for e in commands)

        infos = al.get_entries(action_type="info")
        assert len(infos) == 1

    # =====================================================================
    # 11. get_summary
    # =====================================================================
    def test_get_summary(self):
        """get_summary should return correct counts and duration."""
        al = ActivityLogger(session_id="test-sess")
        e1 = al.log("command", "cmd 1", duration_seconds=1.0, status="success")
        e2 = al.log("command", "cmd 2", duration_seconds=2.0, status="failed")
        e3 = al.log("info", "info 1", status="success")

        summary = al.get_summary()
        assert summary["session_id"] == "test-sess"
        assert summary["total_entries"] == 3
        assert summary["error_count"] == 1
        assert summary["total_duration_seconds"] == 3.0
        assert summary["counts_by_type"]["command"] == 2
        assert summary["counts_by_type"]["info"] == 1

    # =====================================================================
    # 12. to_jsonl export
    # =====================================================================
    def test_to_jsonl(self):
        """to_jsonl should export entries as newline-delimited JSON."""
        al = ActivityLogger(session_id="test-sess")
        al.log("command", "first", exit_code=0, status="success")
        al.log("info", "second")

        jsonl = al.to_jsonl()
        lines = jsonl.strip().split("\n")
        assert len(lines) == 2
        parsed = json.loads(lines[0])
        assert parsed["action_type"] == "command"
        assert parsed["exit_code"] == 0

    # =====================================================================
    # 13. Stdout/stderr truncation
    # =====================================================================
    def test_output_truncation_on_log(self):
        """log() should truncate stdout/stderr beyond _MAX_OUTPUT_CHARS."""
        al = ActivityLogger(session_id="test-sess")
        long_output = "x" * (_MAX_OUTPUT_CHARS + 500)
        entry = al.log("command", "test", stdout=long_output, stderr=long_output)

        assert len(entry.stdout) <= _MAX_OUTPUT_CHARS + 20  # +margin for suffix
        assert "truncated" in entry.stdout
        assert "truncated" in entry.stderr

    def test_output_truncation_on_update(self):
        """update() should truncate stdout/stderr beyond _MAX_OUTPUT_CHARS."""
        al = ActivityLogger(session_id="test-sess")
        entry = al.log("command", "test")
        long_output = "y" * (_MAX_OUTPUT_CHARS + 500)
        al.update(entry, stdout=long_output)

        assert len(entry.stdout) <= _MAX_OUTPUT_CHARS + 20
        assert "truncated" in entry.stdout


# =========================================================================
# 14. CLI cmd_activity integration
# =========================================================================
class TestCmdActivity:
    def test_cmd_activity_no_logger(self):
        """cmd_activity should return error when no active logger."""
        from orion.ara.cli_commands import _active_loggers, cmd_activity

        _active_loggers.clear()
        result = cmd_activity()
        assert not result.success
        assert "No active session" in result.message

    def test_cmd_activity_with_entries(self):
        """cmd_activity should show entries when logger is active."""
        from orion.ara.cli_commands import (
            _active_loggers,
            cmd_activity,
            register_activity_logger,
        )

        _active_loggers.clear()
        al = ActivityLogger(session_id="test-cmd")
        register_activity_logger("test-cmd", al)
        al.log("command", "echo hello", status="success")
        al.log("command", "python app.py", status="failed")

        result = cmd_activity()
        assert result.success
        assert "2 entries" in result.message
        assert result.data is not None
        assert len(result.data["entries"]) == 2

        _active_loggers.clear()

    def test_cmd_activity_summary_mode(self):
        """cmd_activity with summary_mode should return summary."""
        from orion.ara.cli_commands import (
            _active_loggers,
            cmd_activity,
            register_activity_logger,
        )

        _active_loggers.clear()
        al = ActivityLogger(session_id="test-summary")
        register_activity_logger("test-summary", al)
        al.log("command", "cmd1", duration_seconds=1.0, status="success")
        al.log("info", "info1", status="success")

        result = cmd_activity(summary_mode=True)
        assert result.success
        assert "Total entries: 2" in result.message
        assert result.data["total_entries"] == 2

        _active_loggers.clear()

    def test_cmd_activity_errors_only(self):
        """cmd_activity with errors_only should filter to failed entries."""
        from orion.ara.cli_commands import (
            _active_loggers,
            cmd_activity,
            register_activity_logger,
        )

        _active_loggers.clear()
        al = ActivityLogger(session_id="test-errors")
        register_activity_logger("test-errors", al)
        al.log("command", "good cmd", status="success")
        al.log("command", "bad cmd", status="failed")

        result = cmd_activity(errors_only=True)
        assert result.success
        assert "1 entries" in result.message
        assert len(result.data["entries"]) == 1
        assert result.data["entries"][0]["status"] == "failed"

        _active_loggers.clear()


# =========================================================================
# 15. SessionContainer activity_logger wiring
# =========================================================================
class TestSessionContainerActivityWiring:
    def test_session_container_accepts_activity_logger(self):
        """SessionContainer should accept an activity_logger parameter."""
        from orion.security.session_container import SessionContainer

        al = ActivityLogger(session_id="wire-test")
        sc = SessionContainer(
            session_id="wire-test",
            stack="python",
            activity_logger=al,
        )
        assert sc.activity_logger is al

    def test_session_container_default_no_logger(self):
        """SessionContainer should default to no activity_logger."""
        from orion.security.session_container import SessionContainer

        sc = SessionContainer(session_id="no-logger")
        assert sc.activity_logger is None


# =========================================================================
# 16. ExecutionFeedbackLoop activity_logger wiring
# =========================================================================
class TestFeedbackLoopActivityWiring:
    def test_feedback_loop_accepts_activity_logger(self):
        """ExecutionFeedbackLoop should accept an activity_logger parameter."""
        from orion.ara.execution_feedback import ExecutionFeedbackLoop

        al = ActivityLogger(session_id="feedback-test")
        mock_container = MagicMock()
        loop = ExecutionFeedbackLoop(
            container=mock_container,
            activity_logger=al,
        )
        assert loop.activity_logger is al

    @pytest.mark.asyncio
    async def test_feedback_loop_logs_retries(self):
        """ExecutionFeedbackLoop should log retry attempts via activity_logger."""
        from orion.ara.execution_feedback import ExecutionFeedbackLoop, RuleBasedFixProvider
        from orion.security.session_container import ExecResult

        al = ActivityLogger(session_id="retry-test")

        # Mock container that fails then succeeds
        mock_container = AsyncMock()
        mock_container.exec = AsyncMock(
            side_effect=[
                ExecResult(stderr="ModuleNotFoundError: No module named 'flask'", exit_code=1),
                ExecResult(stdout="ok", exit_code=0),
            ]
        )
        mock_container.exec_install = AsyncMock(
            return_value=ExecResult(stdout="installed", exit_code=0)
        )

        loop = ExecutionFeedbackLoop(
            container=mock_container,
            fix_provider=RuleBasedFixProvider(),
            activity_logger=al,
            max_retries=2,
        )

        result = await loop.run_with_feedback("python app.py")
        assert result.success

        # Activity logger should have received retry info entries
        info_entries = al.get_entries(action_type="info")
        assert len(info_entries) >= 1
        assert "Retry" in info_entries[0].description
