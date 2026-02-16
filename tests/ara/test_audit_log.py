# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Phase 10: AuditLog — tamper-proof audit log with HMAC hash chain."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from orion.ara.audit_log import GENESIS_HASH, AuditEntry, AuditLog


@pytest.fixture
def audit_path(tmp_path: Path) -> Path:
    return tmp_path / "audit" / "audit.jsonl"


@pytest.fixture
def hmac_key() -> bytes:
    return b"test-key-for-audit-log-0123456789abcdef"


@pytest.fixture
def log(audit_path: Path, hmac_key: bytes) -> AuditLog:
    return AuditLog(path=audit_path, hmac_key=hmac_key)


class TestAuditEntry:
    def test_compute_hash_deterministic(self):
        e = AuditEntry(
            timestamp=1000.0,
            session_id="s1",
            event_type="test",
            actor="orion",
        )
        h1 = e.compute_hash()
        h2 = e.compute_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_compute_hash_changes_with_data(self):
        e1 = AuditEntry(
            timestamp=1000.0,
            session_id="s1",
            event_type="test",
            actor="orion",
        )
        e2 = AuditEntry(
            timestamp=1000.0,
            session_id="s2",
            event_type="test",
            actor="orion",
        )
        assert e1.compute_hash() != e2.compute_hash()

    def test_compute_hmac(self):
        e = AuditEntry(
            timestamp=1000.0,
            session_id="s1",
            event_type="test",
            actor="orion",
        )
        e.entry_hash = e.compute_hash()
        sig = e.compute_hmac(b"key1")
        assert len(sig) == 64
        # Different key = different HMAC
        sig2 = e.compute_hmac(b"key2")
        assert sig != sig2


class TestAuditLogAppend:
    def test_append_creates_file(self, log: AuditLog, audit_path: Path):
        assert not audit_path.exists()
        log.log_event("s1", "test_event")
        assert audit_path.exists()

    def test_append_writes_jsonl(self, log: AuditLog, audit_path: Path):
        log.log_event("s1", "event_a")
        log.log_event("s1", "event_b")
        lines = audit_path.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "entry_hash" in data
            assert "hmac_sig" in data

    def test_first_entry_has_genesis_prev(self, log: AuditLog, audit_path: Path):
        log.log_event("s1", "first")
        data = json.loads(audit_path.read_text().strip())
        assert data["prev_hash"] == GENESIS_HASH

    def test_chain_links(self, log: AuditLog, audit_path: Path):
        log.log_event("s1", "first")
        log.log_event("s1", "second")
        lines = audit_path.read_text().strip().split("\n")
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert second["prev_hash"] == first["entry_hash"]

    def test_log_event_with_details(self, log: AuditLog):
        entry = log.log_event("s1", "task_done", actor="user", details={"task": "write_tests"})
        assert entry.actor == "user"
        assert entry.details["task"] == "write_tests"

    def test_entry_count(self, log: AuditLog):
        assert log.entry_count == 0
        log.log_event("s1", "a")
        log.log_event("s1", "b")
        log.log_event("s2", "c")
        assert log.entry_count == 3


class TestAuditLogVerify:
    def test_verify_empty(self, log: AuditLog):
        valid, count = log.verify_chain()
        assert valid is True
        assert count == 0

    def test_verify_valid_chain(self, log: AuditLog):
        for i in range(5):
            log.log_event("s1", f"event_{i}")
        valid, count = log.verify_chain()
        assert valid is True
        assert count == 5

    def test_verify_detects_tampered_hash(self, log: AuditLog, audit_path: Path):
        log.log_event("s1", "legit")
        log.log_event("s1", "also_legit")

        # Tamper with the second entry's entry_hash
        lines = audit_path.read_text().strip().split("\n")
        data = json.loads(lines[1])
        data["entry_hash"] = "0" * 64  # fake hash
        lines[1] = json.dumps(data, sort_keys=True, separators=(",", ":"))
        audit_path.write_text("\n".join(lines) + "\n")

        valid, count = log.verify_chain()
        assert valid is False

    def test_verify_detects_tampered_hmac(self, log: AuditLog, audit_path: Path):
        log.log_event("s1", "legit")

        lines = audit_path.read_text().strip().split("\n")
        data = json.loads(lines[0])
        data["hmac_sig"] = "f" * 64
        lines[0] = json.dumps(data, sort_keys=True, separators=(",", ":"))
        audit_path.write_text("\n".join(lines) + "\n")

        valid, count = log.verify_chain()
        assert valid is False

    def test_verify_detects_broken_chain(self, log: AuditLog, audit_path: Path):
        log.log_event("s1", "first")
        log.log_event("s1", "second")

        lines = audit_path.read_text().strip().split("\n")
        data = json.loads(lines[1])
        data["prev_hash"] = "a" * 64
        lines[1] = json.dumps(data, sort_keys=True, separators=(",", ":"))
        audit_path.write_text("\n".join(lines) + "\n")

        valid, count = log.verify_chain()
        assert valid is False

    def test_persistence_across_instances(
        self,
        audit_path: Path,
        hmac_key: bytes,
    ):
        log1 = AuditLog(path=audit_path, hmac_key=hmac_key)
        log1.log_event("s1", "from_log1")

        log2 = AuditLog(path=audit_path, hmac_key=hmac_key)
        log2.log_event("s1", "from_log2")

        valid, count = log2.verify_chain()
        assert valid is True
        assert count == 2


class TestAuditLogQuery:
    def test_get_all_entries(self, log: AuditLog):
        log.log_event("s1", "a")
        log.log_event("s2", "b")
        entries = log.get_entries()
        assert len(entries) == 2

    def test_filter_by_session(self, log: AuditLog):
        log.log_event("s1", "a")
        log.log_event("s2", "b")
        log.log_event("s1", "c")
        entries = log.get_entries(session_id="s1")
        assert len(entries) == 2

    def test_filter_by_event_type(self, log: AuditLog):
        log.log_event("s1", "task_started")
        log.log_event("s1", "task_completed")
        log.log_event("s1", "task_started")
        entries = log.get_entries(event_type="task_started")
        assert len(entries) == 2

    def test_limit(self, log: AuditLog):
        for i in range(10):
            log.log_event("s1", f"event_{i}")
        entries = log.get_entries(limit=3)
        assert len(entries) == 3

    def test_empty_log(self, log: AuditLog):
        entries = log.get_entries()
        assert entries == []
