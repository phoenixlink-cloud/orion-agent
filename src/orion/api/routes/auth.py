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
#    See LICENSE-ENTERPRISE.md or contact licensing@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""Orion Agent -- API Key & OAuth Routes."""

import os
import json
import time
import hashlib
import base64
import secrets
import string
import logging
from pathlib import Path
from typing import Dict
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from orion.api._shared import (
    APIKeySetRequest, OAuthConfigureRequest, OAuthLoginRequest,
    OAuthRevokeRequest, SETTINGS_DIR, _get_secure_store,
)

logger = logging.getLogger("orion.api.server")

router = APIRouter()


# =============================================================================
# API KEY MANAGEMENT
# =============================================================================

API_KEY_PROVIDERS = [
    {"provider": "openai", "description": "OpenAI (GPT models)"},
    {"provider": "anthropic", "description": "Anthropic (Claude models)"},
    {"provider": "google", "description": "Google (Gemini models)"},
    {"provider": "groq", "description": "Groq (fast inference)"},
]


def _load_api_keys_legacy() -> dict:
    """Legacy plaintext key loading -- used only as fallback."""
    keys_file = SETTINGS_DIR / "api_keys.json"
    if keys_file.exists():
        try:
            return json.loads(keys_file.read_text())
        except Exception:
            pass
    return {}


@router.get("/api/keys/status")
async def get_api_key_status():
    """Get configured status of all API keys (never exposes actual keys)."""
    store = _get_secure_store()
    legacy_keys = _load_api_keys_legacy() if not store else {}
    result = []
    for entry in API_KEY_PROVIDERS:
        provider = entry["provider"]
        env_key = os.environ.get(f"{provider.upper()}_API_KEY", "")
        has_secure = store.has_key(provider) if store else False
        has_legacy = bool(legacy_keys.get(provider))
        has_key = bool(env_key) or has_secure or has_legacy

        if env_key:
            source = "environment"
        elif has_secure:
            source = f"secure_store ({store.backend_name})"
        elif has_legacy:
            source = "legacy_plaintext"
        else:
            source = "none"

        result.append({
            "provider": provider,
            "configured": has_key,
            "description": entry["description"],
            "source": source,
        })
    return result


@router.post("/api/keys/set")
async def set_api_key(request: APIKeySetRequest):
    """Store an API key in the secure credential store."""
    valid_providers = [p["provider"] for p in API_KEY_PROVIDERS]
    if request.provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")
    if not request.key or len(request.key) < 8:
        raise HTTPException(status_code=400, detail="API key too short")

    store = _get_secure_store()
    if store:
        try:
            backend = store.set_key(request.provider, request.key)
            os.environ[f"{request.provider.upper()}_API_KEY"] = request.key
            return {
                "status": "success",
                "provider": request.provider,
                "backend": backend,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to store key: {e}")
    else:
        raise HTTPException(
            status_code=503,
            detail=(
                "No secure storage backend available. "
                "Install 'keyring' or 'cryptography': pip install keyring cryptography"
            ),
        )


@router.delete("/api/keys/{provider}")
async def remove_api_key(provider: str):
    """Remove a stored API key from secure store."""
    store = _get_secure_store()
    if store:
        store.delete_key(provider)
    # Also remove from legacy
    keys_file = SETTINGS_DIR / "api_keys.json"
    if keys_file.exists():
        try:
            keys = json.loads(keys_file.read_text())
            keys.pop(provider, None)
            keys_file.write_text(json.dumps(keys, indent=2))
        except Exception:
            pass
    os.environ.pop(f"{provider.upper()}_API_KEY", None)
    return {"status": "success", "provider": provider}


@router.post("/api/keys/migrate")
async def migrate_legacy_keys():
    """Migrate plaintext API keys to secure store."""
    store = _get_secure_store()
    if not store:
        raise HTTPException(status_code=503, detail="No secure storage backend available")
    migrated = store.migrate_plaintext_keys()
    return {"status": "success", "migrated": migrated}


@router.get("/api/keys/store-status")
async def get_key_store_status():
    """Get secure store diagnostics."""
    store = _get_secure_store()
    if store:
        return store.get_status()
    return {
        "available": False,
        "backend": "none",
        "message": "Install 'keyring' or 'cryptography' for secure storage",
    }


# =============================================================================
# OAUTH AUTHENTICATION
# =============================================================================

OAUTH_PLATFORMS = {
    "google": {
        "name": "Google",
        "description": "Access Gemini AI, Google Workspace, YouTube",
        "scopes": ["openid", "profile", "email"],
        "free_tier": "1500 req/day Gemini free",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "revoke_url": "https://oauth2.googleapis.com/revoke",
        "supports_pkce": True,
    },
    "github": {
        "name": "GitHub",
        "description": "Repository access, issues, pull requests, Copilot",
        "scopes": ["repo", "read:org", "read:user"],
        "free_tier": "Public repos free",
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "revoke_url": None,
        "supports_pkce": False,
    },
    "gitlab": {
        "name": "GitLab",
        "description": "Repository access, CI/CD, merge requests",
        "scopes": ["api", "read_user", "read_repository"],
        "free_tier": "Public repos free",
        "auth_url": "https://gitlab.com/oauth/authorize",
        "token_url": "https://gitlab.com/oauth/token",
        "revoke_url": "https://gitlab.com/oauth/revoke",
        "supports_pkce": True,
    },
    "microsoft": {
        "name": "Microsoft",
        "description": "Azure OpenAI, OneDrive, Office 365",
        "scopes": ["openid", "profile", "User.Read"],
        "free_tier": "Azure free tier available",
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "revoke_url": None,
        "supports_pkce": True,
    },
    "slack": {
        "name": "Slack",
        "description": "Send messages, read channels, team notifications",
        "scopes": ["channels:read", "chat:write", "users:read", "team:read"],
        "free_tier": "Free for small teams",
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "revoke_url": "https://slack.com/api/auth.revoke",
        "supports_pkce": False,
    },
    "discord": {
        "name": "Discord",
        "description": "Send messages, read servers, notifications",
        "scopes": ["identify", "guilds", "bot", "messages.read"],
        "free_tier": "Free",
        "auth_url": "https://discord.com/api/oauth2/authorize",
        "token_url": "https://discord.com/api/oauth2/token",
        "revoke_url": "https://discord.com/api/oauth2/token/revoke",
        "supports_pkce": False,
    },
    "notion": {
        "name": "Notion",
        "description": "Access pages, databases, and project docs",
        "scopes": [],
        "free_tier": "Free personal plan",
        "auth_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "revoke_url": None,
        "supports_pkce": False,
        "owner": "user",
    },
    "linear": {
        "name": "Linear",
        "description": "Issue tracking and project management",
        "scopes": ["read", "write", "issues:create"],
        "free_tier": "Free for small teams",
        "auth_url": "https://linear.app/oauth/authorize",
        "token_url": "https://api.linear.app/oauth/token",
        "revoke_url": "https://api.linear.app/oauth/revoke",
        "supports_pkce": True,
    },
    "atlassian": {
        "name": "Jira / Atlassian",
        "description": "Issue tracking, Confluence docs, Bitbucket",
        "scopes": ["read:jira-work", "write:jira-work", "read:jira-user", "offline_access"],
        "free_tier": "Free for up to 10 users",
        "auth_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "revoke_url": None,
        "supports_pkce": True,
        "audience": "api.atlassian.com",
    },
}

# In-memory PKCE state storage (short-lived, per-session)
_oauth_pending: Dict[str, Dict[str, str]] = {}


def _generate_pkce_pair() -> tuple:
    """Generate PKCE code_verifier + code_challenge (S256)."""
    rand = secrets.SystemRandom()
    code_verifier = ''.join(rand.choices(string.ascii_letters + string.digits, k=128))
    code_sha256 = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(code_sha256).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge


def _load_oauth_state() -> dict:
    """Load OAuth token state. Client credentials stored in SecureStore."""
    oauth_file = SETTINGS_DIR / "oauth_tokens.json"
    if oauth_file.exists():
        try:
            return json.loads(oauth_file.read_text())
        except Exception:
            pass
    return {}


def _save_oauth_state(state: dict):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    (SETTINGS_DIR / "oauth_tokens.json").write_text(json.dumps(state, indent=2))


@router.get("/api/oauth/status")
async def get_oauth_status():
    """Get OAuth status for all supported platforms."""
    saved = _load_oauth_state()
    store = _get_secure_store()
    result = {}
    for key, platform in OAUTH_PLATFORMS.items():
        token_state = saved.get(key, {})
        has_client_id = False
        if store:
            has_client_id = store.has_key(f"oauth_{key}_client_id")
        # Fallback: check legacy oauth_state.json
        if not has_client_id:
            legacy_file = SETTINGS_DIR / "oauth_state.json"
            if legacy_file.exists():
                try:
                    legacy = json.loads(legacy_file.read_text())
                    has_client_id = bool(legacy.get(key, {}).get("client_id"))
                except Exception:
                    pass

        is_authenticated = bool(token_state.get("access_token"))
        expires_at = token_state.get("expires_at")
        if expires_at and time.time() > expires_at:
            is_authenticated = False  # Token expired

        result[key] = {
            "name": platform["name"],
            "description": platform["description"],
            "scopes": ", ".join(platform["scopes"]),
            "free_tier": platform["free_tier"],
            "configured": has_client_id,
            "authenticated": is_authenticated,
            "expires_at": expires_at,
            "supports_pkce": platform["supports_pkce"],
        }
    return result


@router.post("/api/oauth/configure")
async def configure_oauth(request: OAuthConfigureRequest):
    """Store OAuth client credentials in SecureStore."""
    if request.provider not in OAUTH_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown OAuth provider: {request.provider}")

    store = _get_secure_store()
    if store:
        store.set_key(f"oauth_{request.provider}_client_id", request.client_id)
        if request.client_secret:
            store.set_key(f"oauth_{request.provider}_client_secret", request.client_secret)
        return {"status": "success", "provider": request.provider, "backend": store.backend_name}
    else:
        raise HTTPException(
            status_code=503,
            detail="No secure storage backend. Install 'keyring' or 'cryptography'.",
        )


@router.post("/api/oauth/login")
async def oauth_login(request: OAuthLoginRequest):
    """
    Initiate OAuth2 Authorization Code flow with PKCE.

    Returns the auth_url for the frontend to redirect the user to.
    The callback will be handled by /api/oauth/callback.
    """
    if request.provider not in OAUTH_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown OAuth provider: {request.provider}")

    platform = OAUTH_PLATFORMS[request.provider]
    store = _get_secure_store()

    # Retrieve client_id from secure store or legacy
    client_id = None
    if store:
        client_id = store.get_key(f"oauth_{request.provider}_client_id")
    if not client_id:
        legacy_file = SETTINGS_DIR / "oauth_state.json"
        if legacy_file.exists():
            try:
                legacy = json.loads(legacy_file.read_text())
                client_id = legacy.get(request.provider, {}).get("client_id")
            except Exception:
                pass
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="OAuth not configured. Set client_id first via /api/oauth/configure.",
        )

    # Generate PKCE pair and state token
    code_verifier, code_challenge = _generate_pkce_pair()
    state_token = secrets.token_urlsafe(32)

    # Store pending auth (short-lived)
    _oauth_pending[state_token] = {
        "provider": request.provider,
        "code_verifier": code_verifier,
        "created_at": str(time.time()),
    }

    # Use provided redirect_uri or default to our callback
    redirect_uri = request.redirect_uri or "http://localhost:8000/api/oauth/callback"

    # Build authorization URL
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state_token,
    }

    # Add scopes (some providers like Notion have no explicit scopes)
    scopes = platform.get("scopes", [])
    if scopes:
        params["scope"] = " ".join(scopes)

    if platform.get("supports_pkce"):
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    # Atlassian requires audience parameter
    if platform.get("audience"):
        params["audience"] = platform["audience"]
        params["prompt"] = "consent"

    # Notion uses owner=user
    if platform.get("owner"):
        params["owner"] = platform["owner"]

    auth_url = f"{platform['auth_url']}?{urlencode(params)}"
    return {
        "status": "redirect",
        "auth_url": auth_url,
        "provider": request.provider,
        "state": state_token,
    }


@router.get("/api/oauth/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """
    OAuth2 callback handler.

    Receives the authorization code from the OAuth provider,
    exchanges it for access + refresh tokens using PKCE verification.
    Returns an HTML page that closes itself and notifies the parent window.
    """
    # Validate state token
    pending = _oauth_pending.pop(state, None)
    if not pending:
        return HTMLResponse(
            "<html><body><h2>Error: Invalid or expired OAuth state.</h2>"
            "<p>Please try logging in again from the Settings page.</p></body></html>",
            status_code=400,
        )

    provider = pending["provider"]
    code_verifier = pending["code_verifier"]
    platform = OAUTH_PLATFORMS[provider]
    store = _get_secure_store()

    # Retrieve client credentials
    client_id = store.get_key(f"oauth_{provider}_client_id") if store else None
    client_secret = store.get_key(f"oauth_{provider}_client_secret") if store else None

    # Fallback to legacy
    if not client_id:
        legacy_file = SETTINGS_DIR / "oauth_state.json"
        if legacy_file.exists():
            try:
                legacy = json.loads(legacy_file.read_text())
                pstate = legacy.get(provider, {})
                client_id = client_id or pstate.get("client_id")
                client_secret = client_secret or pstate.get("client_secret")
            except Exception:
                pass

    if not client_id:
        return HTMLResponse(
            "<html><body><h2>Error: OAuth client_id not found.</h2></body></html>",
            status_code=400,
        )

    # Exchange authorization code for tokens
    import httpx
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "http://localhost:8000/api/oauth/callback",
        "client_id": client_id,
    }
    if client_secret:
        token_data["client_secret"] = client_secret
    if platform.get("supports_pkce"):
        token_data["code_verifier"] = code_verifier

    headers = {"Accept": "application/json"}

    # Notion uses Basic auth (base64 of client_id:client_secret) instead of POST body
    if provider == "notion" and client_secret:
        import base64 as b64
        basic_creds = b64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {basic_creds}"
        token_data.pop("client_id", None)
        token_data.pop("client_secret", None)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                platform["token_url"],
                data=token_data,
                headers=headers,
            )
            if resp.status_code != 200:
                return HTMLResponse(
                    f"<html><body><h2>Token exchange failed</h2>"
                    f"<p>{resp.status_code}: {resp.text[:500]}</p></body></html>",
                    status_code=400,
                )
            tokens = resp.json()
    except Exception as e:
        return HTMLResponse(
            f"<html><body><h2>Token exchange error</h2><p>{e}</p></body></html>",
            status_code=500,
        )

    # Extract access_token -- different providers return it in different places
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    # Slack returns tokens nested under authed_user or bot
    if provider == "slack":
        access_token = (
            tokens.get("access_token")
            or (tokens.get("authed_user") or {}).get("access_token")
        )

    # Notion returns access_token at top level but also workspace info
    if provider == "notion":
        access_token = tokens.get("access_token")
        expires_in = 0  # Notion tokens don't expire

    # Store tokens
    oauth_state = _load_oauth_state()
    oauth_state[provider] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_at": time.time() + expires_in if expires_in else 0,
        "scope": tokens.get("scope", ""),
    }
    _save_oauth_state(oauth_state)

    # Also store access token in secure store for other modules
    if store and access_token:
        store.set_key(f"oauth_{provider}_access_token", access_token)
        if refresh_token:
            store.set_key(f"oauth_{provider}_refresh_token", refresh_token)

    # Return HTML that closes the popup and signals the parent
    return HTMLResponse(
        f"""<html>
<head><title>Orion -- OAuth Success</title></head>
<body style="font-family: system-ui; text-align: center; padding: 40px;">
  <h2 style="color: #22c55e;">✓ {OAUTH_PLATFORMS[provider]['name']} Connected</h2>
  <p>You can close this window. The Settings page will update automatically.</p>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{type: 'oauth_success', provider: '{provider}'}}, '*');
    }}
    setTimeout(() => window.close(), 2000);
  </script>
</body></html>"""
    )


@router.post("/api/oauth/revoke")
async def oauth_revoke(request: OAuthRevokeRequest):
    """Revoke OAuth tokens for a platform."""
    if request.provider not in OAUTH_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown OAuth provider: {request.provider}")

    platform = OAUTH_PLATFORMS[request.provider]
    state = _load_oauth_state()
    token_state = state.get(request.provider, {})
    access_token = token_state.get("access_token")

    # Attempt remote revocation if the provider supports it
    if access_token and platform.get("revoke_url"):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    platform["revoke_url"],
                    data={"token": access_token},
                )
        except Exception as e:
            logger.debug(f"Remote revocation failed for {request.provider}: {e}")

    # Clear local tokens
    if request.provider in state:
        state.pop(request.provider)
        _save_oauth_state(state)

    # Clear from secure store
    store = _get_secure_store()
    if store:
        store.delete_key(f"oauth_{request.provider}_access_token")
        store.delete_key(f"oauth_{request.provider}_refresh_token")

    return {"status": "success", "provider": request.provider}


# =============================================================================
# ONE-CLICK OAUTH (uses oauth_manager module)
# =============================================================================

@router.get("/api/oauth/providers")
async def list_oauth_providers():
    """List all OAuth providers with connection status and setup steps."""
    try:
        from orion.integrations.oauth_manager import get_provider_status
        return get_provider_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/oauth/connect/{provider}")
async def oauth_connect(provider: str):
    """
    Start OAuth connection flow for a provider.
    - GitHub: returns device_code + user_code for Device Flow
    - PKCE providers: returns auth_url for popup
    - oauth_secret providers: returns auth_url (needs client_id/secret first)
    """
    try:
        from orion.integrations.oauth_manager import (
            PROVIDERS, get_client_id, get_client_secret,
            github_device_flow_start, build_auth_url,
        )

        if provider not in PROVIDERS:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

        prov = PROVIDERS[provider]
        client_id = get_client_id(provider)

        if not client_id:
            return {
                "status": "needs_setup",
                "provider": provider,
                "auth_type": prov["auth_type"],
                "message": f"Configure a Client ID for {prov['name']} first",
                "setup_steps": _get_provider_setup_help(provider, prov),
            }

        # GitHub Device Flow -- best UX for desktop apps
        if prov["auth_type"] == "device_flow":
            device_data = await github_device_flow_start(client_id)
            return {
                "status": "device_flow",
                "provider": provider,
                "user_code": device_data.get("user_code"),
                "verification_uri": device_data.get("verification_uri"),
                "device_code": device_data.get("device_code"),
                "expires_in": device_data.get("expires_in", 900),
                "interval": device_data.get("interval", 5),
            }

        # PKCE or oauth_secret -- redirect to auth URL
        if prov["auth_type"] == "oauth_secret":
            client_secret = get_client_secret(provider)
            if not client_secret:
                return {
                    "status": "needs_setup",
                    "provider": provider,
                    "auth_type": prov["auth_type"],
                    "message": f"Configure Client Secret for {prov['name']}",
                }

        redirect_uri = "http://localhost:8000/api/oauth/callback"
        auth_url, state_token = build_auth_url(provider, redirect_uri, client_id)
        return {
            "status": "redirect",
            "provider": provider,
            "auth_url": auth_url,
            "state": state_token,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_provider_setup_help(provider: str, prov: dict) -> list:
    """Get setup help for providers that need client_id/secret."""
    setup_urls = {
        "github": "https://github.com/settings/developers",
        "google": "https://console.cloud.google.com/apis/credentials",
        "microsoft": "https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps",
        "gitlab": "https://gitlab.com/-/user_settings/applications",
        "linear": "https://linear.app/settings/api",
        "atlassian": "https://developer.atlassian.com/console/myapps/",
        "slack": "https://api.slack.com/apps",
        "discord": "https://discord.com/developers/applications",
        "notion": "https://www.notion.so/my-integrations",
    }
    url = setup_urls.get(provider, "")
    return [
        f"1. Go to {url}",
        f"2. Create a new OAuth App for Orion",
        f"3. Set the callback URL to: http://localhost:8000/api/oauth/callback",
        f"4. Copy the Client ID (and Secret if needed) and paste below",
    ]


@router.post("/api/oauth/device-poll/{provider}")
async def oauth_device_poll(provider: str, device_code: str = ""):
    """Poll for GitHub Device Flow completion."""
    try:
        from orion.integrations.oauth_manager import (
            PROVIDERS, get_client_id, github_device_flow_poll,
            _load_oauth_tokens, _save_oauth_tokens,
        )

        if provider not in PROVIDERS:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

        client_id = get_client_id(provider)
        if not client_id or not device_code:
            raise HTTPException(status_code=400, detail="Missing client_id or device_code")

        result = await github_device_flow_poll(client_id, device_code)

        if result is None:
            return {"status": "pending", "message": "Waiting for user authorization..."}

        # Got token -- store it
        access_token = result.get("access_token")
        stored = _load_oauth_tokens()
        stored[provider] = {
            "access_token": access_token,
            "refresh_token": result.get("refresh_token"),
            "token_type": result.get("token_type", "bearer"),
            "scope": result.get("scope", ""),
            "connected_at": time.time(),
            "expires_at": 0,
        }
        _save_oauth_tokens(stored)

        # Also store in SecureStore
        store = _get_secure_store()
        if store and access_token:
            store.set_key(f"oauth_{provider}_access_token", access_token)

        return {"status": "success", "provider": provider, "name": PROVIDERS[provider]["name"]}

    except HTTPException:
        raise
    except Exception as e:
        if "expired" in str(e).lower() or "denied" in str(e).lower():
            return {"status": "error", "message": str(e)}
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/oauth/token/{provider}")
async def store_oauth_token(provider: str, token: str = ""):
    """Store a manually provided token (PAT, bot token, integration token)."""
    try:
        from orion.integrations.oauth_manager import PROVIDERS, store_manual_token

        if provider not in PROVIDERS:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
        if not token:
            raise HTTPException(status_code=400, detail="Token is required")

        store_manual_token(provider, token)

        # Also store in SecureStore
        store = _get_secure_store()
        if store:
            store.set_key(f"oauth_{provider}_access_token", token)

        return {"status": "success", "provider": provider, "name": PROVIDERS[provider]["name"]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/oauth/disconnect/{provider}")
async def oauth_disconnect(provider: str):
    """Disconnect a provider -- remove all stored tokens."""
    try:
        from orion.integrations.oauth_manager import PROVIDERS, disconnect_provider

        if provider not in PROVIDERS:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

        disconnect_provider(provider)
        return {"status": "success", "provider": provider}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/oauth/setup/{provider}")
async def oauth_setup_client(provider: str, client_id: str = "", client_secret: str = ""):
    """Store OAuth client_id and client_secret for a provider."""
    try:
        from orion.integrations.oauth_manager import (
            PROVIDERS, _load_client_configs, _save_client_configs,
        )

        if provider not in PROVIDERS:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id is required")

        configs = _load_client_configs()
        configs[provider] = {
            "client_id": client_id,
            "client_secret": client_secret or None,
        }
        _save_client_configs(configs)

        # Also store in SecureStore for backward compat
        store = _get_secure_store()
        if store:
            store.set_key(f"oauth_{provider}_client_id", client_id)
            if client_secret:
                store.set_key(f"oauth_{provider}_client_secret", client_secret)

        return {"status": "success", "provider": provider, "configured": True}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
