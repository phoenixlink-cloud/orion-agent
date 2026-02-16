# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""Tamper-proof audit log with HMAC hash chain.

Every significant ARA event is appended to an append-only JSONL log.
Each entry includes a SHA-256 hash of the previous entry (hash chain)
and an HMAC-SHA256 signature for integrity verification.

See ARA-001 §3.5 for design.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.ara.audit_log")

DEFAULT_AUDIT_DIR = Path.home() / ".orion" / "audit"
DEFAULT_AUDIT_FILE = DEFAULT_AUDIT_DIR / "audit.jsonl"

# Sentinel for the first entry in the chain
GENESIS_HASH = "0" * 64


def _derive_hmac_key() -> bytes:
    """Derive a machine-specific HMAC key.

    Uses a combination of the machine's hostname and the audit directory path
    to create a deterministic but machine-specific key.
    """
    import platform

    raw = f"orion-ara-audit-{platform.node()}-{DEFAULT_AUDIT_DIR}".encode()
    return hashlib.sha256(raw).digest()


@dataclass
class AuditEntry:
    """A single tamper-proof audit log entry."""

    timestamp: float
    session_id: str
    event_type: str
    actor: str
    details: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = GENESIS_HASH
    entry_hash: str = ""
    hmac_sig: str = ""

    def compute_hash(self) -> str:
        """Compute the SHA-256 hash of this entry (excluding entry_hash and hmac_sig)."""
        payload = {
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "details": self.details,
            "prev_hash": self.prev_hash,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()

    def compute_hmac(self, key: bytes) -> str:
        """Compute HMAC-SHA256 signature for this entry."""
        payload = {
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "details": self.details,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(key, raw, hashlib.sha256).hexdigest()


class AuditLog:
    """Append-only, tamper-proof audit log with hash chain and HMAC.

    Usage::

        log = AuditLog()
        log.append(AuditEntry(
            timestamp=time.time(),
            session_id="abc123",
            event_type="task_completed",
            actor="orion",
            details={"task": "write_tests"},
        ))
        valid, checked = log.verify_chain()
    """

    def __init__(
        self,
        path: Path | None = None,
        hmac_key: bytes | None = None,
    ):
        self._path = path or DEFAULT_AUDIT_FILE
        self._hmac_key = hmac_key or _derive_hmac_key()
        self._last_hash: str = GENESIS_HASH
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Load the last hash from existing log
        if self._path.exists():
            self._load_last_hash()

    def _load_last_hash(self) -> None:
        """Read the last entry's hash to continue the chain."""
        try:
            with open(self._path) as f:
                last_line = ""
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
                if last_line:
                    data = json.loads(last_line)
                    self._last_hash = data.get("entry_hash", GENESIS_HASH)
        except Exception as e:
            logger.warning("Could not read last audit hash: %s", e)
            self._last_hash = GENESIS_HASH

    def append(self, entry: AuditEntry) -> AuditEntry:
        """Append an entry to the audit log with hash chain and HMAC."""
        entry.prev_hash = self._last_hash
        entry.entry_hash = entry.compute_hash()
        entry.hmac_sig = entry.compute_hmac(self._hmac_key)

        with open(self._path, "a") as f:
            f.write(json.dumps(asdict(entry), sort_keys=True, separators=(",", ":")) + "\n")

        self._last_hash = entry.entry_hash
        logger.debug("Audit: %s [%s] %s", entry.event_type, entry.actor, entry.session_id)
        return entry

    def log_event(
        self,
        session_id: str,
        event_type: str,
        actor: str = "orion",
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Convenience method to create and append an entry."""
        entry = AuditEntry(
            timestamp=time.time(),
            session_id=session_id,
            event_type=event_type,
            actor=actor,
            details=details or {},
        )
        return self.append(entry)

    def verify_chain(self) -> tuple[bool, int]:
        """Verify the integrity of the entire audit log.

        Returns (all_valid, entries_checked).
        """
        if not self._path.exists():
            return True, 0

        entries_checked = 0
        prev_hash = GENESIS_HASH

        with open(self._path) as f:
            for i, line in enumerate(f):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError:
                    logger.error("Audit chain broken: invalid JSON at line %d", i + 1)
                    return False, entries_checked

                entry = AuditEntry(**data)

                # Verify hash chain
                if entry.prev_hash != prev_hash:
                    logger.error(
                        "Audit chain broken at line %d: prev_hash mismatch (expected %s, got %s)",
                        i + 1,
                        prev_hash[:16],
                        entry.prev_hash[:16],
                    )
                    return False, entries_checked

                # Verify entry hash
                expected_hash = entry.compute_hash()
                if entry.entry_hash != expected_hash:
                    logger.error(
                        "Audit tampered at line %d: entry_hash mismatch",
                        i + 1,
                    )
                    return False, entries_checked

                # Verify HMAC
                expected_hmac = entry.compute_hmac(self._hmac_key)
                if entry.hmac_sig != expected_hmac:
                    logger.error(
                        "Audit tampered at line %d: HMAC mismatch",
                        i + 1,
                    )
                    return False, entries_checked

                prev_hash = entry.entry_hash
                entries_checked += 1

        return True, entries_checked

    def get_entries(
        self,
        session_id: str | None = None,
        event_type: str | None = None,
        limit: int | None = None,
    ) -> list[AuditEntry]:
        """Retrieve entries, optionally filtered by session_id and/or event_type."""
        if not self._path.exists():
            return []

        entries: list[AuditEntry] = []
        with open(self._path) as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    entry = AuditEntry(**data)
                    if session_id and entry.session_id != session_id:
                        continue
                    if event_type and entry.event_type != event_type:
                        continue
                    entries.append(entry)
                except Exception:
                    continue

        if limit:
            entries = entries[-limit:]
        return entries

    @property
    def entry_count(self) -> int:
        """Number of entries in the log."""
        if not self._path.exists():
            return 0
        count = 0
        with open(self._path) as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
