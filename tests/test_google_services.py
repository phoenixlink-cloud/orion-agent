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
"""Tests for Phase 3.2: Per-service AEGIS whitelist (Google Services toggle).

Tests verify:
  1. GOOGLE_SERVICES constant is consistent with _BLOCKED_GOOGLE_SERVICES
  2. EgressConfig persists allowed_google_services
  3. check_network_access() respects user_allowed_services override
  4. Default state: all Google services blocked
  5. Graduated access: user-whitelisted services pass AEGIS
"""

from __future__ import annotations

import pytest

from orion.core.governance.aegis import (
    _BLOCKED_GOOGLE_SERVICES,
    NetworkAccessRequest,
    check_network_access,
)
from orion.security.egress.config import (
    GOOGLE_SERVICES,
    EgressConfig,
    load_config,
    save_config,
)

# ============================================================================
# GOOGLE_SERVICES constant
# ============================================================================


class TestGoogleServicesConstant:
    """Verify the GOOGLE_SERVICES registry."""

    def test_all_blocked_services_in_registry(self):
        """Every domain in _BLOCKED_GOOGLE_SERVICES must be in GOOGLE_SERVICES."""
        for domain in _BLOCKED_GOOGLE_SERVICES:
            # www.googleapis.com/drive is a path-based entry, not a domain
            if "/" in domain:
                continue
            assert domain in GOOGLE_SERVICES, f"{domain} missing from GOOGLE_SERVICES"

    def test_registry_has_required_fields(self):
        for domain, info in GOOGLE_SERVICES.items():
            assert "name" in info, f"{domain} missing 'name'"
            assert "description" in info, f"{domain} missing 'description'"
            assert "risk" in info, f"{domain} missing 'risk'"
            assert info["risk"] in ("low", "medium", "high"), f"{domain} has invalid risk"

    def test_nine_services_registered(self):
        assert len(GOOGLE_SERVICES) == 9


# ============================================================================
# EgressConfig persistence
# ============================================================================


class TestEgressConfigGoogleServices:
    """Verify allowed_google_services field on EgressConfig."""

    def test_default_empty(self):
        config = EgressConfig()
        assert config.allowed_google_services == []

    def test_save_and_load(self, tmp_path):
        config = EgressConfig(
            allowed_google_services=["gmail.googleapis.com", "drive.googleapis.com"]
        )
        path = tmp_path / "egress.yaml"
        save_config(config, path)

        loaded = load_config(path)
        assert set(loaded.allowed_google_services) == {
            "gmail.googleapis.com",
            "drive.googleapis.com",
        }

    def test_invalid_services_filtered_on_load(self, tmp_path):
        """Unknown domains are stripped when loading."""
        config = EgressConfig(allowed_google_services=["gmail.googleapis.com", "evil.example.com"])
        path = tmp_path / "egress.yaml"
        save_config(config, path)

        loaded = load_config(path)
        assert loaded.allowed_google_services == ["gmail.googleapis.com"]

    def test_roundtrip_preserves_order(self, tmp_path):
        services = [
            "calendar.googleapis.com",
            "docs.googleapis.com",
            "gmail.googleapis.com",
        ]
        config = EgressConfig(allowed_google_services=services)
        path = tmp_path / "egress.yaml"
        save_config(config, path)

        loaded = load_config(path)
        assert loaded.allowed_google_services == services


# ============================================================================
# AEGIS check_network_access with user_allowed_services
# ============================================================================


class TestAegisGraduatedAccess:
    """Verify AEGIS Invariant 7 respects user-whitelisted overrides."""

    def test_default_blocks_all_google_services(self):
        """Without user override, all Google services are blocked."""
        for domain in _BLOCKED_GOOGLE_SERVICES:
            if "/" in domain:
                continue
            result = check_network_access(
                NetworkAccessRequest(hostname=domain, method="GET", url=f"https://{domain}/")
            )
            assert not result.passed, f"{domain} should be blocked by default"

    def test_user_allowed_service_passes(self):
        """A user-whitelisted Google service should pass AEGIS."""
        result = check_network_access(
            NetworkAccessRequest(
                hostname="gmail.googleapis.com",
                method="GET",
                url="https://gmail.googleapis.com/v1/users/me",
            ),
            user_allowed_services={"gmail.googleapis.com"},
        )
        assert result.passed, "gmail should pass when user-whitelisted"
        assert any("user-whitelisted" in w for w in result.warnings)

    def test_non_whitelisted_service_still_blocked(self):
        """Whitelisting one service doesn't unblock others."""
        result = check_network_access(
            NetworkAccessRequest(
                hostname="drive.googleapis.com",
                method="GET",
                url="https://drive.googleapis.com/v3/files",
            ),
            user_allowed_services={"gmail.googleapis.com"},
        )
        assert not result.passed, "drive should still be blocked"

    def test_multiple_services_allowed(self):
        """Multiple services can be whitelisted simultaneously."""
        allowed = {"gmail.googleapis.com", "calendar.googleapis.com", "docs.googleapis.com"}
        for domain in allowed:
            result = check_network_access(
                NetworkAccessRequest(hostname=domain, method="GET", url=f"https://{domain}/"),
                user_allowed_services=allowed,
            )
            assert result.passed, f"{domain} should pass when in allowed set"

    def test_empty_allowed_set_blocks_all(self):
        """An empty allowed set is equivalent to no override."""
        result = check_network_access(
            NetworkAccessRequest(hostname="gmail.googleapis.com"),
            user_allowed_services=set(),
        )
        assert not result.passed

    def test_non_google_domain_unaffected(self):
        """Non-Google domains are unaffected by user_allowed_services."""
        result = check_network_access(
            NetworkAccessRequest(
                hostname="api.openai.com",
                method="GET",
                url="https://api.openai.com/v1/models",
            ),
            user_allowed_services={"gmail.googleapis.com"},
        )
        assert result.passed, "OpenAI should always pass"

    def test_write_method_still_warns(self):
        """Even whitelisted services get write-method warnings."""
        result = check_network_access(
            NetworkAccessRequest(
                hostname="gmail.googleapis.com",
                method="POST",
                url="https://gmail.googleapis.com/v1/users/me/messages/send",
            ),
            user_allowed_services={"gmail.googleapis.com"},
        )
        assert result.passed
        assert any("write" in w.lower() for w in result.warnings)

    def test_frozenset_accepted(self):
        """user_allowed_services accepts frozenset."""
        result = check_network_access(
            NetworkAccessRequest(hostname="gmail.googleapis.com"),
            user_allowed_services=frozenset({"gmail.googleapis.com"}),
        )
        assert result.passed


# ============================================================================
# Integration: config → AEGIS check
# ============================================================================


class TestConfigToAegisIntegration:
    """Verify end-to-end flow: config → allowed set → AEGIS check."""

    def test_config_allowed_services_to_aegis(self):
        """allowed_google_services from config should be usable in check_network_access."""
        config = EgressConfig(allowed_google_services=["calendar.googleapis.com"])

        result = check_network_access(
            NetworkAccessRequest(hostname="calendar.googleapis.com"),
            user_allowed_services=set(config.allowed_google_services),
        )
        assert result.passed

    def test_config_empty_blocks_all(self):
        config = EgressConfig()  # default: no allowed services

        result = check_network_access(
            NetworkAccessRequest(hostname="calendar.googleapis.com"),
            user_allowed_services=set(config.allowed_google_services),
        )
        assert not result.passed

    def test_roundtrip_config_to_aegis(self, tmp_path):
        """Save config with allowed services, reload, and verify AEGIS passes."""
        config = EgressConfig(allowed_google_services=["sheets.googleapis.com"])
        path = tmp_path / "egress.yaml"
        save_config(config, path)

        loaded = load_config(path)
        result = check_network_access(
            NetworkAccessRequest(hostname="sheets.googleapis.com"),
            user_allowed_services=set(loaded.allowed_google_services),
        )
        assert result.passed
