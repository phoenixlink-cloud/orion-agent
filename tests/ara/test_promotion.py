# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Phase 11: PromotionManager — sandbox → workspace file promotion."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orion.ara.promotion import ConflictFile, FileDiff, PromotionManager, PromotionResult


def _git_init(path: Path) -> None:
    """Initialize a git repo with an initial commit."""
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), capture_output=True)
    (path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "-A"], cwd=str(path), capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(path), capture_output=True)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    _git_init(ws)
    return ws


@pytest.fixture
def pm(workspace: Path, tmp_path: Path) -> PromotionManager:
    sandbox_root = tmp_path / "sandboxes"
    return PromotionManager(workspace=workspace, sandbox_root=sandbox_root)


class TestDataclasses:
    def test_file_diff(self):
        d = FileDiff(path="src/main.py", status="added", additions=10)
        assert d.path == "src/main.py"
        assert d.status == "added"

    def test_conflict_file(self):
        c = ConflictFile(path="a.py", sandbox_status="modified", workspace_status="modified")
        assert c.path == "a.py"

    def test_promotion_result_success(self):
        r = PromotionResult(success=True, message="ok", files_promoted=3)
        assert r.success
        assert r.files_promoted == 3

    def test_promotion_result_failure(self):
        r = PromotionResult(success=False, message="no sandbox")
        assert not r.success


class TestCreateSandbox:
    def test_creates_directory(self, pm: PromotionManager):
        path = pm.create_sandbox("sess-001")
        assert path.exists()
        assert (path / ".base_commit").exists()
        assert (path / ".created_at").exists()
        assert (path / "workspace").exists()

    def test_get_sandbox_path(self, pm: PromotionManager):
        pm.create_sandbox("sess-002")
        assert pm.get_sandbox_path("sess-002") is not None
        assert pm.get_sandbox_path("nonexistent") is None

    def test_recreate_sandbox(self, pm: PromotionManager):
        pm.create_sandbox("sess-003")
        pm.add_file("sess-003", "old.txt", "old content")
        pm.create_sandbox("sess-003")  # recreate
        assert not (pm.get_sandbox_path("sess-003") / "workspace" / "old.txt").exists()


class TestAddDeleteFile:
    def test_add_file(self, pm: PromotionManager):
        pm.create_sandbox("s1")
        assert pm.add_file("s1", "src/new.py", "print('hello')")
        sandbox = pm.get_sandbox_path("s1")
        assert (sandbox / "workspace" / "src" / "new.py").exists()

    def test_add_to_nonexistent_sandbox(self, pm: PromotionManager):
        assert pm.add_file("nope", "file.py", "content") is False

    def test_delete_file(self, pm: PromotionManager):
        pm.create_sandbox("s2")
        assert pm.delete_file("s2", "README.md")
        sandbox = pm.get_sandbox_path("s2")
        assert "README.md" in (sandbox / ".deletions").read_text()

    def test_delete_nonexistent_sandbox(self, pm: PromotionManager):
        assert pm.delete_file("nope", "file.py") is False


class TestGetDiff:
    def test_no_changes(self, pm: PromotionManager):
        pm.create_sandbox("d1")
        diffs = pm.get_diff("d1")
        assert diffs == []

    def test_added_file(self, pm: PromotionManager):
        pm.create_sandbox("d2")
        pm.add_file("d2", "new.py", "line1\nline2\n")
        diffs = pm.get_diff("d2")
        assert len(diffs) == 1
        assert diffs[0].status == "added"
        assert diffs[0].path == "new.py"
        assert diffs[0].additions > 0

    def test_modified_file(self, pm: PromotionManager, workspace: Path):
        (workspace / "existing.py").write_text("original\n")
        pm.create_sandbox("d3")
        pm.add_file("d3", "existing.py", "modified\ncontent\n")
        diffs = pm.get_diff("d3")
        assert len(diffs) == 1
        assert diffs[0].status == "modified"

    def test_deleted_file(self, pm: PromotionManager):
        pm.create_sandbox("d4")
        pm.delete_file("d4", "README.md")
        diffs = pm.get_diff("d4")
        assert len(diffs) == 1
        assert diffs[0].status == "deleted"
        assert diffs[0].path == "README.md"

    def test_mixed_changes(self, pm: PromotionManager, workspace: Path):
        (workspace / "mod.py").write_text("old\n")
        pm.create_sandbox("d5")
        pm.add_file("d5", "new.py", "new content\n")
        pm.add_file("d5", "mod.py", "new content\n")
        pm.delete_file("d5", "README.md")
        diffs = pm.get_diff("d5")
        assert len(diffs) == 3
        statuses = {d.status for d in diffs}
        assert statuses == {"added", "modified", "deleted"}

    def test_nonexistent_sandbox(self, pm: PromotionManager):
        assert pm.get_diff("nope") == []


class TestPromote:
    def test_promote_added_file(self, pm: PromotionManager, workspace: Path):
        pm.create_sandbox("p1")
        pm.add_file("p1", "src/hello.py", "print('hello')\n")
        result = pm.promote("p1", goal="Add hello script")
        assert result.success
        assert result.files_promoted == 1
        assert (workspace / "src" / "hello.py").exists()

    def test_promote_deleted_file(self, pm: PromotionManager, workspace: Path):
        (workspace / "delete_me.txt").write_text("bye\n")
        subprocess.run(["git", "add", "-A"], cwd=str(workspace), capture_output=True)
        subprocess.run(["git", "commit", "-m", "add file"], cwd=str(workspace), capture_output=True)

        pm.create_sandbox("p2")
        pm.delete_file("p2", "delete_me.txt")
        result = pm.promote("p2", goal="Remove old file")
        assert result.success
        assert not (workspace / "delete_me.txt").exists()

    def test_promote_no_changes(self, pm: PromotionManager):
        pm.create_sandbox("p3")
        result = pm.promote("p3")
        assert not result.success
        assert "No changes" in result.message

    def test_promote_nonexistent(self, pm: PromotionManager):
        result = pm.promote("nope")
        assert not result.success

    def test_promote_creates_tags(self, pm: PromotionManager, workspace: Path):
        pm.create_sandbox("p4")
        pm.add_file("p4", "tagged.py", "content\n")
        result = pm.promote("p4", goal="Tagged promote")
        assert result.pre_tag.startswith("orion-pre-promote/")
        assert result.post_tag.startswith("orion-post-promote/")

        # Verify tags exist
        tag_check = subprocess.run(
            ["git", "tag", "-l", "orion-*"],
            capture_output=True, text=True, cwd=str(workspace),
        )
        assert "orion-pre-promote" in tag_check.stdout
        assert "orion-post-promote" in tag_check.stdout


class TestReject:
    def test_reject_marks_sandbox(self, pm: PromotionManager):
        pm.create_sandbox("r1")
        assert pm.reject("r1") is True
        sandbox = pm.get_sandbox_path("r1")
        assert (sandbox / ".rejected").exists()

    def test_reject_nonexistent(self, pm: PromotionManager):
        assert pm.reject("nope") is False


class TestCleanup:
    def test_cleanup_removes_sandbox(self, pm: PromotionManager):
        pm.create_sandbox("c1")
        assert pm.get_sandbox_path("c1") is not None
        assert pm.cleanup_sandbox("c1") is True
        assert pm.get_sandbox_path("c1") is None

    def test_cleanup_nonexistent(self, pm: PromotionManager):
        assert pm.cleanup_sandbox("nope") is False


class TestUndoPromote:
    def test_undo_nonexistent(self, pm: PromotionManager):
        result = pm.undo_promote("nope")
        assert not result.success

    def test_undo_after_promote(self, pm: PromotionManager, workspace: Path):
        # Create and promote
        pm.create_sandbox("u1")
        pm.add_file("u1", "undo_test.py", "new content\n")
        promote_result = pm.promote("u1", goal="Test undo")
        assert promote_result.success
        assert (workspace / "undo_test.py").exists()

        # Undo
        undo_result = pm.undo_promote("u1")
        assert undo_result.success
        # File should be reverted (removed since it didn't exist before)
        assert not (workspace / "undo_test.py").exists()
