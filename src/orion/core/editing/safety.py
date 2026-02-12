# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
#    You may use, modify, and distribute this file under AGPL-3.0.
#    See LICENSE for the full text.
#
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#    For proprietary use, SaaS deployment, or enterprise licensing.
#    See LICENSE-ENTERPRISE.md or contact info@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- Git Safety Net (v7.4.0)

Automatic git-based undo for all AI edits.

Architecture:
    1. SAVEPOINT:  Auto-commit workspace state before any AI edit batch
    2. APPLY:      Let the edit proceed normally
    3. UNDO:       Single command reverts to the last savepoint
    4. STACK:      Maintains a stack of savepoints for multi-level undo

Safety invariants:
- Every AI edit is bookended by a git savepoint
- /undo reverts to the exact state before the last AI edit
- Non-destructive: user commits are never touched
- Works even if the workspace is not a git repo (auto-init)

Savepoint commits use a special prefix: [orion:savepoint]
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# DATA TYPES
# ---------------------------------------------------------------------------


@dataclass
class Savepoint:
    """A recorded git savepoint before an AI edit."""

    commit_hash: str
    timestamp: str
    description: str
    files_snapshot: list[str]


@dataclass
class UndoResult:
    """Result of an undo operation."""

    success: bool
    message: str
    reverted_to: str | None = None
    files_restored: int = 0
    files_removed: int = 0


SAVEPOINT_PREFIX = "[orion:savepoint]"
EDIT_PREFIX = "[orion:edit]"


# ---------------------------------------------------------------------------
# GIT HELPERS
# ---------------------------------------------------------------------------


def _run_git(workspace: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the workspace."""
    cmd = ["git"] + list(args)
    return subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
    )


def _is_git_repo(workspace: str) -> bool:
    """Check if workspace is inside a git repository."""
    try:
        result = _run_git(workspace, "rev-parse", "--is-inside-work-tree", check=False)
        return result.returncode == 0 and result.stdout.strip() == "true"
    except Exception:
        return False


def _git_init(workspace: str) -> bool:
    """Initialize a git repo if needed."""
    try:
        _run_git(workspace, "init")
        _run_git(workspace, "config", "user.email", "orion@local", check=False)
        _run_git(workspace, "config", "user.name", "Orion AI", check=False)
        return True
    except Exception:
        return False


def _get_head_hash(workspace: str) -> str | None:
    """Get current HEAD commit hash."""
    try:
        result = _run_git(workspace, "rev-parse", "HEAD", check=False)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _has_changes(workspace: str) -> bool:
    """Check if there are uncommitted changes."""
    try:
        result = _run_git(workspace, "status", "--porcelain", check=False)
        return bool(result.stdout.strip())
    except Exception:
        return False


def _get_tracked_files(workspace: str) -> list[str]:
    """Get list of tracked files."""
    try:
        result = _run_git(workspace, "ls-files", check=False)
        if result.returncode == 0:
            return [f for f in result.stdout.strip().split("\n") if f]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# GIT SAFETY NET
# ---------------------------------------------------------------------------


class GitSafetyNet:
    """
    Git-based safety net for AI edits.

    Usage:
        safety = GitSafetyNet(workspace_path)
        safety.create_savepoint("Before refactoring auth module")
        # ... AI edits happen ...
        safety.commit_edit("Refactored auth module")
        # If user wants to undo:
        result = safety.undo()
    """

    def __init__(self, workspace_path: str):
        self.workspace = str(Path(workspace_path).resolve())
        self._savepoints: list[Savepoint] = []
        self._initialized = False
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    def ensure_git(self) -> bool:
        """Ensure workspace has git. Returns True if ready."""
        if self._initialized:
            return True
        if _is_git_repo(self.workspace):
            self._initialized = True
            return True
        if _git_init(self.workspace):
            self._initialized = True
            return True
        return False

    def create_savepoint(self, description: str = "") -> Savepoint | None:
        """Create a savepoint before AI edits."""
        if not self._enabled:
            return None
        if not self.ensure_git():
            return None
        try:
            _run_git(self.workspace, "add", "-A", check=False)
            msg = f"{SAVEPOINT_PREFIX} {description or 'Pre-edit state'}"
            _run_git(self.workspace, "commit", "-m", msg, "--allow-empty", check=False)
            commit_hash = _get_head_hash(self.workspace)
            if not commit_hash:
                return None
            files = _get_tracked_files(self.workspace)
            savepoint = Savepoint(
                commit_hash=commit_hash,
                timestamp=datetime.utcnow().isoformat(),
                description=description or "Pre-edit state",
                files_snapshot=files,
            )
            self._savepoints.append(savepoint)
            return savepoint
        except Exception:
            return None

    def commit_edit(self, description: str = "", files: list[str] | None = None) -> str | None:
        """Commit AI edit results."""
        if not self._enabled or not self._initialized:
            return None
        try:
            if files:
                for f in files:
                    _run_git(self.workspace, "add", f, check=False)
            else:
                _run_git(self.workspace, "add", "-A", check=False)
            if not _has_changes(self.workspace):
                result = _run_git(self.workspace, "diff", "--cached", "--quiet", check=False)
                if result.returncode == 0:
                    return _get_head_hash(self.workspace)
            msg = f"{EDIT_PREFIX} {description or 'AI edit'}"
            _run_git(self.workspace, "commit", "-m", msg, check=False)
            return _get_head_hash(self.workspace)
        except Exception:
            return None

    def undo(self) -> UndoResult:
        """Undo the last AI edit by reverting to the most recent savepoint."""
        if not self._enabled:
            return UndoResult(success=False, message="Git safety net is disabled")
        if not self._initialized:
            return UndoResult(success=False, message="Git not initialized")
        if not self._savepoints:
            return UndoResult(success=False, message="No savepoints available")
        savepoint = self._savepoints[-1]
        try:
            _run_git(self.workspace, "reset", "--hard", savepoint.commit_hash)
            _run_git(self.workspace, "clean", "-fd", check=False)
            self._savepoints.pop()
            current_files = _get_tracked_files(self.workspace)
            restored = len(set(savepoint.files_snapshot) & set(current_files))
            removed = len(set(current_files) - set(savepoint.files_snapshot))
            return UndoResult(
                success=True,
                message=f"Reverted to: {savepoint.description}",
                reverted_to=savepoint.commit_hash,
                files_restored=restored,
                files_removed=removed,
            )
        except subprocess.CalledProcessError as e:
            return UndoResult(
                success=False,
                message=f"Git reset failed: {e.stderr.strip() if e.stderr else str(e)}",
            )
        except Exception as e:
            return UndoResult(success=False, message=f"Undo failed: {str(e)}")

    def undo_all(self) -> UndoResult:
        """Undo ALL AI edits back to the first savepoint."""
        if not self._savepoints:
            return UndoResult(success=False, message="No savepoints available")
        first = self._savepoints[0]
        try:
            _run_git(self.workspace, "reset", "--hard", first.commit_hash)
            _run_git(self.workspace, "clean", "-fd", check=False)
            count = len(self._savepoints)
            self._savepoints.clear()
            return UndoResult(
                success=True,
                message=f"Reverted {count} edit(s) to initial state",
                reverted_to=first.commit_hash,
            )
        except Exception as e:
            return UndoResult(success=False, message=f"Undo-all failed: {str(e)}")

    def get_undo_stack(self) -> list[dict]:
        """Get the current undo stack for display."""
        return [
            {
                "index": i,
                "hash": sp.commit_hash[:8],
                "description": sp.description,
                "timestamp": sp.timestamp,
                "files": len(sp.files_snapshot),
            }
            for i, sp in enumerate(reversed(self._savepoints))
        ]

    def get_savepoint_count(self) -> int:
        return len(self._savepoints)

    def get_last_savepoint(self) -> Savepoint | None:
        return self._savepoints[-1] if self._savepoints else None

    def get_edit_history(self, max_entries: int = 20) -> list[dict]:
        """Get history of Orion edits from git log."""
        if not self._initialized:
            return []
        try:
            result = _run_git(
                self.workspace,
                "log",
                f"--max-count={max_entries}",
                "--pretty=format:%H|%ai|%s",
                check=False,
            )
            if result.returncode != 0:
                return []
            entries = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|", 2)
                if len(parts) == 3:
                    commit_hash, timestamp, message = parts
                    entry_type = (
                        "savepoint"
                        if SAVEPOINT_PREFIX in message
                        else ("edit" if EDIT_PREFIX in message else "user")
                    )
                    entries.append(
                        {
                            "hash": commit_hash[:8],
                            "timestamp": timestamp.strip(),
                            "message": message.strip(),
                            "type": entry_type,
                        }
                    )
            return entries
        except Exception:
            return []

    def get_last_edit_diff(self) -> str | None:
        """Get the diff of the last AI edit."""
        if not self._savepoints:
            return None
        savepoint = self._savepoints[-1]
        try:
            result = _run_git(self.workspace, "diff", savepoint.commit_hash, "HEAD", check=False)
            return result.stdout if result.returncode == 0 else None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# CONVENIENCE API
# ---------------------------------------------------------------------------

_instances: dict[str, GitSafetyNet] = {}


def get_git_safety(workspace_path: str) -> GitSafetyNet:
    """Get or create a GitSafetyNet for a workspace (singleton per workspace)."""
    key = str(Path(workspace_path).resolve())
    if key not in _instances:
        _instances[key] = GitSafetyNet(key)
    return _instances[key]
