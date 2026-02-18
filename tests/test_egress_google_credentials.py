# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Google OAuth credential management."""

import json
import time
from pathlib import Path

import pytest

from orion.security.egress.google_credentials import (
    ALLOWED_SCOPES,
    BLOCKED_SCOPES,
    GoogleCredentialManager,
    GoogleCredentials,
)


class TestGoogleCredentials:
    """Tests for GoogleCredentials data structure."""

    def test_create_credentials(self):
        creds = GoogleCredentials(
            access_token="ya29.test",
            refresh_token="1//test",
            expires_at=time.time() + 3600,
            scope="openid email profile",
            email="orion-llm@example.com",
        )
        assert creds.access_token == "ya29.test"
        assert creds.is_expired is False
        assert creds.has_refresh_token is True

    def test_expired_token(self):
        creds = GoogleCredentials(
            access_token="ya29.test",
            expires_at=time.time() - 100,
        )
        assert creds.is_expired is True

    def test_almost_expired_token(self):
        # Within the 5-minute buffer
        creds = GoogleCredentials(
            access_token="ya29.test",
            expires_at=time.time() + 200,  # < 300s buffer
        )
        assert creds.is_expired is True

    def test_not_expired_token(self):
        creds = GoogleCredentials(
            access_token="ya29.test",
            expires_at=time.time() + 3600,
        )
        assert creds.is_expired is False

    def test_scopes_parsing(self):
        creds = GoogleCredentials(scope="openid email profile")
        assert creds.scopes == {"openid", "email", "profile"}

    def test_empty_scopes(self):
        creds = GoogleCredentials(scope="")
        assert creds.scopes == set()

    def test_blocked_scopes_detected(self):
        creds = GoogleCredentials(scope="openid email https://www.googleapis.com/auth/drive")
        assert creds.has_blocked_scopes is True
        assert "https://www.googleapis.com/auth/drive" in creds.blocked_scope_list

    def test_clean_scopes_not_blocked(self):
        creds = GoogleCredentials(scope="openid email profile")
        assert creds.has_blocked_scopes is False
        assert creds.blocked_scope_list == []

    def test_to_dict_roundtrip(self):
        creds = GoogleCredentials(
            access_token="ya29.test",
            refresh_token="1//test",
            expires_at=1700000000.0,
            scope="openid email",
            email="test@example.com",
            refresh_count=5,
        )
        d = creds.to_dict()
        restored = GoogleCredentials.from_dict(d)
        assert restored.access_token == creds.access_token
        assert restored.refresh_token == creds.refresh_token
        assert restored.email == creds.email
        assert restored.refresh_count == 5

    def test_to_safe_dict_redacts_tokens(self):
        creds = GoogleCredentials(
            access_token="ya29.secret",
            refresh_token="1//secret",
            email="test@example.com",
            expires_at=time.time() + 3600,
        )
        safe = creds.to_safe_dict()
        assert "access_token" not in safe
        assert "refresh_token" not in safe
        assert safe["has_access_token"] is True
        assert safe["has_refresh_token"] is True
        assert safe["email"] == "test@example.com"

    def test_from_dict_missing_fields(self):
        creds = GoogleCredentials.from_dict({"access_token": "ya29.test"})
        assert creds.access_token == "ya29.test"
        assert creds.refresh_token == ""
        assert creds.email == ""


class TestGoogleCredentialManager:
    """Tests for GoogleCredentialManager."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a manager with a temporary credentials path.

        Uses use_secure_store=False to avoid touching the real OS keyring.
        """
        return GoogleCredentialManager(
            credentials_path=tmp_path / "google_credentials.json",
            use_secure_store=False,
        )

    def test_no_credentials_initially(self, manager):
        assert manager.has_credentials is False
        assert manager.get_credentials() is None
        assert manager.get_access_token() is None

    def test_store_and_retrieve(self, manager):
        creds = GoogleCredentials(
            access_token="ya29.test",
            refresh_token="1//test",
            expires_at=time.time() + 3600,
            scope="openid email profile",
            email="orion@example.com",
        )
        manager.store(creds)

        assert manager.has_credentials is True
        retrieved = manager.get_credentials(auto_refresh=False)
        assert retrieved is not None
        assert retrieved.access_token == "ya29.test"
        assert retrieved.email == "orion@example.com"

    def test_store_rejects_blocked_scopes(self, manager):
        creds = GoogleCredentials(
            access_token="ya29.test",
            scope="openid https://www.googleapis.com/auth/drive",
        )
        with pytest.raises(ValueError, match="blocked scopes"):
            manager.store(creds)

    def test_store_accepts_allowed_scopes(self, manager):
        creds = GoogleCredentials(
            access_token="ya29.test",
            scope="openid email profile",
        )
        manager.store(creds)
        assert manager.has_credentials is True

    def test_get_access_token(self, manager):
        creds = GoogleCredentials(
            access_token="ya29.mytoken",
            expires_at=time.time() + 3600,
        )
        manager.store(creds)
        assert manager.get_access_token() == "ya29.mytoken"

    def test_clear_credentials(self, manager):
        creds = GoogleCredentials(access_token="ya29.test")
        manager.store(creds)
        assert manager.has_credentials is True

        manager.clear()
        assert manager.has_credentials is False
        assert manager.get_credentials() is None

    def test_persistence_to_file(self, manager):
        creds = GoogleCredentials(
            access_token="ya29.persist",
            refresh_token="1//persist",
            scope="openid email",
            email="persist@example.com",
        )
        manager.store(creds)

        # File should exist
        assert manager.credentials_path.exists()

        # Load into a new manager instance (also without SecureStore)
        manager2 = GoogleCredentialManager(
            credentials_path=manager.credentials_path,
            use_secure_store=False,
        )
        retrieved = manager2.get_credentials(auto_refresh=False)
        assert retrieved is not None
        assert retrieved.access_token == "ya29.persist"
        assert retrieved.email == "persist@example.com"

    def test_get_status_no_credentials(self, manager):
        status = manager.get_status()
        assert status["configured"] is False

    def test_get_status_with_credentials(self, manager):
        creds = GoogleCredentials(
            access_token="ya29.test",
            expires_at=time.time() + 3600,
            scope="openid email",
            email="test@example.com",
        )
        manager.store(creds)
        status = manager.get_status()
        assert status["configured"] is True
        assert status["email"] == "test@example.com"
        assert status["has_access_token"] is True

    def test_write_container_credentials(self, manager, tmp_path):
        creds = GoogleCredentials(
            access_token="ya29.container",
            refresh_token="1//secret_refresh",
            expires_at=time.time() + 3600,
            scope="openid email",
            email="container@example.com",
        )
        manager.store(creds)

        out_path = tmp_path / "container_creds.json"
        result = manager.write_container_credentials(out_path)

        assert result == out_path
        assert out_path.exists()

        data = json.loads(out_path.read_text())
        # Should have access token
        assert data["access_token"] == "ya29.container"
        # Should NOT have refresh token (container can't refresh)
        assert "refresh_token" not in data
        # Should have metadata
        assert data["email"] == "container@example.com"

    def test_write_container_credentials_no_creds(self, manager):
        with pytest.raises(RuntimeError, match="No Google credentials"):
            manager.write_container_credentials()

    def test_created_at_auto_set(self, manager):
        creds = GoogleCredentials(access_token="ya29.test")
        assert creds.created_at == 0.0
        manager.store(creds)
        stored = manager.get_credentials(auto_refresh=False)
        assert stored.created_at > 0


class TestScopeConstants:
    """Tests for scope constant definitions."""

    def test_allowed_scopes_frozen(self):
        assert isinstance(ALLOWED_SCOPES, frozenset)
        with pytest.raises(AttributeError):
            ALLOWED_SCOPES.add("bad")

    def test_blocked_scopes_frozen(self):
        assert isinstance(BLOCKED_SCOPES, frozenset)

    def test_no_overlap_between_allowed_and_blocked(self):
        overlap = ALLOWED_SCOPES & BLOCKED_SCOPES
        assert len(overlap) == 0, f"Scopes in both allowed and blocked: {overlap}"

    def test_drive_is_blocked(self):
        assert "https://www.googleapis.com/auth/drive" in BLOCKED_SCOPES

    def test_gmail_is_blocked(self):
        blocked_gmail = [s for s in BLOCKED_SCOPES if "gmail" in s]
        assert len(blocked_gmail) > 0

    def test_openid_is_allowed(self):
        assert "openid" in ALLOWED_SCOPES
