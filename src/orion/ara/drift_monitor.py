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
"""ARA Drift Monitor — detects when the real workspace has changed under Orion.

Compares the real workspace against the sandbox baseline to detect
external modifications that could cause merge conflicts or stale work.

See ARA-001 §C.6 for full design.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.ara.drift_monitor")

# Extensions to skip when hashing
_SKIP_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".so", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".zip", ".tar", ".gz",
    ".sqlite", ".db",
})

# Directories to skip
_SKIP_DIRS = frozenset({
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".eggs", "*.egg-info",
})


class DriftSeverity(str, Enum):
    NONE = "none"
    LOW = "low"         # Files changed but not in sandbox working set
    MEDIUM = "medium"   # Files changed that overlap with sandbox changes
    HIGH = "high"       # Critical files changed (e.g. requirements, config)


@dataclass
class DriftResult:
    """Result of a drift check."""

    severity: DriftSeverity = DriftSeverity.NONE
    changed_files: list[str] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    conflicting_files: list[str] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        return self.severity != DriftSeverity.NONE

    @property
    def total_changes(self) -> int:
        return len(self.changed_files) + len(self.new_files) + len(self.deleted_files)

    def summary(self) -> str:
        if not self.has_drift:
            return "No drift detected"
        return (
            f"Drift detected ({self.severity.value}): "
            f"{len(self.changed_files)} changed, "
            f"{len(self.new_files)} new, "
            f"{len(self.deleted_files)} deleted"
            + (f", {len(self.conflicting_files)} conflicts" if self.conflicting_files else "")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "has_drift": self.has_drift,
            "changed_files": self.changed_files,
            "new_files": self.new_files,
            "deleted_files": self.deleted_files,
            "conflicting_files": self.conflicting_files,
            "total_changes": self.total_changes,
        }


# Files that raise drift severity when changed
CRITICAL_FILES = frozenset({
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "package.json", "package-lock.json",
    "Dockerfile", "docker-compose.yml",
    ".env", ".env.local",
    "Makefile", "Cargo.toml", "go.mod",
})


class DriftMonitor:
    """Monitors workspace for external changes during an ARA session."""

    def __init__(self, workspace_path: Path):
        self._workspace = workspace_path
        self._baseline: dict[str, str] = {}  # relative_path -> content_hash

    def _should_skip(self, path: Path) -> bool:
        """Check if a path should be skipped."""
        if path.suffix.lower() in _SKIP_EXTENSIONS:
            return True
        for part in path.parts:
            if part in _SKIP_DIRS:
                return True
        return False

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Generate a content hash for a file."""
        try:
            content = path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception:
            return ""

    def capture_baseline(self) -> int:
        """Capture a hash baseline of the workspace. Returns file count."""
        self._baseline.clear()
        if not self._workspace.exists():
            return 0

        for path in self._workspace.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self._workspace)
            if self._should_skip(rel):
                continue
            self._baseline[str(rel)] = self._hash_file(path)

        logger.info("Drift baseline captured: %d files", len(self._baseline))
        return len(self._baseline)

    def check_drift(self, sandbox_changed_files: list[str] | None = None) -> DriftResult:
        """Check for drift against the baseline.

        Args:
            sandbox_changed_files: Files that Orion has modified in the sandbox.
                Used to detect conflicts (workspace changes overlapping sandbox changes).
        """
        result = DriftResult()
        sandbox_set = set(sandbox_changed_files or [])

        if not self._baseline:
            return result

        current_files: dict[str, str] = {}
        if self._workspace.exists():
            for path in self._workspace.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(self._workspace)
                if self._should_skip(rel):
                    continue
                current_files[str(rel)] = self._hash_file(path)

        # Detect changes
        for rel_path, old_hash in self._baseline.items():
            if rel_path not in current_files:
                result.deleted_files.append(rel_path)
            elif current_files[rel_path] != old_hash:
                result.changed_files.append(rel_path)

        # Detect new files
        for rel_path in current_files:
            if rel_path not in self._baseline:
                result.new_files.append(rel_path)

        # Detect conflicts
        if sandbox_set:
            all_changed = set(result.changed_files + result.deleted_files)
            result.conflicting_files = sorted(all_changed & sandbox_set)

        # Determine severity
        if result.total_changes == 0:
            result.severity = DriftSeverity.NONE
        elif result.conflicting_files:
            result.severity = DriftSeverity.HIGH
        elif any(Path(f).name in CRITICAL_FILES for f in result.changed_files + result.deleted_files):
            result.severity = DriftSeverity.MEDIUM
        else:
            result.severity = DriftSeverity.LOW

        if result.has_drift:
            logger.warning(result.summary())
        return result

    def refresh_baseline(self) -> int:
        """Re-capture the baseline (e.g. after acknowledging drift)."""
        return self.capture_baseline()
