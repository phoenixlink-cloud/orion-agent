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
"""Egress content inspector -- credential leakage detection.

Inspects outbound HTTP request bodies for credential patterns before
they leave the Docker sandbox. Reuses patterns from the existing
SecretScanner but adapted for network payload inspection.

This is a BLOCKING check: if a credential pattern is found in an
outbound request body, the request is rejected and the event is
logged in the audit trail.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("orion.security.egress.inspector")

# ---------------------------------------------------------------------------
# Credential patterns for outbound payload inspection.
# These are deliberately broad -- false positives are acceptable because
# blocking a legitimate request is always safer than leaking a credential.
# ---------------------------------------------------------------------------
_CREDENTIAL_PATTERNS: dict[str, re.Pattern] = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "aws_secret_key": re.compile(r"(?<![A-Za-z0-9/+])[0-9a-zA-Z/+]{40}(?![A-Za-z0-9/+=])"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
    "openai_api_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "anthropic_api_key": re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    "slack_token": re.compile(r"xox[bpras]-[A-Za-z0-9\-]{10,}"),
    "slack_webhook": re.compile(
        r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"
    ),
    "private_key_header": re.compile(r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----"),
    "connection_string": re.compile(r"(?i)(mongodb|postgres|mysql|redis)://[^\s]+@[^\s]+"),
    "generic_bearer_token": re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.~+/]{40,}"),
    "generic_password_assignment": re.compile(
        r'(?i)(password|passwd|pwd|secret)\s*[:=]\s*["\'][^"\']{8,}["\']'
    ),
}

# Patterns that are EXPECTED in LLM API calls and should NOT trigger
# blocking. For example, the Authorization header with the user's own
# API key being sent TO the LLM provider is legitimate traffic.
_LLM_PROVIDER_DOMAINS = frozenset(
    {
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
        "aiplatform.googleapis.com",
        "localhost",
        "127.0.0.1",
    }
)


@dataclass
class InspectionResult:
    """Result of inspecting an outbound payload."""

    clean: bool
    patterns_found: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return not self.clean


class ContentInspector:
    """Inspects outbound HTTP payloads for credential leakage.

    This inspector is deliberately conservative: it blocks on any
    pattern match. The user can review blocked requests in the audit
    log and add exceptions if needed.
    """

    def __init__(
        self,
        extra_patterns: dict[str, re.Pattern] | None = None,
        max_body_size: int = 10 * 1024 * 1024,
    ) -> None:
        self._patterns = dict(_CREDENTIAL_PATTERNS)
        if extra_patterns:
            self._patterns.update(extra_patterns)
        self._max_body_size = max_body_size

    def inspect(
        self,
        body: bytes | str,
        target_hostname: str,
        method: str = "POST",
    ) -> InspectionResult:
        """Inspect an outbound request body for credential patterns.

        Args:
            body: The request body (bytes or string).
            target_hostname: The destination hostname.
            method: The HTTP method.

        Returns:
            InspectionResult indicating whether the payload is clean.
        """
        # GET/HEAD/OPTIONS requests have no meaningful body to inspect
        if method.upper() in ("GET", "HEAD", "OPTIONS"):
            return InspectionResult(clean=True)

        # Skip inspection for traffic TO LLM providers -- these are
        # legitimate API calls that will contain auth headers/keys
        if target_hostname.lower() in _LLM_PROVIDER_DOMAINS:
            return InspectionResult(clean=True)

        # Convert to string for regex matching
        if isinstance(body, bytes):
            try:
                text = body.decode("utf-8", errors="replace")
            except Exception:
                return InspectionResult(clean=True)
        else:
            text = body

        # Skip if body is too large (likely a file upload, not credential leak)
        if len(text) > self._max_body_size:
            logger.warning(
                "Skipping content inspection: body too large (%d bytes)",
                len(text),
            )
            return InspectionResult(clean=True)

        # Skip empty bodies
        if not text.strip():
            return InspectionResult(clean=True)

        # Run all patterns
        patterns_found: list[str] = []
        details: list[str] = []

        for pattern_name, pattern in self._patterns.items():
            matches = pattern.findall(text)
            if matches:
                patterns_found.append(pattern_name)
                # Redact the match for the detail message
                for match in matches[:3]:  # Cap at 3 matches per pattern
                    redacted = _redact(match if isinstance(match, str) else str(match))
                    details.append(f"{pattern_name}: {redacted}")

        if patterns_found:
            logger.warning(
                "CREDENTIAL LEAK BLOCKED: %d pattern(s) in request to %s: %s",
                len(patterns_found),
                target_hostname,
                ", ".join(patterns_found),
            )

        return InspectionResult(
            clean=len(patterns_found) == 0,
            patterns_found=patterns_found,
            details=details,
        )


def _redact(text: str) -> str:
    """Redact a value, showing only first 4 and last 2 characters."""
    if len(text) <= 8:
        return "***REDACTED***"
    return f"{text[:4]}...{text[-2:]}"
