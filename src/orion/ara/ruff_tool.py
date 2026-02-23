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
"""Ruff Linter Tool — static analysis validation for generated Python code.

Wraps the Ruff linter to validate Python files inside Docker containers
or locally. Used by the ExecutionFeedbackLoop and TaskExecutor to catch
code quality issues before promotion.

Design:
  - Runs ``ruff check --output-format=json`` on target files
  - Parses JSON output into structured ``RuffIssue`` / ``RuffResult`` objects
  - Supports running inside SessionContainer (Docker) or locally
  - Integrates with ActivityLogger for audit trail

See Phase 4C.2 specification.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orion.ara.activity_logger import ActivityLogger
    from orion.security.session_container import SessionContainer

logger = logging.getLogger("orion.ara.ruff_tool")

# ---------------------------------------------------------------------------
# Default Ruff rules (match pyproject.toml convention)
# ---------------------------------------------------------------------------
DEFAULT_SELECT = ["E", "F", "W", "I"]  # pycodestyle errors/warnings, pyflakes, isort
DEFAULT_IGNORE: list[str] = []


# ---------------------------------------------------------------------------
# RuffIssue dataclass
# ---------------------------------------------------------------------------


@dataclass
class RuffIssue:
    """A single issue reported by Ruff."""

    code: str = ""
    message: str = ""
    filename: str = ""
    row: int = 0
    col: int = 0
    end_row: int = 0
    end_col: int = 0
    severity: str = "warning"  # 'error', 'warning', 'info'
    fix_available: bool = False
    fix_description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "code": self.code,
            "message": self.message,
            "filename": self.filename,
            "row": self.row,
            "col": self.col,
            "end_row": self.end_row,
            "end_col": self.end_col,
            "severity": self.severity,
            "fix_available": self.fix_available,
            "fix_description": self.fix_description,
        }

    @classmethod
    def from_ruff_json(cls, item: dict[str, Any]) -> RuffIssue:
        """Parse a single Ruff JSON output item into a RuffIssue."""
        code = item.get("code", "")
        # Classify severity: E=error, F=error, W=warning, I=info
        if code.startswith(("E9", "F")):
            severity = "error"
        elif code.startswith(("E", "W")):
            severity = "warning"
        else:
            severity = "info"

        location = item.get("location", {})
        end_location = item.get("end_location", {})
        fix = item.get("fix", None)

        return cls(
            code=code,
            message=item.get("message", ""),
            filename=item.get("filename", ""),
            row=location.get("row", 0),
            col=location.get("column", 0),
            end_row=end_location.get("row", 0),
            end_col=end_location.get("column", 0),
            severity=severity,
            fix_available=fix is not None and bool(fix.get("applicability")),
            fix_description=fix.get("message", "") if fix else "",
        )

    @property
    def location_str(self) -> str:
        """Format location as 'file:row:col'."""
        return f"{self.filename}:{self.row}:{self.col}"


# ---------------------------------------------------------------------------
# RuffResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class RuffResult:
    """Aggregated result of a Ruff lint run."""

    success: bool = True
    issues: list[RuffIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    files_checked: int = 0
    raw_output: str = ""
    ruff_available: bool = True
    exit_code: int = 0

    @property
    def total_issues(self) -> int:
        """Total number of issues found."""
        return len(self.issues)

    @property
    def has_errors(self) -> bool:
        """True if any error-severity issues exist."""
        return self.error_count > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "success": self.success,
            "total_issues": self.total_issues,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "files_checked": self.files_checked,
            "has_errors": self.has_errors,
            "ruff_available": self.ruff_available,
            "issues": [i.to_dict() for i in self.issues],
        }

    def summary_line(self) -> str:
        """One-line summary for CLI/logs."""
        if not self.ruff_available:
            return "Ruff not available — lint skipped"
        total = self.error_count + self.warning_count + self.info_count
        if total == 0 and self.total_issues == 0:
            return f"Ruff: {self.files_checked} file(s) clean ✓"
        parts = []
        if self.error_count:
            parts.append(f"{self.error_count} error(s)")
        if self.warning_count:
            parts.append(f"{self.warning_count} warning(s)")
        if self.info_count:
            parts.append(f"{self.info_count} info")
        return f"Ruff: {', '.join(parts)} in {self.files_checked} file(s)"


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def parse_ruff_json(raw_json: str) -> list[RuffIssue]:
    """Parse Ruff's JSON output into a list of RuffIssue objects."""
    try:
        items = json.loads(raw_json)
        if not isinstance(items, list):
            return []
        return [RuffIssue.from_ruff_json(item) for item in items]
    except (json.JSONDecodeError, TypeError):
        return []


def _build_result(issues: list[RuffIssue], raw_output: str, exit_code: int) -> RuffResult:
    """Build a RuffResult from parsed issues."""
    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    info_count = sum(1 for i in issues if i.severity == "info")
    files = {i.filename for i in issues}

    return RuffResult(
        success=error_count == 0,
        issues=issues,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        files_checked=max(len(files), 1),
        raw_output=raw_output[:5000],
        ruff_available=True,
        exit_code=exit_code,
    )


# ---------------------------------------------------------------------------
# Local execution
# ---------------------------------------------------------------------------


def run_ruff_local(
    target: str | Path,
    select: list[str] | None = None,
    ignore: list[str] | None = None,
    timeout: int = 60,
) -> RuffResult:
    """Run Ruff locally (not in Docker) on a file or directory.

    Args:
        target: File or directory path to lint.
        select: Ruff rule codes to select (default: E, F, W, I).
        ignore: Ruff rule codes to ignore.
        timeout: Max seconds for the Ruff process.

    Returns:
        RuffResult with parsed issues.
    """
    select = select or DEFAULT_SELECT
    ignore = ignore or DEFAULT_IGNORE

    cmd = [
        "ruff",
        "check",
        "--output-format=json",
        "--select",
        ",".join(select),
    ]
    if ignore:
        cmd.extend(["--ignore", ",".join(ignore)])
    cmd.append(str(target))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        issues = parse_ruff_json(result.stdout)
        return _build_result(issues, result.stdout, result.returncode)

    except FileNotFoundError:
        return RuffResult(
            success=True,
            ruff_available=False,
            raw_output="ruff not found in PATH",
        )
    except subprocess.TimeoutExpired:
        return RuffResult(
            success=False,
            ruff_available=True,
            raw_output=f"Ruff timed out after {timeout}s",
            exit_code=-1,
        )
    except Exception as exc:
        return RuffResult(
            success=False,
            ruff_available=True,
            raw_output=f"Ruff execution error: {exc}",
            exit_code=-1,
        )


# ---------------------------------------------------------------------------
# Docker execution (via SessionContainer)
# ---------------------------------------------------------------------------


async def run_ruff_in_container(
    container: SessionContainer,
    target: str = "/workspace",
    select: list[str] | None = None,
    ignore: list[str] | None = None,
    timeout: int = 60,
    activity_logger: ActivityLogger | None = None,
) -> RuffResult:
    """Run Ruff inside a SessionContainer.

    Args:
        container: The Docker session container.
        target: Path inside the container to lint (default: /workspace).
        select: Ruff rule codes to select.
        ignore: Ruff rule codes to ignore.
        timeout: Max seconds for the Ruff process.
        activity_logger: Optional activity logger for audit trail.

    Returns:
        RuffResult with parsed issues.
    """
    select = select or DEFAULT_SELECT
    ignore = ignore or DEFAULT_IGNORE

    cmd_parts = [
        "ruff",
        "check",
        "--output-format=json",
        "--select",
        ",".join(select),
    ]
    if ignore:
        cmd_parts.extend(["--ignore", ",".join(ignore)])
    cmd_parts.append(target)
    command = " ".join(cmd_parts)

    # Activity log: start
    activity_entry = None
    if activity_logger:
        activity_entry = activity_logger.log(
            action_type="test",
            description=f"Ruff lint: {target}",
            command=command,
            phase="test",
        )

    exec_result = await container.exec(command, timeout=timeout, phase="test")

    # Parse output
    issues = parse_ruff_json(exec_result.stdout)

    # If ruff is not installed, the exit code will be non-zero with "command not found"
    if exec_result.exit_code != 0 and "command not found" in exec_result.stderr:
        result = RuffResult(
            success=True,
            ruff_available=False,
            raw_output=exec_result.stderr[:500],
        )
    else:
        result = _build_result(issues, exec_result.stdout, exec_result.exit_code)

    # Activity log: complete
    if activity_logger and activity_entry:
        activity_logger.update(
            activity_entry,
            exit_code=exec_result.exit_code,
            stdout=result.summary_line(),
            status="success" if result.success else "failed",
            duration_seconds=exec_result.duration_seconds,
        )

    return result
