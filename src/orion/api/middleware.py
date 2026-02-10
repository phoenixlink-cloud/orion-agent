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
#    See LICENSE-ENTERPRISE.md or contact licensing@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- API Middleware (Rate Limiting + Optional Auth)

Lightweight middleware for production hardening:
- Token-bucket rate limiter (per-IP)
- Optional Bearer token auth (disabled by default for localhost)

Both are no-ops when unconfigured -- zero overhead for local development.
"""

import time
import logging
from collections import defaultdict
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("orion.api.middleware")


# =============================================================================
# RATE LIMITING (token bucket, per-IP)
# =============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Token-bucket rate limiter per client IP.

    Defaults: 120 requests/minute, burst of 20.
    Skips health/ready endpoints to avoid interfering with probes.
    """

    def __init__(self, app, requests_per_minute: int = 120, burst: int = 20):
        super().__init__(app)
        self.rate = requests_per_minute / 60.0  # tokens per second
        self.burst = burst
        self._buckets: dict = defaultdict(lambda: {"tokens": burst, "last": time.monotonic()})

    def _consume(self, client_ip: str) -> bool:
        """Try to consume a token. Returns True if allowed."""
        bucket = self._buckets[client_ip]
        now = time.monotonic()
        elapsed = now - bucket["last"]
        bucket["last"] = now

        # Refill tokens
        bucket["tokens"] = min(self.burst, bucket["tokens"] + elapsed * self.rate)

        if bucket["tokens"] >= 1.0:
            bucket["tokens"] -= 1.0
            return True
        return False

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health probes
        path = request.url.path
        if path in ("/health", "/ready"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        if not self._consume(client_ip):
            logger.warning("Rate limit exceeded for %s on %s", client_ip, path)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again shortly.",
                    "retry_after_seconds": 1,
                },
            )

        return await call_next(request)


# =============================================================================
# OPTIONAL API KEY AUTH (Bearer token)
# =============================================================================

class OptionalAuthMiddleware(BaseHTTPMiddleware):
    """
    Optional Bearer token authentication.

    If an API key is configured in ~/.orion/settings.json under
    "api_server_key", all requests must include:
        Authorization: Bearer <key>

    If no key is configured, all requests pass through (localhost-safe default).
    Skips auth for: health probes, OAuth callbacks (they come from external redirects).
    """

    # Paths that never require auth
    _EXEMPT_PATHS = {"/health", "/ready", "/api/oauth/callback"}

    def __init__(self, app):
        super().__init__(app)
        self._cached_key: Optional[str] = None
        self._last_check: float = 0

    def _get_server_key(self) -> Optional[str]:
        """Load the server key from settings (cached for 30s)."""
        now = time.monotonic()
        if now - self._last_check < 30:
            return self._cached_key

        self._last_check = now
        try:
            from orion.api._shared import _load_user_settings
            settings = _load_user_settings()
            self._cached_key = settings.get("api_server_key") or None
        except Exception:
            self._cached_key = None
        return self._cached_key

    async def dispatch(self, request: Request, call_next):
        server_key = self._get_server_key()

        # No key configured -> pass through (localhost default)
        if not server_key:
            return await call_next(request)

        # Exempt paths
        if request.url.path in self._EXEMPT_PATHS:
            return await call_next(request)

        # WebSocket upgrade requests -- check query param instead of header
        if request.url.path.startswith("/ws/"):
            token = request.query_params.get("token", "")
            if token == server_key:
                return await call_next(request)
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid or missing authentication token."},
            )

        # Check Bearer token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token == server_key:
                return await call_next(request)

        logger.warning("Unauthorized request to %s from %s",
                        request.url.path,
                        request.client.host if request.client else "unknown")
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required. Set Authorization: Bearer <key> header."},
        )
