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
"""Session Container Manager — persistent Docker container per ARA session.

Manages a single Docker container that persists across multiple commands
within one ARA work session.  Replaces the spin-up-per-command pattern
in SandboxManager with a long-lived container that supports:

- Phased networking: install phase gets egress proxy, execute phase has no network
- Resource profiles: light / standard / heavy
- AEGIS config read-only mount preserved
- Workspace read-write mount
- Audit logging per command

The container runs a pre-baked stack image (orion-stack-{stack}:latest)
and stays alive via ``sleep infinity`` until the session ends.

Security invariants:
  - Execute phase: --network none (no internet access)
  - Install phase: temporary connection to orion-egress network (proxy-filtered)
  - AEGIS config: read-only bind mount, container cannot modify
  - Workspace: read-write bind mount within /workspace only
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.security.session_container")

# ---------------------------------------------------------------------------
# Resource profiles
# ---------------------------------------------------------------------------
PROFILES: dict[str, dict[str, str | int]] = {
    "light": {"memory": "512m", "cpus": "1", "pids": 128},
    "standard": {"memory": "2g", "cpus": "2", "pids": 256},
    "heavy": {"memory": "4g", "cpus": "4", "pids": 512},
}

# ---------------------------------------------------------------------------
# Egress network name (must match docker-compose / proxy setup)
# ---------------------------------------------------------------------------
EGRESS_NETWORK = "orion-egress"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ORION_HOME = Path(os.environ.get("ORION_HOME", Path.home() / ".orion"))
_AEGIS_CONFIG_DIR = _ORION_HOME / "aegis"


# ---------------------------------------------------------------------------
# ExecResult dataclass
# ---------------------------------------------------------------------------
@dataclass
class ExecResult:
    """Result of executing a command inside the session container."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_seconds: float = 0.0
    command: str = ""
    phase: str = "execute"  # 'install', 'execute', 'test'


# ---------------------------------------------------------------------------
# AuditEntry dataclass
# ---------------------------------------------------------------------------
@dataclass
class AuditEntry:
    """Audit log entry for a container command."""

    session_id: str
    command: str
    exit_code: int
    duration_seconds: float
    phase: str
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ---------------------------------------------------------------------------
# SessionContainer
# ---------------------------------------------------------------------------
class SessionContainer:
    """Persistent Docker container for a single ARA work session.

    Usage::

        container = SessionContainer(session_id="abc123", stack="python")
        await container.start()
        result = await container.exec("python app.py")
        result = await container.exec_install("pip install flask")
        await container.stop()
    """

    CONTAINER_PREFIX = "orion-session-"

    def __init__(
        self,
        session_id: str,
        stack: str = "python",
        profile: str = "standard",
        workspace_path: Path | str | None = None,
        aegis_config_dir: Path | None = None,
        activity_logger: Any | None = None,
    ) -> None:
        self.session_id = session_id
        self.stack = stack
        self.profile = profile
        self.container_name = f"{self.CONTAINER_PREFIX}{session_id}"
        self.workspace_path = Path(workspace_path) if workspace_path else Path.cwd()
        self.aegis_config_dir = aegis_config_dir or _AEGIS_CONFIG_DIR
        self.activity_logger = activity_logger

        # State
        self._running = False
        self._started_at: float = 0.0
        self._command_count: int = 0
        self._audit_log: list[AuditEntry] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        """Check if the container is currently running."""
        return self._running

    @property
    def image_name(self) -> str:
        """Docker image name for this stack."""
        return f"orion-stack-{self.stack}:latest"

    @property
    def resource_profile(self) -> dict[str, Any]:
        """Current resource profile dict."""
        return dict(PROFILES.get(self.profile, PROFILES["standard"]))

    @property
    def audit_log(self) -> list[AuditEntry]:
        """Return audit log entries."""
        return list(self._audit_log)

    @property
    def command_count(self) -> int:
        """Total commands executed in this session."""
        return self._command_count

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------
    async def start(self) -> bool:
        """Start the persistent session container.

        - Pulls/verifies the stack image
        - Runs the container with workspace + AEGIS mounts
        - Applies resource profile limits
        - NO network by default (added only during install phase)

        Returns True if the container starts successfully.
        """
        if self._running:
            logger.warning("Container %s already running", self.container_name)
            return True

        if not self._is_docker_available():
            logger.error("Docker is not available")
            return False

        # Ensure workspace exists
        self.workspace_path.mkdir(parents=True, exist_ok=True)

        # Ensure AEGIS config dir exists (create empty if needed)
        self.aegis_config_dir.mkdir(parents=True, exist_ok=True)

        # Build docker run command
        prof = self.resource_profile
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            self.container_name,
            "--memory",
            str(prof["memory"]),
            "--cpus",
            str(prof["cpus"]),
            "--pids-limit",
            str(prof["pids"]),
            "--network",
            "none",
            "-v",
            f"{self.workspace_path}:/workspace:rw",
            "-v",
            f"{self.aegis_config_dir}:/etc/orion/aegis:ro",
            "-w",
            "/workspace",
            self.image_name,
            "sleep",
            "infinity",
        ]

        try:
            result = await self._run_docker(cmd, timeout=60)
            if result.returncode != 0:
                stderr = result.stderr.strip()[:500] if result.stderr else "unknown error"
                logger.error("Failed to start container: %s", stderr)
                return False

            self._running = True
            self._started_at = time.time()
            logger.info(
                "Session container started: %s (stack=%s, profile=%s)",
                self.container_name,
                self.stack,
                self.profile,
            )
            return True

        except Exception as exc:
            logger.error("Failed to start session container: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Exec (execute phase — no network)
    # ------------------------------------------------------------------
    async def exec(
        self,
        command: str,
        timeout: int = 120,
        phase: str = "execute",
    ) -> ExecResult:
        """Execute a command inside the container (no network).

        Args:
            command: Shell command to run.
            timeout: Max seconds before the process is killed.
            phase: Execution phase label for audit.

        Returns:
            ExecResult with stdout, stderr, exit_code, duration.
        """
        if not self._running:
            return ExecResult(
                stderr="Container not running",
                exit_code=-1,
                command=command,
                phase=phase,
            )

        # Activity log: start
        activity_entry = None
        if self.activity_logger:
            activity_entry = self.activity_logger.log(
                action_type="command",
                description=f"Running: {command[:100]}",
                command=command,
                phase=phase,
            )

        start = time.time()
        cmd = [
            "docker",
            "exec",
            self.container_name,
            "sh",
            "-c",
            command,
        ]

        try:
            result = await self._run_docker(cmd, timeout=timeout)
            duration = time.time() - start

            exec_result = ExecResult(
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                exit_code=result.returncode,
                duration_seconds=round(duration, 3),
                command=command,
                phase=phase,
            )

        except asyncio.TimeoutError:
            duration = time.time() - start
            # Kill the process inside the container, not the container itself
            await self._kill_exec_process(command)
            exec_result = ExecResult(
                stderr=f"Command timed out after {timeout}s",
                exit_code=-1,
                duration_seconds=round(duration, 3),
                command=command,
                phase=phase,
            )

        # Audit log
        self._command_count += 1
        self._audit_log.append(
            AuditEntry(
                session_id=self.session_id,
                command=command,
                exit_code=exec_result.exit_code,
                duration_seconds=exec_result.duration_seconds,
                phase=phase,
            )
        )

        # Activity log: complete
        if self.activity_logger and activity_entry:
            self.activity_logger.update(
                activity_entry,
                exit_code=exec_result.exit_code,
                stdout=exec_result.stdout[:2000] if exec_result.stdout else None,
                stderr=exec_result.stderr[:2000] if exec_result.stderr else None,
                duration_seconds=exec_result.duration_seconds,
                status="success" if exec_result.exit_code == 0 else "failed",
            )

        logger.debug(
            "exec [%s] exit=%d duration=%.1fs: %s",
            phase,
            exec_result.exit_code,
            exec_result.duration_seconds,
            command[:100],
        )
        return exec_result

    # ------------------------------------------------------------------
    # Exec Install (install phase — temporary egress network)
    # ------------------------------------------------------------------
    async def exec_install(
        self,
        command: str,
        timeout: int = 300,
    ) -> ExecResult:
        """Execute an install command with temporary network access.

        Connects the container to the egress proxy network, runs the
        install command, then disconnects — restoring network isolation.

        Args:
            command: Install command (e.g. ``pip install -r requirements.txt``).
            timeout: Max seconds for the install.

        Returns:
            ExecResult with stdout, stderr, exit_code, duration.
        """
        if not self._running:
            return ExecResult(
                stderr="Container not running",
                exit_code=-1,
                command=command,
                phase="install",
            )

        # Connect to egress network
        connected = await self._connect_network()
        try:
            result = await self.exec(command, timeout=timeout, phase="install")
        finally:
            # Always disconnect — even on timeout/error
            if connected:
                await self._disconnect_network()

        return result

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    async def write_file(self, path: str, content: str) -> bool:
        """Write a file inside the container.

        Path must be within /workspace/ (AEGIS workspace confinement).

        Args:
            path: Absolute path inside container (e.g. ``/workspace/app.py``).
            content: File content to write.

        Returns:
            True if the file was written successfully.
        """
        # Validate path confinement
        if not self._is_workspace_path(path):
            logger.warning("Rejected write outside workspace: %s", path)
            return False

        # Activity log: start
        activity_entry = None
        if self.activity_logger:
            activity_entry = self.activity_logger.log(
                action_type="file_write",
                description=f"Writing file: {path}",
                phase="execute",
            )

        # Ensure parent directory exists, then write via stdin pipe
        parent_dir = str(Path(path).parent)
        mkdir_cmd = ["docker", "exec", self.container_name, "mkdir", "-p", parent_dir]
        await self._run_docker(mkdir_cmd, timeout=10)

        # Write content via docker exec with stdin
        write_cmd = [
            "docker",
            "exec",
            "-i",
            self.container_name,
            "sh",
            "-c",
            f"cat > {path}",
        ]
        try:
            result = await self._run_docker(
                write_cmd,
                timeout=30,
                input_data=content,
            )
            success = result.returncode == 0
            if self.activity_logger and activity_entry:
                self.activity_logger.update(
                    activity_entry,
                    status="success" if success else "failed",
                )
            return success
        except Exception as exc:
            logger.error("Failed to write file %s: %s", path, exc)
            if self.activity_logger and activity_entry:
                self.activity_logger.update(activity_entry, status="failed")
            return False

    async def read_file(self, path: str) -> str:
        """Read a file from inside the container.

        Args:
            path: Absolute path inside container.

        Returns:
            File content as string, or empty string on failure.
        """
        activity_entry = None
        if self.activity_logger:
            activity_entry = self.activity_logger.log(
                action_type="file_read",
                description=f"Reading file: {path}",
                phase="execute",
            )

        cmd = ["docker", "exec", self.container_name, "cat", path]
        try:
            result = await self._run_docker(cmd, timeout=30)
            if result.returncode == 0:
                if self.activity_logger and activity_entry:
                    self.activity_logger.update(activity_entry, status="success")
                return result.stdout or ""
        except Exception as exc:
            logger.debug("Failed to read file %s: %s", path, exc)

        if self.activity_logger and activity_entry:
            self.activity_logger.update(activity_entry, status="failed")
        return ""

    async def list_files(self, path: str = "/workspace") -> list[str]:
        """List files inside the container directory.

        Args:
            path: Directory path inside container.

        Returns:
            List of file paths relative to the given path.
        """
        cmd = [
            "docker",
            "exec",
            self.container_name,
            "find",
            path,
            "-type",
            "f",
        ]
        try:
            result = await self._run_docker(cmd, timeout=30)
            if result.returncode == 0 and result.stdout:
                return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        except Exception as exc:
            logger.debug("Failed to list files in %s: %s", path, exc)
        return []

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------
    async def stop(self) -> bool:
        """Stop and remove the session container.

        Returns True if the container was stopped successfully.
        """
        if not self._running:
            return True

        duration = time.time() - self._started_at

        try:
            # Stop the container
            stop_cmd = ["docker", "stop", "-t", "5", self.container_name]
            await self._run_docker(stop_cmd, timeout=15)

            # Remove the container
            rm_cmd = ["docker", "rm", "-f", self.container_name]
            await self._run_docker(rm_cmd, timeout=15)

            self._running = False
            logger.info(
                "Session container stopped: %s (duration=%.0fs, commands=%d)",
                self.container_name,
                duration,
                self._command_count,
            )

            # Audit: session end
            self._audit_log.append(
                AuditEntry(
                    session_id=self.session_id,
                    command="__session_end__",
                    exit_code=0,
                    duration_seconds=round(duration, 1),
                    phase="lifecycle",
                )
            )
            return True

        except Exception as exc:
            logger.error("Failed to stop container %s: %s", self.container_name, exc)
            # Force remove
            try:
                force_cmd = ["docker", "rm", "-f", self.container_name]
                await self._run_docker(force_cmd, timeout=10)
                self._running = False
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # Network management (for install phase)
    # ------------------------------------------------------------------
    async def _connect_network(self) -> bool:
        """Connect the container to the egress proxy network."""
        cmd = ["docker", "network", "connect", EGRESS_NETWORK, self.container_name]
        try:
            result = await self._run_docker(cmd, timeout=15)
            if result.returncode == 0:
                logger.debug("Connected %s to egress network", self.container_name)
                return True
            logger.warning(
                "Failed to connect to egress network: %s",
                (result.stderr or "")[:200],
            )
            return False
        except Exception as exc:
            logger.warning("Network connect error: %s", exc)
            return False

    async def _disconnect_network(self) -> bool:
        """Disconnect the container from the egress proxy network."""
        cmd = ["docker", "network", "disconnect", EGRESS_NETWORK, self.container_name]
        try:
            result = await self._run_docker(cmd, timeout=15)
            if result.returncode == 0:
                logger.debug("Disconnected %s from egress network", self.container_name)
                return True
            return False
        except Exception as exc:
            logger.warning("Network disconnect error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _is_workspace_path(path: str) -> bool:
        """Check that a path is confined to /workspace/."""
        # Normalize and check prefix
        normalized = os.path.normpath(path).replace("\\", "/")
        return normalized.startswith("/workspace/") or normalized == "/workspace"

    async def _kill_exec_process(self, command: str) -> None:
        """Best-effort kill of a timed-out process inside the container."""
        # Kill all sh processes that might be running our command
        kill_cmd = [
            "docker",
            "exec",
            self.container_name,
            "sh",
            "-c",
            "kill -9 $(pgrep -f 'sh -c' | head -5) 2>/dev/null || true",
        ]
        try:
            await self._run_docker(kill_cmd, timeout=5)
        except Exception:
            pass

    @staticmethod
    def _is_docker_available() -> bool:
        """Check if Docker daemon is running."""
        if not shutil.which("docker"):
            return False
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    @staticmethod
    async def _run_docker(
        cmd: list[str],
        timeout: int = 60,
        input_data: str | None = None,
    ) -> subprocess.CompletedProcess:
        """Run a Docker CLI command asynchronously.

        Uses asyncio subprocess for non-blocking execution.
        """
        loop = asyncio.get_event_loop()

        def _run() -> subprocess.CompletedProcess:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                input=input_data,
            )

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, _run),
                timeout=timeout + 5,  # Slightly longer than subprocess timeout
            )
        except asyncio.TimeoutError:
            raise
        except subprocess.TimeoutExpired:
            raise asyncio.TimeoutError(f"Docker command timed out ({timeout}s): {' '.join(cmd)}")
