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
"""Sandbox security / escape tests (ARA-001 §C.13, Layer 3).

These tests verify Docker container hardening. They require Docker to be
running and are skipped automatically if Docker is unavailable.

Marked with @pytest.mark.docker — run with: pytest -m docker
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

# Skip entire module if Docker is not available
pytestmark = pytest.mark.docker

DOCKER_IMAGE = "python:3.11-slim"
CONTAINER_BASE = "orion-test-security"


def docker_available() -> bool:
    """Check if Docker daemon is running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


if not shutil.which("docker") or not docker_available():
    pytest.skip("Docker not available", allow_module_level=True)


def run_in_hardened_container(
    code: str,
    network: bool = False,
    workspace_path: str | None = None,
) -> subprocess.CompletedProcess:
    """Run Python code in a hardened container matching ARA config."""
    cmd = [
        "docker", "run", "--rm",
        "--memory", "256m",
        "--cpus", "1.0",
        "--pids-limit", "64",
        "--cap-drop", "ALL",
        "--no-new-privileges",
        "--security-opt", "no-new-privileges",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
    ]
    if not network:
        cmd.extend(["--network", "none"])
    if workspace_path:
        cmd.extend(["-v", f"{workspace_path}:/workspace", "-w", "/workspace"])
    cmd.extend([DOCKER_IMAGE, "python3", "-c", code])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


class TestNetworkIsolation:
    """Verify containers cannot make network requests."""

    def test_cannot_make_network_requests(self):
        code = """
import urllib.request
try:
    urllib.request.urlopen("http://1.1.1.1", timeout=3)
    print("NETWORK_ACCESSIBLE")
except Exception as e:
    print(f"BLOCKED: {e}")
"""
        result = run_in_hardened_container(code, network=False)
        assert "NETWORK_ACCESSIBLE" not in result.stdout
        assert "BLOCKED" in result.stdout or result.returncode != 0

    def test_cannot_resolve_dns(self):
        code = """
import socket
try:
    socket.getaddrinfo("google.com", 80, socket.AF_INET)
    print("DNS_WORKS")
except Exception:
    print("DNS_BLOCKED")
"""
        result = run_in_hardened_container(code, network=False)
        assert "DNS_WORKS" not in result.stdout


class TestFilesystemIsolation:
    """Verify containers cannot access host filesystem."""

    def test_cannot_access_host_filesystem(self):
        code = """
import os
try:
    entries = os.listdir("/host")
    print(f"HOST_VISIBLE: {entries}")
except Exception:
    print("HOST_BLOCKED")
"""
        result = run_in_hardened_container(code)
        assert "HOST_VISIBLE" not in result.stdout

    def test_root_filesystem_readonly(self):
        code = """
try:
    with open("/etc/test_write", "w") as f:
        f.write("test")
    print("ROOT_WRITABLE")
except Exception:
    print("ROOT_READONLY")
"""
        result = run_in_hardened_container(code)
        assert "ROOT_WRITABLE" not in result.stdout
        assert "ROOT_READONLY" in result.stdout

    def test_can_write_to_tmp(self):
        code = """
try:
    with open("/tmp/test_file", "w") as f:
        f.write("test")
    print("TMP_WRITABLE")
except Exception as e:
    print(f"TMP_BLOCKED: {e}")
"""
        result = run_in_hardened_container(code)
        assert "TMP_WRITABLE" in result.stdout

    def test_can_write_to_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        code = """
try:
    with open("/workspace/test_file.txt", "w") as f:
        f.write("hello from sandbox")
    print("WORKSPACE_WRITABLE")
except Exception as e:
    print(f"WORKSPACE_BLOCKED: {e}")
"""
        result = run_in_hardened_container(
            code, workspace_path=str(workspace)
        )
        assert "WORKSPACE_WRITABLE" in result.stdout
        assert (workspace / "test_file.txt").read_text() == "hello from sandbox"


class TestPrivilegeEscalation:
    """Verify containers cannot escalate privileges."""

    def test_cannot_escalate_privileges(self):
        code = """
import os
try:
    os.setuid(0)
    print("ESCALATED")
except Exception:
    print("ESCALATION_BLOCKED")
"""
        result = run_in_hardened_container(code)
        assert "ESCALATED" not in result.stdout

    def test_capabilities_dropped(self):
        code = """
import subprocess
result = subprocess.run(["cat", "/proc/self/status"], capture_output=True, text=True)
for line in result.stdout.splitlines():
    if line.startswith("CapEff"):
        cap_value = int(line.split(":")[1].strip(), 16)
        if cap_value == 0:
            print("CAPS_DROPPED")
        else:
            print(f"CAPS_PRESENT: {cap_value}")
        break
"""
        result = run_in_hardened_container(code)
        assert "CAPS_DROPPED" in result.stdout


class TestResourceLimits:
    """Verify resource limits are enforced."""

    def test_pids_limit_enforced(self):
        code = """
import os
pids = []
try:
    for i in range(200):
        pid = os.fork()
        if pid == 0:
            import time; time.sleep(10)
            os._exit(0)
        pids.append(pid)
    print(f"FORKED: {len(pids)}")
except Exception as e:
    print(f"PID_LIMITED: {len(pids)} forks before limit")
finally:
    import signal
    for p in pids:
        try:
            os.kill(p, signal.SIGKILL)
            os.waitpid(p, 0)
        except Exception:
            pass
"""
        result = run_in_hardened_container(code)
        # Should hit PID limit well before 200
        assert "PID_LIMITED" in result.stdout or result.returncode != 0

    def test_memory_limit_enforced(self):
        code = """
import sys
blocks = []
try:
    for i in range(500):
        blocks.append(b"X" * (1024 * 1024))  # 1MB each, 500MB total > 256MB limit
    print(f"ALLOCATED: {len(blocks)}MB")
except MemoryError:
    print(f"MEMORY_LIMITED: {len(blocks)}MB allocated before OOM")
"""
        result = run_in_hardened_container(code)
        # Container should be killed (137) or Python should hit MemoryError
        assert (
            "MEMORY_LIMITED" in result.stdout
            or result.returncode == 137
            or result.returncode != 0
        )
