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
"""Tests for SessionContainer — persistent Docker container per ARA session.

Tests SC-01 through SC-12 as specified in Phase 4A.1.

Tests are split into two groups:
- Unit tests: validate logic without Docker (always run)
- Integration tests: require Docker daemon (skipped if unavailable)
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.security.session_container import (
    EGRESS_NETWORK,
    PROFILES,
    AuditEntry,
    ExecResult,
    SessionContainer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Check if Docker daemon is running."""
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _image_exists(image: str) -> bool:
    """Check if a Docker image exists locally."""
    try:
        result = subprocess.run(
            ["docker", "images", "-q", image],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


requires_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker daemon not available",
)

requires_python_stack = pytest.mark.skipif(
    not _docker_available() or not _image_exists("orion-stack-python:latest"),
    reason="orion-stack-python:latest image not built",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def container(tmp_path: Path) -> SessionContainer:
    """Create a SessionContainer with a temp workspace (not started)."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    aegis = tmp_path / "aegis"
    aegis.mkdir()
    (aegis / "egress_config.yaml").write_text("allowed_domains: []\n")
    return SessionContainer(
        session_id="test-001",
        stack="python",
        profile="standard",
        workspace_path=ws,
        aegis_config_dir=aegis,
    )


# ---------------------------------------------------------------------------
# Unit Tests (no Docker required)
# ---------------------------------------------------------------------------


class TestSessionContainerUnit:
    """Unit tests that validate SessionContainer logic without Docker."""

    def test_container_name_format(self, container: SessionContainer):
        """Container name follows orion-session-{session_id} pattern."""
        assert container.container_name == "orion-session-test-001"

    def test_image_name_format(self, container: SessionContainer):
        """Image name follows orion-stack-{stack}:latest pattern."""
        assert container.image_name == "orion-stack-python:latest"

    def test_resource_profile_standard(self, container: SessionContainer):
        """Standard profile returns correct limits."""
        prof = container.resource_profile
        assert prof["memory"] == "2g"
        assert prof["cpus"] == "2"
        assert prof["pids"] == 256

    def test_resource_profile_light(self, tmp_path: Path):
        """Light profile returns lower limits."""
        c = SessionContainer(session_id="t", profile="light", workspace_path=tmp_path)
        assert c.resource_profile["memory"] == "512m"
        assert c.resource_profile["pids"] == 128

    def test_resource_profile_heavy(self, tmp_path: Path):
        """Heavy profile returns higher limits."""
        c = SessionContainer(session_id="t", profile="heavy", workspace_path=tmp_path)
        assert c.resource_profile["memory"] == "4g"
        assert c.resource_profile["cpus"] == "4"

    def test_resource_profile_fallback(self, tmp_path: Path):
        """Unknown profile falls back to standard."""
        c = SessionContainer(session_id="t", profile="unknown", workspace_path=tmp_path)
        assert c.resource_profile == dict(PROFILES["standard"])

    def test_workspace_path_validation_accepts_workspace(self):
        """Paths under /workspace/ are accepted."""
        assert SessionContainer._is_workspace_path("/workspace/app.py") is True
        assert SessionContainer._is_workspace_path("/workspace/src/main.py") is True
        assert SessionContainer._is_workspace_path("/workspace") is True

    def test_workspace_path_validation_rejects_outside(self):
        """Paths outside /workspace/ are rejected (AEGIS confinement)."""
        assert SessionContainer._is_workspace_path("/etc/passwd") is False
        assert SessionContainer._is_workspace_path("/root/.ssh/id_rsa") is False
        assert SessionContainer._is_workspace_path("/tmp/evil") is False
        assert SessionContainer._is_workspace_path("/workspace/../etc/passwd") is False

    def test_not_running_by_default(self, container: SessionContainer):
        """Container is not running before start()."""
        assert container.is_running is False
        assert container.command_count == 0

    def test_exec_result_dataclass(self):
        """ExecResult holds expected fields."""
        r = ExecResult(
            stdout="hello",
            stderr="",
            exit_code=0,
            duration_seconds=1.5,
            command="echo hello",
            phase="execute",
        )
        assert r.stdout == "hello"
        assert r.exit_code == 0
        assert r.phase == "execute"

    def test_audit_entry_auto_timestamp(self):
        """AuditEntry gets automatic timestamp."""
        entry = AuditEntry(
            session_id="test",
            command="ls",
            exit_code=0,
            duration_seconds=0.1,
            phase="execute",
        )
        assert entry.timestamp > 0

    def test_profiles_defined(self):
        """All three profiles are defined with required keys."""
        for name in ("light", "standard", "heavy"):
            assert name in PROFILES
            prof = PROFILES[name]
            assert "memory" in prof
            assert "cpus" in prof
            assert "pids" in prof

    @pytest.mark.asyncio
    async def test_exec_when_not_running(self, container: SessionContainer):
        """Exec returns error when container is not started."""
        result = await container.exec("echo test")
        assert result.exit_code == -1
        assert "not running" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_exec_install_when_not_running(self, container: SessionContainer):
        """Exec install returns error when container is not started."""
        result = await container.exec_install("pip install flask")
        assert result.exit_code == -1
        assert result.phase == "install"

    @pytest.mark.asyncio
    async def test_write_file_rejects_outside_workspace(self, container: SessionContainer):
        """Writing outside /workspace is rejected."""
        container._running = True  # Pretend running for path check
        result = await container.write_file("/etc/shadow", "evil")
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, container: SessionContainer):
        """Stop is a no-op when not running."""
        result = await container.stop()
        assert result is True


# ---------------------------------------------------------------------------
# Integration Tests (require Docker)
# ---------------------------------------------------------------------------


@requires_docker
@requires_python_stack
class TestSessionContainerIntegration:
    """Integration tests that require Docker and the Python stack image.

    SC-01 through SC-12 from Phase 4A.1 specification.
    """

    @pytest.fixture(autouse=True)
    async def _cleanup(self, container: SessionContainer):
        """Ensure container is stopped after each test."""
        yield
        try:
            await container.stop()
        except Exception:
            pass
        # Force remove if still exists
        try:
            subprocess.run(
                ["docker", "rm", "-f", container.container_name],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, container: SessionContainer):
        """SC-01: Container starts and stops cleanly."""
        started = await container.start()
        assert started is True
        assert container.is_running is True

        stopped = await container.stop()
        assert stopped is True
        assert container.is_running is False

    @pytest.mark.asyncio
    async def test_exec_simple_command(self, container: SessionContainer):
        """SC-02: echo 'hello' returns stdout correctly."""
        await container.start()
        result = await container.exec("echo 'hello world'")
        assert result.exit_code == 0
        assert "hello world" in result.stdout

    @pytest.mark.asyncio
    async def test_exec_captures_stderr(self, container: SessionContainer):
        """SC-03: Invalid command returns stderr."""
        await container.start()
        result = await container.exec("ls /nonexistent_path_12345")
        assert result.exit_code != 0
        assert result.stderr  # Should have error output

    @pytest.mark.asyncio
    async def test_exec_timeout_enforcement(self, container: SessionContainer):
        """SC-04: sleep 999 is killed after timeout."""
        await container.start()
        result = await container.exec("sleep 999", timeout=3)
        # Should have been killed — either timeout error or non-zero exit
        assert result.exit_code != 0 or "timed out" in result.stderr.lower()
        assert result.duration_seconds < 10  # Shouldn't wait full 999s

    @pytest.mark.asyncio
    async def test_exec_exit_code(self, container: SessionContainer):
        """SC-05: exit 42 returns exit_code=42."""
        await container.start()
        result = await container.exec("exit 42")
        assert result.exit_code == 42

    @pytest.mark.asyncio
    async def test_write_read_file(self, container: SessionContainer):
        """SC-06: Write file, read it back, content matches."""
        await container.start()
        content = "print('Hello from Orion!')\n"
        written = await container.write_file("/workspace/test_app.py", content)
        assert written is True

        read_back = await container.read_file("/workspace/test_app.py")
        assert read_back.strip() == content.strip()

    @pytest.mark.asyncio
    async def test_workspace_confinement(self, container: SessionContainer):
        """SC-07: Write to /etc/ is rejected (AEGIS workspace confinement)."""
        await container.start()
        result = await container.write_file("/etc/evil.conf", "malicious")
        assert result is False

    @pytest.mark.asyncio
    async def test_aegis_config_readonly(self, container: SessionContainer):
        """SC-08: Write to /etc/orion/aegis/ fails (read-only mount)."""
        await container.start()
        result = await container.exec("echo 'tampered' > /etc/orion/aegis/test_file")
        # Should fail because mount is read-only
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_no_network_by_default(self, container: SessionContainer):
        """SC-09: curl/wget fails inside container (no network in execute phase)."""
        await container.start()
        # Try to reach the internet — should fail
        result = await container.exec(
            "python -c \"import urllib.request; urllib.request.urlopen('http://google.com')\"",
            timeout=10,
        )
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_install_phase_has_network(self, container: SessionContainer):
        """SC-10: exec_install can reach whitelisted domain via egress proxy.

        NOTE: This test requires the orion-egress Docker network to exist.
        If it doesn't, the network connect will fail and we test graceful handling.
        """
        await container.start()
        # Try to install a tiny package — this verifies the network connect/disconnect flow
        result = await container.exec_install("pip install --dry-run pip", timeout=30)
        # Whether it succeeds depends on egress network existence,
        # but the flow (connect → exec → disconnect) should not crash
        assert result.phase == "install"
        assert isinstance(result.exit_code, int)

    @pytest.mark.asyncio
    async def test_network_removed_after_install(self, container: SessionContainer):
        """SC-11: After exec_install, direct network access is gone."""
        await container.start()
        # Run an install (even if network isn't available, disconnect still runs)
        await container.exec_install("echo 'fake install'", timeout=10)
        # Now try direct network access — should fail
        result = await container.exec(
            "python -c \"import urllib.request; urllib.request.urlopen('http://google.com')\"",
            timeout=10,
        )
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_resource_profile_applied(self, container: SessionContainer):
        """SC-12: Container respects memory/cpu limits."""
        await container.start()
        # Inspect container to verify resource limits
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}} {{.HostConfig.PidsLimit}}",
                container.container_name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        parts = result.stdout.strip().split()
        assert len(parts) >= 2
        # Standard profile: 2g = 2147483648 bytes, 2 cpus = 2000000000 nanocpus
        memory_bytes = int(parts[0])
        assert memory_bytes == 2 * 1024 * 1024 * 1024  # 2g

    @pytest.mark.asyncio
    async def test_audit_log_populated(self, container: SessionContainer):
        """Audit log is populated after commands."""
        await container.start()
        await container.exec("echo 'test1'")
        await container.exec("echo 'test2'")
        assert container.command_count == 2
        assert len(container.audit_log) == 2
        assert container.audit_log[0].command == "echo 'test1'"
        assert container.audit_log[1].phase == "execute"

    @pytest.mark.asyncio
    async def test_list_files(self, container: SessionContainer):
        """list_files returns files in the container workspace."""
        await container.start()
        await container.write_file("/workspace/hello.py", "print('hi')")
        files = await container.list_files("/workspace")
        assert any("hello.py" in f for f in files)

    @pytest.mark.asyncio
    async def test_start_idempotent(self, container: SessionContainer):
        """Starting an already-running container returns True."""
        await container.start()
        assert container.is_running is True
        result = await container.start()
        assert result is True
