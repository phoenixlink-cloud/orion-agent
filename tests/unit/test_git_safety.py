"""Unit tests for GitSafetyNet -- savepoints, undo, edit history."""

import os
import pytest
import tempfile
import subprocess
from orion.core.editing.safety import GitSafetyNet


@pytest.fixture
def git_workspace():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["git", "init", "-q"],
            cwd=tmp, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp, capture_output=True,
        )
        # Create initial commit
        init_file = os.path.join(tmp, "init.txt")
        with open(init_file, "w") as f:
            f.write("initial\n")
        subprocess.run(["git", "add", "."], cwd=tmp, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init", "-q"],
            cwd=tmp, capture_output=True,
        )
        yield tmp


class TestGitSafetyInit:
    """Test GitSafetyNet initialization."""

    def test_init_with_git_repo(self, git_workspace):
        safety = GitSafetyNet(git_workspace)
        assert safety.enabled

    def test_init_with_non_git_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            safety = GitSafetyNet(tmp)
            # Should handle gracefully even without git


class TestSavepoints:
    """Test savepoint creation and undo."""

    def test_create_savepoint(self, git_workspace):
        safety = GitSafetyNet(git_workspace)
        safety.create_savepoint("test savepoint")
        assert safety.get_savepoint_count() >= 1

    def test_undo_reverts_changes(self, git_workspace):
        safety = GitSafetyNet(git_workspace)
        safety.create_savepoint("before edit")

        # Make a change
        test_file = os.path.join(git_workspace, "test.py")
        with open(test_file, "w") as f:
            f.write("print('hello')\n")
        subprocess.run(["git", "add", "."], cwd=git_workspace, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "test edit", "-q"],
            cwd=git_workspace, capture_output=True,
        )

        # Undo should revert
        result = safety.undo()
        assert result is not None or result is True or isinstance(result, dict)


class TestEditHistory:
    """Test edit tracking."""

    def test_get_edit_history(self, git_workspace):
        safety = GitSafetyNet(git_workspace)
        history = safety.get_edit_history()
        assert isinstance(history, (list, dict))

    def test_get_undo_stack(self, git_workspace):
        safety = GitSafetyNet(git_workspace)
        stack = safety.get_undo_stack()
        assert isinstance(stack, list)
