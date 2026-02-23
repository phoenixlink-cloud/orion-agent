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
"""Tests for Phase 4C.2 — Ruff Linter Tool.

12 tests covering:
  - RuffIssue dataclass (creation, from_ruff_json, severity classification)
  - RuffResult dataclass (properties, to_dict, summary_line)
  - parse_ruff_json helper
  - run_ruff_local (success, issues found, ruff not available, timeout)
  - run_ruff_in_container (mock Docker execution)
  - ActivityLogger integration
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.ara.ruff_tool import (
    DEFAULT_SELECT,
    RuffIssue,
    RuffResult,
    _build_result,
    parse_ruff_json,
    run_ruff_in_container,
    run_ruff_local,
)

# =========================================================================
# Sample Ruff JSON output for testing
# =========================================================================
SAMPLE_RUFF_JSON = json.dumps(
    [
        {
            "code": "F401",
            "message": "'os' imported but unused",
            "filename": "/workspace/app.py",
            "location": {"row": 1, "column": 1},
            "end_location": {"row": 1, "column": 10},
            "fix": {"applicability": "safe", "message": "Remove unused import"},
        },
        {
            "code": "E501",
            "message": "Line too long (120 > 88)",
            "filename": "/workspace/app.py",
            "location": {"row": 15, "column": 89},
            "end_location": {"row": 15, "column": 120},
            "fix": None,
        },
        {
            "code": "E999",
            "message": "SyntaxError: invalid syntax",
            "filename": "/workspace/broken.py",
            "location": {"row": 5, "column": 1},
            "end_location": {"row": 5, "column": 1},
            "fix": None,
        },
    ]
)


# =========================================================================
# 1. RuffIssue creation and serialization
# =========================================================================
class TestRuffIssue:
    def test_create_defaults(self):
        """RuffIssue should have sensible defaults."""
        issue = RuffIssue()
        assert issue.code == ""
        assert issue.severity == "warning"
        assert issue.fix_available is False

    def test_from_ruff_json_f_code(self):
        """from_ruff_json should classify F codes as errors."""
        item = {
            "code": "F401",
            "message": "'os' imported but unused",
            "filename": "app.py",
            "location": {"row": 1, "column": 1},
            "end_location": {"row": 1, "column": 10},
            "fix": {"applicability": "safe", "message": "Remove unused import"},
        }
        issue = RuffIssue.from_ruff_json(item)
        assert issue.code == "F401"
        assert issue.severity == "error"
        assert issue.fix_available is True
        assert issue.fix_description == "Remove unused import"
        assert issue.row == 1
        assert issue.col == 1

    def test_from_ruff_json_e_code(self):
        """from_ruff_json should classify E codes (non-E9xx) as warnings."""
        item = {
            "code": "E501",
            "message": "Line too long",
            "filename": "app.py",
            "location": {"row": 15, "column": 89},
            "end_location": {"row": 15, "column": 120},
            "fix": None,
        }
        issue = RuffIssue.from_ruff_json(item)
        assert issue.code == "E501"
        assert issue.severity == "warning"
        assert issue.fix_available is False

    def test_from_ruff_json_e9_code(self):
        """from_ruff_json should classify E9xx codes as errors."""
        item = {
            "code": "E999",
            "message": "SyntaxError",
            "filename": "broken.py",
            "location": {"row": 5, "column": 1},
            "end_location": {"row": 5, "column": 1},
            "fix": None,
        }
        issue = RuffIssue.from_ruff_json(item)
        assert issue.severity == "error"

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        issue = RuffIssue(code="F401", message="unused", filename="app.py", row=1, col=1)
        d = issue.to_dict()
        assert d["code"] == "F401"
        assert d["filename"] == "app.py"
        assert "severity" in d

    def test_location_str(self):
        """location_str should format as file:row:col."""
        issue = RuffIssue(filename="app.py", row=10, col=5)
        assert issue.location_str == "app.py:10:5"


# =========================================================================
# 2. RuffResult properties
# =========================================================================
class TestRuffResult:
    def test_empty_result(self):
        """Empty RuffResult should be successful with no issues."""
        result = RuffResult()
        assert result.success is True
        assert result.total_issues == 0
        assert result.has_errors is False

    def test_result_with_issues(self):
        """RuffResult should compute counts correctly."""
        issues = parse_ruff_json(SAMPLE_RUFF_JSON)
        result = _build_result(issues, SAMPLE_RUFF_JSON, exit_code=1)
        assert result.total_issues == 3
        assert result.error_count == 2  # F401 + E999
        assert result.warning_count == 1  # E501
        assert result.has_errors is True
        assert result.success is False

    def test_to_dict(self):
        """to_dict should include all key fields."""
        result = RuffResult(
            success=True,
            error_count=0,
            warning_count=2,
            files_checked=3,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["warning_count"] == 2
        assert d["files_checked"] == 3
        assert "issues" in d

    def test_summary_line_clean(self):
        """summary_line should show clean message when no issues."""
        result = RuffResult(success=True, files_checked=5)
        assert "clean" in result.summary_line()

    def test_summary_line_with_issues(self):
        """summary_line should show counts when issues exist."""
        result = RuffResult(
            success=False,
            error_count=2,
            warning_count=1,
            files_checked=3,
        )
        line = result.summary_line()
        assert "2 error(s)" in line
        assert "1 warning(s)" in line

    def test_summary_line_not_available(self):
        """summary_line should show skip message when ruff unavailable."""
        result = RuffResult(ruff_available=False)
        assert "not available" in result.summary_line()


# =========================================================================
# 3. parse_ruff_json helper
# =========================================================================
class TestParseRuffJson:
    def test_parse_valid_json(self):
        """parse_ruff_json should parse valid Ruff JSON output."""
        issues = parse_ruff_json(SAMPLE_RUFF_JSON)
        assert len(issues) == 3
        assert issues[0].code == "F401"
        assert issues[1].code == "E501"
        assert issues[2].code == "E999"

    def test_parse_empty_array(self):
        """parse_ruff_json should return empty list for empty array."""
        issues = parse_ruff_json("[]")
        assert issues == []

    def test_parse_invalid_json(self):
        """parse_ruff_json should return empty list for invalid JSON."""
        issues = parse_ruff_json("not json at all")
        assert issues == []

    def test_parse_non_array(self):
        """parse_ruff_json should return empty list for non-array JSON."""
        issues = parse_ruff_json('{"key": "value"}')
        assert issues == []


# =========================================================================
# 4. run_ruff_local
# =========================================================================
class TestRunRuffLocal:
    @patch("orion.ara.ruff_tool.subprocess.run")
    def test_clean_run(self, mock_run):
        """run_ruff_local should return clean result when no issues."""
        mock_run.return_value = MagicMock(stdout="[]", stderr="", returncode=0)
        result = run_ruff_local("/workspace")
        assert result.success is True
        assert result.total_issues == 0
        assert result.ruff_available is True

    @patch("orion.ara.ruff_tool.subprocess.run")
    def test_issues_found(self, mock_run):
        """run_ruff_local should parse issues from Ruff output."""
        mock_run.return_value = MagicMock(stdout=SAMPLE_RUFF_JSON, stderr="", returncode=1)
        result = run_ruff_local("/workspace")
        assert result.total_issues == 3
        assert result.error_count == 2

    @patch("orion.ara.ruff_tool.subprocess.run", side_effect=FileNotFoundError)
    def test_ruff_not_found(self, mock_run):
        """run_ruff_local should handle ruff not installed gracefully."""
        result = run_ruff_local("/workspace")
        assert result.ruff_available is False
        assert result.success is True

    @patch("orion.ara.ruff_tool.subprocess.run")
    def test_timeout(self, mock_run):
        """run_ruff_local should handle timeout."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ruff", timeout=60)
        result = run_ruff_local("/workspace")
        assert result.success is False
        assert "timed out" in result.raw_output

    @patch("orion.ara.ruff_tool.subprocess.run")
    def test_custom_select_ignore(self, mock_run):
        """run_ruff_local should pass custom select/ignore to ruff."""
        mock_run.return_value = MagicMock(stdout="[]", stderr="", returncode=0)
        run_ruff_local("/workspace", select=["E", "F"], ignore=["E501"])
        call_args = mock_run.call_args[0][0]
        assert "--select" in call_args
        assert "E,F" in call_args
        assert "--ignore" in call_args
        assert "E501" in call_args


# =========================================================================
# 5. run_ruff_in_container
# =========================================================================
class TestRunRuffInContainer:
    @pytest.mark.asyncio
    async def test_container_clean_run(self):
        """run_ruff_in_container should return clean result."""
        from orion.security.session_container import ExecResult

        mock_container = AsyncMock()
        mock_container.exec = AsyncMock(
            return_value=ExecResult(stdout="[]", stderr="", exit_code=0, duration_seconds=0.5)
        )

        result = await run_ruff_in_container(mock_container)
        assert result.success is True
        assert result.ruff_available is True
        mock_container.exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_container_issues_found(self):
        """run_ruff_in_container should parse issues from container output."""
        from orion.security.session_container import ExecResult

        mock_container = AsyncMock()
        mock_container.exec = AsyncMock(
            return_value=ExecResult(
                stdout=SAMPLE_RUFF_JSON, stderr="", exit_code=1, duration_seconds=1.0
            )
        )

        result = await run_ruff_in_container(mock_container)
        assert result.total_issues == 3
        assert result.error_count == 2

    @pytest.mark.asyncio
    async def test_container_ruff_not_installed(self):
        """run_ruff_in_container should handle ruff not installed in container."""
        from orion.security.session_container import ExecResult

        mock_container = AsyncMock()
        mock_container.exec = AsyncMock(
            return_value=ExecResult(
                stdout="", stderr="sh: ruff: command not found", exit_code=127, duration_seconds=0.1
            )
        )

        result = await run_ruff_in_container(mock_container)
        assert result.ruff_available is False
        assert result.success is True

    @pytest.mark.asyncio
    async def test_container_with_activity_logger(self):
        """run_ruff_in_container should log to activity_logger."""
        from orion.ara.activity_logger import ActivityLogger
        from orion.security.session_container import ExecResult

        al = ActivityLogger(session_id="ruff-test")
        mock_container = AsyncMock()
        mock_container.exec = AsyncMock(
            return_value=ExecResult(stdout="[]", stderr="", exit_code=0, duration_seconds=0.3)
        )

        result = await run_ruff_in_container(mock_container, activity_logger=al)
        assert result.success is True

        # Activity logger should have a test entry
        entries = al.get_entries(action_type="test")
        assert len(entries) == 1
        assert "Ruff lint" in entries[0].description
        assert entries[0].status == "success"
