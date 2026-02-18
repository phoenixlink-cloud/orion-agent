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
"""Tests for the Sandbox Orchestrator (Phase 3.1).

Tests verify the 6-step governed boot sequence, shutdown, status
reporting, and error handling.  Docker-dependent tests are marked
with @pytest.mark.docker and skipped when Docker is unavailable.

Non-Docker tests exercise the orchestrator logic by mocking Docker
subprocess calls, ensuring the security invariants hold without
requiring a running Docker daemon.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orion.security.orchestrator import (
    BootPhase,
    OrchestratorStatus,
    SandboxOrchestrator,
    ShutdownReason,
)

# ============================================================================
# Helpers
# ============================================================================


def _mock_docker_available(monkeypatch):
    """Patch subprocess so Docker appears available."""
    original_run = subprocess.run

    def _fake_run(cmd, **kwargs):
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd

        if "docker info" in cmd_str:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "docker version" in cmd_str:
            return subprocess.CompletedProcess(cmd, 0, stdout="24.0.7\n", stderr="")
        if "docker compose" in cmd_str and "build" in cmd_str:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "docker compose" in cmd_str and "up" in cmd_str:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "docker compose" in cmd_str and "down" in cmd_str:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "docker compose" in cmd_str and "ps" in cmd_str:
            data = json.dumps({"State": "running", "Health": "healthy"})
            return subprocess.CompletedProcess(cmd, 0, stdout=data + "\n", stderr="")

        # Fall through to original for non-docker commands
        return original_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    # Also mock shutil.which to say docker exists
    import shutil

    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/docker" if x == "docker" else None)


# ============================================================================
# BootPhase & Status
# ============================================================================


class TestBootPhase:
    """Verify BootPhase enum values."""

    def test_all_phases_exist(self):
        phases = [
            "not_started",
            "aegis_config",
            "docker_build",
            "egress_proxy",
            "approval_queue",
            "dns_filter",
            "container_launch",
            "running",
            "shutting_down",
            "stopped",
            "failed",
        ]
        for p in phases:
            assert BootPhase(p).value == p

    def test_shutdown_reasons(self):
        assert ShutdownReason.USER_REQUESTED.value == "user_requested"
        assert ShutdownReason.BOOT_FAILURE.value == "boot_failure"
        assert ShutdownReason.DOCKER_DIED.value == "docker_died"


class TestOrchestratorStatus:
    """Verify status dataclass serialization."""

    def test_to_dict_has_all_fields(self):
        status = OrchestratorStatus()
        d = status.to_dict()

        required_keys = {
            "phase",
            "running",
            "docker_available",
            "google_account_configured",
            "egress_proxy_running",
            "dns_filter_running",
            "approval_queue_running",
            "container_running",
            "container_healthy",
            "uptime_s",
            "error",
            "boot_log",
        }
        assert required_keys == set(d.keys())

    def test_default_status_is_not_started(self):
        status = OrchestratorStatus()
        assert status.phase == "not_started"
        assert not status.running

    def test_boot_log_truncated_to_20(self):
        status = OrchestratorStatus(boot_log=[f"line {i}" for i in range(50)])
        d = status.to_dict()
        assert len(d["boot_log"]) == 20


# ============================================================================
# Orchestrator construction
# ============================================================================


class TestOrchestratorConstruction:
    """Verify orchestrator initializes with correct defaults."""

    def test_default_ports(self):
        orch = SandboxOrchestrator()
        assert orch._egress_port == 8888
        assert orch._dns_port == 5353
        assert orch._api_port == 8000

    def test_custom_ports(self):
        orch = SandboxOrchestrator(egress_port=9999, dns_port=5454, api_port=8080)
        assert orch._egress_port == 9999
        assert orch._dns_port == 5454
        assert orch._api_port == 8080

    def test_initial_phase(self):
        orch = SandboxOrchestrator()
        assert orch.phase == BootPhase.NOT_STARTED

    def test_not_running_initially(self):
        orch = SandboxOrchestrator()
        assert not orch.is_running

    def test_status_returns_dataclass(self):
        orch = SandboxOrchestrator()
        status = orch.status
        assert isinstance(status, OrchestratorStatus)
        assert status.phase == "not_started"

    def test_custom_orion_home(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path / ".orion")
        assert orch._orion_home == tmp_path / ".orion"


# ============================================================================
# Step 1: AEGIS Config
# ============================================================================


class TestStep1AegisConfig:
    """Verify Step 1 loads AEGIS/egress config correctly."""

    def test_step1_loads_config(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path / ".orion")
        orch._boot_step_1_aegis_config()

        assert orch._phase == BootPhase.AEGIS_CONFIG
        assert any("AEGIS" in msg for msg in orch._boot_log)
        assert any("OK" in msg for msg in orch._boot_log)

    def test_step1_reports_domain_count(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path / ".orion")
        orch._boot_step_1_aegis_config()

        # Should mention domain count
        assert any("domains" in msg.lower() for msg in orch._boot_log)

    def test_step1_loads_aegis_invariants(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path / ".orion")
        orch._boot_step_1_aegis_config()

        assert any("7 invariants" in msg for msg in orch._boot_log)


# ============================================================================
# Step 2: Docker Build (requires mocking)
# ============================================================================


class TestStep2DockerBuild:
    """Verify Step 2 checks Docker availability and builds images."""

    def test_step2_fails_without_docker(self, tmp_path, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: None)
        orch = SandboxOrchestrator(orion_home=tmp_path)

        with pytest.raises(RuntimeError, match="Docker is not installed"):
            orch._boot_step_2_docker_build()

    def test_step2_succeeds_with_docker(self, tmp_path, monkeypatch):
        _mock_docker_available(monkeypatch)

        # Need a compose file
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3.9'\nservices: {}\n")

        orch = SandboxOrchestrator(
            orion_home=tmp_path,
            compose_file=compose,
        )
        orch._boot_step_2_docker_build()

        assert orch._phase == BootPhase.DOCKER_BUILD
        assert any("OK" in msg for msg in orch._boot_log)

    def test_step2_fails_missing_compose(self, tmp_path, monkeypatch):
        _mock_docker_available(monkeypatch)

        orch = SandboxOrchestrator(
            orion_home=tmp_path,
            compose_file=tmp_path / "nonexistent.yml",
        )

        with pytest.raises(RuntimeError, match="docker-compose.yml not found"):
            orch._boot_step_2_docker_build()


# ============================================================================
# Step 3: Egress Proxy
# ============================================================================


class TestStep3EgressProxy:
    """Verify Step 3 starts the egress proxy."""

    def test_step3_starts_proxy(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path, egress_port=0)

        with patch("orion.security.egress.proxy.EgressProxyServer") as MockProxy:
            mock_instance = MagicMock()
            mock_instance.is_running = True
            MockProxy.return_value = mock_instance

            orch._boot_step_3_egress_proxy()

            mock_instance.start.assert_called_once()
            assert orch._egress_proxy is mock_instance

    def test_step3_fails_if_proxy_wont_start(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path)

        with patch("orion.security.egress.proxy.EgressProxyServer") as MockProxy:
            mock_instance = MagicMock()
            mock_instance.is_running = False
            MockProxy.return_value = mock_instance

            with pytest.raises(RuntimeError, match="Egress proxy failed to start"):
                orch._boot_step_3_egress_proxy()


# ============================================================================
# Step 4: Approval Queue
# ============================================================================


class TestStep4ApprovalQueue:
    """Verify Step 4 starts the approval queue."""

    def test_step4_starts_queue(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path)
        orch._boot_step_4_approval_queue()

        assert orch._approval_queue is not None
        assert orch._phase == BootPhase.APPROVAL_QUEUE
        assert any("OK" in msg for msg in orch._boot_log)

        # Cleanup
        orch._approval_queue.stop()

    def test_step4_persist_path_in_orion_home(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path)
        orch._boot_step_4_approval_queue()

        assert any(str(tmp_path) in msg for msg in orch._boot_log)

        orch._approval_queue.stop()


# ============================================================================
# Step 5: DNS Filter
# ============================================================================


class TestStep5DNSFilter:
    """Verify Step 5 starts the DNS filter."""

    def test_step5_starts_filter(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path, dns_port=0)

        with patch("orion.security.egress.dns_filter.DNSFilter") as MockDNS:
            mock_instance = MagicMock()
            mock_instance.is_running = True
            MockDNS.return_value = mock_instance

            orch._boot_step_5_dns_filter()

            mock_instance.start.assert_called_once()
            assert orch._dns_filter is mock_instance

    def test_step5_fails_if_dns_wont_start(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path)

        with patch("orion.security.egress.dns_filter.DNSFilter") as MockDNS:
            mock_instance = MagicMock()
            mock_instance.is_running = False
            MockDNS.return_value = mock_instance

            with pytest.raises(RuntimeError, match="DNS filter failed to start"):
                orch._boot_step_5_dns_filter()


# ============================================================================
# Step 6: Container Launch
# ============================================================================


class TestStep6ContainerLaunch:
    """Verify Step 6 launches the Docker container."""

    def test_step6_launches_container(self, tmp_path, monkeypatch):
        _mock_docker_available(monkeypatch)

        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3.9'\nservices: {}\n")

        orch = SandboxOrchestrator(
            orion_home=tmp_path,
            compose_file=compose,
        )
        orch._boot_step_6_container_launch()

        assert orch._phase == BootPhase.CONTAINER_LAUNCH
        assert any("OK" in msg for msg in orch._boot_log)

    def test_step6_prepares_google_creds(self, tmp_path, monkeypatch):
        _mock_docker_available(monkeypatch)

        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3.9'\nservices: {}\n")

        orch = SandboxOrchestrator(orion_home=tmp_path, compose_file=compose)

        # Mock google credential manager
        mock_creds = MagicMock()
        mock_creds.has_credentials = True
        mock_creds.write_container_credentials.return_value = tmp_path / "container_creds.json"
        orch._google_creds = mock_creds

        orch._boot_step_6_container_launch()

        mock_creds.write_container_credentials.assert_called_once()
        assert any("Google credentials" in msg for msg in orch._boot_log)


# ============================================================================
# Full boot sequence (mocked Docker)
# ============================================================================


class TestFullBoot:
    """Verify the complete 6-step boot sequence with mocked Docker."""

    def test_full_boot_and_shutdown(self, tmp_path, monkeypatch):
        _mock_docker_available(monkeypatch)

        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3.9'\nservices: {}\n")

        # Mock the network services to avoid real port binding
        with (
            patch("orion.security.egress.proxy.EgressProxyServer") as MockProxy,
            patch("orion.security.egress.dns_filter.DNSFilter") as MockDNS,
        ):
            mock_proxy = MagicMock()
            mock_proxy.is_running = True
            MockProxy.return_value = mock_proxy

            mock_dns = MagicMock()
            mock_dns.is_running = True
            MockDNS.return_value = mock_dns

            orch = SandboxOrchestrator(
                orion_home=tmp_path,
                compose_file=compose,
            )
            # Skip real health check wait
            orch._wait_for_healthy = lambda timeout=60: True

            status = orch.start()

            assert status.running
            assert status.phase == "running"
            assert orch.is_running
            assert len(orch._boot_log) >= 6  # At least one log per step

            # Verify all components were started
            mock_proxy.start.assert_called_once()
            mock_dns.start.assert_called_once()
            assert orch._approval_queue is not None

            # Shutdown
            orch.stop()

            assert not orch.is_running
            assert orch.phase == BootPhase.STOPPED
            mock_proxy.stop.assert_called_once()
            mock_dns.stop.assert_called_once()

    def test_boot_failure_tears_down(self, tmp_path, monkeypatch):
        _mock_docker_available(monkeypatch)

        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3.9'\nservices: {}\n")

        with (
            patch("orion.security.egress.proxy.EgressProxyServer") as MockProxy,
            patch("orion.security.egress.dns_filter.DNSFilter") as MockDNS,
        ):
            mock_proxy = MagicMock()
            mock_proxy.is_running = True
            MockProxy.return_value = mock_proxy

            # DNS fails to start
            mock_dns = MagicMock()
            mock_dns.is_running = False
            MockDNS.return_value = mock_dns

            orch = SandboxOrchestrator(
                orion_home=tmp_path,
                compose_file=compose,
            )
            orch._wait_for_healthy = lambda timeout=60: True

            status = orch.start()

            # Should have failed
            assert status.phase == "failed"
            assert "DNS filter" in status.error
            assert not orch.is_running

            # Proxy should have been torn down
            mock_proxy.stop.assert_called_once()

    def test_duplicate_start_ignored(self, tmp_path, monkeypatch):
        _mock_docker_available(monkeypatch)

        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3.9'\nservices: {}\n")

        with (
            patch("orion.security.egress.proxy.EgressProxyServer") as MockProxy,
            patch("orion.security.egress.dns_filter.DNSFilter") as MockDNS,
        ):
            mock_proxy = MagicMock()
            mock_proxy.is_running = True
            MockProxy.return_value = mock_proxy

            mock_dns = MagicMock()
            mock_dns.is_running = True
            MockDNS.return_value = mock_dns

            orch = SandboxOrchestrator(
                orion_home=tmp_path,
                compose_file=compose,
            )
            orch._wait_for_healthy = lambda timeout=60: True

            orch.start()
            assert orch.is_running

            # Second start should be no-op
            status2 = orch.start()
            assert status2.running
            assert mock_proxy.start.call_count == 1  # Only called once

            orch.stop()


# ============================================================================
# Reload
# ============================================================================


class TestReload:
    """Verify hot-reload of config without restart."""

    def test_reload_calls_components(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path)
        orch._running = True

        mock_proxy = MagicMock()
        mock_dns = MagicMock()
        orch._egress_proxy = mock_proxy
        orch._dns_filter = mock_dns

        orch.reload_config()

        mock_proxy.reload_config.assert_called_once()
        mock_dns.reload_config.assert_called_once()

    def test_reload_noop_when_not_running(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path)
        # Should not raise
        orch.reload_config()


# ============================================================================
# Docker availability
# ============================================================================


class TestDockerAvailability:
    """Verify Docker detection logic."""

    def test_no_docker_binary(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda x: None)
        orch = SandboxOrchestrator()
        assert not orch._is_docker_available()

    def test_docker_daemon_not_running(self, monkeypatch):
        import shutil as _shutil

        monkeypatch.setattr(_shutil, "which", lambda x: "/usr/bin/docker")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, stderr="daemon not running"),
        )
        orch = SandboxOrchestrator()
        assert not orch._is_docker_available()


# ============================================================================
# Security invariants
# ============================================================================


class TestSecurityInvariants:
    """Verify the orchestrator enforces security properties from the Milestone Document."""

    def test_compose_env_has_egress_port(self):
        orch = SandboxOrchestrator(egress_port=9999)
        env = orch._build_compose_env()
        assert env["EGRESS_PORT"] == "9999"

    def test_compose_env_has_orion_home(self, tmp_path):
        orch = SandboxOrchestrator(orion_home=tmp_path)
        env = orch._build_compose_env()
        assert env["ORION_HOME"] == str(tmp_path)

    def test_teardown_reverse_order(self, tmp_path):
        """Teardown must happen in reverse boot order."""
        call_order = []

        orch = SandboxOrchestrator(orion_home=tmp_path)

        mock_proxy = MagicMock()
        mock_proxy.stop.side_effect = lambda: call_order.append("egress")
        mock_dns = MagicMock()
        mock_dns.stop.side_effect = lambda: call_order.append("dns")
        mock_queue = MagicMock()
        mock_queue.stop.side_effect = lambda: call_order.append("approval")

        orch._egress_proxy = mock_proxy
        orch._dns_filter = mock_dns
        orch._approval_queue = mock_queue

        orch._teardown()

        # Reverse order: container (docker compose down) → DNS → approval → egress
        assert call_order == ["dns", "approval", "egress"]

    def test_stop_idempotent(self, tmp_path):
        """Calling stop on a not-started orchestrator should not raise."""
        orch = SandboxOrchestrator(orion_home=tmp_path)
        orch.stop()  # Should not raise
        assert orch.phase == BootPhase.NOT_STARTED  # Unchanged
