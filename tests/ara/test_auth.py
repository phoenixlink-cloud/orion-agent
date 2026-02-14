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
"""Tests for ARA Authentication (ARA-001 §5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.ara.auth import (
    AuthStore,
    RoleAuthenticator,
    _generate_totp_code,
    _verify_totp_code,
)


@pytest.fixture
def auth_store(tmp_path: Path) -> AuthStore:
    return AuthStore(store_path=tmp_path / "auth.json")


@pytest.fixture
def authenticator(auth_store: AuthStore) -> RoleAuthenticator:
    return RoleAuthenticator(auth_store=auth_store)


class TestPINSetup:
    """Test PIN configuration."""

    def test_set_pin(self, auth_store: AuthStore):
        auth_store.set_pin("1234")
        assert auth_store.has_pin is True

    def test_reject_non_numeric(self, auth_store: AuthStore):
        with pytest.raises(ValueError, match="digits"):
            auth_store.set_pin("abcd")

    def test_reject_too_short(self, auth_store: AuthStore):
        with pytest.raises(ValueError, match="4-8"):
            auth_store.set_pin("12")

    def test_reject_too_long(self, auth_store: AuthStore):
        with pytest.raises(ValueError, match="4-8"):
            auth_store.set_pin("123456789")

    def test_pin_persists(self, tmp_path: Path):
        store1 = AuthStore(store_path=tmp_path / "auth.json")
        store1.set_pin("5678")
        store2 = AuthStore(store_path=tmp_path / "auth.json")
        assert store2.has_pin is True


class TestPINVerification:
    """Test PIN verification."""

    def test_correct_pin(self, auth_store: AuthStore):
        auth_store.set_pin("1234")
        result = auth_store.verify_pin("1234")
        assert result.success is True
        assert result.method == "pin"

    def test_wrong_pin(self, auth_store: AuthStore):
        auth_store.set_pin("1234")
        result = auth_store.verify_pin("0000")
        assert result.success is False
        assert result.remaining_attempts is not None
        assert result.remaining_attempts > 0

    def test_no_pin_configured(self, auth_store: AuthStore):
        result = auth_store.verify_pin("1234")
        assert result.success is False
        assert "No PIN" in result.message

    def test_lockout_after_max_attempts(self, auth_store: AuthStore):
        auth_store.set_pin("1234")
        for _ in range(5):
            auth_store.verify_pin("0000")
        result = auth_store.verify_pin("1234")
        assert result.success is False
        assert "locked" in result.message.lower() or result.remaining_attempts == 0


class TestTOTP:
    """Test TOTP setup and verification."""

    def test_setup_totp(self, auth_store: AuthStore):
        secret = auth_store.set_totp_secret()
        assert secret is not None
        assert auth_store.has_totp is True

    def test_generate_and_verify(self, auth_store: AuthStore):
        secret = auth_store.set_totp_secret()
        code = _generate_totp_code(secret)
        assert len(code) == 6
        assert code.isdigit()
        result = auth_store.verify_totp(code)
        assert result.success is True

    def test_wrong_code(self, auth_store: AuthStore):
        auth_store.set_totp_secret()
        result = auth_store.verify_totp("000000")
        assert result.success is False

    def test_no_totp_configured(self, auth_store: AuthStore):
        result = auth_store.verify_totp("123456")
        assert result.success is False
        assert "No TOTP" in result.message

    def test_verify_with_window(self):
        secret = "0123456789abcdef0123456789abcdef01234567"
        code = _generate_totp_code(secret)
        assert _verify_totp_code(secret, code, window=1) is True


class TestRoleAuthenticator:
    """Test the role-level authenticator."""

    def test_is_configured_pin(self, authenticator: RoleAuthenticator):
        assert authenticator.is_configured("pin") is False
        authenticator.setup_pin("1234")
        assert authenticator.is_configured("pin") is True

    def test_is_configured_totp(self, authenticator: RoleAuthenticator):
        assert authenticator.is_configured("totp") is False
        authenticator.setup_totp()
        assert authenticator.is_configured("totp") is True

    def test_authenticate_pin(self, authenticator: RoleAuthenticator):
        authenticator.setup_pin("5678")
        result = authenticator.authenticate("pin", "5678")
        assert result.success is True

    def test_authenticate_totp(self, authenticator: RoleAuthenticator):
        secret = authenticator.setup_totp()
        code = _generate_totp_code(secret)
        result = authenticator.authenticate("totp", code)
        assert result.success is True

    def test_authenticate_unknown_method(self, authenticator: RoleAuthenticator):
        result = authenticator.authenticate("biometric", "xxx")
        assert result.success is False

    def test_generate_current_totp(self, authenticator: RoleAuthenticator):
        authenticator.setup_totp()
        code = authenticator.generate_current_totp()
        assert code is not None
        assert len(code) == 6

    def test_clear_store(self, auth_store: AuthStore):
        auth_store.set_pin("1234")
        auth_store.set_totp_secret()
        auth_store.clear()
        assert auth_store.has_pin is False
        assert auth_store.has_totp is False
