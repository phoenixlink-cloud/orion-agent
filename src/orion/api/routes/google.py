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
"""Google Account sign-in routes for governed sandbox access.

Dedicated endpoints for connecting a Google account to Orion's sandbox.
These are SEPARATE from the generic OAuth platform integrations because:

  1. They use LLM-only scopes (Gemini API, Vertex AI) — not generic openid
  2. The callback bridges to GoogleCredentialManager (not generic oauth_tokens.json)
  3. Scope validation rejects blocked services (Drive, Gmail, Calendar, YouTube)
  4. Container credential file is generated (read-only, access-token-only)
  5. Token refresh happens host-side only — container cannot refresh

Security model:
  - Orion NEVER sees the user's Google password (standard OAuth browser redirect)
  - Only a scoped access token is stored (encrypted via SecureStore)
  - BLOCKED_SCOPES are rejected at storage time (AEGIS enforcement)
  - Container gets a READ-ONLY file with access token only (no refresh token)
  - Egress proxy enforces domain whitelist at network level (AEGIS Invariant 7)
  - Token refresh is host-side only — the sandbox cannot extend its own access

Endpoints:
  POST /api/google/connect     — Start Google OAuth flow (returns auth_url)
  GET  /api/google/callback    — OAuth callback → GoogleCredentialManager.store()
  GET  /api/google/status      — Account status (tokens redacted)
  POST /api/google/disconnect  — Revoke token and clear credentials
  POST /api/google/refresh     — Force host-side token refresh
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import string
import time
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger("orion.api.routes.google")

router = APIRouter(tags=["google"])

# ---------------------------------------------------------------------------
# Google OAuth configuration — uses LLM-only scopes from google_credentials.py
# ---------------------------------------------------------------------------

# Import the authoritative scope definitions from the credential manager.
# These are the scopes that AEGIS allows for the dedicated Google account.
from orion.security.egress.google_credentials import (
    ALLOWED_SCOPES,
    BLOCKED_SCOPES,
    GOOGLE_AUTH_URL,
    GOOGLE_TOKEN_URL,
    GoogleCredentialManager,
    GoogleCredentials,
)

# Scopes to REQUEST during the OAuth flow.
# We request the LLM-access scopes plus basic profile info.
# Google will show the user exactly what they're granting.
_OAUTH_SCOPES: list[str] = sorted(ALLOWED_SCOPES)

# In-memory PKCE state (short-lived, per-session)
_google_oauth_pending: dict[str, dict[str, Any]] = {}

# Module-level credential manager singleton
_credential_manager: GoogleCredentialManager | None = None


def _get_credential_manager() -> GoogleCredentialManager:
    """Get or create the GoogleCredentialManager singleton."""
    global _credential_manager
    if _credential_manager is None:
        _credential_manager = GoogleCredentialManager()
    return _credential_manager


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code_verifier + code_challenge (S256)."""
    rand = secrets.SystemRandom()
    code_verifier = "".join(rand.choices(string.ascii_letters + string.digits, k=128))
    code_sha256 = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(code_sha256).decode("utf-8").rstrip("=")
    return code_verifier, code_challenge


def _get_google_client_id() -> str | None:
    """Get Google OAuth client_id from config, env, or bundled defaults."""
    import os

    # 1. Environment variable
    env_val = os.environ.get("ORION_GOOGLE_CLIENT_ID")
    if env_val:
        return env_val

    # 2. User config via oauth_manager
    try:
        from orion.integrations.oauth_manager import get_client_id

        client_id = get_client_id("google")
        if client_id:
            return client_id
    except Exception:
        pass

    # 3. SecureStore
    try:
        from orion.security.store import get_secure_store

        store = get_secure_store()
        if store:
            client_id = store.get_key("oauth_google_client_id")
            if client_id:
                return client_id
    except Exception:
        pass

    return None


def _get_google_client_secret() -> str | None:
    """Get Google OAuth client_secret (optional for PKCE flows)."""
    import os

    env_val = os.environ.get("ORION_GOOGLE_CLIENT_SECRET")
    if env_val:
        return env_val

    try:
        from orion.integrations.oauth_manager import get_client_secret

        secret = get_client_secret("google")
        if secret:
            return secret
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class GoogleConnectRequest(BaseModel):
    """Request to start Google OAuth flow."""

    redirect_uri: str | None = None


class GoogleDisconnectRequest(BaseModel):
    """Request to disconnect Google account."""

    revoke_token: bool = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/google/connect")
async def google_connect(request: GoogleConnectRequest | None = None):
    """Start the Google OAuth flow for sandbox LLM access.

    Returns an auth_url that the frontend opens in a popup or new tab.
    The user signs in directly with Google — Orion never sees the password.

    The flow requests LLM-only scopes (Gemini API, Vertex AI) plus
    basic profile info (email). Blocked services (Drive, Gmail, etc.)
    are NOT requested and would be rejected even if somehow granted.
    """
    client_id = _get_google_client_id()
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Google OAuth client_id not configured. "
                "Set ORION_GOOGLE_CLIENT_ID environment variable, or register "
                "a Google OAuth app and save the client_id via "
                "POST /api/oauth/quick-setup with provider='google'."
            ),
        )

    # Generate PKCE pair
    code_verifier, code_challenge = _generate_pkce_pair()
    state_token = secrets.token_urlsafe(32)

    redirect_uri = "http://localhost:8001/api/google/callback"
    if request and request.redirect_uri:
        redirect_uri = request.redirect_uri

    # Store pending auth state (short-lived)
    _google_oauth_pending[state_token] = {
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "created_at": time.time(),
    }

    # Clean up stale pending entries (older than 10 minutes)
    cutoff = time.time() - 600
    stale = [k for k, v in _google_oauth_pending.items() if v["created_at"] < cutoff]
    for k in stale:
        _google_oauth_pending.pop(k, None)

    # Build Google authorization URL with LLM-only scopes
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state_token,
        "scope": " ".join(_OAUTH_SCOPES),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",  # Request refresh_token
        "prompt": "consent",  # Always show consent screen (ensures refresh_token)
    }

    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    logger.info(
        "Google OAuth flow initiated (scopes: %d allowed, %d blocked)",
        len(ALLOWED_SCOPES),
        len(BLOCKED_SCOPES),
    )

    return {
        "status": "redirect",
        "auth_url": auth_url,
        "state": state_token,
        "scopes_requested": _OAUTH_SCOPES,
        "blocked_scopes": sorted(BLOCKED_SCOPES),
    }


@router.get("/api/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """OAuth2 callback handler for Google Account sign-in.

    Receives the authorization code from Google, exchanges it for
    access + refresh tokens, validates scopes, and stores credentials
    via GoogleCredentialManager.

    Security checks:
      1. PKCE state validation (prevents CSRF)
      2. Token exchange with code_verifier
      3. Scope validation (rejects blocked scopes like Drive, Gmail)
      4. Credentials stored encrypted via GoogleCredentialManager
      5. Container credential file generated (access-token-only, read-only)
    """
    # 1. Validate state token (CSRF protection)
    pending = _google_oauth_pending.pop(state, None)
    if not pending:
        return HTMLResponse(
            "<html><body><h2>Error: Invalid or expired state.</h2>"
            "<p>Please try signing in again from Settings.</p></body></html>",
            status_code=400,
        )

    code_verifier = pending["code_verifier"]
    redirect_uri = pending["redirect_uri"]

    # 2. Get client credentials
    client_id = _get_google_client_id()
    client_secret = _get_google_client_secret()

    if not client_id:
        return HTMLResponse(
            "<html><body><h2>Error: Google client_id not found.</h2></body></html>",
            status_code=400,
        )

    # 3. Exchange authorization code for tokens
    import httpx

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    if client_secret:
        token_data["client_secret"] = client_secret

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data=token_data,
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                error_detail = resp.text[:500]
                logger.error("Google token exchange failed: %d %s", resp.status_code, error_detail)
                return HTMLResponse(
                    f"<html><body><h2>Token exchange failed</h2>"
                    f"<p>{resp.status_code}: {error_detail}</p></body></html>",
                    status_code=400,
                )
            tokens = resp.json()
    except Exception as e:
        logger.error("Google token exchange error: %s", e)
        return HTMLResponse(
            f"<html><body><h2>Token exchange error</h2><p>{e}</p></body></html>",
            status_code=500,
        )

    # 4. Extract token fields
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)
    scope = tokens.get("scope", "")
    id_token = tokens.get("id_token", "")

    if not access_token:
        return HTMLResponse(
            "<html><body><h2>Error: No access token received from Google.</h2></body></html>",
            status_code=400,
        )

    # 5. Extract email from userinfo (or ID token)
    email = ""
    account_id = ""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code == 200:
                userinfo = userinfo_resp.json()
                email = userinfo.get("email", "")
                account_id = userinfo.get("id", "")
    except Exception as e:
        logger.warning("Could not fetch Google userinfo: %s", e)

    # 6. Build GoogleCredentials and store via manager
    credentials = GoogleCredentials(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=tokens.get("token_type", "Bearer"),
        expires_at=time.time() + expires_in,
        scope=scope,
        id_token=id_token,
        email=email,
        account_id=account_id,
    )

    # 7. Validate scopes and store (GoogleCredentialManager.store() rejects blocked scopes)
    manager = _get_credential_manager()
    try:
        manager.store(credentials)
    except ValueError as e:
        # Blocked scopes detected — this is a security rejection
        logger.error("SECURITY: Google credentials rejected: %s", e)
        return HTMLResponse(
            f"""<html>
<head><title>Orion -- Google Account Rejected</title></head>
<body style="font-family: system-ui; text-align: center; padding: 40px;">
  <h2 style="color: #ef4444;">Google Account Rejected</h2>
  <p>{e}</p>
  <p>The dedicated Google account must be scoped to LLM access only.</p>
  <p>Please create a separate Google account for Orion with restricted permissions.</p>
</body></html>""",
            status_code=403,
        )

    # 8. Generate read-only container credentials (access-token-only)
    try:
        container_path = manager.write_container_credentials()
        logger.info("Container credentials written to %s", container_path)
    except Exception as e:
        logger.warning("Could not write container credentials: %s", e)

    logger.info(
        "Google account connected: %s (scopes: %s)",
        email or "unknown",
        scope,
    )

    # 9. Return success HTML (closes popup, notifies parent window)
    return HTMLResponse(
        f"""<html>
<head><title>Orion -- Google Account Connected</title></head>
<body style="font-family: system-ui; text-align: center; padding: 40px;">
  <h2 style="color: #22c55e;">Google Account Connected</h2>
  <p><strong>{email or "Account"}</strong> is now linked to Orion.</p>
  <p style="color: #6b7280; font-size: 0.9em;">
    Scoped to LLM access only. Drive, Gmail, Calendar, and YouTube are blocked.
  </p>
  <p>You can close this window.</p>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{
        type: 'google_account_connected',
        email: '{email}',
      }}, '*');
    }}
    setTimeout(() => window.close(), 3000);
  </script>
</body></html>"""
    )


@router.get("/api/google/status")
async def google_status():
    """Get the current Google account connection status.

    Returns credential metadata with tokens REDACTED.
    Safe to call from the frontend — no sensitive data exposed.
    """
    manager = _get_credential_manager()
    status = manager.get_status()

    # Add extra context for the frontend
    status["allowed_scopes"] = sorted(ALLOWED_SCOPES)
    status["blocked_scopes"] = sorted(BLOCKED_SCOPES)
    status["client_id_configured"] = _get_google_client_id() is not None

    return status


@router.post("/api/google/disconnect")
async def google_disconnect(request: GoogleDisconnectRequest | None = None):
    """Disconnect the Google account and clear all stored credentials.

    Optionally revokes the access token with Google before clearing.
    """
    manager = _get_credential_manager()
    revoke = request.revoke_token if request else True

    # Optionally revoke the token with Google
    if revoke:
        creds = manager.get_credentials(auto_refresh=False)
        if creds and creds.access_token:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        "https://oauth2.googleapis.com/revoke",
                        params={"token": creds.access_token},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                logger.info("Google token revoked")
            except Exception as e:
                logger.warning("Token revocation failed (non-fatal): %s", e)

    # Clear all stored credentials
    manager.clear()
    logger.info("Google account disconnected and credentials cleared")

    return {
        "status": "disconnected",
        "message": "Google account has been disconnected. "
        "All stored credentials have been cleared.",
    }


@router.post("/api/google/refresh")
async def google_refresh():
    """Force a host-side token refresh.

    This is useful if the access token has expired and the sandbox
    needs fresh credentials before the next automatic refresh.

    The refresh happens on the HOST side only — the container cannot
    refresh tokens (it only has a read-only access token).
    """
    manager = _get_credential_manager()
    creds = manager.get_credentials(auto_refresh=False)

    if creds is None:
        raise HTTPException(
            status_code=404,
            detail="No Google account connected. Use POST /api/google/connect first.",
        )

    if not creds.has_refresh_token:
        raise HTTPException(
            status_code=400,
            detail="No refresh token available. Re-authenticate via POST /api/google/connect.",
        )

    # Get client_id for refresh
    client_id = _get_google_client_id()
    client_secret = _get_google_client_secret()

    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="Google client_id not configured. Cannot refresh token.",
        )

    # Update manager with client credentials for refresh
    manager._client_id = client_id
    manager._client_secret = client_secret or ""

    # Force refresh
    success = manager._refresh_token()

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Token refresh failed. The refresh token may have been revoked. "
            "Re-authenticate via POST /api/google/connect.",
        )

    # Regenerate container credentials with fresh token
    try:
        manager.write_container_credentials()
    except Exception as e:
        logger.warning("Could not update container credentials: %s", e)

    return {
        "status": "refreshed",
        "expires_at": manager.get_credentials(auto_refresh=False).expires_at,
        "message": "Access token refreshed. Container credentials updated.",
    }
