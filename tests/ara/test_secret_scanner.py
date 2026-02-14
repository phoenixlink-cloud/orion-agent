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
"""Tests for AEGIS Secret Scanner (ARA-001 §C.7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.security.secret_scanner import ScanResult, SecretFinding, SecretScanner


@pytest.fixture
def scanner() -> SecretScanner:
    return SecretScanner()


@pytest.fixture
def scanner_with_allowlist() -> SecretScanner:
    return SecretScanner(
        allowlist=[
            {"pattern": "EXAMPLE_API_KEY"},
            {"file": "tests/**"},
        ]
    )


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with sample files."""
    src = tmp_path / "src"
    src.mkdir()
    return tmp_path


class TestPatternDetection:
    """Test that each secret pattern is correctly detected."""

    def test_detects_aws_access_key(self, scanner: SecretScanner, tmp_project: Path):
        f = tmp_project / "src" / "config.py"
        f.write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')
        findings = scanner.scan_file(f, relative_to=tmp_project)
        assert len(findings) >= 1
        assert any(f.pattern_name == "aws_access_key" for f in findings)

    def test_detects_github_token(self, scanner: SecretScanner, tmp_project: Path):
        f = tmp_project / "src" / "deploy.py"
        f.write_text('GITHUB_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl"\n')
        findings = scanner.scan_file(f, relative_to=tmp_project)
        assert len(findings) >= 1
        assert any(f.pattern_name == "github_token" for f in findings)

    def test_detects_private_key(self, scanner: SecretScanner, tmp_project: Path):
        f = tmp_project / "src" / "key.pem"
        f.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n-----END RSA PRIVATE KEY-----\n")
        findings = scanner.scan_file(f, relative_to=tmp_project)
        assert len(findings) >= 1
        assert any(f.pattern_name == "private_key" for f in findings)

    def test_detects_generic_password(self, scanner: SecretScanner, tmp_project: Path):
        f = tmp_project / "src" / "db.py"
        f.write_text("password = 'supersecretpassword123'\n")
        findings = scanner.scan_file(f, relative_to=tmp_project)
        assert len(findings) >= 1
        assert any(f.pattern_name == "generic_password" for f in findings)

    def test_detects_connection_string(self, scanner: SecretScanner, tmp_project: Path):
        f = tmp_project / "src" / "db.py"
        f.write_text('DB_URL = "postgres://admin:pass@db.example.com:5432/mydb"\n')
        findings = scanner.scan_file(f, relative_to=tmp_project)
        assert len(findings) >= 1
        assert any(f.pattern_name == "connection_string" for f in findings)

    def test_detects_slack_webhook(self, scanner: SecretScanner, tmp_project: Path):
        f = tmp_project / "src" / "notify.py"
        f.write_text('WEBHOOK = "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"\n')
        findings = scanner.scan_file(f, relative_to=tmp_project)
        assert len(findings) >= 1
        assert any(f.pattern_name == "slack_webhook" for f in findings)

    def test_detects_generic_api_key(self, scanner: SecretScanner, tmp_project: Path):
        f = tmp_project / "src" / "api.py"
        f.write_text("api_key='skliveABCDEFGHIJKLMNOPQRSTUVWXYZab'\n")
        findings = scanner.scan_file(f, relative_to=tmp_project)
        assert len(findings) >= 1
        types = [finding.pattern_name for finding in findings]
        assert "generic_api_key" in types

    def test_detects_jwt_token(self, scanner: SecretScanner, tmp_project: Path):
        f = tmp_project / "src" / "auth.py"
        f.write_text(
            'TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            '.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"\n'
        )
        findings = scanner.scan_file(f, relative_to=tmp_project)
        assert len(findings) >= 1
        assert any(f.pattern_name == "jwt_token" for f in findings)


class TestCleanFiles:
    """Test that clean files produce no findings."""

    def test_clean_python_file(self, scanner: SecretScanner, tmp_project: Path):
        f = tmp_project / "src" / "main.py"
        f.write_text('def hello():\n    print("Hello world")\n')
        findings = scanner.scan_file(f, relative_to=tmp_project)
        assert len(findings) == 0

    def test_skips_binary_files(self, scanner: SecretScanner, tmp_project: Path):
        f = tmp_project / "src" / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"AKIAIOSFODNN7EXAMPLE")
        findings = scanner.scan_file(f, relative_to=tmp_project)
        assert len(findings) == 0


class TestAllowlist:
    """Test allowlist functionality."""

    def test_respects_pattern_allowlist(
        self, scanner_with_allowlist: SecretScanner, tmp_project: Path
    ):
        f = tmp_project / "src" / "docs.py"
        f.write_text('api_key = "EXAMPLE_API_KEY_FOR_DOCS_HERE"\n')
        findings = scanner_with_allowlist.scan_file(f, relative_to=tmp_project)
        assert len(findings) == 0

    def test_respects_file_allowlist(
        self, scanner_with_allowlist: SecretScanner, tmp_project: Path
    ):
        test_dir = tmp_project / "tests"
        test_dir.mkdir()
        f = test_dir / "test_auth.py"
        f.write_text('password = "testpassword123"\n')
        findings = scanner_with_allowlist.scan_file(f, relative_to=tmp_project)
        assert len(findings) == 0

    def test_blocks_non_allowlisted(
        self, scanner_with_allowlist: SecretScanner, tmp_project: Path
    ):
        f = tmp_project / "src" / "real_secret.py"
        f.write_text('password = "production_password_here"\n')
        findings = scanner_with_allowlist.scan_file(f, relative_to=tmp_project)
        assert len(findings) >= 1


class TestRedaction:
    """Test that output is properly redacted."""

    def test_redacts_output(self, scanner: SecretScanner):
        redacted = SecretScanner._redact("AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in redacted
        assert redacted.startswith("AKIA")
        assert len(redacted) < len("AKIAIOSFODNN7EXAMPLE")

    def test_redacts_short_string(self, scanner: SecretScanner):
        redacted = SecretScanner._redact("short")
        assert redacted == "***REDACTED***"


class TestDirectoryScan:
    """Test full directory scanning."""

    def test_scans_all_files(self, scanner: SecretScanner, tmp_project: Path):
        (tmp_project / "src" / "clean.py").write_text("x = 1\n")
        (tmp_project / "src" / "dirty.py").write_text(
            '-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n'
        )
        result = scanner.scan_directory(tmp_project / "src")
        assert result.files_scanned == 2
        assert len(result.findings) >= 1
        assert result.blocked is True

    def test_clean_directory(self, scanner: SecretScanner, tmp_project: Path):
        (tmp_project / "src" / "a.py").write_text("x = 1\n")
        (tmp_project / "src" / "b.py").write_text("y = 2\n")
        result = scanner.scan_directory(tmp_project / "src")
        assert result.clean is True
        assert result.blocked is False
        assert result.files_scanned == 2


class TestScanResult:
    """Test ScanResult properties."""

    def test_clean_summary(self):
        result = ScanResult(files_scanned=10)
        assert "clean" in result.summary().lower()

    def test_blocked_summary(self):
        result = ScanResult(
            findings=[
                SecretFinding("f.py", 1, "test", "secret", "***")
            ],
            files_scanned=5,
            blocked=True,
        )
        assert "BLOCKED" in result.summary()

    def test_finding_to_dict(self):
        finding = SecretFinding("f.py", 10, "aws_access_key", "AKIA...", "AKIA...LE")
        d = finding.to_dict()
        assert d["file"] == "f.py"
        assert d["line"] == 10
        assert d["type"] == "aws_access_key"
