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
"""AEGIS Secret Scanner — blocks promotion of files containing hardcoded secrets.

Part of the AEGIS traffic gate (ARA-001 §C.7). Runs automatically before
every sandbox-to-workspace promotion. Uses regex pattern matching with a
user-managed allowlist for false positives.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.security.secret_scanner")

# Binary file extensions to skip
_BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".sqlite", ".db",
})


@dataclass
class SecretFinding:
    """A single secret detection result."""

    file_path: str
    line_number: int
    pattern_name: str
    matched_text: str
    redacted_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "line": self.line_number,
            "type": self.pattern_name,
            "redacted": self.redacted_text,
        }


@dataclass
class ScanResult:
    """Result of scanning a set of files."""

    findings: list[SecretFinding] = field(default_factory=list)
    files_scanned: int = 0
    blocked: bool = False

    @property
    def clean(self) -> bool:
        return len(self.findings) == 0

    def summary(self) -> str:
        if self.clean:
            return f"Secret scan clean ({self.files_scanned} files scanned)"
        return (
            f"SECRET SCAN BLOCKED: {len(self.findings)} finding(s) "
            f"in {self.files_scanned} files scanned"
        )


class SecretScanner:
    """Regex-based secret scanner for pre-promotion checks.

    Detects common secret patterns (API keys, tokens, passwords, private keys,
    connection strings) in files. Supports a user-managed allowlist for
    suppressing false positives.
    """

    PATTERNS: dict[str, re.Pattern] = {
        "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
        "aws_secret_key": re.compile(r"(?<![A-Za-z0-9/+])[0-9a-zA-Z/+]{40}(?![A-Za-z0-9/+=])"),
        "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
        "jwt_token": re.compile(
            r"eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"
        ),
        "generic_api_key": re.compile(
            r"(?i)(api[_\-]?key|apikey)\s*[:=]\s*['\"][A-Za-z0-9]{20,}['\"]"
        ),
        "generic_password": re.compile(
            r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
        ),
        "private_key": re.compile(r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----"),
        "connection_string": re.compile(
            r"(?i)(mongodb|postgres|mysql|redis)://[^\s]+@[^\s]+"
        ),
        "slack_webhook": re.compile(
            r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"
        ),
        "generic_secret": re.compile(
            r"(?i)(secret|token|credential)\s*[:=]\s*['\"][A-Za-z0-9+/=]{20,}['\"]"
        ),
    }

    def __init__(self, allowlist: list[dict[str, str]] | None = None):
        self._allowlist_patterns: list[str] = []
        self._allowlist_files: list[str] = []
        if allowlist:
            for entry in allowlist:
                if "pattern" in entry:
                    self._allowlist_patterns.append(entry["pattern"])
                if "file" in entry:
                    self._allowlist_files.append(entry["file"])

    @classmethod
    def load_allowlist(cls, allowlist_path: Path) -> list[dict[str, str]]:
        """Load allowlist from a YAML file."""
        if not allowlist_path.exists():
            return []
        try:
            import yaml

            with open(allowlist_path) as f:
                data = yaml.safe_load(f)
            return data.get("allowlist", []) if data else []
        except Exception as e:
            logger.warning("Failed to load secrets allowlist: %s", e)
            return []

    def _is_allowlisted_file(self, file_path: str) -> bool:
        """Check if a file path matches any allowlist file glob."""
        from fnmatch import fnmatch

        for pattern in self._allowlist_files:
            if fnmatch(file_path, pattern):
                return True
        return False

    def _is_allowlisted_text(self, matched_text: str) -> bool:
        """Check if matched text contains an allowlisted pattern."""
        for pattern in self._allowlist_patterns:
            if pattern in matched_text:
                return True
        return False

    @staticmethod
    def _redact(text: str) -> str:
        """Redact a secret, showing only first 4 and last 2 characters."""
        if len(text) <= 8:
            return "***REDACTED***"
        return f"{text[:4]}...{text[-2:]}"

    @staticmethod
    def _is_binary(file_path: Path) -> bool:
        """Check if a file is likely binary based on extension."""
        return file_path.suffix.lower() in _BINARY_EXTENSIONS

    def scan_file(self, file_path: Path, relative_to: Path | None = None) -> list[SecretFinding]:
        """Scan a single file for secrets."""
        if self._is_binary(file_path):
            return []

        rel_path = str(file_path.relative_to(relative_to)) if relative_to else str(file_path)

        if self._is_allowlisted_file(rel_path):
            return []

        findings: list[SecretFinding] = []
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []

        for line_num, line in enumerate(text.splitlines(), start=1):
            for pattern_name, pattern in self.PATTERNS.items():
                for match in pattern.finditer(line):
                    matched = match.group(0)
                    if self._is_allowlisted_text(matched):
                        continue
                    findings.append(
                        SecretFinding(
                            file_path=rel_path,
                            line_number=line_num,
                            pattern_name=pattern_name,
                            matched_text=matched,
                            redacted_text=self._redact(matched),
                        )
                    )
        return findings

    def scan_directory(self, directory: Path) -> ScanResult:
        """Scan all files in a directory recursively."""
        result = ScanResult()
        if not directory.is_dir():
            return result

        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.name.startswith("."):
                continue
            result.files_scanned += 1
            file_findings = self.scan_file(file_path, relative_to=directory)
            result.findings.extend(file_findings)

        result.blocked = not result.clean
        logger.info(result.summary())
        return result

    def scan_files(self, files: list[Path], relative_to: Path | None = None) -> ScanResult:
        """Scan a specific list of files."""
        result = ScanResult()
        for file_path in files:
            if not file_path.is_file():
                continue
            result.files_scanned += 1
            file_findings = self.scan_file(file_path, relative_to=relative_to)
            result.findings.extend(file_findings)

        result.blocked = not result.clean
        logger.info(result.summary())
        return result
