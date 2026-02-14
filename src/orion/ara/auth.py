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
"""ARA Authentication — PIN and TOTP verification for session gating.

Every autonomous session requires authentication before:
- Starting a new session
- Approving promoted files in review
- Resuming a paused session

See ARA-001 §5 for full design.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.ara.auth")

# Where auth credentials are stored
AUTH_STORE_PATH = Path.home() / ".orion" / "auth.json"

# PIN constraints
MIN_PIN_LENGTH = 4
MAX_PIN_LENGTH = 8
MAX_PIN_ATTEMPTS = 5
PIN_LOCKOUT_SECONDS = 300  # 5 minutes


@dataclass
class AuthResult:
    """Result of an authentication attempt."""

    success: bool
    method: str
    message: str = ""
    remaining_attempts: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "method": self.method,
            "message": self.message,
            "remaining_attempts": self.remaining_attempts,
        }


class AuthStore:
    """Persistent storage for authentication credentials.

    Stores hashed PINs and TOTP secrets in ~/.orion/auth.json.
    PINs are salted and hashed with SHA-256.
    """

    def __init__(self, store_path: Path | None = None):
        self._path = store_path or AUTH_STORE_PATH
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load auth data from disk."""
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to load auth store: %s", e)
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        """Persist auth data to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    @property
    def has_pin(self) -> bool:
        return "pin_hash" in self._data

    @property
    def has_totp(self) -> bool:
        return "totp_secret" in self._data

    def set_pin(self, pin: str) -> None:
        """Store a new PIN (hashed with salt)."""
        if not pin.isdigit():
            raise ValueError("PIN must contain only digits")
        if len(pin) < MIN_PIN_LENGTH or len(pin) > MAX_PIN_LENGTH:
            raise ValueError(f"PIN must be {MIN_PIN_LENGTH}-{MAX_PIN_LENGTH} digits")

        salt = secrets.token_hex(16)
        pin_hash = hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()
        self._data["pin_hash"] = pin_hash
        self._data["pin_salt"] = salt
        self._data["pin_attempts"] = 0
        self._data["pin_lockout_until"] = 0
        self._save()
        logger.info("PIN set successfully")

    def verify_pin(self, pin: str) -> AuthResult:
        """Verify a PIN against the stored hash."""
        if not self.has_pin:
            return AuthResult(
                success=False, method="pin", message="No PIN configured"
            )

        # Check lockout
        lockout_until = self._data.get("pin_lockout_until", 0)
        if time.time() < lockout_until:
            remaining = int(lockout_until - time.time())
            return AuthResult(
                success=False,
                method="pin",
                message=f"Account locked. Try again in {remaining}s",
                remaining_attempts=0,
            )

        salt = self._data["pin_salt"]
        expected = self._data["pin_hash"]
        actual = hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()

        if hmac.compare_digest(actual, expected):
            self._data["pin_attempts"] = 0
            self._save()
            return AuthResult(success=True, method="pin", message="PIN verified")

        # Wrong PIN
        attempts = self._data.get("pin_attempts", 0) + 1
        self._data["pin_attempts"] = attempts
        remaining = MAX_PIN_ATTEMPTS - attempts

        if remaining <= 0:
            self._data["pin_lockout_until"] = time.time() + PIN_LOCKOUT_SECONDS
            self._data["pin_attempts"] = 0
            self._save()
            return AuthResult(
                success=False,
                method="pin",
                message=f"Too many attempts. Locked for {PIN_LOCKOUT_SECONDS}s",
                remaining_attempts=0,
            )

        self._save()
        return AuthResult(
            success=False,
            method="pin",
            message="Incorrect PIN",
            remaining_attempts=remaining,
        )

    def set_totp_secret(self, secret: str | None = None) -> str:
        """Store a TOTP secret. Returns the secret (for QR code generation)."""
        if secret is None:
            secret = secrets.token_hex(20)
        self._data["totp_secret"] = secret
        self._save()
        logger.info("TOTP secret configured")
        return secret

    def get_totp_secret(self) -> str | None:
        """Get the stored TOTP secret."""
        return self._data.get("totp_secret")

    def verify_totp(self, code: str, window: int = 1) -> AuthResult:
        """Verify a TOTP code against the stored secret."""
        if not self.has_totp:
            return AuthResult(
                success=False, method="totp", message="No TOTP configured"
            )

        secret = self._data["totp_secret"]
        if _verify_totp_code(secret, code, window=window):
            return AuthResult(success=True, method="totp", message="TOTP verified")

        return AuthResult(
            success=False, method="totp", message="Invalid TOTP code"
        )

    def clear(self) -> None:
        """Clear all auth data."""
        self._data = {}
        self._save()


def _generate_totp_code(secret: str, time_step: int = 30, digits: int = 6) -> str:
    """Generate a TOTP code from a hex secret."""
    counter = int(time.time()) // time_step
    key = bytes.fromhex(secret)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    truncated = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    code = truncated % (10 ** digits)
    return str(code).zfill(digits)


def _verify_totp_code(
    secret: str, code: str, time_step: int = 30, digits: int = 6, window: int = 1
) -> bool:
    """Verify a TOTP code with a time window tolerance."""
    current_counter = int(time.time()) // time_step
    for offset in range(-window, window + 1):
        counter = current_counter + offset
        key = bytes.fromhex(secret)
        msg = struct.pack(">Q", counter)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        off = h[-1] & 0x0F
        truncated = struct.unpack(">I", h[off:off + 4])[0] & 0x7FFFFFFF
        expected = str(truncated % (10 ** digits)).zfill(digits)
        if hmac.compare_digest(code, expected):
            return True
    return False


class RoleAuthenticator:
    """Authenticates users based on role auth_method configuration."""

    def __init__(self, auth_store: AuthStore | None = None):
        self._store = auth_store or AuthStore()

    @property
    def store(self) -> AuthStore:
        return self._store

    def is_configured(self, method: str) -> bool:
        """Check if the given auth method is configured."""
        if method == "pin":
            return self._store.has_pin
        if method == "totp":
            return self._store.has_totp
        return False

    def authenticate(self, method: str, credential: str) -> AuthResult:
        """Authenticate using the specified method."""
        if method == "pin":
            return self._store.verify_pin(credential)
        if method == "totp":
            return self._store.verify_totp(credential)
        return AuthResult(
            success=False, method=method, message=f"Unknown auth method: {method}"
        )

    def setup_pin(self, pin: str) -> None:
        """Set up PIN authentication."""
        self._store.set_pin(pin)

    def setup_totp(self, secret: str | None = None) -> str:
        """Set up TOTP authentication. Returns the secret."""
        return self._store.set_totp_secret(secret)

    def generate_current_totp(self) -> str | None:
        """Generate the current TOTP code (for testing/display)."""
        secret = self._store.get_totp_secret()
        if not secret:
            return None
        return _generate_totp_code(secret)
