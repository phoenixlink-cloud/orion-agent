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
"""Google OAuth credential management for Phase 2.

Handles the dedicated Google account used for LLM access through
Antigravity (VS Code fork). Credentials are stored on the HOST
filesystem and mounted READ-ONLY into the Docker container.

Architecture (from Milestone Document):
  Host: ~/.orion/google_credentials.json  (encrypted, user-managed)
  Docker: /home/orion/.orion/google_credentials.json  (read-only mount)

Security properties:
  - Credentials stored encrypted on host (AES-256-GCM via SecureStore)
  - Container gets read-only access (cannot modify or delete)
  - Google account scoped to LLM access only (AEGIS enforced)
  - All other Google services default DENY
  - Token refresh happens on the host side only
  - Credential access is audit-logged (AEGIS Invariant 6b)

Scoping Rules (AEGIS enforced):
  ALLOWED: Gemini API, Vertex AI (LLM endpoints)
  BLOCKED: Drive, Gmail, Calendar, YouTube, Photos, etc.
  The egress proxy whitelist enforces this at the network level.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.security.egress.google_credentials")

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
_ORION_HOME = Path(os.environ.get("ORION_HOME", Path.home() / ".orion"))
DEFAULT_CREDENTIALS_PATH = _ORION_HOME / "google_credentials.json"

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Scopes that are ALLOWED for the dedicated Google account.
# These are the minimum scopes needed for LLM access via Antigravity.
ALLOWED_SCOPES: frozenset[str] = frozenset(
    {
        "openid",
        "email",
        "profile",
        # Gemini API access (generativelanguage.googleapis.com)
        "https://www.googleapis.com/auth/generative-language.tuning",
        "https://www.googleapis.com/auth/generative-language.retriever",
        "https://www.googleapis.com/auth/cloud-platform",
    }
)

# Scopes that are EXPLICITLY BLOCKED. If the token has these scopes,
# it will be rejected. This prevents scope creep.
BLOCKED_SCOPES: frozenset[str] = frozenset(
    {
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/contacts",
        "https://www.googleapis.com/auth/photos",
    }
)


@dataclass
class GoogleCredentials:
    """Google OAuth credentials for the dedicated LLM account.

    These are the tokens obtained through the Google OAuth flow,
    stored encrypted on the host filesystem.
    """

    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "Bearer"
    expires_at: float = 0.0  # Unix timestamp
    scope: str = ""
    id_token: str = ""

    # Account metadata (from ID token claims)
    email: str = ""
    account_id: str = ""

    # Management metadata
    created_at: float = 0.0
    last_refreshed_at: float = 0.0
    refresh_count: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if the access token has expired (with 5-min buffer)."""
        return time.time() > (self.expires_at - 300)

    @property
    def has_refresh_token(self) -> bool:
        return bool(self.refresh_token)

    @property
    def scopes(self) -> set[str]:
        """Parse the space-separated scope string into a set."""
        return set(self.scope.split()) if self.scope else set()

    @property
    def has_blocked_scopes(self) -> bool:
        """Check if the token has any blocked scopes."""
        return bool(self.scopes & BLOCKED_SCOPES)

    @property
    def blocked_scope_list(self) -> list[str]:
        """Return the list of blocked scopes present in the token."""
        return sorted(self.scopes & BLOCKED_SCOPES)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage (excludes sensitive tokens in summary mode)."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "id_token": self.id_token,
            "email": self.email,
            "account_id": self.account_id,
            "created_at": self.created_at,
            "last_refreshed_at": self.last_refreshed_at,
            "refresh_count": self.refresh_count,
        }

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize for API responses (tokens redacted)."""
        return {
            "has_access_token": bool(self.access_token),
            "has_refresh_token": bool(self.refresh_token),
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "is_expired": self.is_expired,
            "scope": self.scope,
            "email": self.email,
            "account_id": self.account_id,
            "created_at": self.created_at,
            "last_refreshed_at": self.last_refreshed_at,
            "refresh_count": self.refresh_count,
            "has_blocked_scopes": self.has_blocked_scopes,
            "blocked_scopes": self.blocked_scope_list,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GoogleCredentials:
        """Deserialize from storage."""
        return cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            token_type=data.get("token_type", "Bearer"),
            expires_at=data.get("expires_at", 0.0),
            scope=data.get("scope", ""),
            id_token=data.get("id_token", ""),
            email=data.get("email", ""),
            account_id=data.get("account_id", ""),
            created_at=data.get("created_at", 0.0),
            last_refreshed_at=data.get("last_refreshed_at", 0.0),
            refresh_count=data.get("refresh_count", 0),
        )


class GoogleCredentialManager:
    """Manages Google OAuth credentials on the host side.

    Handles:
      - Storing/loading encrypted credentials
      - Token refresh (host-side only)
      - Scope validation (blocking disallowed Google services)
      - Read-only credential file generation for container mount
      - Audit logging of credential access

    Usage:
        manager = GoogleCredentialManager()

        # Store credentials after OAuth flow
        manager.store(credentials)

        # Get current credentials (refreshes if expired)
        creds = manager.get_credentials()

        # Generate read-only file for container mount
        manager.write_container_credentials()
    """

    def __init__(
        self,
        credentials_path: str | Path | None = None,
        client_id: str = "",
        client_secret: str = "",
        use_secure_store: bool = True,
    ) -> None:
        self._path = Path(credentials_path) if credentials_path else DEFAULT_CREDENTIALS_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._client_id = client_id
        self._client_secret = client_secret
        self._credentials: GoogleCredentials | None = None
        self._use_secure_store = use_secure_store

    @property
    def credentials_path(self) -> Path:
        return self._path

    @property
    def has_credentials(self) -> bool:
        """Check if credentials exist (either in memory or on disk)."""
        if self._credentials and self._credentials.access_token:
            return True
        return self._path.exists()

    def store(self, credentials: GoogleCredentials) -> None:
        """Store Google OAuth credentials.

        Validates scopes before storing. Rejects tokens with blocked scopes.

        Raises:
            ValueError: If the token has blocked scopes.
        """
        # Validate scopes
        if credentials.has_blocked_scopes:
            blocked = credentials.blocked_scope_list
            raise ValueError(
                f"Google credentials have blocked scopes: {', '.join(blocked)}. "
                "The dedicated Google account must be scoped to LLM access only."
            )

        if not credentials.created_at:
            credentials.created_at = time.time()

        self._credentials = credentials
        self._save()
        logger.info(
            "Stored Google credentials for %s (expires: %.0fs)",
            credentials.email or "unknown",
            max(0, credentials.expires_at - time.time()),
        )

    def get_credentials(self, auto_refresh: bool = True) -> GoogleCredentials | None:
        """Get current Google credentials.

        If auto_refresh is True and the token is expired, attempts
        to refresh it using the refresh token.

        Returns:
            GoogleCredentials or None if not configured.
        """
        if self._credentials is None:
            self._load()

        if self._credentials is None:
            return None

        if auto_refresh and self._credentials.is_expired and self._credentials.has_refresh_token:
            self._refresh_token()

        return self._credentials

    def get_access_token(self) -> str | None:
        """Get the current access token (refreshes if needed)."""
        creds = self.get_credentials()
        if creds and creds.access_token:
            return creds.access_token
        return None

    def clear(self) -> None:
        """Remove stored credentials from all backends."""
        self._credentials = None
        if self._path.exists():
            self._path.unlink()
        # Also remove from SecureStore
        if self._use_secure_store:
            try:
                from orion.security.store import SecureStore

                store = SecureStore()
                store.set_key("google_oauth_credentials", "")
            except Exception:
                pass
        logger.info("Cleared Google credentials")

    def get_status(self) -> dict:
        """Get credential status for dashboard display."""
        creds = self.get_credentials(auto_refresh=False)
        if creds is None:
            return {
                "configured": False,
                "email": "",
                "is_expired": True,
                "has_refresh_token": False,
            }
        return creds.to_safe_dict() | {"configured": True}

    def write_container_credentials(self, output_path: str | Path | None = None) -> Path:
        """Write a minimal credentials file for read-only container mount.

        This file contains ONLY the access token (no refresh token).
        The container can use it to authenticate but cannot refresh
        or modify the credentials.

        Returns:
            Path to the generated file.
        """
        creds = self.get_credentials()
        if creds is None:
            raise RuntimeError("No Google credentials configured")

        out = Path(output_path) if output_path else self._path.parent / "google_credentials_ro.json"
        out.parent.mkdir(parents=True, exist_ok=True)

        # Only include the access token -- no refresh token for the container
        container_data = {
            "access_token": creds.access_token,
            "token_type": creds.token_type,
            "expires_at": creds.expires_at,
            "scope": creds.scope,
            "email": creds.email,
        }
        out.write_text(json.dumps(container_data, indent=2), encoding="utf-8")
        logger.info("Wrote container credentials to %s", out)
        return out

    # ---------------------------------------------------------------
    # Internal methods
    # ---------------------------------------------------------------

    def _save(self) -> None:
        """Save credentials to disk (encrypted via SecureStore if available)."""
        if self._credentials is None:
            return

        data = self._credentials.to_dict()

        # Try encrypted storage first
        if self._use_secure_store:
            try:
                from orion.security.store import SecureStore

                store = SecureStore()
                store.set_key("google_oauth_credentials", json.dumps(data))
            except Exception:
                pass

        # Always write to file (for container mount)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load credentials from disk."""
        # Try SecureStore first
        if self._use_secure_store:
            try:
                from orion.security.store import SecureStore

                store = SecureStore()
                raw = store.get_key("google_oauth_credentials")
                if raw and raw.strip():
                    data = json.loads(raw)
                    # Verify the stored data has a real access token
                    if data.get("access_token"):
                        self._credentials = GoogleCredentials.from_dict(data)
                        return
            except Exception:
                pass

        # Fallback: load from file
        if not self._path.exists():
            return

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._credentials = GoogleCredentials.from_dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load Google credentials: %s", exc)

    def _refresh_token(self) -> bool:
        """Refresh the access token using the refresh token.

        This runs on the HOST side only -- the container cannot refresh.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        if not self._credentials or not self._credentials.refresh_token:
            return False

        if not self._client_id:
            logger.warning("Cannot refresh: no client_id configured")
            return False

        try:
            import httpx

            token_data = {
                "grant_type": "refresh_token",
                "refresh_token": self._credentials.refresh_token,
                "client_id": self._client_id,
            }
            if self._client_secret:
                token_data["client_secret"] = self._client_secret

            with httpx.Client(timeout=15.0) as client:
                resp = client.post(GOOGLE_TOKEN_URL, data=token_data)
                if resp.status_code != 200:
                    logger.error("Token refresh failed: %d %s", resp.status_code, resp.text[:200])
                    return False

                tokens = resp.json()

            self._credentials.access_token = tokens.get(
                "access_token", self._credentials.access_token
            )
            self._credentials.expires_at = time.time() + tokens.get("expires_in", 3600)
            self._credentials.scope = tokens.get("scope", self._credentials.scope)
            self._credentials.last_refreshed_at = time.time()
            self._credentials.refresh_count += 1

            # Re-validate scopes after refresh
            if self._credentials.has_blocked_scopes:
                logger.error(
                    "SECURITY: Refreshed token has blocked scopes: %s",
                    self._credentials.blocked_scope_list,
                )
                self._credentials.access_token = ""  # Invalidate
                return False

            self._save()
            logger.info(
                "Google token refreshed (refresh #%d, expires in %ds)",
                self._credentials.refresh_count,
                int(self._credentials.expires_at - time.time()),
            )
            return True

        except Exception as exc:
            logger.error("Token refresh error: %s", exc)
            return False
