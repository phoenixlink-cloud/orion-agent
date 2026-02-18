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
"""Egress rate limiter -- prevents runaway API costs.

Uses a sliding-window counter per domain and a global counter.
When a limit is exceeded, requests are rejected with a clear
message and the event is audit-logged.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger("orion.security.egress.rate_limiter")


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    reason: str = ""
    domain_rpm: int = 0  # Current requests/minute for this domain
    global_rpm: int = 0  # Current requests/minute globally
    domain_limit: int = 0  # The limit for this domain
    global_limit: int = 0  # The global limit


class SlidingWindowCounter:
    """Thread-safe sliding window counter for rate limiting.

    Tracks request timestamps in a 60-second window and counts
    them to determine the current requests-per-minute rate.
    """

    def __init__(self) -> None:
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def add(self) -> int:
        """Record a request and return the current count in the window."""
        now = time.time()
        with self._lock:
            # Remove timestamps older than 60 seconds
            cutoff = now - 60.0
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            self._timestamps.append(now)
            return len(self._timestamps)

    def count(self) -> int:
        """Return the current count without adding a new entry."""
        now = time.time()
        with self._lock:
            cutoff = now - 60.0
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            return len(self._timestamps)

    def reset(self) -> None:
        """Clear all timestamps."""
        with self._lock:
            self._timestamps.clear()


class RateLimiter:
    """Per-domain and global rate limiter for the egress proxy.

    Enforces two levels of rate limiting:
    1. Per-domain: each domain has its own RPM limit (from whitelist config)
    2. Global: total requests across all domains (prevents abuse even on allowed domains)
    """

    def __init__(self, global_limit_rpm: int = 300) -> None:
        self._global_limit = global_limit_rpm
        self._global_counter = SlidingWindowCounter()
        self._domain_counters: dict[str, SlidingWindowCounter] = defaultdict(
            SlidingWindowCounter
        )
        self._lock = threading.Lock()

    def check(self, hostname: str, domain_limit_rpm: int = 60) -> RateLimitResult:
        """Check if a request to the given hostname is within rate limits.

        This method is called BEFORE making the request. If the result
        is not allowed, the request should be rejected.

        Args:
            hostname: The target hostname.
            domain_limit_rpm: The per-domain RPM limit (from config).

        Returns:
            RateLimitResult indicating whether the request is allowed.
        """
        hostname = hostname.lower()

        # Check global limit first
        global_count = self._global_counter.count()
        if global_count >= self._global_limit:
            logger.warning(
                "Global rate limit exceeded: %d/%d RPM",
                global_count,
                self._global_limit,
            )
            return RateLimitResult(
                allowed=False,
                reason=f"Global rate limit exceeded ({global_count}/{self._global_limit} RPM)",
                global_rpm=global_count,
                global_limit=self._global_limit,
                domain_limit=domain_limit_rpm,
            )

        # Check per-domain limit
        with self._lock:
            counter = self._domain_counters[hostname]
        domain_count = counter.count()

        if domain_count >= domain_limit_rpm:
            logger.warning(
                "Domain rate limit exceeded for %s: %d/%d RPM",
                hostname,
                domain_count,
                domain_limit_rpm,
            )
            return RateLimitResult(
                allowed=False,
                reason=f"Domain rate limit exceeded for {hostname} ({domain_count}/{domain_limit_rpm} RPM)",
                domain_rpm=domain_count,
                domain_limit=domain_limit_rpm,
                global_rpm=global_count,
                global_limit=self._global_limit,
            )

        # Record the request in both counters
        self._global_counter.add()
        counter.add()

        return RateLimitResult(
            allowed=True,
            domain_rpm=domain_count + 1,
            domain_limit=domain_limit_rpm,
            global_rpm=global_count + 1,
            global_limit=self._global_limit,
        )

    def get_stats(self) -> dict[str, int]:
        """Get current rate limit stats for all tracked domains."""
        stats: dict[str, int] = {"_global": self._global_counter.count()}
        with self._lock:
            for hostname, counter in self._domain_counters.items():
                stats[hostname] = counter.count()
        return stats

    def reset(self, hostname: str | None = None) -> None:
        """Reset counters. If hostname is None, reset all."""
        if hostname is None:
            self._global_counter.reset()
            with self._lock:
                for counter in self._domain_counters.values():
                    counter.reset()
                self._domain_counters.clear()
        else:
            with self._lock:
                if hostname in self._domain_counters:
                    self._domain_counters[hostname].reset()
