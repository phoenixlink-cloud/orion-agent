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
"""Tests for Phase 3.4: Graduated Google service access (end-to-end).

Verifies the full flow:
  toggle UI → save config → reload proxy → AEGIS allows → proxy allows

This is the integration test that ties P3.1 (orchestrator), P3.2
(Google services toggle), and P3.3 (search routing) together.
"""

from __future__ import annotations

from orion.core.governance.aegis import (
    _BLOCKED_GOOGLE_SERVICES,
    NetworkAccessRequest,
    check_network_access,
)
from orion.security.egress.config import (
    GOOGLE_SERVICES,
    SEARCH_API_DOMAINS,
    EgressConfig,
    load_config,
    save_config,
)

# ============================================================================
# End-to-end: toggle → config → proxy → AEGIS
# ============================================================================


class TestGraduatedAccessE2E:
    """Full end-to-end graduated access flow."""

    def test_e2e_enable_gmail(self, tmp_path):
        """Enable Gmail → config saved → proxy allows → AEGIS passes."""
        path = tmp_path / "egress.yaml"

        # 1. Start with default config (all Google services blocked)
        config = EgressConfig()
        save_config(config, path)

        loaded = load_config(path)
        assert loaded.allowed_google_services == []

        # Gmail should be blocked at both levels
        assert loaded.is_domain_allowed("gmail.googleapis.com") is None
        aegis = check_network_access(
            NetworkAccessRequest(hostname="gmail.googleapis.com"),
            user_allowed_services=set(loaded.allowed_google_services),
        )
        assert not aegis.passed

        # 2. User enables Gmail (simulates PUT /api/egress/google-services/gmail.googleapis.com)
        loaded.allowed_google_services = ["gmail.googleapis.com"]
        save_config(loaded, path)

        # 3. Reload config (simulates orchestrator.reload_config())
        reloaded = load_config(path)

        # 4. Proxy now allows Gmail
        rule = reloaded.is_domain_allowed("gmail.googleapis.com")
        assert rule is not None
        assert rule.domain == "gmail.googleapis.com"
        assert not rule.allow_write  # Default: read-only

        # 5. AEGIS also passes
        aegis = check_network_access(
            NetworkAccessRequest(hostname="gmail.googleapis.com"),
            user_allowed_services=set(reloaded.allowed_google_services),
        )
        assert aegis.passed
        assert any("user-whitelisted" in w for w in aegis.warnings)

    def test_e2e_disable_gmail(self, tmp_path):
        """Enable then disable Gmail → proxy blocks → AEGIS blocks."""
        path = tmp_path / "egress.yaml"

        # Enable Gmail
        config = EgressConfig(allowed_google_services=["gmail.googleapis.com"])
        save_config(config, path)

        loaded = load_config(path)
        assert loaded.is_domain_allowed("gmail.googleapis.com") is not None

        # Disable Gmail
        loaded.allowed_google_services = []
        save_config(loaded, path)

        reloaded = load_config(path)
        assert reloaded.is_domain_allowed("gmail.googleapis.com") is None

        aegis = check_network_access(
            NetworkAccessRequest(hostname="gmail.googleapis.com"),
            user_allowed_services=set(reloaded.allowed_google_services),
        )
        assert not aegis.passed

    def test_e2e_enable_multiple_services(self, tmp_path):
        """Enable Calendar + Docs → both pass, others still blocked."""
        path = tmp_path / "egress.yaml"

        config = EgressConfig(
            allowed_google_services=["calendar.googleapis.com", "docs.googleapis.com"]
        )
        save_config(config, path)
        loaded = load_config(path)

        # Enabled services pass
        assert loaded.is_domain_allowed("calendar.googleapis.com") is not None
        assert loaded.is_domain_allowed("docs.googleapis.com") is not None

        # Non-enabled services still blocked
        assert loaded.is_domain_allowed("gmail.googleapis.com") is None
        assert loaded.is_domain_allowed("drive.googleapis.com") is None

    def test_e2e_google_service_read_only_by_default(self, tmp_path):
        """Enabled Google services are read-only (GET) by default."""
        path = tmp_path / "egress.yaml"

        config = EgressConfig(allowed_google_services=["gmail.googleapis.com"])
        save_config(config, path)
        loaded = load_config(path)

        # GET allowed
        assert loaded.is_domain_allowed("gmail.googleapis.com") is not None
        # POST/write blocked
        assert not loaded.is_write_allowed("gmail.googleapis.com")

    def test_e2e_llm_domains_unaffected(self, tmp_path):
        """LLM domains stay allowed regardless of Google service toggles."""
        path = tmp_path / "egress.yaml"

        config = EgressConfig()  # No Google services enabled
        save_config(config, path)
        loaded = load_config(path)

        # LLM domains always allowed
        assert loaded.is_domain_allowed("api.openai.com") is not None
        assert loaded.is_domain_allowed("api.anthropic.com") is not None
        assert loaded.is_domain_allowed("generativelanguage.googleapis.com") is not None

    def test_e2e_search_plus_google_services(self, tmp_path):
        """Search APIs + Google services coexist correctly."""
        path = tmp_path / "egress.yaml"

        config = EgressConfig(
            allowed_google_services=["calendar.googleapis.com"],
            research_domains=["en.wikipedia.org"],
        )
        save_config(config, path)
        loaded = load_config(path)

        # Search API: allowed + write
        assert loaded.is_domain_allowed("customsearch.googleapis.com") is not None
        assert loaded.is_write_allowed("customsearch.googleapis.com")

        # Google service: allowed + read-only
        assert loaded.is_domain_allowed("calendar.googleapis.com") is not None
        assert not loaded.is_write_allowed("calendar.googleapis.com")

        # Research domain: allowed + read-only
        assert loaded.is_domain_allowed("en.wikipedia.org") is not None
        assert not loaded.is_write_allowed("en.wikipedia.org")

        # Unknown: blocked
        assert loaded.is_domain_allowed("evil.example.com") is None


# ============================================================================
# Security invariants (must always hold)
# ============================================================================


class TestSecurityInvariants:
    """Security properties that must hold across the graduated access flow."""

    def test_invariant_orion_cannot_modify_config(self):
        """Config file lives on host — verified by architecture, not code."""
        # This is verified by Docker volume mount being read-only.
        # We verify the config path is outside the sandbox.
        from orion.security.egress.config import DEFAULT_CONFIG_PATH

        config_str = str(DEFAULT_CONFIG_PATH)
        assert ".orion" in config_str
        # Config is NOT inside /app (container path)
        assert not config_str.startswith("/app")

    def test_invariant_blocked_services_unchanged(self):
        """_BLOCKED_GOOGLE_SERVICES frozenset is immutable."""
        assert isinstance(_BLOCKED_GOOGLE_SERVICES, frozenset)
        assert len(_BLOCKED_GOOGLE_SERVICES) >= 9

    def test_invariant_google_services_match_blocked(self):
        """Every non-path entry in _BLOCKED_GOOGLE_SERVICES has a GOOGLE_SERVICES entry."""
        for domain in _BLOCKED_GOOGLE_SERVICES:
            if "/" in domain:
                continue
            assert domain in GOOGLE_SERVICES

    def test_invariant_search_domains_not_google_blocked(self):
        """Search API domains must not overlap with blocked Google services."""
        overlap = SEARCH_API_DOMAINS & _BLOCKED_GOOGLE_SERVICES
        assert len(overlap) == 0, f"Overlap: {overlap}"

    def test_invariant_default_config_blocks_all_google(self):
        """Default config (no user changes) blocks all Google services."""
        config = EgressConfig()
        for domain in _BLOCKED_GOOGLE_SERVICES:
            if "/" in domain:
                continue
            rule = config.is_domain_allowed(domain)
            assert rule is None, f"{domain} should be blocked by default"

    def test_invariant_aegis_blocks_without_override(self):
        """Without user_allowed_services, AEGIS blocks all Google services."""
        for domain in _BLOCKED_GOOGLE_SERVICES:
            if "/" in domain:
                continue
            result = check_network_access(NetworkAccessRequest(hostname=domain))
            assert not result.passed, f"{domain} should be AEGIS-blocked"

    def test_invariant_allowed_google_in_domain_list(self):
        """Enabled Google services must appear in get_all_allowed_domains."""
        config = EgressConfig(allowed_google_services=["gmail.googleapis.com"])
        all_domains = {r.domain for r in config.get_all_allowed_domains()}
        assert "gmail.googleapis.com" in all_domains

    def test_invariant_domain_count_consistent(self):
        """Total domain count = LLM + search + google_enabled + research + user."""
        from orion.security.egress.config import HARDCODED_LLM_DOMAINS, DomainRule

        config = EgressConfig(
            allowed_google_services=["gmail.googleapis.com"],
            research_domains=["wiki.org"],
            whitelist=[DomainRule(domain="custom.com", added_by="user")],
        )
        all_rules = config.get_all_allowed_domains()

        expected = (
            len(HARDCODED_LLM_DOMAINS)
            + len(SEARCH_API_DOMAINS)
            + 1  # gmail
            + 1  # wiki.org
            + 1  # custom.com
        )
        assert len(all_rules) == expected
