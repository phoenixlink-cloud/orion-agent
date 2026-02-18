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
"""Approval queue service -- host-side human gate for write operations.

When AEGIS Invariant 6 classifies a request as requiring approval
(all write operations: POST, PUT, PATCH, DELETE), the request is
parked in this queue until a human approves or denies it.

Architecture:
  Orion (container) --> Egress Proxy --> Approval Queue (host) --> User Decision

Security properties:
  - Queue lives on the HOST side, outside Docker sandbox
  - Orion cannot approve its own requests
  - Orion cannot modify pending requests
  - Requests expire after a configurable timeout
  - All decisions are audit-logged
  - The queue is thread-safe for concurrent access
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("orion.security.egress.approval_queue")


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RequestCategory(str, Enum):
    """Category of the request for UI grouping."""

    NETWORK_WRITE = "network_write"  # Outbound POST/PUT/DELETE
    DOMAIN_ADD = "domain_add"  # Adding a new domain to whitelist
    CREDENTIAL_USE = "credential_use"  # Using stored credentials
    FILE_PROMOTION = "file_promotion"  # Promoting sandbox files to workspace
    EXTERNAL_API = "external_api"  # External API call
    OTHER = "other"


@dataclass
class ApprovalRequest:
    """A single request pending human approval.

    This is the core data structure for the approval queue.
    Each request captures full context so the user can make
    an informed decision.
    """

    id: str
    category: str
    summary: str  # Human-readable one-line summary
    details: dict[str, Any]  # Full request details for inspection
    created_at: float
    expires_at: float
    status: str = ApprovalStatus.PENDING.value

    # Decision metadata (filled when approved/denied)
    decided_at: float = 0.0
    decided_by: str = ""  # "user" or "timeout"
    decision_reason: str = ""

    # Source context
    source_ip: str = ""  # Container IP that made the request
    method: str = ""  # HTTP method
    url: str = ""  # Target URL
    hostname: str = ""  # Target hostname
    body_preview: str = ""  # First N chars of request body (redacted)

    def is_expired(self) -> bool:
        """Check if this request has expired."""
        return time.time() > self.expires_at and self.status == ApprovalStatus.PENDING.value

    def to_dict(self) -> dict:
        """Serialize for API responses."""
        return {
            "id": self.id,
            "category": self.category,
            "summary": self.summary,
            "details": self.details,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "decision_reason": self.decision_reason,
            "method": self.method,
            "url": self.url,
            "hostname": self.hostname,
            "body_preview": self.body_preview,
            "is_expired": self.is_expired(),
            "time_remaining_s": max(0, self.expires_at - time.time()),
        }


class ApprovalQueue:
    """Thread-safe approval queue for pending write operations.

    This queue runs on the HOST side. The container sends requests
    through the egress proxy, which parks write operations here.
    The web UI polls for pending requests and lets the user decide.

    Usage:
        queue = ApprovalQueue()

        # Egress proxy submits a request
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="POST to https://api.github.com/repos",
            details={"method": "POST", "url": "https://api.github.com/repos"},
        )

        # Wait for user decision (blocks up to timeout)
        result = queue.wait_for_decision(req_id, timeout=300)

        # Or: Web UI approves/denies
        queue.approve(req_id, reason="Looks legitimate")
        queue.deny(req_id, reason="Suspicious target")
    """

    def __init__(
        self,
        default_timeout_s: float = 300.0,  # 5 minutes
        max_pending: int = 100,
        persist_path: str | Path | None = None,
    ) -> None:
        self._default_timeout = default_timeout_s
        self._max_pending = max_pending
        self._requests: dict[str, ApprovalRequest] = {}
        self._lock = threading.Lock()
        self._events: dict[str, threading.Event] = {}
        self._callbacks: list[Callable[[ApprovalRequest], None]] = []

        # Persistence
        if persist_path is None:
            orion_home = Path(os.environ.get("ORION_HOME", Path.home() / ".orion"))
            persist_path = orion_home / "approval_queue.json"
        self._persist_path = Path(persist_path)
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)

        # Start expiry checker
        self._running = True
        self._expiry_thread = threading.Thread(
            target=self._check_expiry_loop,
            name="approval-expiry",
            daemon=True,
        )
        self._expiry_thread.start()

    def submit(
        self,
        category: str | RequestCategory,
        summary: str,
        details: dict[str, Any] | None = None,
        timeout_s: float | None = None,
        method: str = "",
        url: str = "",
        hostname: str = "",
        body_preview: str = "",
        source_ip: str = "",
    ) -> str:
        """Submit a new request for approval.

        Returns:
            The request ID (use this to check/wait for the decision).

        Raises:
            RuntimeError: If the queue is full.
        """
        with self._lock:
            # Check queue capacity
            pending_count = sum(
                1
                for r in self._requests.values()
                if r.status == ApprovalStatus.PENDING.value
            )
            if pending_count >= self._max_pending:
                raise RuntimeError(
                    f"Approval queue full ({pending_count}/{self._max_pending} pending)"
                )

            req_id = str(uuid.uuid4())
            now = time.time()
            timeout = timeout_s or self._default_timeout

            request = ApprovalRequest(
                id=req_id,
                category=category.value if isinstance(category, RequestCategory) else category,
                summary=summary,
                details=details or {},
                created_at=now,
                expires_at=now + timeout,
                method=method,
                url=url,
                hostname=hostname,
                body_preview=body_preview[:500] if body_preview else "",
                source_ip=source_ip,
            )

            self._requests[req_id] = request
            self._events[req_id] = threading.Event()

        logger.info("Approval request submitted: [%s] %s", req_id[:8], summary)
        self._notify_callbacks(request)
        self._persist()
        return req_id

    def approve(self, request_id: str, reason: str = "") -> bool:
        """Approve a pending request.

        Returns:
            True if the request was approved, False if not found or not pending.
        """
        return self._decide(request_id, ApprovalStatus.APPROVED, reason, "user")

    def deny(self, request_id: str, reason: str = "") -> bool:
        """Deny a pending request.

        Returns:
            True if the request was denied, False if not found or not pending.
        """
        return self._decide(request_id, ApprovalStatus.DENIED, reason, "user")

    def cancel(self, request_id: str, reason: str = "") -> bool:
        """Cancel a pending request (e.g., Orion no longer needs it).

        Returns:
            True if the request was cancelled, False if not found or not pending.
        """
        return self._decide(request_id, ApprovalStatus.CANCELLED, reason, "system")

    def wait_for_decision(
        self, request_id: str, timeout: float | None = None
    ) -> ApprovalStatus:
        """Block until a decision is made on the request.

        Args:
            request_id: The request to wait for.
            timeout: Maximum seconds to wait (default: request's own timeout).

        Returns:
            The final status of the request.
        """
        event = self._events.get(request_id)
        if event is None:
            return ApprovalStatus.EXPIRED

        request = self._requests.get(request_id)
        if request is None:
            return ApprovalStatus.EXPIRED

        wait_timeout = timeout or max(0, request.expires_at - time.time())
        event.wait(timeout=wait_timeout)

        # Re-check status after waking
        request = self._requests.get(request_id)
        if request is None:
            return ApprovalStatus.EXPIRED

        if request.status == ApprovalStatus.PENDING.value and request.is_expired():
            self._decide(request_id, ApprovalStatus.EXPIRED, "Timed out", "timeout")

        return ApprovalStatus(request.status)

    def get_pending(self) -> list[ApprovalRequest]:
        """Get all pending (non-expired) requests."""
        with self._lock:
            return [
                r
                for r in self._requests.values()
                if r.status == ApprovalStatus.PENDING.value and not r.is_expired()
            ]

    def get_recent(self, limit: int = 50) -> list[ApprovalRequest]:
        """Get recent requests (all statuses) sorted by creation time."""
        with self._lock:
            sorted_requests = sorted(
                self._requests.values(),
                key=lambda r: r.created_at,
                reverse=True,
            )
            return sorted_requests[:limit]

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        """Get a specific request by ID."""
        with self._lock:
            return self._requests.get(request_id)

    def get_stats(self) -> dict:
        """Get queue statistics."""
        with self._lock:
            statuses = {}
            for r in self._requests.values():
                status = r.status
                statuses[status] = statuses.get(status, 0) + 1

            return {
                "total": len(self._requests),
                "pending": statuses.get(ApprovalStatus.PENDING.value, 0),
                "approved": statuses.get(ApprovalStatus.APPROVED.value, 0),
                "denied": statuses.get(ApprovalStatus.DENIED.value, 0),
                "expired": statuses.get(ApprovalStatus.EXPIRED.value, 0),
                "cancelled": statuses.get(ApprovalStatus.CANCELLED.value, 0),
            }

    def on_request(self, callback: Callable[[ApprovalRequest], None]) -> None:
        """Register a callback for new requests (e.g., WebSocket notification)."""
        self._callbacks.append(callback)

    def clear_decided(self, older_than_s: float = 3600) -> int:
        """Remove decided requests older than the specified age.

        Returns:
            Number of requests removed.
        """
        cutoff = time.time() - older_than_s
        removed = 0
        with self._lock:
            to_remove = [
                rid
                for rid, r in self._requests.items()
                if r.status != ApprovalStatus.PENDING.value and r.created_at < cutoff
            ]
            for rid in to_remove:
                del self._requests[rid]
                self._events.pop(rid, None)
                removed += 1
        if removed:
            self._persist()
        return removed

    def stop(self) -> None:
        """Stop the expiry checker thread."""
        self._running = False

    # ---------------------------------------------------------------
    # Internal methods
    # ---------------------------------------------------------------

    def _decide(
        self,
        request_id: str,
        status: ApprovalStatus,
        reason: str,
        decided_by: str,
    ) -> bool:
        """Apply a decision to a request."""
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                return False
            if request.status != ApprovalStatus.PENDING.value:
                return False

            request.status = status.value
            request.decided_at = time.time()
            request.decided_by = decided_by
            request.decision_reason = reason

        # Wake up any thread waiting on this request
        event = self._events.get(request_id)
        if event:
            event.set()

        logger.info(
            "Approval %s: [%s] %s (by %s: %s)",
            status.value,
            request_id[:8],
            request.summary,
            decided_by,
            reason or "no reason",
        )
        self._persist()
        return True

    def _notify_callbacks(self, request: ApprovalRequest) -> None:
        """Notify registered callbacks about a new request."""
        for cb in self._callbacks:
            try:
                cb(request)
            except Exception as exc:
                logger.error("Approval callback error: %s", exc)

    def _check_expiry_loop(self) -> None:
        """Periodically check for and expire stale requests."""
        while self._running:
            time.sleep(5)
            with self._lock:
                for request in self._requests.values():
                    if request.is_expired():
                        request.status = ApprovalStatus.EXPIRED.value
                        request.decided_at = time.time()
                        request.decided_by = "timeout"
                        request.decision_reason = "Request expired"
                        event = self._events.get(request.id)
                        if event:
                            event.set()

    def _persist(self) -> None:
        """Save queue state to disk for crash recovery."""
        try:
            with self._lock:
                data = [r.to_dict() for r in self._requests.values()]
            self._persist_path.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("Failed to persist approval queue: %s", exc)

    def _load(self) -> None:
        """Load queue state from disk."""
        if not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for entry in data:
                req = ApprovalRequest(
                    id=entry["id"],
                    category=entry["category"],
                    summary=entry["summary"],
                    details=entry.get("details", {}),
                    created_at=entry["created_at"],
                    expires_at=entry["expires_at"],
                    status=entry.get("status", ApprovalStatus.PENDING.value),
                    decided_at=entry.get("decided_at", 0.0),
                    decided_by=entry.get("decided_by", ""),
                    decision_reason=entry.get("decision_reason", ""),
                    method=entry.get("method", ""),
                    url=entry.get("url", ""),
                    hostname=entry.get("hostname", ""),
                    body_preview=entry.get("body_preview", ""),
                    source_ip=entry.get("source_ip", ""),
                )
                self._requests[req.id] = req
                self._events[req.id] = threading.Event()
                if req.status != ApprovalStatus.PENDING.value:
                    self._events[req.id].set()
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.error("Failed to load approval queue: %s", exc)
