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
Orion Agent -- Metrics Collector & Rate Limiter (v7.4.0)

Prometheus-compatible metrics export and token bucket rate limiter.
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List
from collections import defaultdict
from contextlib import contextmanager


# =============================================================================
# RATE LIMITER
# =============================================================================

class RateLimiter:
    """
    Token bucket rate limiter.

    Limits the number of requests per time window to protect
    downstream services and API quotas.
    """

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window = window_seconds
        self._tokens = float(max_requests)
        self._last_refill = time.time()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        """Check if a request is allowed under the rate limit."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    def remaining(self) -> int:
        """Get remaining allowed requests in current window."""
        with self._lock:
            self._refill()
            return int(self._tokens)

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self.max_requests),
            self._tokens + elapsed * (self.max_requests / self.window),
        )
        self._last_refill = now


# =============================================================================
# REQUEST METRICS
# =============================================================================

@dataclass
class RequestMetrics:
    """Tracks request metrics for observability."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    in_flight: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    requests_per_minute: float = 0.0
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    latency_by_endpoint: Dict[str, float] = field(default_factory=dict)


class MetricsCollector:
    """
    Collects and exports request metrics.

    Compatible with Prometheus exposition format.
    """

    def __init__(self):
        self._total = 0
        self._success = 0
        self._failed = 0
        self._in_flight = 0
        self._latencies: List[float] = []
        self._errors: Dict[str, int] = defaultdict(int)
        self._endpoint_latencies: Dict[str, List[float]] = defaultdict(list)
        self._start_time = time.time()
        self._lock = threading.Lock()

    @contextmanager
    def track(self, endpoint: str = "default"):
        """Track a request: count, latency, success/failure."""
        with self._lock:
            self._total += 1
            self._in_flight += 1

        start = time.time()
        try:
            yield
            with self._lock:
                self._success += 1
        except Exception as e:
            with self._lock:
                self._failed += 1
                self._errors[type(e).__name__] += 1
            raise
        finally:
            elapsed_ms = (time.time() - start) * 1000
            with self._lock:
                self._in_flight -= 1
                self._latencies.append(elapsed_ms)
                self._endpoint_latencies[endpoint].append(elapsed_ms)
                if len(self._latencies) > 1000:
                    self._latencies = self._latencies[-1000:]

    def get_metrics(self) -> RequestMetrics:
        """Get current metrics snapshot."""
        with self._lock:
            latencies = sorted(self._latencies)
            n = len(latencies)
            elapsed_min = (time.time() - self._start_time) / 60

            return RequestMetrics(
                total_requests=self._total,
                successful_requests=self._success,
                failed_requests=self._failed,
                in_flight=self._in_flight,
                avg_latency_ms=round(sum(latencies) / n, 2) if n > 0 else 0.0,
                p95_latency_ms=round(latencies[int(n * 0.95)] if n >= 20 else (latencies[-1] if n > 0 else 0), 2),
                p99_latency_ms=round(latencies[int(n * 0.99)] if n >= 100 else (latencies[-1] if n > 0 else 0), 2),
                requests_per_minute=round(self._total / elapsed_min, 2) if elapsed_min > 0 else 0.0,
                errors_by_type=dict(self._errors),
                latency_by_endpoint={
                    ep: round(sum(lats) / len(lats), 2)
                    for ep, lats in self._endpoint_latencies.items()
                    if lats
                },
            )

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus exposition format."""
        m = self.get_metrics()
        lines = [
            f'# HELP orion_requests_total Total requests',
            f'# TYPE orion_requests_total counter',
            f'orion_requests_total {m.total_requests}',
            f'# HELP orion_requests_success Successful requests',
            f'# TYPE orion_requests_success counter',
            f'orion_requests_success {m.successful_requests}',
            f'# HELP orion_requests_failed Failed requests',
            f'# TYPE orion_requests_failed counter',
            f'orion_requests_failed {m.failed_requests}',
            f'# HELP orion_requests_in_flight Current in-flight requests',
            f'# TYPE orion_requests_in_flight gauge',
            f'orion_requests_in_flight {m.in_flight}',
            f'# HELP orion_latency_avg_ms Average latency in ms',
            f'# TYPE orion_latency_avg_ms gauge',
            f'orion_latency_avg_ms {m.avg_latency_ms}',
            f'# HELP orion_latency_p95_ms P95 latency in ms',
            f'# TYPE orion_latency_p95_ms gauge',
            f'orion_latency_p95_ms {m.p95_latency_ms}',
        ]
        return "\n".join(lines)

    def reset(self):
        """Reset all metrics."""
        with self._lock:
            self._total = 0
            self._success = 0
            self._failed = 0
            self._in_flight = 0
            self._latencies.clear()
            self._errors.clear()
            self._endpoint_latencies.clear()
            self._start_time = time.time()
