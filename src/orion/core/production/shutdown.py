"""
Orion Agent — Graceful Shutdown (v6.4.0)

Handles graceful shutdown with in-flight request tracking.
"""

import time
import signal
import threading
from typing import List, Optional, Callable
from contextlib import contextmanager

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
        self._cleanup_callbacks: List[Callable] = []
        self._health_probe: Optional[HealthProbe] = None

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
            try:
                callback()
            except Exception:
                pass

    def shutdown(self):
        """Manually trigger shutdown (for testing or programmatic use)."""
        self._handle_signal(signal.SIGTERM, None)
