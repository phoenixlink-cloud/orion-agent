# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA Drift Monitor (ARA-001 §C.6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.ara.drift_monitor import DriftMonitor, DriftResult, DriftSeverity


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "main.py").write_text("print('hello')\n")
    (ws / "utils.py").write_text("x = 1\n")
    (ws / "config.py").write_text("DEBUG = True\n")
    return ws


@pytest.fixture
def monitor(workspace: Path) -> DriftMonitor:
    m = DriftMonitor(workspace)
    m.capture_baseline()
    return m


class TestBaseline:
    def test_capture_baseline(self, workspace: Path):
        m = DriftMonitor(workspace)
        count = m.capture_baseline()
        assert count == 3

    def test_empty_workspace(self, tmp_path: Path):
        ws = tmp_path / "empty"
        ws.mkdir()
        m = DriftMonitor(ws)
        count = m.capture_baseline()
        assert count == 0

    def test_nonexistent_workspace(self, tmp_path: Path):
        m = DriftMonitor(tmp_path / "nope")
        count = m.capture_baseline()
        assert count == 0


class TestNoDrift:
    def test_no_changes(self, monitor: DriftMonitor):
        result = monitor.check_drift()
        assert result.has_drift is False
        assert result.severity == DriftSeverity.NONE
        assert result.total_changes == 0


class TestFileChanges:
    def test_detects_modified_file(self, monitor: DriftMonitor, workspace: Path):
        (workspace / "main.py").write_text("print('changed')\n")
        result = monitor.check_drift()
        assert result.has_drift is True
        assert "main.py" in result.changed_files

    def test_detects_new_file(self, monitor: DriftMonitor, workspace: Path):
        (workspace / "new_file.py").write_text("y = 2\n")
        result = monitor.check_drift()
        assert result.has_drift is True
        assert "new_file.py" in result.new_files

    def test_detects_deleted_file(self, monitor: DriftMonitor, workspace: Path):
        (workspace / "utils.py").unlink()
        result = monitor.check_drift()
        assert result.has_drift is True
        assert "utils.py" in result.deleted_files

    def test_detects_multiple_changes(self, monitor: DriftMonitor, workspace: Path):
        (workspace / "main.py").write_text("changed\n")
        (workspace / "new.py").write_text("new\n")
        (workspace / "utils.py").unlink()
        result = monitor.check_drift()
        assert result.total_changes == 3


class TestSeverity:
    def test_low_severity_non_overlapping(self, monitor: DriftMonitor, workspace: Path):
        (workspace / "main.py").write_text("changed\n")
        result = monitor.check_drift(sandbox_changed_files=["other.py"])
        assert result.severity == DriftSeverity.LOW

    def test_high_severity_conflicting(self, monitor: DriftMonitor, workspace: Path):
        (workspace / "main.py").write_text("changed\n")
        result = monitor.check_drift(sandbox_changed_files=["main.py"])
        assert result.severity == DriftSeverity.HIGH
        assert "main.py" in result.conflicting_files

    def test_medium_severity_critical_file(self, monitor: DriftMonitor, workspace: Path):
        (workspace / "requirements.txt").write_text("flask==2.0\n")
        # Need to capture baseline with requirements.txt first
        m2 = DriftMonitor(workspace)
        m2.capture_baseline()
        (workspace / "requirements.txt").write_text("flask==3.0\n")
        result = m2.check_drift()
        assert result.severity == DriftSeverity.MEDIUM


class TestRefreshBaseline:
    def test_refresh_clears_drift(self, monitor: DriftMonitor, workspace: Path):
        (workspace / "main.py").write_text("changed\n")
        result1 = monitor.check_drift()
        assert result1.has_drift is True
        monitor.refresh_baseline()
        result2 = monitor.check_drift()
        assert result2.has_drift is False


class TestSkipPatterns:
    def test_skips_pycache(self, workspace: Path):
        pycache = workspace / "__pycache__"
        pycache.mkdir()
        (pycache / "main.cpython-311.pyc").write_bytes(b"\x00\x00")
        m = DriftMonitor(workspace)
        count = m.capture_baseline()
        assert count == 3  # Only the 3 .py files, not .pyc

    def test_skips_binary_extensions(self, workspace: Path):
        (workspace / "image.png").write_bytes(b"\x89PNG")
        m = DriftMonitor(workspace)
        count = m.capture_baseline()
        assert count == 3


class TestDriftResult:
    def test_summary_no_drift(self):
        r = DriftResult()
        assert "No drift" in r.summary()

    def test_summary_with_drift(self):
        r = DriftResult(
            severity=DriftSeverity.LOW,
            changed_files=["a.py"],
            new_files=["b.py"],
        )
        assert "LOW" in r.summary() or "low" in r.summary()

    def test_to_dict(self):
        r = DriftResult(severity=DriftSeverity.HIGH, conflicting_files=["x.py"])
        d = r.to_dict()
        assert d["severity"] == "high"
        assert d["has_drift"] is True
