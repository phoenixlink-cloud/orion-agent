# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for egress audit logger."""

import json
import time
from pathlib import Path

import pytest

from orion.security.egress.audit import AuditEntry, AuditLogger


class TestAuditEntry:
    """Tests for AuditEntry dataclass and factory methods."""

    def test_blocked_entry(self):
        entry = AuditEntry.blocked("GET", "http://evil.com/steal", "evil.com", "Domain not whitelisted")
        assert entry.event_type == "blocked"
        assert entry.method == "GET"
        assert entry.hostname == "evil.com"
        assert entry.blocked_reason == "Domain not whitelisted"
        assert entry.rule_matched == "BLOCKED"
        assert entry.timestamp > 0

    def test_allowed_entry(self):
        entry = AuditEntry.allowed(
            "POST", "https://api.openai.com/v1/chat/completions",
            "api.openai.com", "api.openai.com",
            status_code=200, duration_ms=150.5,
            request_size=1024, response_size=2048,
        )
        assert entry.event_type == "request"
        assert entry.status_code == 200
        assert entry.duration_ms == 150.5
        assert entry.request_size == 1024

    def test_rate_limited_entry(self):
        entry = AuditEntry.rate_limited("GET", "https://api.openai.com/models", "api.openai.com")
        assert entry.event_type == "rate_limited"
        assert entry.rule_matched == "RATE_LIMITED"

    def test_credential_leak_entry(self):
        entry = AuditEntry.credential_leak(
            "POST", "https://evil.com/exfil", "evil.com",
            ["openai_api_key", "github_token"],
        )
        assert entry.event_type == "credential_leak"
        assert len(entry.credential_patterns) == 2
        assert "openai_api_key" in entry.credential_patterns

    def test_to_json_roundtrip(self):
        entry = AuditEntry.blocked("GET", "http://test.com", "test.com", "blocked")
        json_str = entry.to_json()
        data = json.loads(json_str)
        assert data["event_type"] == "blocked"
        assert data["hostname"] == "test.com"

    def test_timestamp_is_recent(self):
        before = time.time()
        entry = AuditEntry.blocked("GET", "http://test.com", "test.com", "test")
        after = time.time()
        assert before <= entry.timestamp <= after


class TestAuditLogger:
    """Tests for AuditLogger file operations."""

    def test_log_creates_file(self, tmp_path):
        log_path = tmp_path / "audit.log"
        with AuditLogger(log_path) as logger:
            logger.log(AuditEntry.blocked("GET", "http://test.com", "test.com", "test"))
        assert log_path.exists()

    def test_log_writes_json_lines(self, tmp_path):
        log_path = tmp_path / "audit.log"
        with AuditLogger(log_path) as logger:
            logger.log(AuditEntry.blocked("GET", "http://a.com", "a.com", "test"))
            logger.log(AuditEntry.allowed("POST", "http://b.com", "b.com", "rule1"))
            logger.log(AuditEntry.rate_limited("GET", "http://c.com", "c.com"))

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 3
        # Each line is valid JSON
        for line in lines:
            data = json.loads(line)
            assert "event_type" in data

    def test_entry_count(self, tmp_path):
        log_path = tmp_path / "audit.log"
        with AuditLogger(log_path) as logger:
            assert logger.entry_count == 0
            logger.log(AuditEntry.blocked("GET", "http://a.com", "a.com", "test"))
            assert logger.entry_count == 1
            logger.log(AuditEntry.blocked("GET", "http://b.com", "b.com", "test"))
            assert logger.entry_count == 2

    def test_read_recent(self, tmp_path):
        log_path = tmp_path / "audit.log"
        with AuditLogger(log_path) as logger:
            for i in range(10):
                logger.log(AuditEntry.blocked("GET", f"http://test{i}.com", f"test{i}.com", "test"))

        reader = AuditLogger(log_path)
        recent = reader.read_recent(5)
        assert len(recent) == 5
        # Should be the last 5 entries
        assert recent[-1].hostname == "test9.com"
        reader.close()

    def test_read_recent_empty_file(self, tmp_path):
        log_path = tmp_path / "audit.log"
        reader = AuditLogger(log_path)
        recent = reader.read_recent()
        assert recent == []
        reader.close()

    def test_get_stats(self, tmp_path):
        log_path = tmp_path / "audit.log"
        with AuditLogger(log_path) as logger:
            logger.log(AuditEntry.blocked("GET", "http://a.com", "a.com", "test"))
            logger.log(AuditEntry.allowed("POST", "http://b.com", "b.com", "rule"))
            logger.log(AuditEntry.rate_limited("GET", "http://c.com", "c.com"))
            logger.log(AuditEntry.credential_leak("POST", "http://d.com", "d.com", ["sk"]))
            logger.log(AuditEntry.allowed("GET", "http://b.com", "b.com", "rule"))

        reader = AuditLogger(log_path)
        stats = reader.get_stats()
        assert stats["total_requests"] == 5
        assert stats["blocked"] == 1
        assert stats["allowed"] == 2
        assert stats["rate_limited"] == 1
        assert stats["credential_leaks"] == 1
        assert stats["unique_domains"] == 4
        reader.close()

    def test_path_property(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = AuditLogger(log_path)
        assert logger.path == log_path
        logger.close()

    def test_creates_parent_dirs(self, tmp_path):
        log_path = tmp_path / "subdir" / "nested" / "audit.log"
        logger = AuditLogger(log_path)
        logger.log(AuditEntry.blocked("GET", "http://test.com", "test.com", "test"))
        assert log_path.exists()
        logger.close()
