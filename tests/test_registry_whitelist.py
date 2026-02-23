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
"""Tests for registry whitelist (Phase 4B.2).

Tests RW-01 through RW-08 validating registry domain whitelisting
per stack, user extras, and hostname validation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orion.security.registry_whitelist import (
    COMMON_REGISTRY_DOMAINS,
    REGISTRY_DOMAINS,
    get_all_registry_domains,
    get_install_phase_domains,
    get_registry_domains,
    get_registry_rules,
    load_extra_registries,
    _is_valid_hostname,
)


# ---------------------------------------------------------------------------
# RW-01: Per-stack registry domains
# ---------------------------------------------------------------------------


class TestPerStackRegistries:
    """RW-01: Each stack returns correct registries + common domains."""

    def test_python_registries(self):
        domains = get_registry_domains("python")
        assert "pypi.org" in domains
        assert "files.pythonhosted.org" in domains
        # Common domains included
        assert "github.com" in domains

    def test_node_registries(self):
        domains = get_registry_domains("node")
        assert "registry.npmjs.org" in domains
        assert "registry.yarnpkg.com" in domains
        assert "github.com" in domains

    def test_go_registries(self):
        domains = get_registry_domains("go")
        assert "proxy.golang.org" in domains
        assert "sum.golang.org" in domains

    def test_rust_registries(self):
        domains = get_registry_domains("rust")
        assert "crates.io" in domains
        assert "static.crates.io" in domains

    def test_base_only_common(self):
        domains = get_registry_domains("base")
        assert set(domains) == set(COMMON_REGISTRY_DOMAINS)

    def test_unknown_stack_only_common(self):
        domains = get_registry_domains("nonexistent")
        assert set(domains) == set(COMMON_REGISTRY_DOMAINS)

    def test_domains_are_sorted(self):
        domains = get_registry_domains("python")
        assert domains == sorted(domains)

    def test_no_duplicates(self):
        domains = get_registry_domains("python")
        assert len(domains) == len(set(domains))


# ---------------------------------------------------------------------------
# RW-02: Registry rules
# ---------------------------------------------------------------------------


class TestRegistryRules:
    """RW-02: get_registry_rules returns proper RegistryRule objects."""

    def test_python_rules(self):
        rules = get_registry_rules("python")
        domains = [r.domain for r in rules]
        assert "pypi.org" in domains
        assert "github.com" in domains

    def test_rule_stack_labels(self):
        rules = get_registry_rules("node")
        node_rules = [r for r in rules if r.stack == "node"]
        common_rules = [r for r in rules if r.stack == "common"]
        assert len(node_rules) >= 2
        assert len(common_rules) >= 2


# ---------------------------------------------------------------------------
# RW-03: All registry domains
# ---------------------------------------------------------------------------


class TestAllRegistryDomains:
    """RW-03: get_all_registry_domains returns union of all stacks."""

    def test_includes_all_stacks(self):
        all_domains = get_all_registry_domains()
        assert "pypi.org" in all_domains
        assert "registry.npmjs.org" in all_domains
        assert "proxy.golang.org" in all_domains
        assert "crates.io" in all_domains
        assert "github.com" in all_domains

    def test_sorted_and_unique(self):
        all_domains = get_all_registry_domains()
        assert all_domains == sorted(all_domains)
        assert len(all_domains) == len(set(all_domains))


# ---------------------------------------------------------------------------
# RW-04: User extra registries
# ---------------------------------------------------------------------------


class TestExtraRegistries:
    """RW-04: load_extra_registries reads from ARA settings."""

    def test_no_settings_file(self, tmp_path: Path):
        result = load_extra_registries(tmp_path / "nope.json")
        assert result == []

    def test_valid_extras(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps(
                {
                    "execution": {
                        "extra_registries": [
                            "my-registry.example.com",
                            "internal.corp.dev",
                        ]
                    }
                }
            )
        )
        result = load_extra_registries(settings)
        assert "my-registry.example.com" in result
        assert "internal.corp.dev" in result

    def test_invalid_entries_filtered(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps(
                {
                    "execution": {
                        "extra_registries": [
                            "valid.example.com",
                            "",  # Empty
                            "nodot",  # No TLD
                            "has space.com",  # Space
                            42,  # Not a string
                            None,
                        ]
                    }
                }
            )
        )
        result = load_extra_registries(settings)
        assert result == ["valid.example.com"]

    def test_corrupt_json(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text("NOT JSON {{{")
        result = load_extra_registries(settings)
        assert result == []

    def test_missing_execution_key(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(json.dumps({"other": True}))
        result = load_extra_registries(settings)
        assert result == []


# ---------------------------------------------------------------------------
# RW-05: Install-phase domains (combined)
# ---------------------------------------------------------------------------


class TestInstallPhaseDomains:
    """RW-05: get_install_phase_domains combines all sources."""

    def test_python_with_extras(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps({"execution": {"extra_registries": ["private.pypi.example.com"]}})
        )
        domains = get_install_phase_domains("python", settings)
        assert "pypi.org" in domains
        assert "github.com" in domains
        assert "private.pypi.example.com" in domains

    def test_no_settings_file(self, tmp_path: Path):
        domains = get_install_phase_domains("node", tmp_path / "nope.json")
        assert "registry.npmjs.org" in domains
        assert "github.com" in domains

    def test_sorted_and_unique(self, tmp_path: Path):
        domains = get_install_phase_domains("python", tmp_path / "nope.json")
        assert domains == sorted(domains)
        assert len(domains) == len(set(domains))


# ---------------------------------------------------------------------------
# RW-06: Hostname validation
# ---------------------------------------------------------------------------


class TestHostnameValidation:
    """RW-06: _is_valid_hostname correctly validates."""

    @pytest.mark.parametrize(
        "hostname",
        [
            "pypi.org",
            "registry.npmjs.org",
            "my-reg.example.com",
            "a.b.c.d.e.f.org",
        ],
    )
    def test_valid(self, hostname):
        assert _is_valid_hostname(hostname) is True

    @pytest.mark.parametrize(
        "hostname",
        [
            "",
            "nodot",
            "has space.com",
            "has@special.com",
            "a" * 254 + ".com",
        ],
    )
    def test_invalid(self, hostname):
        assert _is_valid_hostname(hostname) is False


# ---------------------------------------------------------------------------
# RW-07: Python registries don't include Node domains
# ---------------------------------------------------------------------------


class TestStackIsolation:
    """RW-07: Stack registries don't leak across stacks."""

    def test_python_no_node(self):
        domains = get_registry_domains("python")
        assert "registry.npmjs.org" not in domains

    def test_node_no_python(self):
        domains = get_registry_domains("node")
        assert "pypi.org" not in domains

    def test_go_no_rust(self):
        domains = get_registry_domains("go")
        assert "crates.io" not in domains

    def test_rust_no_go(self):
        domains = get_registry_domains("rust")
        assert "proxy.golang.org" not in domains
