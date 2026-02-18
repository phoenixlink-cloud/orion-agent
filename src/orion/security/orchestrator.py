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
"""Sandbox Orchestrator -- Governed Docker Startup Sequence.

Implements the 6-step boot sequence from the Milestone Decision Document
(Section 5.3).  All security infrastructure is hardcoded and active
BEFORE Orion's first line of code executes inside the container.

Startup Sequence:
  Step 1: AEGIS reads configuration                          (Host)
  Step 2: Docker images built / pulled                       (Host)
  Step 3: Egress proxy starts with domain whitelist          (Host)
  Step 4: Approval queue starts                              (Host)
  Step 5: DNS filter activates                               (Host)
  Step 6: Container launches in governed environment         (Sandbox)

Shutdown is the reverse: container → DNS → approval → egress → done.

Key invariant:
  AEGIS configuration lives OUTSIDE the Docker sandbox.
  Orion executes INSIDE the sandbox.  Orion can NEVER modify AEGIS.
  This is a physical boundary enforced by container isolation.
"""

from __future__ import annotations

import enum
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.security.orchestrator")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ORION_HOME = Path(os.environ.get("ORION_HOME", Path.home() / ".orion"))
_DEFAULT_COMPOSE_FILE = Path(__file__).resolve().parents[3] / "docker" / "docker-compose.yml"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class BootPhase(enum.Enum):
    """Phases of the governed startup sequence."""

    NOT_STARTED = "not_started"
    AEGIS_CONFIG = "aegis_config"
    DOCKER_BUILD = "docker_build"
    EGRESS_PROXY = "egress_proxy"
    APPROVAL_QUEUE = "approval_queue"
    DNS_FILTER = "dns_filter"
    CONTAINER_LAUNCH = "container_launch"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"
    FAILED = "failed"


class ShutdownReason(enum.Enum):
    """Why the orchestrator is shutting down."""

    USER_REQUESTED = "user_requested"
    BOOT_FAILURE = "boot_failure"
    HEALTH_CHECK_FAILED = "health_check_failed"
    DOCKER_DIED = "docker_died"


# ---------------------------------------------------------------------------
# Status dataclass
# ---------------------------------------------------------------------------
@dataclass
class OrchestratorStatus:
    """Current state of the sandbox orchestrator."""

    phase: str = BootPhase.NOT_STARTED.value
    running: bool = False
    docker_available: bool = False
    google_account_configured: bool = False
    egress_proxy_running: bool = False
    dns_filter_running: bool = False
    approval_queue_running: bool = False
    container_running: bool = False
    container_healthy: bool = False
    uptime_s: float = 0.0
    error: str = ""
    boot_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "running": self.running,
            "docker_available": self.docker_available,
            "google_account_configured": self.google_account_configured,
            "egress_proxy_running": self.egress_proxy_running,
            "dns_filter_running": self.dns_filter_running,
            "approval_queue_running": self.approval_queue_running,
            "container_running": self.container_running,
            "container_healthy": self.container_healthy,
            "uptime_s": round(self.uptime_s, 1),
            "error": self.error,
            "boot_log": self.boot_log[-20:],
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class SandboxOrchestrator:
    """Governed Docker startup sequence for Orion Agent.

    Implements the security architecture from the Milestone Decision
    Document: all security infrastructure is hardcoded and active before
    Orion's first line of code executes inside the container.

    Usage:
        orchestrator = SandboxOrchestrator()
        orchestrator.start()          # 6-step governed boot
        status = orchestrator.status  # Check current state
        orchestrator.stop()           # Graceful reverse shutdown
    """

    def __init__(
        self,
        orion_home: Path | None = None,
        compose_file: Path | None = None,
        egress_port: int = 8888,
        dns_port: int = 5353,
        api_port: int = 8000,
        web_port: int = 3000,
        health_check_interval_s: float = 30.0,
        health_check_timeout_s: float = 5.0,
    ) -> None:
        self._orion_home = orion_home or _ORION_HOME
        self._compose_file = compose_file or _DEFAULT_COMPOSE_FILE
        self._egress_port = egress_port
        self._dns_port = dns_port
        self._api_port = api_port
        self._web_port = web_port
        self._health_interval = health_check_interval_s
        self._health_timeout = health_check_timeout_s

        # State
        self._phase = BootPhase.NOT_STARTED
        self._started_at: float = 0.0
        self._error: str = ""
        self._boot_log: list[str] = []
        self._lock = threading.Lock()

        # Component references (created during boot)
        self._egress_proxy = None  # EgressProxyServer
        self._dns_filter = None  # DNSFilter
        self._approval_queue = None  # ApprovalQueue
        self._google_creds = None  # GoogleCredentialManager

        # Health monitor thread
        self._health_thread: threading.Thread | None = None
        self._running = False

    # -------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------
    @property
    def phase(self) -> BootPhase:
        return self._phase

    @property
    def is_running(self) -> bool:
        return self._running and self._phase == BootPhase.RUNNING

    @property
    def status(self) -> OrchestratorStatus:
        """Get current orchestrator status."""
        return OrchestratorStatus(
            phase=self._phase.value,
            running=self._running,
            docker_available=self._is_docker_available(),
            google_account_configured=self._google_creds is not None
            and self._google_creds.has_credentials,
            egress_proxy_running=self._egress_proxy is not None and self._egress_proxy.is_running,
            dns_filter_running=self._dns_filter is not None and self._dns_filter.is_running,
            approval_queue_running=self._approval_queue is not None,
            container_running=self._is_container_running(),
            container_healthy=self._is_container_healthy(),
            uptime_s=time.time() - self._started_at if self._started_at else 0.0,
            error=self._error,
            boot_log=list(self._boot_log),
        )

    @property
    def egress_proxy(self):
        """Access the egress proxy server (None if not started)."""
        return self._egress_proxy

    @property
    def approval_queue(self):
        """Access the approval queue (None if not started)."""
        return self._approval_queue

    @property
    def dns_filter(self):
        """Access the DNS filter (None if not started)."""
        return self._dns_filter

    # -------------------------------------------------------------------
    # Start -- 6-step governed boot sequence
    # -------------------------------------------------------------------
    def start(self) -> OrchestratorStatus:
        """Execute the 6-step governed startup sequence.

        Returns the final status.  If any step fails, all previously
        started components are torn down and the status contains the
        error details.

        Raises:
            RuntimeError: If Docker is not installed (hard requirement).
        """
        with self._lock:
            if self._running:
                self._log("Already running — ignoring duplicate start()")
                return self.status

        self._started_at = time.time()
        self._error = ""
        self._boot_log = []

        try:
            # Step 1: AEGIS reads configuration
            self._boot_step_1_aegis_config()

            # Step 2: Docker images built / verified
            self._boot_step_2_docker_build()

            # Step 3: Egress proxy starts
            self._boot_step_3_egress_proxy()

            # Step 4: Approval queue starts
            self._boot_step_4_approval_queue()

            # Step 5: DNS filter activates
            self._boot_step_5_dns_filter()

            # Step 6: Container launches
            self._boot_step_6_container_launch()

            # All steps passed — start health monitor
            self._running = True
            self._phase = BootPhase.RUNNING
            self._log("Boot complete — Orion sandbox is governed and running")

            self._health_thread = threading.Thread(
                target=self._health_monitor_loop,
                name="orchestrator-health",
                daemon=True,
            )
            self._health_thread.start()

        except Exception as exc:
            self._error = str(exc)
            self._phase = BootPhase.FAILED
            self._log(f"BOOT FAILED at {self._phase.value}: {exc}")
            logger.error("Sandbox boot failed: %s", exc)
            # Tear down anything that was started
            self._teardown()
            return self.status

        return self.status

    # -------------------------------------------------------------------
    # Stop -- reverse shutdown
    # -------------------------------------------------------------------
    def stop(self, reason: ShutdownReason = ShutdownReason.USER_REQUESTED) -> None:
        """Graceful reverse shutdown: container → DNS → approval → egress."""
        if not self._running and self._phase == BootPhase.NOT_STARTED:
            return

        self._log(f"Shutdown initiated: {reason.value}")
        self._phase = BootPhase.SHUTTING_DOWN
        self._running = False

        self._teardown()

        self._phase = BootPhase.STOPPED
        self._log("Shutdown complete")
        logger.info("Sandbox orchestrator stopped (%s)", reason.value)

    # -------------------------------------------------------------------
    # Reload -- hot-reload config without full restart
    # -------------------------------------------------------------------
    def reload_config(self) -> None:
        """Reload egress/DNS config from disk without restarting."""
        if not self._running:
            return

        self._log("Reloading configuration...")

        if self._egress_proxy:
            self._egress_proxy.reload_config()
            self._log("  Egress proxy config reloaded")

        if self._dns_filter:
            self._dns_filter.reload_config()
            self._log("  DNS filter config reloaded")

        self._log("Configuration reload complete")

    # -------------------------------------------------------------------
    # Boot steps
    # -------------------------------------------------------------------
    def _boot_step_1_aegis_config(self) -> None:
        """Step 1: AEGIS reads configuration from host filesystem."""
        self._phase = BootPhase.AEGIS_CONFIG
        self._log("Step 1/6: Reading AEGIS configuration...")

        # Ensure ORION_HOME exists
        self._orion_home.mkdir(parents=True, exist_ok=True)

        # Load egress config (creates default if missing)
        from orion.security.egress.config import load_config

        config = load_config()
        domain_count = len(config.get_all_allowed_domains())
        self._log(f"  Egress config loaded: {domain_count} allowed domains")

        # Check for Google credentials
        try:
            from orion.security.egress.google_credentials import GoogleCredentialManager

            self._google_creds = GoogleCredentialManager(use_secure_store=False)
            if self._google_creds.has_credentials:
                cred_status = self._google_creds.get_status()
                self._log(f"  Google account: {cred_status.get('email', 'configured')}")
            else:
                self._log("  Google account: not configured (BYOK mode)")
                self._google_creds = None
        except Exception as exc:
            self._log(f"  Google credentials check skipped: {exc}")
            self._google_creds = None

        # Verify AEGIS core is loadable
        from orion.core.governance.aegis import check_network_access

        assert callable(check_network_access), "AEGIS check_network_access not callable"
        self._log("  AEGIS governance gate: loaded (7 invariants)")
        self._log("Step 1/6: AEGIS configuration — OK")

    def _boot_step_2_docker_build(self) -> None:
        """Step 2: Verify Docker is available and images are ready."""
        self._phase = BootPhase.DOCKER_BUILD
        self._log("Step 2/6: Checking Docker environment...")

        # Hard requirement: Docker must be installed
        if not self._is_docker_available():
            raise RuntimeError(
                "Docker is not installed or not running. "
                "Docker is a HARD REQUIREMENT for governed sandbox mode. "
                "Install Docker Desktop and ensure the daemon is running."
            )

        # Get Docker version info
        version = self._docker_cmd(["docker", "version", "--format", "{{.Server.Version}}"])
        self._log(f"  Docker daemon: v{version.strip()}")

        # Verify compose file exists
        if not self._compose_file.exists():
            raise RuntimeError(
                f"docker-compose.yml not found at {self._compose_file}. "
                "Cannot build sandbox without compose configuration."
            )

        # Build images (or verify they exist)
        self._log("  Building Docker images...")
        compose_dir = self._compose_file.parent
        self._docker_cmd(
            ["docker", "compose", "-f", str(self._compose_file), "build"],
            cwd=str(compose_dir),
            timeout=300,
        )
        self._log("Step 2/6: Docker environment — OK")

    def _boot_step_3_egress_proxy(self) -> None:
        """Step 3: Start the egress proxy (host-side, The Narrow Door)."""
        self._phase = BootPhase.EGRESS_PROXY
        self._log("Step 3/6: Starting egress proxy...")

        from orion.security.egress.config import load_config
        from orion.security.egress.proxy import EgressProxyServer

        config = load_config()
        config.proxy_port = self._egress_port

        self._egress_proxy = EgressProxyServer(config=config)
        self._egress_proxy.start()

        # Verify it's running
        time.sleep(0.5)
        if not self._egress_proxy.is_running:
            raise RuntimeError("Egress proxy failed to start")

        domain_count = len(config.get_all_allowed_domains())
        self._log(f"  Listening on port {self._egress_port} ({domain_count} whitelisted domains)")
        self._log("Step 3/6: Egress proxy — OK")

    def _boot_step_4_approval_queue(self) -> None:
        """Step 4: Start the approval queue (host-side)."""
        self._phase = BootPhase.APPROVAL_QUEUE
        self._log("Step 4/6: Starting approval queue...")

        from orion.security.egress.approval_queue import ApprovalQueue

        persist_path = self._orion_home / "approval_queue.json"
        self._approval_queue = ApprovalQueue(persist_path=persist_path)

        self._log(f"  Persist path: {persist_path}")
        self._log("Step 4/6: Approval queue — OK")

    def _boot_step_5_dns_filter(self) -> None:
        """Step 5: Activate DNS filter (host-side)."""
        self._phase = BootPhase.DNS_FILTER
        self._log("Step 5/6: Activating DNS filter...")

        from orion.security.egress.config import load_config
        from orion.security.egress.dns_filter import DNSFilter

        config = load_config()
        self._dns_filter = DNSFilter(
            egress_config=config,
            listen_port=self._dns_port,
        )
        self._dns_filter.start()

        # Verify it's running
        time.sleep(0.3)
        if not self._dns_filter.is_running:
            raise RuntimeError("DNS filter failed to start")

        self._log(f"  Listening on port {self._dns_port} (non-whitelisted → NXDOMAIN)")
        self._log("Step 5/6: DNS filter — OK")

    def _boot_step_6_container_launch(self) -> None:
        """Step 6: Launch the Docker container in governed environment."""
        self._phase = BootPhase.CONTAINER_LAUNCH
        self._log("Step 6/6: Launching governed container...")

        # Prepare environment variables for docker compose
        env = self._build_compose_env()

        # If Google credentials exist, write read-only container credentials
        if self._google_creds and self._google_creds.has_credentials:
            container_cred_path = self._orion_home / "google_credentials_container.json"
            self._google_creds.write_container_credentials(container_cred_path)
            self._log("  Google credentials: read-only mount prepared")

        # Launch via docker compose (api + web services only; egress runs host-side)
        compose_dir = self._compose_file.parent
        self._docker_cmd(
            [
                "docker",
                "compose",
                "-f",
                str(self._compose_file),
                "up",
                "-d",
                "--no-build",  # Already built in step 2
                "api",
                "web",
            ],
            cwd=str(compose_dir),
            env=env,
            timeout=120,
        )

        # Wait for container health check
        self._log("  Waiting for container health check...")
        healthy = self._wait_for_healthy(timeout=60)
        if not healthy:
            raise RuntimeError(
                "Container failed health check within 60s. "
                "Check 'docker compose logs api' for details."
            )

        self._log("  Container: healthy and governed")
        self._log("Step 6/6: Container launch — OK")

    # -------------------------------------------------------------------
    # Docker helpers
    # -------------------------------------------------------------------
    def _is_docker_available(self) -> bool:
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

    def _docker_cmd(
        self,
        cmd: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 60,
    ) -> str:
        """Run a Docker CLI command and return stdout."""
        run_env = {**os.environ}
        if env:
            run_env.update(env)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                env=run_env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Docker command timed out ({timeout}s): {' '.join(cmd)}")

        if result.returncode != 0:
            stderr = result.stderr.strip()[:500] if result.stderr else "no output"
            raise RuntimeError(f"Docker command failed: {' '.join(cmd)}\n{stderr}")

        return result.stdout

    def _build_compose_env(self) -> dict[str, str]:
        """Build environment variables for docker compose."""
        env = {
            "EGRESS_PORT": str(self._egress_port),
            "API_PORT": str(self._api_port),
            "WEB_PORT": str(self._web_port),
            "ORION_HOME": str(self._orion_home),
        }
        return env

    def _is_container_running(self) -> bool:
        """Check if the Orion API container is running."""
        try:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(self._compose_file),
                    "ps",
                    "--format",
                    "json",
                    "api",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False
            # Parse JSON output — look for "running" state
            output = result.stdout.strip()
            if not output:
                return False
            for line in output.splitlines():
                try:
                    data = json.loads(line)
                    if data.get("State") == "running":
                        return True
                except json.JSONDecodeError:
                    continue
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _is_container_healthy(self) -> bool:
        """Check if the Orion API container is healthy."""
        try:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(self._compose_file),
                    "ps",
                    "--format",
                    "json",
                    "api",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False
            output = result.stdout.strip()
            if not output:
                return False
            for line in output.splitlines():
                try:
                    data = json.loads(line)
                    if data.get("Health") == "healthy":
                        return True
                except json.JSONDecodeError:
                    continue
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _wait_for_healthy(self, timeout: float = 60) -> bool:
        """Block until the container passes its health check or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._is_container_healthy():
                return True
            time.sleep(2)
        return False

    # -------------------------------------------------------------------
    # Teardown (reverse order)
    # -------------------------------------------------------------------
    def _teardown(self) -> None:
        """Tear down all components in reverse order."""
        # 6. Stop container
        try:
            self._log("  Stopping container...")
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(self._compose_file),
                    "down",
                    "--timeout",
                    "10",
                ],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("Container stop error: %s", exc)

        # 5. Stop DNS filter
        if self._dns_filter:
            try:
                self._log("  Stopping DNS filter...")
                self._dns_filter.stop()
            except Exception as exc:
                logger.warning("DNS filter stop error: %s", exc)
            self._dns_filter = None

        # 4. Stop approval queue
        if self._approval_queue:
            try:
                self._log("  Stopping approval queue...")
                self._approval_queue.stop()
            except Exception as exc:
                logger.warning("Approval queue stop error: %s", exc)
            self._approval_queue = None

        # 3. Stop egress proxy
        if self._egress_proxy:
            try:
                self._log("  Stopping egress proxy...")
                self._egress_proxy.stop()
            except Exception as exc:
                logger.warning("Egress proxy stop error: %s", exc)
            self._egress_proxy = None

    # -------------------------------------------------------------------
    # Health monitor
    # -------------------------------------------------------------------
    def _health_monitor_loop(self) -> None:
        """Periodically check container health while running."""
        while self._running:
            time.sleep(self._health_interval)
            if not self._running:
                break

            if not self._is_container_running():
                logger.error("Container died — initiating shutdown")
                self._log("ALERT: Container died unexpectedly")
                self._error = "Container died unexpectedly"
                self.stop(ShutdownReason.DOCKER_DIED)
                break

    # -------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------
    def _log(self, message: str) -> None:
        """Add a message to the boot log and emit to logger."""
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self._boot_log.append(entry)
        logger.info(message)
