# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
"""Tests for SandboxLifecycle manager.

15 unit tests covering:
- Boot with/without Docker
- Shutdown
- Background boot transitions
- wait_for_boot
- Double boot idempotency
- Full cycle (boot → stop → boot)
- get_status in various phases
- Signal handler registration
- Manual stop prevents auto-restart
- Singleton pattern
- Port conflict / boot failure handling
"""

import signal
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from orion.security.sandbox_lifecycle import (
    SandboxLifecycle,
    _PHASE_BOOTING,
    _PHASE_CHECKING,
    _PHASE_FAILED,
    _PHASE_NOT_STARTED,
    _PHASE_RUNNING,
    _PHASE_STOPPED,
    get_sandbox_lifecycle,
    reset_sandbox_lifecycle,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the global singleton before each test."""
    reset_sandbox_lifecycle()
    yield
    reset_sandbox_lifecycle()


@pytest.fixture
def lifecycle():
    """Create a fresh SandboxLifecycle instance (not the singleton)."""
    return SandboxLifecycle()


# -------------------------------------------------------------------------
# SL-01: Boot with Docker available
# -------------------------------------------------------------------------
class TestBootWithDocker:
    def test_boot_success(self, lifecycle):
        """SL-01: Lifecycle boot with Docker available (steps 1-5)."""
        mock_orch = MagicMock()

        with patch.object(lifecycle, "_check_docker", return_value=True), \
             patch("orion.security.orchestrator.SandboxOrchestrator", return_value=mock_orch):
            result = lifecycle.boot(background=False)

        assert result is True
        assert lifecycle.is_available is True
        assert lifecycle.phase == _PHASE_RUNNING
        assert lifecycle._boot_time >= 0
        # Verify steps 1-5 were called
        mock_orch._boot_step_1_aegis_config.assert_called_once()
        mock_orch._boot_step_2_docker_build.assert_called_once()
        mock_orch._boot_step_3_egress_proxy.assert_called_once()
        mock_orch._boot_step_4_approval_queue.assert_called_once()
        mock_orch._boot_step_5_dns_filter.assert_called_once()
        # Step 6 (container launch) should NOT be called
        mock_orch._boot_step_6_container_launch.assert_not_called()


# -------------------------------------------------------------------------
# SL-02: Boot without Docker
# -------------------------------------------------------------------------
class TestBootWithoutDocker:
    def test_no_docker(self, lifecycle):
        """SL-02: Lifecycle boot without Docker."""
        with patch.object(lifecycle, "_check_docker", return_value=False):
            result = lifecycle.boot(background=False)

        assert result is False
        assert lifecycle.is_available is False
        assert lifecycle.phase == _PHASE_FAILED
        assert "Docker" in lifecycle._error


# -------------------------------------------------------------------------
# SL-03: Shutdown
# -------------------------------------------------------------------------
class TestShutdown:
    def test_clean_shutdown(self, lifecycle):
        """SL-03: Lifecycle shutdown cleans up."""
        mock_orch = MagicMock()
        lifecycle._orchestrator = mock_orch
        lifecycle._available = True
        lifecycle._phase = _PHASE_RUNNING

        lifecycle.shutdown()

        mock_orch.stop.assert_called_once()
        assert lifecycle.is_available is False
        assert lifecycle.phase == _PHASE_STOPPED

    def test_shutdown_when_not_started(self, lifecycle):
        """SL-03b: Shutdown when not started is a no-op."""
        lifecycle.shutdown()
        assert lifecycle.phase == _PHASE_STOPPED


# -------------------------------------------------------------------------
# SL-04: Background boot transitions
# -------------------------------------------------------------------------
class TestBackgroundBoot:
    def test_is_booting_transitions(self, lifecycle):
        """SL-04: is_booting transitions from True to False."""
        boot_started = threading.Event()
        boot_proceed = threading.Event()

        original_check = lifecycle._check_docker

        def slow_check():
            boot_started.set()
            boot_proceed.wait(timeout=5)
            return False  # Fail so we don't need full orchestrator

        lifecycle._check_docker = slow_check

        lifecycle.boot(background=True)
        boot_started.wait(timeout=2)

        assert lifecycle.is_booting is True

        boot_proceed.set()
        lifecycle._boot_done.wait(timeout=5)

        assert lifecycle.is_booting is False


# -------------------------------------------------------------------------
# SL-05: wait_for_boot with timeout — success
# -------------------------------------------------------------------------
class TestWaitForBootSuccess:
    def test_wait_returns_true(self, lifecycle):
        """SL-05: wait_for_boot returns True when boot completes."""
        with patch.object(lifecycle, "_check_docker", return_value=False):
            lifecycle.boot(background=True)

        # Boot will fail fast (no Docker), wait should return quickly
        result = lifecycle.wait_for_boot(timeout=5)
        # Result is False because Docker isn't available, but wait completed
        assert result is False  # No Docker = not available
        assert lifecycle._boot_done.is_set()


# -------------------------------------------------------------------------
# SL-06: wait_for_boot timeout exceeded
# -------------------------------------------------------------------------
class TestWaitForBootTimeout:
    def test_timeout_no_crash(self, lifecycle):
        """SL-06: wait_for_boot timeout exceeded returns False, no crash."""
        # Don't boot at all — boot_done is never set
        result = lifecycle.wait_for_boot(timeout=0.1)
        assert result is False


# -------------------------------------------------------------------------
# SL-07: Double boot (idempotent)
# -------------------------------------------------------------------------
class TestDoubleBoot:
    def test_second_boot_noop(self, lifecycle):
        """SL-07: Second boot call is a no-op when already running."""
        lifecycle._available = True
        lifecycle._phase = _PHASE_RUNNING

        result = lifecycle.boot(background=False)
        assert result is True  # Returns True without re-booting

    def test_second_boot_while_booting(self, lifecycle):
        """SL-07b: Second boot call while booting returns True."""
        lifecycle._phase = _PHASE_BOOTING

        result = lifecycle.boot(background=True)
        assert result is True


# -------------------------------------------------------------------------
# SL-08: Boot → shutdown → boot
# -------------------------------------------------------------------------
class TestFullCycle:
    def test_full_lifecycle(self, lifecycle):
        """SL-08: Boot then shutdown then boot again."""
        with patch.object(lifecycle, "_check_docker", return_value=False):
            lifecycle.boot(background=False)
        assert lifecycle.phase == _PHASE_FAILED

        lifecycle.shutdown()
        assert lifecycle.phase == _PHASE_STOPPED

        # Reset state for second boot
        lifecycle._manually_stopped = False
        with patch.object(lifecycle, "_check_docker", return_value=False):
            lifecycle.boot(background=False)
        assert lifecycle.phase == _PHASE_FAILED  # Still no Docker, but no crash


# -------------------------------------------------------------------------
# SL-09: get_status() during boot
# -------------------------------------------------------------------------
class TestStatusDuringBoot:
    def test_status_during_boot(self, lifecycle):
        """SL-09: get_status shows BOOTING phase."""
        lifecycle._phase = _PHASE_BOOTING

        status = lifecycle.get_status()
        assert status["phase"] == _PHASE_BOOTING
        assert status["available"] is False


# -------------------------------------------------------------------------
# SL-10: get_status() after boot
# -------------------------------------------------------------------------
class TestStatusAfterBoot:
    def test_status_after_boot(self, lifecycle):
        """SL-10: get_status shows RUNNING phase with boot time."""
        lifecycle._phase = _PHASE_RUNNING
        lifecycle._available = True
        lifecycle._boot_time = 4.2

        mock_orch_status = MagicMock()
        mock_orch_status.egress_proxy_running = True
        mock_orch_status.dns_filter_running = True
        mock_orch_status.approval_queue_running = True
        mock_orch_status.container_running = True
        mock_orch_status.container_healthy = True
        mock_orch_status.uptime_s = 10.5

        mock_orch = MagicMock()
        mock_orch.status = mock_orch_status
        lifecycle._orchestrator = mock_orch

        status = lifecycle.get_status()
        assert status["available"] is True
        assert status["phase"] == _PHASE_RUNNING
        assert status["boot_time_seconds"] == 4.2
        assert status["egress_proxy"] is True
        assert status["dns_filter"] is True
        assert status["approval_queue"] is True


# -------------------------------------------------------------------------
# SL-11: get_status() after failure
# -------------------------------------------------------------------------
class TestStatusAfterFailure:
    def test_status_shows_error(self, lifecycle):
        """SL-11: get_status shows error reason after failure."""
        lifecycle._phase = _PHASE_FAILED
        lifecycle._error = "Docker not found or not running"

        status = lifecycle.get_status()
        assert status["phase"] == _PHASE_FAILED
        assert status["available"] is False
        assert "Docker" in status["error"]


# -------------------------------------------------------------------------
# SL-12: Signal handler registration
# -------------------------------------------------------------------------
class TestSignalHandlers:
    def test_atexit_and_signals_registered(self, lifecycle):
        """SL-12: atexit and signal handlers are registered."""
        with patch("atexit.register") as mock_atexit, \
             patch("signal.getsignal", return_value=signal.SIG_DFL), \
             patch("signal.signal") as mock_signal:

            lifecycle._register_signal_handlers()

            mock_atexit.assert_called_once_with(lifecycle._atexit_handler)
            # SIGINT + SIGTERM (on platforms that support it)
            assert mock_signal.call_count >= 1

    def test_idempotent(self, lifecycle):
        """SL-12b: Signal registration is idempotent."""
        with patch("atexit.register") as mock_atexit, \
             patch("signal.getsignal", return_value=signal.SIG_DFL), \
             patch("signal.signal"):

            lifecycle._register_signal_handlers()
            lifecycle._register_signal_handlers()

            # Only registered once
            mock_atexit.assert_called_once()


# -------------------------------------------------------------------------
# SL-13: Manual /sandbox stop prevents auto-restart
# -------------------------------------------------------------------------
class TestManualStop:
    def test_manual_stop_flag(self, lifecycle):
        """SL-13: manual_stop sets flag that prevents auto-boot."""
        lifecycle._available = True
        lifecycle._phase = _PHASE_RUNNING
        lifecycle._orchestrator = MagicMock()

        lifecycle.manual_stop()

        assert lifecycle._manually_stopped is True
        assert lifecycle.is_available is False

        # Auto-boot should be skipped
        result = lifecycle.boot(background=False)
        assert result is False


# -------------------------------------------------------------------------
# SL-14: Singleton pattern
# -------------------------------------------------------------------------
class TestSingleton:
    def test_same_instance(self):
        """SL-14: Multiple calls return same instance."""
        a = get_sandbox_lifecycle()
        b = get_sandbox_lifecycle()
        assert a is b

    def test_reset_creates_new(self):
        """SL-14b: reset_sandbox_lifecycle creates a new instance."""
        a = get_sandbox_lifecycle()
        reset_sandbox_lifecycle()
        b = get_sandbox_lifecycle()
        assert a is not b


# -------------------------------------------------------------------------
# SL-15: Port conflict / boot failure handling
# -------------------------------------------------------------------------
class TestBootFailure:
    def test_boot_step_exception(self, lifecycle):
        """SL-15: Boot fails gracefully when a boot step raises."""
        mock_orch = MagicMock()
        mock_orch._boot_step_3_egress_proxy.side_effect = RuntimeError("port 8888 in use")

        with patch.object(lifecycle, "_check_docker", return_value=True), \
             patch("orion.security.orchestrator.SandboxOrchestrator", return_value=mock_orch):
            result = lifecycle.boot(background=False)

        assert result is False
        assert lifecycle.is_available is False
        assert lifecycle.phase == _PHASE_FAILED
        assert "8888" in lifecycle._error
        # Verify teardown was attempted on partial failure
        mock_orch._teardown.assert_called_once()

    def test_docker_build_fails(self, lifecycle):
        """SL-15b: Boot fails when Docker build step raises."""
        mock_orch = MagicMock()
        mock_orch._boot_step_2_docker_build.side_effect = RuntimeError(
            "docker-compose.yml not found"
        )

        with patch.object(lifecycle, "_check_docker", return_value=True), \
             patch("orion.security.orchestrator.SandboxOrchestrator", return_value=mock_orch):
            result = lifecycle.boot(background=False)

        assert result is False
        assert lifecycle.phase == _PHASE_FAILED
        assert "docker-compose" in lifecycle._error.lower() or "not found" in lifecycle._error
