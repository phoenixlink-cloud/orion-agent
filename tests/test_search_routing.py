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
"""Tests for Phase 3.3: LLM web search routing through egress proxy.

Tests verify:
  1. Search API domains are auto-allowed (SEARCH_API_DOMAINS constant)
  2. Research domains get GET-only access
  3. Research domains block write methods
  4. Config persistence for research_domains
  5. Search + research domains appear in get_all_allowed_domains()
"""

from __future__ import annotations

from orion.security.egress.config import (
    SEARCH_API_DOMAINS,
    EgressConfig,
    load_config,
    save_config,
)

# ============================================================================
# SEARCH_API_DOMAINS constant
# ============================================================================


class TestSearchApiDomains:
    """Verify the search API domains constant."""

    def test_google_custom_search_included(self):
        assert "customsearch.googleapis.com" in SEARCH_API_DOMAINS

    def test_bing_search_included(self):
        assert "api.bing.microsoft.com" in SEARCH_API_DOMAINS

    def test_brave_search_included(self):
        assert "api.search.brave.com" in SEARCH_API_DOMAINS

    def test_serpapi_included(self):
        assert "serpapi.com" in SEARCH_API_DOMAINS

    def test_five_search_domains(self):
        assert len(SEARCH_API_DOMAINS) == 5

    def test_search_domains_in_allowed_list(self):
        """Search API domains must appear in get_all_allowed_domains."""
        config = EgressConfig()
        all_domains = {r.domain for r in config.get_all_allowed_domains()}
        for domain in SEARCH_API_DOMAINS:
            assert domain in all_domains, f"{domain} missing from allowed domains"

    def test_search_domains_allow_write(self):
        """Search APIs use POST for queries — write must be allowed."""
        config = EgressConfig()
        for domain in SEARCH_API_DOMAINS:
            assert config.is_write_allowed(domain), f"{domain} should allow write"


# ============================================================================
# Research domains
# ============================================================================


class TestResearchDomains:
    """Verify research domain GET-only access."""

    def test_default_no_research_domains(self):
        config = EgressConfig()
        assert config.research_domains == []

    def test_research_domain_allowed(self):
        config = EgressConfig(research_domains=["en.wikipedia.org"])
        rule = config.is_domain_allowed("en.wikipedia.org")
        assert rule is not None
        assert rule.domain == "en.wikipedia.org"

    def test_research_domain_read_only(self):
        """Research domains must be GET-only (no write)."""
        config = EgressConfig(research_domains=["en.wikipedia.org", "docs.python.org"])
        assert not config.is_write_allowed("en.wikipedia.org")
        assert not config.is_write_allowed("docs.python.org")

    def test_research_domain_not_in_regular_whitelist(self):
        """Research domains are separate from the user whitelist."""
        config = EgressConfig(research_domains=["example.com"])
        assert len(config.whitelist) == 0
        assert config.is_domain_allowed("example.com") is not None

    def test_unknown_domain_still_blocked(self):
        """Domains not in any list are still blocked."""
        config = EgressConfig(research_domains=["en.wikipedia.org"])
        assert config.is_domain_allowed("evil.example.com") is None

    def test_multiple_research_domains(self):
        domains = [
            "en.wikipedia.org",
            "docs.python.org",
            "developer.mozilla.org",
            "stackoverflow.com",
        ]
        config = EgressConfig(research_domains=domains)
        for d in domains:
            assert config.is_domain_allowed(d) is not None, f"{d} should be allowed"
            assert not config.is_write_allowed(d), f"{d} should be read-only"


# ============================================================================
# Config persistence
# ============================================================================


class TestResearchDomainPersistence:
    """Verify research_domains save/load round-trip."""

    def test_save_and_load(self, tmp_path):
        domains = ["en.wikipedia.org", "docs.python.org"]
        config = EgressConfig(research_domains=domains)
        path = tmp_path / "egress.yaml"
        save_config(config, path)

        loaded = load_config(path)
        assert loaded.research_domains == domains

    def test_empty_default(self, tmp_path):
        config = EgressConfig()
        path = tmp_path / "egress.yaml"
        save_config(config, path)

        loaded = load_config(path)
        assert loaded.research_domains == []

    def test_invalid_entries_filtered(self, tmp_path):
        """Non-string entries should be stripped on load."""
        import yaml

        path = tmp_path / "egress.yaml"
        data = {"research_domains": ["valid.com", 123, None, "", "also-valid.com"]}
        path.write_text(yaml.dump(data))

        loaded = load_config(path)
        assert loaded.research_domains == ["valid.com", "also-valid.com"]


# ============================================================================
# Integration: search + research in domain list
# ============================================================================


class TestSearchRoutingIntegration:
    """Verify search and research domains work together."""

    def test_search_api_plus_research_plus_llm(self):
        """All three categories should coexist in allowed domains."""
        config = EgressConfig(research_domains=["en.wikipedia.org"])
        all_domains = {r.domain for r in config.get_all_allowed_domains()}

        # LLM domains
        assert "api.openai.com" in all_domains
        assert "api.anthropic.com" in all_domains

        # Search API domains
        assert "customsearch.googleapis.com" in all_domains
        assert "api.bing.microsoft.com" in all_domains

        # Research domains
        assert "en.wikipedia.org" in all_domains

    def test_domain_count_includes_all_categories(self):
        config = EgressConfig(research_domains=["a.com", "b.com"])
        all_rules = config.get_all_allowed_domains()

        system_count = sum(1 for r in all_rules if r.added_by == "system")
        user_count = sum(1 for r in all_rules if r.added_by == "user")

        # System = LLM hardcoded + search API
        from orion.security.egress.config import HARDCODED_LLM_DOMAINS

        assert system_count == len(HARDCODED_LLM_DOMAINS) + len(SEARCH_API_DOMAINS)
        assert user_count == 2  # research domains

    def test_search_flow_simulation(self):
        """Simulate: LLM calls search API → fetches result page → blocks unknown."""
        config = EgressConfig(research_domains=["en.wikipedia.org"])

        # Step 1: LLM calls search API (POST allowed)
        assert config.is_domain_allowed("customsearch.googleapis.com") is not None
        assert config.is_write_allowed("customsearch.googleapis.com")

        # Step 2: LLM fetches result from research domain (GET only)
        assert config.is_domain_allowed("en.wikipedia.org") is not None
        assert not config.is_write_allowed("en.wikipedia.org")

        # Step 3: Unknown domain in results — blocked
        assert config.is_domain_allowed("malicious-site.example.com") is None
