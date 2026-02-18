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
"""Egress audit logger.

Every outbound request is logged on the host side, unmodifiable by
Orion (which runs inside the Docker sandbox). The audit log is the
authoritative record of all network activity.

Log format: JSON Lines (one JSON object per line) for easy parsing.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TextIO

logger = logging.getLogger("orion.security.egress.audit")


@dataclass
class AuditEntry:
    """A single auditable network event."""

    timestamp: float
    event_type: str  # "request", "blocked", "rate_limited", "credential_leak", "error"
    method: str  # HTTP method
    url: str  # Full URL
    hostname: str
    port: int = 443
    protocol: str = "https"
    status_code: int = 0  # Response status (0 if blocked before sending)
    request_size: int = 0  # Request body size in bytes
    response_size: int = 0  # Response body size in bytes
    duration_ms: float = 0.0  # Request duration in milliseconds
    rule_matched: str = ""  # Which whitelist rule matched (or "BLOCKED")
    blocked_reason: str = ""  # Why the request was blocked
    credential_patterns: list[str] = field(default_factory=list)  # Patterns detected
    client_ip: str = ""  # Source IP (container IP)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def blocked(
        cls,
        method: str,
        url: str,
        hostname: str,
        reason: str,
        client_ip: str = "",
    ) -> AuditEntry:
        """Create an entry for a blocked request."""
        return cls(
            timestamp=time.time(),
            event_type="blocked",
            method=method,
            url=url,
            hostname=hostname,
            blocked_reason=reason,
            rule_matched="BLOCKED",
            client_ip=client_ip,
        )

    @classmethod
    def allowed(
        cls,
        method: str,
        url: str,
        hostname: str,
        rule: str,
        status_code: int = 0,
        duration_ms: float = 0.0,
        request_size: int = 0,
        response_size: int = 0,
        client_ip: str = "",
    ) -> AuditEntry:
        """Create an entry for an allowed request."""
        return cls(
            timestamp=time.time(),
            event_type="request",
            method=method,
            url=url,
            hostname=hostname,
            status_code=status_code,
            duration_ms=duration_ms,
            request_size=request_size,
            response_size=response_size,
            rule_matched=rule,
            client_ip=client_ip,
        )

    @classmethod
    def rate_limited(
        cls,
        method: str,
        url: str,
        hostname: str,
        client_ip: str = "",
    ) -> AuditEntry:
        """Create an entry for a rate-limited request."""
        return cls(
            timestamp=time.time(),
            event_type="rate_limited",
            method=method,
            url=url,
            hostname=hostname,
            blocked_reason="Rate limit exceeded",
            rule_matched="RATE_LIMITED",
            client_ip=client_ip,
        )

    @classmethod
    def credential_leak(
        cls,
        method: str,
        url: str,
        hostname: str,
        patterns: list[str],
        client_ip: str = "",
    ) -> AuditEntry:
        """Create an entry for a detected credential leak attempt."""
        return cls(
            timestamp=time.time(),
            event_type="credential_leak",
            method=method,
            url=url,
            hostname=hostname,
            blocked_reason="Credential pattern detected in outbound payload",
            rule_matched="CREDENTIAL_LEAK",
            credential_patterns=patterns,
            client_ip=client_ip,
        )


class AuditLogger:
    """Thread-safe audit logger that writes JSON Lines to a host-side file.

    The audit log file lives on the host filesystem, outside the Docker
    sandbox. Orion cannot modify or delete it.
    """

    def __init__(self, log_path: str | Path | None = None) -> None:
        if log_path is None:
            from .config import _ORION_HOME

            log_path = _ORION_HOME / "egress_audit.log"

        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file: TextIO | None = None
        self._entry_count = 0

    def _ensure_open(self) -> TextIO:
        """Lazily open the log file."""
        if self._file is None or self._file.closed:
            self._file = open(self._path, "a", encoding="utf-8")
        return self._file

    def log(self, entry: AuditEntry) -> None:
        """Write an audit entry to the log file (thread-safe)."""
        line = entry.to_json() + "\n"
        with self._lock:
            try:
                f = self._ensure_open()
                f.write(line)
                f.flush()
                self._entry_count += 1
            except OSError as exc:
                logger.error("Failed to write audit entry: %s", exc)

    def close(self) -> None:
        """Close the log file."""
        with self._lock:
            if self._file and not self._file.closed:
                self._file.close()
                self._file = None

    @property
    def entry_count(self) -> int:
        """Number of entries written in this session."""
        return self._entry_count

    @property
    def path(self) -> Path:
        """Path to the audit log file."""
        return self._path

    def read_recent(self, n: int = 50) -> list[AuditEntry]:
        """Read the N most recent audit entries (for dashboard display)."""
        if not self._path.exists():
            return []

        entries: list[AuditEntry] = []
        try:
            lines = self._path.read_text(encoding="utf-8").strip().splitlines()
            for line in lines[-n:]:
                try:
                    data = json.loads(line)
                    entries.append(AuditEntry(**data))
                except (json.JSONDecodeError, TypeError):
                    continue
        except OSError as exc:
            logger.error("Failed to read audit log: %s", exc)

        return entries

    def get_stats(self) -> dict:
        """Get summary statistics from the audit log."""
        entries = self.read_recent(1000)
        if not entries:
            return {
                "total_requests": 0,
                "blocked": 0,
                "allowed": 0,
                "rate_limited": 0,
                "credential_leaks": 0,
                "unique_domains": 0,
            }

        blocked = sum(1 for e in entries if e.event_type == "blocked")
        rate_limited = sum(1 for e in entries if e.event_type == "rate_limited")
        credential_leaks = sum(1 for e in entries if e.event_type == "credential_leak")
        allowed = sum(1 for e in entries if e.event_type == "request")
        domains = {e.hostname for e in entries}

        return {
            "total_requests": len(entries),
            "blocked": blocked,
            "allowed": allowed,
            "rate_limited": rate_limited,
            "credential_leaks": credential_leaks,
            "unique_domains": len(domains),
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
