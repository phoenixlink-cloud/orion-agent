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
Orion Agent -- Health Probes (v7.4.0)

Kubernetes/Docker compatible health probe system.
Provides /health, /ready, /live endpoints.
"""

import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthStatus:
    """Health status response."""

    status: str  # "healthy", "degraded", "unhealthy"
    version: str
    uptime_seconds: float
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
        /health  -- Full health check with component status
        /ready   -- Readiness probe (can accept traffic?)
        /live    -- Liveness probe (is the process alive?)
    """

    def __init__(self, version: str = "7.4.0"):
        self.version = version
        self._start_time = time.time()
        self._ready = False
        self._custom_checks: dict[str, Callable] = {}
        self._component_status: dict[str, bool] = {}

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
            status="healthy"
            if all_healthy and self._ready
            else "degraded"
            if self._ready
            else "unhealthy",
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
