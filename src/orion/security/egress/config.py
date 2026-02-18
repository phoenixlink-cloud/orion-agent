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
"""Egress proxy configuration schema.

The egress config lives on the HOST filesystem, outside the Docker
sandbox. Orion (inside the container) can NEVER modify this file.
This is a physical security boundary enforced by container isolation.

Config location: ~/.orion/egress_config.yaml  (host-side)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("orion.security.egress.config")

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
_ORION_HOME = Path(os.environ.get("ORION_HOME", Path.home() / ".orion"))
DEFAULT_CONFIG_PATH = _ORION_HOME / "egress_config.yaml"

# ---------------------------------------------------------------------------
# LLM endpoints that are ALWAYS allowed (hardcoded, not user-removable).
# These are the core LLM provider domains required for Orion to function.
# ---------------------------------------------------------------------------
HARDCODED_LLM_DOMAINS: frozenset[str] = frozenset(
    {
        # Google / Gemini
        "generativelanguage.googleapis.com",
        "aiplatform.googleapis.com",
        "accounts.google.com",
        "oauth2.googleapis.com",
        # Anthropic
        "api.anthropic.com",
        # OpenAI
        "api.openai.com",
        "auth.openai.com",
        # Ollama (local -- typically localhost, but allow the domain too)
        "localhost",
        "127.0.0.1",
    }
)

# ---------------------------------------------------------------------------
# Google services that can be individually whitelisted by users (Phase 3).
# Default state: ALL BLOCKED (AEGIS Invariant 7).  Users toggle services
# on the host side; the container cannot modify this list.
# ---------------------------------------------------------------------------
GOOGLE_SERVICES: dict[str, dict[str, str]] = {
    "drive.googleapis.com": {
        "name": "Google Drive",
        "description": "File storage, sharing, and collaboration",
        "risk": "high",
    },
    "gmail.googleapis.com": {
        "name": "Gmail",
        "description": "Email sending and inbox access",
        "risk": "high",
    },
    "calendar.googleapis.com": {
        "name": "Google Calendar",
        "description": "Event creation, scheduling, and invitations",
        "risk": "medium",
    },
    "youtube.googleapis.com": {
        "name": "YouTube",
        "description": "Video search, metadata, and playlist management",
        "risk": "low",
    },
    "photoslibrary.googleapis.com": {
        "name": "Google Photos",
        "description": "Photo library access and management",
        "risk": "medium",
    },
    "people.googleapis.com": {
        "name": "Google People (Contacts)",
        "description": "Contact list access and management",
        "risk": "high",
    },
    "docs.googleapis.com": {
        "name": "Google Docs",
        "description": "Document creation and editing",
        "risk": "medium",
    },
    "sheets.googleapis.com": {
        "name": "Google Sheets",
        "description": "Spreadsheet creation and data access",
        "risk": "medium",
    },
    "slides.googleapis.com": {
        "name": "Google Slides",
        "description": "Presentation creation and editing",
        "risk": "low",
    },
}


@dataclass
class DomainRule:
    """A single domain whitelist entry with access constraints."""

    domain: str
    allow_write: bool = False  # False = GET-only (read-only web)
    protocols: list[str] = field(default_factory=lambda: ["https"])
    rate_limit_rpm: int = 60  # Requests per minute
    added_by: str = "system"  # "system" (hardcoded) or "user"
    description: str = ""

    def matches(self, hostname: str) -> bool:
        """Check if hostname matches this rule (supports subdomain matching)."""
        hostname = hostname.lower().strip()
        domain = self.domain.lower().strip()
        # Exact match
        if hostname == domain:
            return True
        # Subdomain match: rule for "example.com" matches "api.example.com"
        return bool(hostname.endswith("." + domain))


@dataclass
class EgressConfig:
    """Full egress proxy configuration.

    This dataclass represents the AEGIS-governed network policy.
    It is loaded from the host filesystem and is immutable from
    inside the Docker sandbox.
    """

    # User-configured domain whitelist (additive)
    whitelist: list[DomainRule] = field(default_factory=list)

    # Global rate limit (requests per minute across all domains)
    global_rate_limit_rpm: int = 300

    # Proxy listen address and port
    proxy_host: str = "0.0.0.0"
    proxy_port: int = 8888

    # Enable content inspection for outbound payloads
    content_inspection: bool = True

    # Maximum request body size (bytes) for content inspection
    max_body_size: int = 10 * 1024 * 1024  # 10 MB

    # Enable DNS-level filtering
    dns_filtering: bool = True

    # Audit log path (host-side, outside sandbox)
    audit_log_path: str = str(_ORION_HOME / "egress_audit.log")

    # Whether to block requests to non-whitelisted domains (True)
    # or just log them (False, for debugging)
    enforce: bool = True

    # Google services explicitly enabled by the user (Phase 3).
    # Default: empty (all blocked by AEGIS Invariant 7).
    # Each entry is a domain from GOOGLE_SERVICES.
    # This list lives on the HOST and cannot be modified by Orion.
    allowed_google_services: list[str] = field(default_factory=list)

    def get_all_allowed_domains(self) -> list[DomainRule]:
        """Return all allowed domains: hardcoded LLM + user whitelist."""
        # Build hardcoded rules (always allowed, write permitted for LLM)
        hardcoded_rules = [
            DomainRule(
                domain=d,
                allow_write=True,
                protocols=["https"] if d not in ("localhost", "127.0.0.1") else ["http", "https"],
                rate_limit_rpm=600,  # LLM endpoints get higher rate limit
                added_by="system",
                description="Hardcoded LLM endpoint (non-removable)",
            )
            for d in sorted(HARDCODED_LLM_DOMAINS)
        ]
        return hardcoded_rules + list(self.whitelist)

    def is_domain_allowed(self, hostname: str) -> DomainRule | None:
        """Check if a hostname is allowed. Returns the matching rule or None."""
        for rule in self.get_all_allowed_domains():
            if rule.matches(hostname):
                return rule
        return None

    def is_write_allowed(self, hostname: str) -> bool:
        """Check if write (POST/PUT/PATCH/DELETE) is allowed for a hostname."""
        rule = self.is_domain_allowed(hostname)
        if rule is None:
            return False
        return rule.allow_write

    def is_protocol_allowed(self, hostname: str, protocol: str) -> bool:
        """Check if a specific protocol is allowed for a hostname."""
        rule = self.is_domain_allowed(hostname)
        if rule is None:
            return False
        return protocol.lower() in [p.lower() for p in rule.protocols]


def load_config(path: Path | str | None = None) -> EgressConfig:
    """Load egress configuration from YAML file.

    If the file does not exist, returns the default config
    (hardcoded LLM endpoints only, everything else blocked).
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        logger.info("No egress config at %s -- using defaults (LLM-only)", config_path)
        return EgressConfig()

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            logger.warning("Invalid egress config (not a dict) -- using defaults")
            return EgressConfig()
        return _parse_config(raw)
    except Exception as exc:
        logger.error("Failed to load egress config: %s -- using defaults", exc)
        return EgressConfig()


def save_config(config: EgressConfig, path: Path | str | None = None) -> None:
    """Save egress configuration to YAML file."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {
        "proxy": {
            "host": config.proxy_host,
            "port": config.proxy_port,
        },
        "global_rate_limit_rpm": config.global_rate_limit_rpm,
        "content_inspection": config.content_inspection,
        "max_body_size": config.max_body_size,
        "dns_filtering": config.dns_filtering,
        "audit_log_path": config.audit_log_path,
        "enforce": config.enforce,
        "whitelist": [
            {
                "domain": rule.domain,
                "allow_write": rule.allow_write,
                "protocols": rule.protocols,
                "rate_limit_rpm": rule.rate_limit_rpm,
                "description": rule.description,
            }
            for rule in config.whitelist
        ],
        "allowed_google_services": config.allowed_google_services,
    }
    config_path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8"
    )
    logger.info("Saved egress config to %s", config_path)


def _parse_config(raw: dict) -> EgressConfig:
    """Parse raw YAML dict into EgressConfig."""
    proxy_section = raw.get("proxy", {})

    whitelist_raw = raw.get("whitelist", [])
    whitelist = []
    for entry in whitelist_raw:
        if isinstance(entry, str):
            # Simple form: just a domain name
            whitelist.append(DomainRule(domain=entry, added_by="user"))
        elif isinstance(entry, dict):
            whitelist.append(
                DomainRule(
                    domain=entry.get("domain", ""),
                    allow_write=entry.get("allow_write", False),
                    protocols=entry.get("protocols", ["https"]),
                    rate_limit_rpm=entry.get("rate_limit_rpm", 60),
                    added_by="user",
                    description=entry.get("description", ""),
                )
            )

    # Filter out empty domain entries
    whitelist = [r for r in whitelist if r.domain.strip()]

    # Parse allowed Google services (Phase 3)
    allowed_google = raw.get("allowed_google_services", [])
    if not isinstance(allowed_google, list):
        allowed_google = []
    # Validate entries against known services
    allowed_google = [s for s in allowed_google if isinstance(s, str) and s in GOOGLE_SERVICES]

    return EgressConfig(
        whitelist=whitelist,
        global_rate_limit_rpm=raw.get("global_rate_limit_rpm", 300),
        proxy_host=proxy_section.get("host", "0.0.0.0"),
        proxy_port=proxy_section.get("port", 8888),
        content_inspection=raw.get("content_inspection", True),
        max_body_size=raw.get("max_body_size", 10 * 1024 * 1024),
        dns_filtering=raw.get("dns_filtering", True),
        audit_log_path=raw.get("audit_log_path", str(_ORION_HOME / "egress_audit.log")),
        enforce=raw.get("enforce", True),
        allowed_google_services=allowed_google,
    )
