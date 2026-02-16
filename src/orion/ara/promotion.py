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
"""Promotion Manager — sandbox → workspace file promotion with git tagging.

Handles the complete lifecycle of promoting ARA session work:
- Creating sandbox branches for isolated work
- Computing file diffs between sandbox and workspace
- Detecting conflicts with workspace changes
- Archiving existing workspace files before promotion (prevents name conflicts)
- Promoting (merging) changes with pre/post git tags
- Rejecting changes (branch preserved for reference)
- Undoing promotions via revert commits

See ARA-001 §10, Appendix C.9 for design.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("orion.ara.promotion")


@dataclass
class FileDiff:
    """A single file change in the sandbox."""

    path: str
    status: str  # "added" | "modified" | "deleted"
    additions: int = 0
    deletions: int = 0
    content: str = ""


@dataclass
class ConflictFile:
    """A file that was changed both in the sandbox and workspace."""

    path: str
    sandbox_status: str
    workspace_status: str


@dataclass
class PromotionResult:
    """Result of a promotion operation."""

    success: bool
    message: str
    files_promoted: int = 0
    pre_tag: str = ""
    post_tag: str = ""
    conflicts: list[str] = field(default_factory=list)


class PromotionManager:
    """Manages the sandbox → workspace file promotion flow.

    The promotion flow:
    1. Session work happens in a sandbox directory
    2. On review, compute diffs and check for conflicts
    3. If approved, copy files to workspace with git tags
    4. If rejected, sandbox is preserved for reference
    5. Undo-promote creates a revert commit

    Usage::

        pm = PromotionManager(workspace=Path("/my/project"))
        pm.create_sandbox("session-123")
        # ... session does work in sandbox ...
        diffs = pm.get_diff("session-123")
        conflicts = pm.check_conflicts("session-123")
        result = pm.promote("session-123", goal="Write auth tests")
    """

    def __init__(self, workspace: Path, sandbox_root: Path | None = None):
        self._workspace = workspace
        self._sandbox_root = sandbox_root or (workspace / ".orion-sandbox")
        self._sandbox_root.mkdir(parents=True, exist_ok=True)

    def create_sandbox(self, session_id: str) -> Path:
        """Create an isolated sandbox directory for a session.

        Copies the workspace into a sandbox directory and records the
        base commit (HEAD at creation time) for later conflict detection.
        """
        sandbox_path = self._sandbox_root / session_id
        if sandbox_path.exists():
            shutil.rmtree(sandbox_path)
        sandbox_path.mkdir(parents=True)

        # Record base state
        base_commit = self._get_head_commit()
        (sandbox_path / ".base_commit").write_text(base_commit or "none")
        (sandbox_path / ".created_at").write_text(str(time.time()))

        # Create workspace snapshot directory
        work_dir = sandbox_path / "workspace"
        work_dir.mkdir()

        logger.info(
            "Created sandbox for session %s (base: %s)",
            session_id[:12],
            (base_commit or "none")[:12],
        )
        return sandbox_path

    def get_sandbox_path(self, session_id: str) -> Path | None:
        """Get the sandbox path for a session, or None if it doesn't exist."""
        path = self._sandbox_root / session_id
        return path if path.exists() else None

    def add_file(self, session_id: str, rel_path: str, content: str) -> bool:
        """Add or modify a file in the sandbox workspace."""
        sandbox = self.get_sandbox_path(session_id)
        if sandbox is None:
            return False
        file_path = sandbox / "workspace" / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return True

    def delete_file(self, session_id: str, rel_path: str) -> bool:
        """Mark a file for deletion in the sandbox."""
        sandbox = self.get_sandbox_path(session_id)
        if sandbox is None:
            return False
        # Record deletion marker
        deletions_file = sandbox / ".deletions"
        existing = set()
        if deletions_file.exists():
            existing = set(deletions_file.read_text().strip().split("\n"))
        existing.add(rel_path)
        deletions_file.write_text("\n".join(sorted(existing)))
        return True

    def get_diff(self, session_id: str) -> list[FileDiff]:
        """List all file changes in the sandbox compared to the workspace."""
        sandbox = self.get_sandbox_path(session_id)
        if sandbox is None:
            return []

        diffs: list[FileDiff] = []
        work_dir = sandbox / "workspace"

        # Added/modified files
        if work_dir.exists():
            for file_path in work_dir.rglob("*"):
                if file_path.is_file():
                    rel = str(file_path.relative_to(work_dir)).replace("\\", "/")
                    workspace_file = self._workspace / rel

                    try:
                        content = file_path.read_text(encoding="utf-8")
                    except Exception:
                        content = ""

                    if not workspace_file.exists():
                        additions = content.count("\n") + (1 if content else 0)
                        diffs.append(
                            FileDiff(
                                path=rel,
                                status="added",
                                additions=additions,
                                content=content,
                            )
                        )
                    else:
                        try:
                            original = workspace_file.read_text(encoding="utf-8")
                        except Exception:
                            original = ""
                        if content != original:
                            new_lines = set(content.splitlines())
                            old_lines = set(original.splitlines())
                            diffs.append(
                                FileDiff(
                                    path=rel,
                                    status="modified",
                                    additions=len(new_lines - old_lines),
                                    deletions=len(old_lines - new_lines),
                                    content=content,
                                )
                            )

        # Deleted files
        deletions_file = sandbox / ".deletions"
        if deletions_file.exists():
            for rel in deletions_file.read_text().strip().split("\n"):
                if rel.strip():
                    diffs.append(FileDiff(path=rel.strip(), status="deleted"))

        return sorted(diffs, key=lambda d: d.path)

    def check_conflicts(self, session_id: str) -> list[ConflictFile]:
        """Detect files changed both in sandbox and workspace since session start."""
        sandbox = self.get_sandbox_path(session_id)
        if sandbox is None:
            return []

        base_commit_file = sandbox / ".base_commit"
        if not base_commit_file.exists():
            return []

        base_commit = base_commit_file.read_text().strip()
        if base_commit == "none":
            return []

        # Get files changed in workspace since base commit
        workspace_changes = self._get_changed_files_since(base_commit)
        if not workspace_changes:
            return []

        # Get files changed in sandbox
        sandbox_files = {d.path for d in self.get_diff(session_id)}

        # Intersection = conflicts
        conflicts: list[ConflictFile] = []
        for path in sorted(sandbox_files & workspace_changes):
            conflicts.append(
                ConflictFile(
                    path=path,
                    sandbox_status="modified",
                    workspace_status="modified",
                )
            )

        return conflicts

    def _archive_existing_files(
        self,
        session_id: str,
        diffs: list[FileDiff],
    ) -> Path | None:
        """Archive workspace files that would be overwritten by promotion.

        Creates a timestamped archive directory so Orion never confuses old
        project files with newly promoted ones. Only archives files that would
        be modified or replaced (not new files).

        Returns the archive directory path, or None if nothing was archived.
        """
        files_to_archive = [
            d for d in diffs if d.status == "modified" and (self._workspace / d.path).exists()
        ]
        if not files_to_archive:
            return None

        archive_dir = self._workspace / ".orion-archive" / f"{session_id[:12]}_{int(time.time())}"
        archive_dir.mkdir(parents=True, exist_ok=True)

        for diff in files_to_archive:
            src = self._workspace / diff.path
            dst = archive_dir / diff.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(src), str(dst))
            except Exception as e:
                logger.warning("Could not archive %s: %s", diff.path, e)

        # Write a manifest so it's clear what this archive contains
        manifest = {
            "session_id": session_id,
            "archived_at": time.time(),
            "reason": "Pre-promotion backup of workspace files that were overwritten",
            "files": [d.path for d in files_to_archive],
        }
        import json

        (archive_dir / "_manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        logger.info(
            "Archived %d workspace files to %s before promotion",
            len(files_to_archive),
            archive_dir,
        )
        return archive_dir

    def promote(
        self,
        session_id: str,
        goal: str = "",
    ) -> PromotionResult:
        """Promote sandbox changes to the workspace.

        1. Archive existing workspace files that would be overwritten
        2. Tag pre-promote state
        3. Copy sandbox files to workspace
        4. Remove deleted files
        5. Tag post-promote state
        """
        sandbox = self.get_sandbox_path(session_id)
        if sandbox is None:
            return PromotionResult(
                success=False,
                message=f"Sandbox not found for session {session_id}",
            )

        diffs = self.get_diff(session_id)
        if not diffs:
            return PromotionResult(
                success=False,
                message="No changes to promote.",
            )

        # Check for conflicts
        conflicts = self.check_conflicts(session_id)
        conflict_paths = [c.path for c in conflicts]

        # Archive existing files that would be overwritten
        archive_dir = self._archive_existing_files(session_id, diffs)

        # Tag pre-promote
        pre_tag = f"orion-pre-promote/{session_id[:12]}"
        self._git_tag(pre_tag)

        # Apply changes
        promoted = 0
        work_dir = sandbox / "workspace"

        for diff in diffs:
            if diff.path in conflict_paths:
                continue  # Skip conflicting files

            if diff.status in ("added", "modified"):
                src = work_dir / diff.path
                dst = self._workspace / diff.path
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.exists():
                    shutil.copy2(str(src), str(dst))
                    promoted += 1

            elif diff.status == "deleted":
                dst = self._workspace / diff.path
                if dst.exists():
                    dst.unlink()
                    promoted += 1

        # Git commit
        commit_msg = f"orion(ara): {goal}" if goal else f"orion(ara): session {session_id[:12]}"
        self._git_add_commit(commit_msg)

        # Tag post-promote
        post_tag = f"orion-post-promote/{session_id[:12]}"
        self._git_tag(post_tag)

        msg = f"Promoted {promoted} files."
        if archive_dir:
            msg += f" Archived overwritten files to {archive_dir.relative_to(self._workspace)}"
        if conflict_paths:
            msg += f" Skipped {len(conflict_paths)} conflicting files: {', '.join(conflict_paths)}"

        return PromotionResult(
            success=True,
            message=msg,
            files_promoted=promoted,
            pre_tag=pre_tag,
            post_tag=post_tag,
            conflicts=conflict_paths,
        )

    def reject(self, session_id: str) -> bool:
        """Mark a session as rejected. Sandbox is preserved for reference."""
        sandbox = self.get_sandbox_path(session_id)
        if sandbox is None:
            return False
        (sandbox / ".rejected").write_text(str(time.time()))
        logger.info("Session %s rejected. Sandbox preserved at %s", session_id[:12], sandbox)
        return True

    def undo_promote(self, session_id: str) -> PromotionResult:
        """Undo a promotion by creating a revert commit.

        Non-destructive: original work preserved on post-promote tag.
        """
        pre_tag = f"orion-pre-promote/{session_id[:12]}"

        # Check if pre-promote tag exists
        if not self._tag_exists(pre_tag):
            return PromotionResult(
                success=False,
                message=f"No promotion found for session {session_id[:12]} (tag {pre_tag} not found).",
            )

        # Get the commit of the pre-promote tag
        try:
            result = subprocess.run(
                ["git", "rev-parse", pre_tag],
                capture_output=True,
                text=True,
                cwd=str(self._workspace),
                timeout=10,
            )
            if result.returncode != 0:
                return PromotionResult(success=False, message="Could not resolve pre-promote tag.")
            result.stdout.strip()  # validates tag resolves
        except Exception as e:
            return PromotionResult(success=False, message=f"Git error: {e}")

        # Create a revert: restore files from pre-promote state
        try:
            # Get files that changed between pre-promote and HEAD
            diff_result = subprocess.run(
                ["git", "diff", "--name-status", pre_tag, "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(self._workspace),
                timeout=10,
            )
            if diff_result.returncode == 0:
                lines = [ln for ln in diff_result.stdout.strip().split("\n") if ln.strip()]
                reverted = 0
                for line in lines:
                    parts = line.split("\t", 1)
                    if len(parts) != 2:
                        continue
                    status, path = parts[0].strip(), parts[1].strip()

                    if status.startswith("A"):
                        # File was added by promotion — remove it
                        subprocess.run(
                            ["git", "rm", "-f", path],
                            capture_output=True,
                            cwd=str(self._workspace),
                            timeout=10,
                        )
                    else:
                        # File was modified/deleted — restore from pre-promote
                        subprocess.run(
                            ["git", "checkout", pre_tag, "--", path],
                            capture_output=True,
                            cwd=str(self._workspace),
                            timeout=10,
                        )
                    reverted += 1

                self._git_add_commit(f"revert: undo orion(ara) session {session_id[:12]}")

                return PromotionResult(
                    success=True,
                    message=f"Reverted {reverted} files to pre-promote state.",
                    files_promoted=reverted,
                    pre_tag=pre_tag,
                )
        except Exception as e:
            return PromotionResult(success=False, message=f"Revert failed: {e}")

        return PromotionResult(success=False, message="Undo failed.")

    def cleanup_sandbox(self, session_id: str) -> bool:
        """Remove the sandbox directory for a session."""
        sandbox = self.get_sandbox_path(session_id)
        if sandbox is None:
            return False
        shutil.rmtree(sandbox)
        return True

    # --- Git helpers ---

    def _get_head_commit(self) -> str | None:
        """Get the current HEAD commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(self._workspace),
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _get_changed_files_since(self, commit: str) -> set[str]:
        """Get files changed in workspace since a given commit."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", commit, "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(self._workspace),
                timeout=10,
            )
            if result.returncode == 0:
                return {
                    f.replace("\\", "/") for f in result.stdout.strip().split("\n") if f.strip()
                }
        except Exception:
            pass
        return set()

    def _git_tag(self, tag_name: str) -> bool:
        """Create a lightweight git tag."""
        try:
            result = subprocess.run(
                ["git", "tag", tag_name],
                capture_output=True,
                text=True,
                cwd=str(self._workspace),
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _tag_exists(self, tag_name: str) -> bool:
        """Check if a git tag exists."""
        try:
            result = subprocess.run(
                ["git", "tag", "-l", tag_name],
                capture_output=True,
                text=True,
                cwd=str(self._workspace),
                timeout=10,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    def _git_add_commit(self, message: str) -> bool:
        """Stage all changes and commit."""
        try:
            subprocess.run(
                ["git", "add", "-A"],
                capture_output=True,
                cwd=str(self._workspace),
                timeout=10,
            )
            result = subprocess.run(
                ["git", "commit", "-m", message, "--allow-empty"],
                capture_output=True,
                text=True,
                cwd=str(self._workspace),
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False
