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
"""Sandbox Lifecycle Manager

Integrates the SandboxOrchestrator with Orion's startup/shutdown sequence.
The sandbox is Orion's normal operating environment -- it boots automatically
when Orion starts and tears down when Orion stops.

If Docker is unavailable, Orion continues in BYOK-only mode (no sandbox).
"""

from __future__ import annotations

import atexit
import logging
import shutil
import signal
import subprocess
import threading
import time
from typing import Any

logger = logging.getLogger("orion.security.sandbox_lifecycle")

# ---------------------------------------------------------------------------
# Phase enum (lightweight, avoids importing orchestrator at module level)
# ---------------------------------------------------------------------------
_PHASE_NOT_STARTED = "not_started"
_PHASE_CHECKING = "checking_docker"
_PHASE_BOOTING = "booting"
_PHASE_RUNNING = "running"
_PHASE_FAILED = "failed"
_PHASE_STOPPED = "stopped"


# ---------------------------------------------------------------------------
# SandboxLifecycle
# ---------------------------------------------------------------------------
class SandboxLifecycle:
    """Manages sandbox boot/shutdown across all Orion modes.

    Wraps ``SandboxOrchestrator`` with:
    - Background (non-blocking) boot
    - Docker detection before attempting boot
    - Graceful degradation when Docker is unavailable
    - Signal/atexit handlers for clean shutdown
    - Singleton pattern via ``get_sandbox_lifecycle()``
    """

    def __init__(self) -> None:
        self._orchestrator = None  # Lazy -- created only if Docker is available
        self._phase: str = _PHASE_NOT_STARTED
        self._available: bool = False
        self._boot_time: float = 0.0
        self._error: str = ""
        self._manually_stopped: bool = False
        self._boot_thread: threading.Thread | None = None
        self._boot_done = threading.Event()
        self._lock = threading.Lock()
        self._signals_registered: bool = False
        self._previous_sigint = None
        self._previous_sigterm = None
        self._status_callback = None  # Optional callback for async status updates

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def is_available(self) -> bool:
        """True if the sandbox booted successfully and is running."""
        return self._available

    @property
    def is_booting(self) -> bool:
        """True if boot is currently in progress."""
        return self._phase == _PHASE_BOOTING or self._phase == _PHASE_CHECKING

    @property
    def phase(self) -> str:
        """Current lifecycle phase string."""
        return self._phase

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def boot(self, background: bool = True) -> bool:
        """Start the governed sandbox.

        Args:
            background: If True, boot runs in a background thread and this
                method returns immediately.  If False, blocks until complete.

        Returns:
            True if boot was initiated (or already running).
            False if Docker is not available or boot was skipped.
        """
        with self._lock:
            if self._available:
                logger.info("Sandbox already running -- skipping boot")
                return True
            if self.is_booting:
                logger.info("Sandbox boot already in progress")
                return True
            if self._manually_stopped:
                logger.info("Sandbox was manually stopped -- skipping auto-boot")
                return False

        # Register cleanup handlers (idempotent)
        self._register_signal_handlers()

        if background:
            self._boot_done.clear()
            self._boot_thread = threading.Thread(
                target=self._boot_sync,
                name="sandbox-lifecycle-boot",
                daemon=True,
            )
            self._boot_thread.start()
            return True
        else:
            return self._boot_sync()

    def _boot_sync(self) -> bool:
        """Synchronous boot sequence.  Returns True on success."""
        start = time.time()

        # Phase 1: Check Docker availability
        self._phase = _PHASE_CHECKING
        self._notify_status("Checking Docker availability...")

        if not self._check_docker():
            self._phase = _PHASE_FAILED
            self._error = "Docker not found or not running"
            self._boot_done.set()
            logger.warning("Sandbox unavailable: %s", self._error)
            self._notify_status(f"Sandbox unavailable: {self._error}")
            return False

        # Phase 2: Boot the orchestrator
        self._phase = _PHASE_BOOTING
        self._notify_status("Booting governed sandbox...")

        try:
            from orion.security.orchestrator import SandboxOrchestrator

            self._orchestrator = SandboxOrchestrator()
            status = self._orchestrator.start()

            if status.phase == "running":
                elapsed = time.time() - start
                self._available = True
                self._phase = _PHASE_RUNNING
                self._boot_time = round(elapsed, 1)
                self._error = ""
                logger.info("Sandbox ready (%.1fs)", elapsed)
                self._notify_status(
                    f"Sandbox ready ({self._boot_time}s) "
                    f"-- egress proxy, DNS filter, approval queue active"
                )
                self._boot_done.set()
                return True
            else:
                self._phase = _PHASE_FAILED
                self._error = status.error or "Boot returned non-running phase"
                self._available = False
                logger.warning("Sandbox boot failed: %s", self._error)
                self._notify_status(f"Sandbox boot failed: {self._error}")
                self._boot_done.set()
                return False

        except Exception as exc:
            self._phase = _PHASE_FAILED
            self._error = str(exc)
            self._available = False
            logger.warning("Sandbox boot exception: %s", exc)
            self._notify_status(f"Sandbox boot failed: {exc}")
            self._boot_done.set()
            return False

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        """Stop the sandbox gracefully.  Safe to call multiple times."""
        if self._orchestrator is None:
            self._phase = _PHASE_STOPPED
            return

        if not self._available and self._phase != _PHASE_BOOTING:
            self._phase = _PHASE_STOPPED
            return

        # If boot is still in progress, wait briefly for it to finish
        if self.is_booting:
            logger.info("Waiting for boot to complete before shutdown...")
            self._boot_done.wait(timeout=10)

        try:
            if self._orchestrator and (self._available or self._orchestrator.is_running):
                logger.info("Shutting down sandbox...")
                self._orchestrator.stop()
                logger.info("Sandbox stopped cleanly")
        except Exception as exc:
            logger.warning("Sandbox shutdown error (non-fatal): %s", exc)
        finally:
            self._available = False
            self._phase = _PHASE_STOPPED

    def manual_stop(self) -> None:
        """User explicitly stopped the sandbox -- prevents auto-restart."""
        self._manually_stopped = True
        self.shutdown()

    def manual_start(self) -> bool:
        """User explicitly starts the sandbox -- clears manual stop flag."""
        self._manually_stopped = False
        return self.boot(background=False)

    # ------------------------------------------------------------------
    # Wait / Status
    # ------------------------------------------------------------------
    def wait_for_boot(self, timeout: float = 60.0) -> bool:
        """Block until boot completes or timeout expires.

        Returns True if sandbox is available after waiting.
        """
        self._boot_done.wait(timeout=timeout)
        return self._available

    def get_status(self) -> dict[str, Any]:
        """Return a status dict suitable for API responses and CLI display."""
        result: dict[str, Any] = {
            "available": self._available,
            "phase": self._phase,
            "boot_time_seconds": self._boot_time,
            "manually_stopped": self._manually_stopped,
        }

        if self._error:
            result["error"] = self._error

        # Include orchestrator details when available
        if self._orchestrator and self._available:
            try:
                orch_status = self._orchestrator.status
                result["egress_proxy"] = orch_status.egress_proxy_running
                result["dns_filter"] = orch_status.dns_filter_running
                result["approval_queue"] = orch_status.approval_queue_running
                result["container_running"] = orch_status.container_running
                result["container_healthy"] = orch_status.container_healthy
                result["uptime_s"] = orch_status.uptime_s
            except Exception:
                pass

        return result

    def set_status_callback(self, callback) -> None:
        """Set an optional callback for async status updates.

        The callback receives a single string message.  Used by the CLI
        to print sandbox status after the REPL has started.
        """
        self._status_callback = callback

    # ------------------------------------------------------------------
    # Docker detection
    # ------------------------------------------------------------------
    @staticmethod
    def _check_docker() -> bool:
        """Check if Docker CLI exists and daemon is responsive."""
        if not shutil.which("docker"):
            logger.info("Docker CLI not found in PATH")
            return False
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.info("Docker daemon not running (docker info returned %d)", result.returncode)
                return False
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.info("Docker check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Signal / atexit handlers
    # ------------------------------------------------------------------
    def _register_signal_handlers(self) -> None:
        """Register atexit and signal handlers for clean shutdown.

        Handlers are additive -- previous handlers are chained, not replaced.
        Safe to call multiple times (idempotent).
        """
        if self._signals_registered:
            return
        self._signals_registered = True

        # atexit -- always safe
        atexit.register(self._atexit_handler)

        # Signal handlers -- only from main thread
        try:
            self._previous_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, self._signal_handler)
        except (ValueError, OSError):
            pass  # Not main thread or signal not available

        try:
            self._previous_sigterm = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except (ValueError, OSError, AttributeError):
            pass  # Windows may not have SIGTERM in all contexts

    def _signal_handler(self, signum, frame):
        """Handle SIGINT/SIGTERM: shutdown sandbox, then chain to previous handler."""
        self.shutdown()

        # Chain to previous handler
        previous = None
        if signum == signal.SIGINT:
            previous = self._previous_sigint
        elif hasattr(signal, "SIGTERM") and signum == signal.SIGTERM:
            previous = self._previous_sigterm

        if previous and callable(previous) and previous not in (signal.SIG_DFL, signal.SIG_IGN):
            previous(signum, frame)
        elif previous == signal.SIG_DFL:
            # Re-raise default behaviour
            signal.signal(signum, signal.SIG_DFL)
            signal.raise_signal(signum)

    def _atexit_handler(self) -> None:
        """Atexit: best-effort shutdown."""
        try:
            self.shutdown()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _notify_status(self, message: str) -> None:
        """Send status update to callback if registered."""
        if self._status_callback:
            try:
                self._status_callback(message)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_instance: SandboxLifecycle | None = None
_instance_lock = threading.Lock()


def get_sandbox_lifecycle() -> SandboxLifecycle:
    """Get or create the singleton SandboxLifecycle instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SandboxLifecycle()
    return _instance


def reset_sandbox_lifecycle() -> None:
    """Reset the singleton (for testing only)."""
    global _instance
    with _instance_lock:
        if _instance is not None:
            try:
                _instance.shutdown()
            except Exception:
                pass
            _instance = None
