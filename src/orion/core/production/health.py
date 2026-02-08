"""
Orion Agent — Health Probes (v6.4.0)

Kubernetes/Docker compatible health probe system.
Provides /health, /ready, /live endpoints.
"""

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Callable


@dataclass
class HealthStatus:
    """Health status response."""
    status: str  # "healthy", "degraded", "unhealthy"
    version: str
    uptime_seconds: float
    checks: Dict[str, bool] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "checks": self.checks,
            "details": self.details,
        }

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"

    @property
    def http_status_code(self) -> int:
        return 200 if self.status in ("healthy", "degraded") else 503


class HealthProbe:
    """
    Kubernetes/Docker compatible health probe system.

    Provides three endpoints:
        /health  — Full health check with component status
        /ready   — Readiness probe (can accept traffic?)
        /live    — Liveness probe (is the process alive?)
    """

    def __init__(self, version: str = "6.4.0"):
        self.version = version
        self._start_time = time.time()
        self._ready = False
        self._custom_checks: Dict[str, Callable] = {}
        self._component_status: Dict[str, bool] = {}

    def mark_ready(self):
        """Mark the service as ready to accept traffic."""
        self._ready = True

    def mark_not_ready(self):
        """Mark the service as not ready (draining)."""
        self._ready = False

    def register_check(self, name: str, check_fn: Callable[[], bool]):
        """Register a custom health check function."""
        self._custom_checks[name] = check_fn

    def health(self) -> HealthStatus:
        """Full health check with component status."""
        checks = {}
        for name, check_fn in self._custom_checks.items():
            try:
                checks[name] = check_fn()
            except Exception:
                checks[name] = False

        all_healthy = all(checks.values()) if checks else True
        uptime = time.time() - self._start_time

        return HealthStatus(
            status="healthy" if all_healthy and self._ready else "degraded" if self._ready else "unhealthy",
            version=self.version,
            uptime_seconds=uptime,
            checks=checks,
            details={
                "pid": os.getpid(),
                "python_version": sys.version.split()[0],
                "ready": self._ready,
            },
        )

    def ready(self) -> bool:
        """Readiness probe: can this instance accept traffic?"""
        return self._ready

    def live(self) -> bool:
        """Liveness probe: is the process alive and responsive?"""
        return True
