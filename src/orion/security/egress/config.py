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
# Search API domains -- auto-allowed for LLM web search (Phase 3.3).
# These are the search engine API endpoints that LLMs use internally.
# They are always allowed (like LLM domains) because search is a core
# capability.  Subsequent page fetches go through normal filtering.
# ---------------------------------------------------------------------------
SEARCH_API_DOMAINS: frozenset[str] = frozenset(
    {
        # Google Custom Search / Programmable Search Engine
        "customsearch.googleapis.com",
        "www.googleapis.com",
        # Bing Search API
        "api.bing.microsoft.com",
        # Brave Search API
        "api.search.brave.com",
        # SerpAPI (popular search wrapper)
        "serpapi.com",
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

    # Research domains -- GET-only access for LLM web browsing (Phase 3.3).
    # When an LLM performs a web search, it may need to fetch pages from
    # these domains.  They are auto-allowed for GET requests only.
    # POST/PUT/DELETE are blocked.  Users add these on the host side.
    research_domains: list[str] = field(default_factory=list)

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

        # Search API domains (auto-allowed, read+write for search queries)
        search_rules = [
            DomainRule(
                domain=d,
                allow_write=True,  # Search APIs use POST for queries
                protocols=["https"],
                rate_limit_rpm=300,
                added_by="system",
                description="Search API endpoint (auto-allowed)",
            )
            for d in sorted(SEARCH_API_DOMAINS)
        ]

        # Research domains (GET-only for web browsing)
        research_rules = [
            DomainRule(
                domain=d,
                allow_write=False,  # GET-only -- no POST/PUT/DELETE
                protocols=["https"],
                rate_limit_rpm=60,
                added_by="user",
                description="Research domain (GET-only browsing)",
            )
            for d in self.research_domains
        ]

        # User-enabled Google services (Phase 3.2 graduated access)
        google_rules = [
            DomainRule(
                domain=d,
                allow_write=False,  # Default: read-only; user can upgrade via whitelist
                protocols=["https"],
                rate_limit_rpm=120,
                added_by="user",
                description=f"Google service (user-enabled): {GOOGLE_SERVICES.get(d, {}).get('name', d)}",
            )
            for d in self.allowed_google_services
            if d in GOOGLE_SERVICES
        ]

        return hardcoded_rules + search_rules + google_rules + research_rules + list(self.whitelist)

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


# ---------------------------------------------------------------------------
# Module-level cache (avoids re-reading on every API request / health check)
# ---------------------------------------------------------------------------
_cached_config: EgressConfig | None = None
_config_warning_shown: bool = False


def load_config(path: Path | str | None = None, *, reload: bool = False) -> EgressConfig:
    """Load egress configuration from YAML file.

    Results are cached at module level.  Subsequent calls return the
    cached config unless ``reload=True`` is passed.  Caching only
    applies when using the default path; explicit paths always read
    from disk.

    If the file does not exist, a default config is created.
    If the file cannot be read (permission denied), a warning is
    logged **once** and the default config is returned.
    """
    global _cached_config, _config_warning_shown

    using_default_path = path is None
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if using_default_path and _cached_config is not None and not reload:
        return _cached_config

    # Create default config on first run
    if not config_path.exists():
        _write_default_config(config_path)

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            if not _config_warning_shown:
                logger.warning("Invalid egress config (not a dict) -- using defaults")
                _config_warning_shown = True
            result = EgressConfig()
            if using_default_path:
                _cached_config = result
            return result
        result = _parse_config(raw)
        if using_default_path:
            _cached_config = result
        return result
    except PermissionError:
        if not _config_warning_shown:
            logger.warning("Cannot read %s (permission denied) -- using defaults", config_path)
            _config_warning_shown = True
        result = EgressConfig()
        if using_default_path:
            _cached_config = result
        return result
    except Exception as exc:
        if not _config_warning_shown:
            logger.warning("Failed to load egress config: %s -- using defaults", exc)
            _config_warning_shown = True
        result = EgressConfig()
        if using_default_path:
            _cached_config = result
        return result


_save_warning_shown: bool = False


def save_config(config: EgressConfig, path: Path | str | None = None) -> None:
    """Save egress configuration to YAML file."""
    global _cached_config, _save_warning_shown
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

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
        "research_domains": config.research_domains,
    }

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8"
        )
        logger.info("Saved egress config to %s", config_path)
        _cached_config = config  # Update cache on successful save
    except PermissionError:
        if not _save_warning_shown:
            logger.warning("Cannot write %s (permission denied) -- config not saved", config_path)
            _save_warning_shown = True
    except Exception as exc:
        if not _save_warning_shown:
            logger.warning("Failed to save egress config: %s", exc)
            _save_warning_shown = True


_DEFAULT_CONFIG_YAML = """\
# Orion Egress Proxy Configuration
# See docs/NETWORK_SECURITY.md for details

# User-added domains (additive -- hardcoded LLM domains are always present)
user_whitelist: []

# Google services enabled for sandbox access (default: none)
allowed_google_services: []

# Research domains (GET-only access for LLM web browsing)
research_domains: []
"""


def _write_default_config(config_path: Path) -> None:
    """Create a minimal default config file on first run."""
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(_DEFAULT_CONFIG_YAML, encoding="utf-8")
        logger.info("Created default egress config at %s", config_path)
    except PermissionError:
        logger.warning(
            "Cannot create %s (permission denied) -- using in-memory defaults", config_path
        )
    except Exception as exc:
        logger.warning("Cannot create default config: %s -- using in-memory defaults", exc)


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

    # Parse research domains (Phase 3.3)
    research = raw.get("research_domains", [])
    if not isinstance(research, list):
        research = []
    research = [d for d in research if isinstance(d, str) and d.strip()]

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
        research_domains=research,
    )
