"""Unit tests for WorkspaceSandbox — local mode (no Docker dependency)."""

import os
import pytest
import tempfile
from orion.security.workspace_sandbox import (
    WorkspaceSandbox, SandboxMode, SandboxSession, SandboxDiff, PromoteResult,
)


@pytest.fixture
def test_workspace():
    """Create a temporary workspace with test files."""
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "src"), exist_ok=True)
        with open(os.path.join(tmp, "main.py"), "w") as f:
            f.write("print('hello world')\n")
        with open(os.path.join(tmp, "src", "utils.py"), "w") as f:
            f.write("def add(a, b):\n    return a + b\n")
        with open(os.path.join(tmp, "README.md"), "w") as f:
            f.write("# Test Project\n")
        yield tmp


@pytest.fixture
def local_sandbox():
    """Create a local-mode sandbox."""
    return WorkspaceSandbox(mode="local")


class TestSandboxMode:
    """Test mode resolution."""

    def test_local_mode(self):
        sb = WorkspaceSandbox(mode="local")
        assert sb.requested_mode == SandboxMode.LOCAL

    def test_docker_mode(self):
        sb = WorkspaceSandbox(mode="docker")
        assert sb.requested_mode == SandboxMode.DOCKER

    def test_auto_mode(self):
        sb = WorkspaceSandbox(mode="auto")
        assert sb.requested_mode == SandboxMode.AUTO

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            WorkspaceSandbox(mode="invalid")


class TestLocalSessionLifecycle:
    """Test create → edit → diff → promote → destroy cycle."""

    def test_create_session(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        assert isinstance(session, SandboxSession)
        assert session.mode == "local"
        assert session.file_count >= 3
        assert os.path.exists(session.sandbox_path)
        local_sandbox.destroy_session(session.session_id)

    def test_files_copied(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        assert os.path.exists(os.path.join(session.sandbox_path, "main.py"))
        assert os.path.exists(os.path.join(session.sandbox_path, "src", "utils.py"))
        assert os.path.exists(os.path.join(session.sandbox_path, "README.md"))
        local_sandbox.destroy_session(session.session_id)

    def test_excludes_git(self, local_sandbox):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".git", "objects"), exist_ok=True)
            with open(os.path.join(tmp, ".git", "HEAD"), "w") as f:
                f.write("ref: refs/heads/master\n")
            with open(os.path.join(tmp, "code.py"), "w") as f:
                f.write("x = 1\n")

            session = local_sandbox.create_session(tmp)
            assert not os.path.exists(os.path.join(session.sandbox_path, ".git"))
            assert os.path.exists(os.path.join(session.sandbox_path, "code.py"))
            local_sandbox.destroy_session(session.session_id)

    def test_initial_diff_is_zero(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        diff = local_sandbox.get_diff(session)
        assert isinstance(diff, SandboxDiff)
        assert diff.total_changes == 0
        assert diff.added == []
        assert diff.modified == []
        local_sandbox.destroy_session(session.session_id)

    def test_diff_detects_modification(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        with open(os.path.join(session.sandbox_path, "main.py"), "w") as f:
            f.write("print('MODIFIED')\n")
        diff = local_sandbox.get_diff(session)
        assert "main.py" in diff.modified
        assert diff.total_changes >= 1
        local_sandbox.destroy_session(session.session_id)

    def test_diff_detects_addition(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        with open(os.path.join(session.sandbox_path, "new.py"), "w") as f:
            f.write("# new file\n")
        diff = local_sandbox.get_diff(session)
        assert "new.py" in diff.added
        local_sandbox.destroy_session(session.session_id)

    def test_promote_dry_run(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        with open(os.path.join(session.sandbox_path, "new.py"), "w") as f:
            f.write("# new\n")
        result = local_sandbox.promote(session, dry_run=True)
        assert isinstance(result, PromoteResult)
        assert result.dry_run is True
        assert len(result.files_promoted) >= 1
        # Dry run should NOT create the file in original workspace
        assert not os.path.exists(os.path.join(test_workspace, "new.py"))
        local_sandbox.destroy_session(session.session_id)

    def test_promote_real(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        with open(os.path.join(session.sandbox_path, "main.py"), "w") as f:
            f.write("print('promoted')\n")
        with open(os.path.join(session.sandbox_path, "added.py"), "w") as f:
            f.write("x = 42\n")
        result = local_sandbox.promote(session)
        assert result.success is True
        # Verify files in original workspace
        content = open(os.path.join(test_workspace, "main.py")).read()
        assert "promoted" in content
        assert os.path.exists(os.path.join(test_workspace, "added.py"))
        local_sandbox.destroy_session(session.session_id)

    def test_promote_specific_files(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        with open(os.path.join(session.sandbox_path, "main.py"), "w") as f:
            f.write("print('changed')\n")
        with open(os.path.join(session.sandbox_path, "extra.py"), "w") as f:
            f.write("# extra\n")
        # Only promote main.py
        result = local_sandbox.promote(session, files=["main.py"])
        assert result.success is True
        assert "main.py" in result.files_promoted
        assert not os.path.exists(os.path.join(test_workspace, "extra.py"))
        local_sandbox.destroy_session(session.session_id)

    def test_destroy_cleans_up(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        sandbox_path = session.sandbox_path
        assert os.path.exists(sandbox_path)
        local_sandbox.destroy_session(session.session_id)
        assert not os.path.exists(sandbox_path)

    def test_destroy_nonexistent_returns_false(self, local_sandbox):
        assert local_sandbox.destroy_session("nonexistent") is False


class TestLocalCodeExecution:
    """Test code execution in local sandbox."""

    def test_python_execution(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        result = local_sandbox.run_code(session, "print(2 + 2)", "python")
        assert result["success"] is True
        assert result["stdout"].strip() == "4"
        assert result["mode"] == "local"
        local_sandbox.destroy_session(session.session_id)

    def test_python_can_read_sandbox_files(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        result = local_sandbox.run_code(
            session, "print(open('main.py').read())", "python",
        )
        assert result["success"] is True
        assert "hello world" in result["stdout"]
        local_sandbox.destroy_session(session.session_id)

    def test_timeout_returns_error(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        result = local_sandbox.run_code(
            session, "import time; time.sleep(10)", "python", timeout=1,
        )
        assert result["success"] is False
        assert "Timed out" in result.get("error", "")
        local_sandbox.destroy_session(session.session_id)

    def test_unsupported_language(self, local_sandbox, test_workspace):
        session = local_sandbox.create_session(test_workspace)
        result = local_sandbox.run_code(session, "code", "rust")
        assert result["success"] is False
        assert "Unsupported" in result.get("error", "")
        local_sandbox.destroy_session(session.session_id)


class TestCapabilities:
    """Test capability reporting."""

    def test_local_capabilities(self):
        sb = WorkspaceSandbox(mode="local")
        caps = sb.get_capabilities()
        assert caps.mode == "local"
        assert caps.can_execute_code is True
        assert caps.can_edit_files is True
        assert caps.can_install_packages is False
        assert caps.isolation_level == "filesystem"

    def test_docker_capabilities(self):
        sb = WorkspaceSandbox(mode="docker")
        caps = sb.get_capabilities()
        assert caps.mode == "docker"
        assert caps.can_execute_code is True
        assert caps.isolation_level == "container"
        assert caps.can_install_packages is True


class TestStatus:
    """Test status reporting."""

    def test_status_structure(self):
        sb = WorkspaceSandbox(mode="local")
        status = sb.get_status()
        assert "requested_mode" in status
        assert "resolved_mode" in status
        assert "docker_available" in status
        assert "capabilities" in status
        assert "limits" in status

    def test_status_with_session(self, test_workspace):
        sb = WorkspaceSandbox(mode="local")
        session = sb.create_session(test_workspace)
        status = sb.get_status()
        assert status["active_sessions"] == 1
        assert len(status["sessions"]) == 1
        sb.destroy_session(session.session_id)
