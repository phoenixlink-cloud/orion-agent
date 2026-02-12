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
"""
Orion Agent -- Graceful Shutdown (v7.4.0)

Handles graceful shutdown with in-flight request tracking.
"""

import signal
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager, suppress

from orion.core.production.health import HealthProbe


class GracefulShutdown:
    """
    Handles graceful shutdown with in-flight request tracking.

    When a shutdown signal is received:
    1. Stop accepting new requests
    2. Wait for in-flight requests to complete (up to timeout)
    3. Run cleanup callbacks
    4. Exit
    """

    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout = timeout_seconds
        self._shutting_down = False
        self._in_flight = 0
        self._lock = threading.Lock()
        self._cleanup_callbacks: list[Callable] = []
        self._health_probe: HealthProbe | None = None

    def install_signal_handlers(self):
        """Install SIGTERM and SIGINT handlers."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def set_health_probe(self, probe: HealthProbe):
        """Link a health probe to update on shutdown."""
        self._health_probe = probe

    def on_cleanup(self, callback: Callable):
        """Register a cleanup callback to run on shutdown."""
        self._cleanup_callbacks.append(callback)

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    @property
    def in_flight_count(self) -> int:
        return self._in_flight

    @contextmanager
    def track_request(self):
        """
        Context manager to track an in-flight request.

        Usage:
            with shutdown.track_request():
                handle_request()
        """
        if self._shutting_down:
            raise RuntimeError("Service is shutting down")

        with self._lock:
            self._in_flight += 1
        try:
            yield
        finally:
            with self._lock:
                self._in_flight -= 1

    def _handle_signal(self, signum, frame):
        """Handle shutdown signal."""
        self._shutting_down = True

        if self._health_probe:
            self._health_probe.mark_not_ready()

        deadline = time.time() + self.timeout
        while self._in_flight > 0 and time.time() < deadline:
            time.sleep(0.1)

        for callback in self._cleanup_callbacks:
            with suppress(Exception):
                callback()

    def shutdown(self):
        """Manually trigger shutdown (for testing or programmatic use)."""
        self._handle_signal(signal.SIGTERM, None)
