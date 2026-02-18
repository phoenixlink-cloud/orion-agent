# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for AEGIS Invariant 7: Network Access Control."""

import pytest

from orion.core.governance.aegis import (
    NetworkAccessRequest,
    _BLOCKED_GOOGLE_SERVICES,
    check_network_access,
)


class TestBlockedGoogleServices:
    """Tests for Google service blocking (LLM-only enforcement)."""

    def test_drive_blocked(self):
        req = NetworkAccessRequest(hostname="drive.googleapis.com")
        result = check_network_access(req)
        assert result.passed is False
        assert any("AEGIS-7" in v for v in result.violations)

    def test_gmail_blocked(self):
        req = NetworkAccessRequest(hostname="gmail.googleapis.com")
        result = check_network_access(req)
        assert result.passed is False

    def test_calendar_blocked(self):
        req = NetworkAccessRequest(hostname="calendar.googleapis.com")
        result = check_network_access(req)
        assert result.passed is False

    def test_youtube_blocked(self):
        req = NetworkAccessRequest(hostname="youtube.googleapis.com")
        result = check_network_access(req)
        assert result.passed is False

    def test_photos_blocked(self):
        req = NetworkAccessRequest(hostname="photoslibrary.googleapis.com")
        result = check_network_access(req)
        assert result.passed is False

    def test_docs_blocked(self):
        req = NetworkAccessRequest(hostname="docs.googleapis.com")
        result = check_network_access(req)
        assert result.passed is False

    def test_sheets_blocked(self):
        req = NetworkAccessRequest(hostname="sheets.googleapis.com")
        result = check_network_access(req)
        assert result.passed is False

    def test_all_blocked_services_actually_block(self):
        for domain in _BLOCKED_GOOGLE_SERVICES:
            if "/" in domain:
                continue  # Skip path-based entries
            req = NetworkAccessRequest(hostname=domain)
            result = check_network_access(req)
            assert result.passed is False, f"{domain} should be blocked"

    def test_blocked_services_are_frozenset(self):
        assert isinstance(_BLOCKED_GOOGLE_SERVICES, frozenset)


class TestAllowedDomains:
    """Tests for domains that should be allowed through AEGIS."""

    def test_gemini_api_allowed(self):
        req = NetworkAccessRequest(hostname="generativelanguage.googleapis.com")
        result = check_network_access(req)
        assert result.passed is True

    def test_openai_allowed(self):
        req = NetworkAccessRequest(hostname="api.openai.com")
        result = check_network_access(req)
        assert result.passed is True

    def test_anthropic_allowed(self):
        req = NetworkAccessRequest(hostname="api.anthropic.com")
        result = check_network_access(req)
        assert result.passed is True

    def test_google_oauth_allowed(self):
        req = NetworkAccessRequest(hostname="accounts.google.com")
        result = check_network_access(req)
        assert result.passed is True

    def test_localhost_allowed(self):
        req = NetworkAccessRequest(hostname="localhost", protocol="http")
        result = check_network_access(req)
        assert result.passed is True
        # No protocol warning for localhost
        assert not any("Non-HTTPS" in w for w in result.warnings)


class TestProtocolWarnings:
    """Tests for protocol restriction warnings."""

    def test_https_no_warning(self):
        req = NetworkAccessRequest(hostname="api.openai.com", protocol="https")
        result = check_network_access(req)
        assert not any("Non-HTTPS" in w for w in result.warnings)

    def test_http_external_warns(self):
        req = NetworkAccessRequest(hostname="example.com", protocol="http")
        result = check_network_access(req)
        assert any("Non-HTTPS" in w for w in result.warnings)

    def test_http_localhost_no_warning(self):
        req = NetworkAccessRequest(hostname="localhost", protocol="http")
        result = check_network_access(req)
        assert not any("Non-HTTPS" in w for w in result.warnings)

    def test_http_127_no_warning(self):
        req = NetworkAccessRequest(hostname="127.0.0.1", protocol="http")
        result = check_network_access(req)
        assert not any("Non-HTTPS" in w for w in result.warnings)

    def test_wss_no_warning(self):
        req = NetworkAccessRequest(hostname="example.com", protocol="wss")
        result = check_network_access(req)
        assert not any("Non-HTTPS" in w for w in result.warnings)


class TestWriteMethodWarnings:
    """Tests for write method awareness warnings."""

    def test_get_no_warning(self):
        req = NetworkAccessRequest(hostname="example.com", method="GET")
        result = check_network_access(req)
        assert not any("Write operation" in w for w in result.warnings)

    def test_head_no_warning(self):
        req = NetworkAccessRequest(hostname="example.com", method="HEAD")
        result = check_network_access(req)
        assert not any("Write operation" in w for w in result.warnings)

    def test_post_warns(self):
        req = NetworkAccessRequest(hostname="api.openai.com", method="POST")
        result = check_network_access(req)
        assert any("Write operation" in w for w in result.warnings)
        assert result.passed is True  # Warning, not violation

    def test_put_warns(self):
        req = NetworkAccessRequest(hostname="example.com", method="PUT")
        result = check_network_access(req)
        assert any("Write operation" in w for w in result.warnings)

    def test_delete_warns(self):
        req = NetworkAccessRequest(hostname="example.com", method="DELETE")
        result = check_network_access(req)
        assert any("Write operation" in w for w in result.warnings)

    def test_patch_warns(self):
        req = NetworkAccessRequest(hostname="example.com", method="PATCH")
        result = check_network_access(req)
        assert any("Write operation" in w for w in result.warnings)


class TestNetworkAccessRequest:
    """Tests for the NetworkAccessRequest dataclass."""

    def test_default_values(self):
        req = NetworkAccessRequest(hostname="example.com")
        assert req.port == 443
        assert req.method == "GET"
        assert req.protocol == "https"

    def test_custom_values(self):
        req = NetworkAccessRequest(
            hostname="api.openai.com",
            port=8080,
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            protocol="https",
            description="Chat completion request",
        )
        assert req.hostname == "api.openai.com"
        assert req.port == 8080
        assert req.description == "Chat completion request"


class TestResultActionType:
    """Tests that network access results use the correct action type."""

    def test_allowed_action_type(self):
        req = NetworkAccessRequest(hostname="api.openai.com")
        result = check_network_access(req)
        assert result.action_type == "network_access"

    def test_blocked_action_type(self):
        req = NetworkAccessRequest(hostname="drive.googleapis.com")
        result = check_network_access(req)
        assert result.action_type == "network_access"

    def test_blocked_no_approval_needed(self):
        req = NetworkAccessRequest(hostname="drive.googleapis.com")
        result = check_network_access(req)
        assert result.requires_approval is False  # Hard block, not approval
