# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for egress proxy configuration and domain whitelist."""

import tempfile
from pathlib import Path

import pytest
import yaml

from orion.security.egress.config import (
    DEFAULT_CONFIG_PATH,
    HARDCODED_LLM_DOMAINS,
    DomainRule,
    EgressConfig,
    load_config,
    save_config,
)


class TestDomainRule:
    """Tests for DomainRule matching logic."""

    def test_exact_match(self):
        rule = DomainRule(domain="api.openai.com")
        assert rule.matches("api.openai.com") is True

    def test_exact_match_case_insensitive(self):
        rule = DomainRule(domain="API.OpenAI.COM")
        assert rule.matches("api.openai.com") is True

    def test_subdomain_match(self):
        rule = DomainRule(domain="googleapis.com")
        assert rule.matches("generativelanguage.googleapis.com") is True
        assert rule.matches("storage.googleapis.com") is True

    def test_no_match_different_domain(self):
        rule = DomainRule(domain="openai.com")
        assert rule.matches("evil-openai.com") is False

    def test_no_match_partial_suffix(self):
        rule = DomainRule(domain="ai.com")
        assert rule.matches("openai.com") is False  # Not a subdomain

    def test_match_strips_whitespace(self):
        rule = DomainRule(domain="  api.openai.com  ")
        assert rule.matches("  api.openai.com  ") is True

    def test_default_protocols(self):
        rule = DomainRule(domain="example.com")
        assert rule.protocols == ["https"]

    def test_default_no_write(self):
        rule = DomainRule(domain="example.com")
        assert rule.allow_write is False


class TestEgressConfig:
    """Tests for EgressConfig domain checking."""

    def test_hardcoded_domains_always_allowed(self):
        config = EgressConfig()
        for domain in HARDCODED_LLM_DOMAINS:
            assert config.is_domain_allowed(domain) is not None, f"{domain} should be allowed"

    def test_openai_allowed_by_default(self):
        config = EgressConfig()
        assert config.is_domain_allowed("api.openai.com") is not None

    def test_anthropic_allowed_by_default(self):
        config = EgressConfig()
        assert config.is_domain_allowed("api.anthropic.com") is not None

    def test_google_allowed_by_default(self):
        config = EgressConfig()
        assert config.is_domain_allowed("generativelanguage.googleapis.com") is not None

    def test_unknown_domain_blocked(self):
        config = EgressConfig()
        assert config.is_domain_allowed("evil.example.com") is None

    def test_user_whitelist_domain_allowed(self):
        config = EgressConfig(
            whitelist=[DomainRule(domain="github.com", added_by="user")]
        )
        assert config.is_domain_allowed("github.com") is not None
        assert config.is_domain_allowed("api.github.com") is not None

    def test_user_whitelist_subdomain(self):
        config = EgressConfig(
            whitelist=[DomainRule(domain="google.com", added_by="user")]
        )
        assert config.is_domain_allowed("drive.google.com") is not None

    def test_write_allowed_on_llm_domains(self):
        config = EgressConfig()
        assert config.is_write_allowed("api.openai.com") is True
        assert config.is_write_allowed("api.anthropic.com") is True

    def test_write_blocked_on_readonly_domain(self):
        config = EgressConfig(
            whitelist=[DomainRule(domain="example.com", allow_write=False)]
        )
        assert config.is_write_allowed("example.com") is False

    def test_write_allowed_when_configured(self):
        config = EgressConfig(
            whitelist=[DomainRule(domain="github.com", allow_write=True)]
        )
        assert config.is_write_allowed("github.com") is True

    def test_protocol_allowed_https(self):
        config = EgressConfig()
        assert config.is_protocol_allowed("api.openai.com", "https") is True

    def test_protocol_blocked_http_by_default(self):
        config = EgressConfig(
            whitelist=[DomainRule(domain="example.com", protocols=["https"])]
        )
        assert config.is_protocol_allowed("example.com", "http") is False

    def test_localhost_allows_http(self):
        config = EgressConfig()
        assert config.is_protocol_allowed("localhost", "http") is True

    def test_get_all_allowed_domains_includes_both(self):
        config = EgressConfig(
            whitelist=[DomainRule(domain="github.com")]
        )
        all_domains = config.get_all_allowed_domains()
        domain_names = [r.domain for r in all_domains]
        assert "github.com" in domain_names
        # Hardcoded domains should also be present
        assert "api.openai.com" in domain_names

    def test_default_config_values(self):
        config = EgressConfig()
        assert config.proxy_port == 8888
        assert config.global_rate_limit_rpm == 300
        assert config.content_inspection is True
        assert config.dns_filtering is True
        assert config.enforce is True


class TestConfigPersistence:
    """Tests for loading and saving egress config YAML."""

    def test_load_nonexistent_returns_defaults(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert isinstance(config, EgressConfig)
        assert len(config.whitelist) == 0

    def test_save_and_load_roundtrip(self, tmp_path):
        config = EgressConfig(
            whitelist=[
                DomainRule(domain="github.com", allow_write=True, description="GitHub"),
                DomainRule(domain="example.com", allow_write=False, rate_limit_rpm=30),
            ],
            proxy_port=9999,
            global_rate_limit_rpm=500,
            content_inspection=False,
            enforce=False,
        )
        path = tmp_path / "egress_config.yaml"
        save_config(config, path)

        loaded = load_config(path)
        assert loaded.proxy_port == 9999
        assert loaded.global_rate_limit_rpm == 500
        assert loaded.content_inspection is False
        assert loaded.enforce is False
        assert len(loaded.whitelist) == 2
        assert loaded.whitelist[0].domain == "github.com"
        assert loaded.whitelist[0].allow_write is True
        assert loaded.whitelist[1].domain == "example.com"
        assert loaded.whitelist[1].allow_write is False

    def test_load_simple_domain_list(self, tmp_path):
        path = tmp_path / "egress_config.yaml"
        path.write_text(yaml.dump({
            "whitelist": ["github.com", "pypi.org", "npmjs.com"]
        }))
        config = load_config(path)
        assert len(config.whitelist) == 3
        assert config.whitelist[0].domain == "github.com"
        assert config.whitelist[0].added_by == "user"

    def test_load_invalid_yaml_returns_defaults(self, tmp_path):
        path = tmp_path / "egress_config.yaml"
        path.write_text("not: valid: yaml: [[[")
        config = load_config(path)
        assert isinstance(config, EgressConfig)

    def test_load_non_dict_returns_defaults(self, tmp_path):
        path = tmp_path / "egress_config.yaml"
        path.write_text(yaml.dump(["just", "a", "list"]))
        config = load_config(path)
        assert isinstance(config, EgressConfig)

    def test_saved_file_is_valid_yaml(self, tmp_path):
        config = EgressConfig(
            whitelist=[DomainRule(domain="test.com")]
        )
        path = tmp_path / "egress_config.yaml"
        save_config(config, path)

        raw = yaml.safe_load(path.read_text())
        assert isinstance(raw, dict)
        assert "whitelist" in raw
        assert "proxy" in raw

    def test_empty_domain_entries_filtered(self, tmp_path):
        path = tmp_path / "egress_config.yaml"
        path.write_text(yaml.dump({
            "whitelist": [
                {"domain": "github.com"},
                {"domain": ""},
                {"domain": "  "},
            ]
        }))
        config = load_config(path)
        assert len(config.whitelist) == 1


class TestHardcodedDomains:
    """Tests for the hardcoded LLM domain list."""

    def test_all_major_llm_providers_present(self):
        domains = HARDCODED_LLM_DOMAINS
        # Google
        assert "generativelanguage.googleapis.com" in domains
        # Anthropic
        assert "api.anthropic.com" in domains
        # OpenAI
        assert "api.openai.com" in domains
        # Local
        assert "localhost" in domains
        assert "127.0.0.1" in domains

    def test_hardcoded_domains_are_frozenset(self):
        assert isinstance(HARDCODED_LLM_DOMAINS, frozenset)

    def test_cannot_modify_hardcoded_domains(self):
        with pytest.raises(AttributeError):
            HARDCODED_LLM_DOMAINS.add("evil.com")
