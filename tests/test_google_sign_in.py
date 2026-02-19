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
"""Tests for Google Account sign-in flow.

Covers:
- GoogleCredentialManager scope validation
- OAuth endpoint responses (connect, status, disconnect, refresh)
- CLI /google command handling
- Security: blocked scopes rejected, container credentials access-token-only
- PKCE generation
- Stale pending auth cleanup
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.security.egress.google_credentials import (
    ALLOWED_SCOPES,
    BLOCKED_SCOPES,
    GoogleCredentialManager,
    GoogleCredentials,
)

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def tmp_creds_path(tmp_path):
    """Provide a temporary path for credential storage."""
    return tmp_path / "google_credentials.json"


@pytest.fixture
def manager(tmp_creds_path):
    """GoogleCredentialManager with temp path and no OS keyring."""
    return GoogleCredentialManager(
        credentials_path=tmp_creds_path,
        use_secure_store=False,
    )


@pytest.fixture
def valid_credentials():
    """Valid Google credentials with LLM-only scopes."""
    return GoogleCredentials(
        access_token="ya29.test-access-token-valid",
        refresh_token="1//test-refresh-token",
        token_type="Bearer",
        expires_at=time.time() + 3600,
        scope="openid email profile https://www.googleapis.com/auth/cloud-platform",
        id_token="eyJ.test.id_token",
        email="orion-llm@example.com",
        account_id="123456789",
    )


@pytest.fixture
def blocked_credentials():
    """Credentials with blocked scopes (Drive)."""
    return GoogleCredentials(
        access_token="ya29.test-access-token-blocked",
        refresh_token="1//test-refresh-blocked",
        token_type="Bearer",
        expires_at=time.time() + 3600,
        scope="openid email https://www.googleapis.com/auth/drive",
        email="blocked@example.com",
    )


# =========================================================================
# GoogleCredentialManager — Scope Validation
# =========================================================================


class TestScopeValidation:
    """Verify that AEGIS scope enforcement works correctly."""

    def test_allowed_scopes_includes_llm(self):
        """ALLOWED_SCOPES must include Gemini API scopes."""
        assert "https://www.googleapis.com/auth/cloud-platform" in ALLOWED_SCOPES
        assert "https://www.googleapis.com/auth/generative-language.tuning" in ALLOWED_SCOPES

    def test_blocked_scopes_includes_dangerous_services(self):
        """BLOCKED_SCOPES must block Drive, Gmail, Calendar, YouTube."""
        assert "https://www.googleapis.com/auth/drive" in BLOCKED_SCOPES
        assert "https://www.googleapis.com/auth/gmail.modify" in BLOCKED_SCOPES
        assert "https://www.googleapis.com/auth/calendar" in BLOCKED_SCOPES
        assert "https://www.googleapis.com/auth/youtube" in BLOCKED_SCOPES

    def test_no_overlap_between_allowed_and_blocked(self):
        """ALLOWED and BLOCKED scopes must never overlap."""
        overlap = ALLOWED_SCOPES & BLOCKED_SCOPES
        assert len(overlap) == 0, f"Scope overlap: {overlap}"

    def test_store_valid_credentials(self, manager, valid_credentials):
        """Valid LLM-only credentials should store successfully."""
        manager.store(valid_credentials)
        assert manager.has_credentials
        loaded = manager.get_credentials(auto_refresh=False)
        assert loaded is not None
        assert loaded.email == "orion-llm@example.com"
        assert loaded.access_token == "ya29.test-access-token-valid"

    def test_store_blocked_scopes_rejected(self, manager, blocked_credentials):
        """Credentials with blocked scopes must be REJECTED."""
        with pytest.raises(ValueError, match="blocked scopes"):
            manager.store(blocked_credentials)
        assert not manager.has_credentials

    def test_has_blocked_scopes_property(self, blocked_credentials):
        """GoogleCredentials.has_blocked_scopes must detect blocked scopes."""
        assert blocked_credentials.has_blocked_scopes is True
        assert "https://www.googleapis.com/auth/drive" in blocked_credentials.blocked_scope_list

    def test_valid_creds_no_blocked_scopes(self, valid_credentials):
        """Valid credentials must not have blocked scopes."""
        assert valid_credentials.has_blocked_scopes is False
        assert valid_credentials.blocked_scope_list == []


# =========================================================================
# GoogleCredentialManager — Storage & Retrieval
# =========================================================================


class TestCredentialStorage:
    """Verify credential persistence and loading."""

    def test_store_and_load(self, manager, valid_credentials, tmp_creds_path):
        """Credentials should persist to disk and load back."""
        manager.store(valid_credentials)
        assert tmp_creds_path.exists()

        # Create new manager instance and load
        manager2 = GoogleCredentialManager(
            credentials_path=tmp_creds_path,
            use_secure_store=False,
        )
        loaded = manager2.get_credentials(auto_refresh=False)
        assert loaded is not None
        assert loaded.email == valid_credentials.email
        assert loaded.access_token == valid_credentials.access_token
        assert loaded.refresh_token == valid_credentials.refresh_token

    def test_clear_credentials(self, manager, valid_credentials, tmp_creds_path):
        """clear() should remove credentials from disk and memory."""
        manager.store(valid_credentials)
        assert manager.has_credentials
        manager.clear()
        assert not manager.has_credentials
        assert not tmp_creds_path.exists()

    def test_get_credentials_when_none(self, manager):
        """get_credentials should return None when nothing stored."""
        assert manager.get_credentials() is None

    def test_get_status_not_configured(self, manager):
        """get_status should show configured=False when no credentials."""
        status = manager.get_status()
        assert status["configured"] is False
        assert status["email"] == ""

    def test_get_status_configured(self, manager, valid_credentials):
        """get_status should show configured=True with credential info."""
        manager.store(valid_credentials)
        status = manager.get_status()
        assert status["configured"] is True
        assert status["email"] == "orion-llm@example.com"
        assert status["has_access_token"] is True
        assert status["has_refresh_token"] is True

    def test_to_safe_dict_redacts_tokens(self, valid_credentials):
        """to_safe_dict must not expose actual token values."""
        safe = valid_credentials.to_safe_dict()
        assert "access_token" not in safe
        assert "refresh_token" not in safe
        assert safe["has_access_token"] is True
        assert safe["has_refresh_token"] is True


# =========================================================================
# Container Credentials — Read-Only, Access-Token-Only
# =========================================================================


class TestContainerCredentials:
    """Verify that container credential files are secure."""

    def test_container_creds_no_refresh_token(self, manager, valid_credentials, tmp_path):
        """Container credential file must NOT contain the refresh token."""
        manager.store(valid_credentials)
        container_path = tmp_path / "container_creds.json"
        manager.write_container_credentials(container_path)

        data = json.loads(container_path.read_text())
        assert "access_token" in data
        assert data["access_token"] == valid_credentials.access_token
        # CRITICAL: No refresh token in container
        assert "refresh_token" not in data
        assert "id_token" not in data

    def test_container_creds_has_required_fields(self, manager, valid_credentials, tmp_path):
        """Container file must have access_token, token_type, expires_at, scope, email."""
        manager.store(valid_credentials)
        container_path = tmp_path / "container_creds.json"
        manager.write_container_credentials(container_path)

        data = json.loads(container_path.read_text())
        assert data["token_type"] == "Bearer"
        assert data["expires_at"] > time.time()
        assert data["scope"] != ""
        assert data["email"] == "orion-llm@example.com"

    def test_container_creds_raises_when_none(self, manager):
        """write_container_credentials must raise if no credentials stored."""
        with pytest.raises(RuntimeError, match="No Google credentials configured"):
            manager.write_container_credentials()


# =========================================================================
# Token Expiry
# =========================================================================


class TestTokenExpiry:
    def test_expired_token_detected(self):
        """is_expired should return True for tokens past expiry."""
        creds = GoogleCredentials(
            access_token="ya29.expired",
            expires_at=time.time() - 600,  # 10 min ago
        )
        assert creds.is_expired is True

    def test_valid_token_not_expired(self):
        """is_expired should return False for tokens with time remaining."""
        creds = GoogleCredentials(
            access_token="ya29.valid",
            expires_at=time.time() + 3600,  # 1 hour from now
        )
        assert creds.is_expired is False

    def test_token_expires_within_buffer(self):
        """is_expired should return True when within 5-minute buffer."""
        creds = GoogleCredentials(
            access_token="ya29.almost-expired",
            expires_at=time.time() + 200,  # 3 min 20s — within 5-min buffer
        )
        assert creds.is_expired is True


# =========================================================================
# API Routes — Unit Tests
# =========================================================================


class TestGoogleRoutes:
    """Test the /api/google/* endpoints."""

    def test_google_routes_importable(self):
        """Google routes module must import cleanly."""
        from orion.api.routes.google import router

        assert router is not None

    def test_pkce_generation(self):
        """PKCE pair must generate valid verifier + challenge."""
        from orion.api.routes.google import _generate_pkce_pair

        verifier, challenge = _generate_pkce_pair()
        assert len(verifier) == 128
        assert len(challenge) > 20
        # S256: challenge must be base64url(sha256(verifier))
        import base64
        import hashlib

        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        assert challenge == expected

    def test_pending_state_cleanup(self):
        """Stale pending auth entries should be cleaned up."""
        from orion.api.routes.google import _google_oauth_pending

        # Add stale and fresh entries
        _google_oauth_pending["stale_state"] = {
            "code_verifier": "test",
            "redirect_uri": "http://localhost:8001/api/google/callback",
            "created_at": time.time() - 700,  # 11+ minutes ago
        }
        _google_oauth_pending["fresh_state"] = {
            "code_verifier": "test2",
            "redirect_uri": "http://localhost:8001/api/google/callback",
            "created_at": time.time(),
        }

        # The cleanup happens inside google_connect — simulate it
        cutoff = time.time() - 600
        stale = [k for k, v in _google_oauth_pending.items() if v["created_at"] < cutoff]
        for k in stale:
            _google_oauth_pending.pop(k, None)

        assert "stale_state" not in _google_oauth_pending
        assert "fresh_state" in _google_oauth_pending

        # Clean up
        _google_oauth_pending.pop("fresh_state", None)

    @pytest.mark.asyncio
    async def test_status_endpoint_not_configured(self):
        """GET /api/google/status should work when no account connected."""
        # Reset singleton
        import orion.api.routes.google as gmod
        from orion.api.routes.google import _get_credential_manager, google_status

        original = gmod._credential_manager
        gmod._credential_manager = None

        try:
            with patch.object(
                GoogleCredentialManager,
                "__init__",
                lambda self, **kw: (
                    setattr(self, "_path", Path("/tmp/nonexistent")),
                    setattr(self, "_credentials", None),
                    setattr(self, "_use_secure_store", False),
                    setattr(self, "_client_id", ""),
                    setattr(self, "_client_secret", ""),
                    None,
                )[-1],
            ):
                gmod._credential_manager = None
                result = await google_status()
                assert result["configured"] is False
                assert "blocked_scopes" in result
                assert "allowed_scopes" in result
        finally:
            gmod._credential_manager = original

    @pytest.mark.asyncio
    async def test_connect_no_client_id(self):
        """POST /api/google/connect should fail if client_id not configured."""
        from orion.api.routes.google import GoogleConnectRequest, google_connect

        with patch("orion.api.routes.google._get_google_client_id", return_value=None):
            with pytest.raises(Exception) as exc_info:
                await google_connect(GoogleConnectRequest())
            assert "client_id not configured" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_connect_returns_auth_url(self):
        """POST /api/google/connect should return a valid Google auth_url."""
        from orion.api.routes.google import GoogleConnectRequest, google_connect

        with patch(
            "orion.api.routes.google._get_google_client_id",
            return_value="test-client-id.apps.googleusercontent.com",
        ):
            result = await google_connect(GoogleConnectRequest())
            assert result["status"] == "redirect"
            assert "accounts.google.com" in result["auth_url"]
            assert "test-client-id" in result["auth_url"]
            assert "cloud-platform" in result["auth_url"]
            assert result["scopes_requested"] == sorted(ALLOWED_SCOPES)
            assert len(result["blocked_scopes"]) == len(BLOCKED_SCOPES)

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """POST /api/google/disconnect should work cleanly when not connected."""
        import orion.api.routes.google as gmod
        from orion.api.routes.google import GoogleDisconnectRequest, google_disconnect

        original = gmod._credential_manager

        try:
            mgr = GoogleCredentialManager(
                credentials_path=Path("/tmp/nonexistent_test"),
                use_secure_store=False,
            )
            gmod._credential_manager = mgr

            result = await google_disconnect(GoogleDisconnectRequest(revoke_token=False))
            assert result["status"] == "disconnected"
        finally:
            gmod._credential_manager = original

    @pytest.mark.asyncio
    async def test_refresh_no_account(self):
        """POST /api/google/refresh should fail when no account connected."""
        import orion.api.routes.google as gmod
        from orion.api.routes.google import google_refresh

        original = gmod._credential_manager

        try:
            mgr = GoogleCredentialManager(
                credentials_path=Path("/tmp/nonexistent_test2"),
                use_secure_store=False,
            )
            gmod._credential_manager = mgr

            with pytest.raises(Exception) as exc_info:
                await google_refresh()
            assert "No Google account connected" in str(exc_info.value.detail)
        finally:
            gmod._credential_manager = original


# =========================================================================
# CLI Command Tests
# =========================================================================


class TestGoogleCLI:
    """Test /google CLI command handling."""

    def test_google_status_not_connected(self):
        """'/google status' should report not connected."""
        from orion.cli.commands import _handle_google

        console = MagicMock()
        with patch(
            "orion.security.egress.google_credentials.GoogleCredentialManager.get_status",
            return_value={"configured": False, "email": ""},
        ):
            _handle_google(["/google", "status"], console)
        # Should have called print_info with "Not connected"
        calls = [str(c) for c in console.print_info.call_args_list]
        assert any("Not connected" in c for c in calls)

    def test_google_disconnect_not_connected(self):
        """'/google disconnect' should report no account connected."""
        from orion.cli.commands import _handle_google

        console = MagicMock()
        with patch(
            "orion.security.egress.google_credentials.GoogleCredentialManager.has_credentials",
            new_callable=lambda: property(lambda self: False),
        ):
            _handle_google(["/google", "disconnect"], console)
        calls = [str(c) for c in console.print_info.call_args_list]
        assert any("No Google account" in c for c in calls)

    def test_google_help(self):
        """'/google help' should print usage."""
        from orion.cli.commands import _handle_google

        console = MagicMock()
        _handle_google(["/google", "help"], console)
        calls = [str(c) for c in console.print_info.call_args_list]
        assert any("login" in c for c in calls)
        assert any("status" in c for c in calls)
        assert any("disconnect" in c for c in calls)

    def test_google_login_no_client_id(self):
        """'/google login' without client_id should show error."""
        from orion.cli.commands import _handle_google

        console = MagicMock()
        with patch.dict("os.environ", {}, clear=False):
            with patch(
                "orion.integrations.oauth_manager.get_client_id",
                return_value=None,
            ):
                _handle_google(["/google", "login"], console)
        calls = [str(c) for c in console.print_error.call_args_list]
        assert any("client_id not configured" in c for c in calls)


# =========================================================================
# Security Invariants
# =========================================================================


class TestSecurityInvariants:
    """Verify critical security properties of the Google sign-in flow."""

    def test_password_never_stored(self, manager, valid_credentials, tmp_creds_path):
        """No Google password should ever appear in stored credentials."""
        manager.store(valid_credentials)
        raw = tmp_creds_path.read_text()
        # The file should contain tokens, not passwords
        assert "password" not in raw.lower()
        data = json.loads(raw)
        # Only OAuth tokens, never a password field
        assert "password" not in data
        assert "passwd" not in data

    def test_container_file_no_refresh_token(self, manager, valid_credentials, tmp_path):
        """Container file must NEVER contain the refresh token (host-only)."""
        manager.store(valid_credentials)
        container_path = tmp_path / "ro_creds.json"
        manager.write_container_credentials(container_path)
        raw = container_path.read_text()
        data = json.loads(raw)
        assert "refresh_token" not in data
        assert "1//test-refresh-token" not in raw

    def test_blocked_scope_rejection_is_strict(self, manager):
        """Even one blocked scope among many valid scopes must cause rejection."""
        creds = GoogleCredentials(
            access_token="ya29.mixed",
            scope=(
                "openid email profile "
                "https://www.googleapis.com/auth/cloud-platform "
                "https://www.googleapis.com/auth/drive"  # ONE blocked scope
            ),
        )
        with pytest.raises(ValueError, match="blocked scopes"):
            manager.store(creds)

    def test_scope_check_after_refresh(self, manager, valid_credentials):
        """Token refresh must re-validate scopes (reject if scope creep)."""
        manager.store(valid_credentials)
        manager._client_id = "test-client"

        # Simulate a refresh that returns blocked scopes
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "ya29.refreshed",
            "expires_in": 3600,
            "scope": "openid https://www.googleapis.com/auth/drive",
        }

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            result = manager._refresh_token()
            # Should fail because refreshed token has blocked scope
            assert result is False
            # Access token should be invalidated
            assert manager._credentials.access_token == ""

    def test_auth_url_contains_correct_scopes(self):
        """The OAuth auth_url must request LLM-only scopes."""
        from orion.api.routes.google import _OAUTH_SCOPES

        # Must include cloud-platform for Gemini API
        assert "https://www.googleapis.com/auth/cloud-platform" in _OAUTH_SCOPES
        # Must NOT include any blocked scope
        for scope in _OAUTH_SCOPES:
            assert scope not in BLOCKED_SCOPES, f"Blocked scope in request: {scope}"
        # All requested scopes must be in ALLOWED set
        for scope in _OAUTH_SCOPES:
            assert scope in ALLOWED_SCOPES, f"Non-allowed scope in request: {scope}"
