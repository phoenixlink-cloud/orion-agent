"""
OAuth Manager for Orion — handles one-click authentication for all providers.

Architecture (based on research of Open WebUI, NextAuth.js, ToolJet):
- Tier 1: PKCE OAuth (GitHub, Google, Microsoft, GitLab, Linear, Atlassian)
  → User clicks "Connect" → browser opens → sign in → done
  → GitHub also supports Device Flow (best for desktop/CLI apps)
- Tier 2: Guided token setup (Slack, Discord, Notion, Telegram)
  → Step-by-step wizard in UI → user creates token → pastes it
- Tier 3: API key (OpenAI, Anthropic, etc.)
  → Standard key input
"""

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import string
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

log = logging.getLogger(__name__)

SETTINGS_DIR = Path.home() / ".orion"

# ---------------------------------------------------------------------------
# Provider definitions — the single source of truth for OAuth configs
# ---------------------------------------------------------------------------

PROVIDERS: Dict[str, Dict[str, Any]] = {
    # Only Google and Microsoft need OAuth — all other platforms now use
    # CLI tools (gh, glab) or bot tokens (Slack, Discord, Notion, etc.)
    # per the CLI delegation pattern. See internal-audit-reference.
    "google": {
        "name": "Google",
        "description": "Gemini AI, Google Workspace, Drive, YouTube",
        "auth_type": "pkce",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "revoke_url": "https://oauth2.googleapis.com/revoke",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scopes": ["openid", "profile", "email"],
        "supports_pkce": True,
        "icon": "🔵",
    },
    "microsoft": {
        "name": "Microsoft",
        "description": "Azure OpenAI, OneDrive, Office 365",
        "auth_type": "pkce",
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        "scopes": ["openid", "profile", "User.Read"],
        "supports_pkce": True,
        "icon": "🟦",
    },
}

# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def generate_pkce_pair() -> Tuple[str, str]:
    """Generate PKCE code_verifier + code_challenge (S256)."""
    rand = secrets.SystemRandom()
    code_verifier = "".join(rand.choices(string.ascii_letters + string.digits, k=128))
    code_sha256 = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(code_sha256).decode("utf-8").rstrip("=")
    return code_verifier, code_challenge


# ---------------------------------------------------------------------------
# Pending auth state (in-memory, short-lived)
# ---------------------------------------------------------------------------

_pending_auth: Dict[str, Dict[str, Any]] = {}


def _load_oauth_tokens() -> Dict[str, Any]:
    """Load stored OAuth tokens from disk."""
    path = SETTINGS_DIR / "oauth_tokens.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _save_oauth_tokens(tokens: Dict[str, Any]):
    """Save OAuth tokens to disk."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = SETTINGS_DIR / "oauth_tokens.json"
    path.write_text(json.dumps(tokens, indent=2))


def _load_client_configs() -> Dict[str, Any]:
    """Load OAuth client_id / client_secret configs."""
    path = SETTINGS_DIR / "oauth_clients.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _save_client_configs(configs: Dict[str, Any]):
    """Save OAuth client configs."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = SETTINGS_DIR / "oauth_clients.json"
    path.write_text(json.dumps(configs, indent=2))


def get_client_id(provider: str) -> Optional[str]:
    """Get client_id for a provider from config or env."""
    import os
    # Check environment first
    env_key = f"ORION_{provider.upper()}_CLIENT_ID"
    env_val = os.environ.get(env_key)
    if env_val:
        return env_val
    # Check stored config
    configs = _load_client_configs()
    return configs.get(provider, {}).get("client_id")


def get_client_secret(provider: str) -> Optional[str]:
    """Get client_secret for a provider from config or env."""
    import os
    env_key = f"ORION_{provider.upper()}_CLIENT_SECRET"
    env_val = os.environ.get(env_key)
    if env_val:
        return env_val
    configs = _load_client_configs()
    return configs.get(provider, {}).get("client_secret")


# ---------------------------------------------------------------------------
# GitHub Device Flow — best UX for desktop apps
# ---------------------------------------------------------------------------

async def github_device_flow_start(client_id: str) -> Dict[str, Any]:
    """
    Start GitHub Device Flow. Returns device_code, user_code, verification_uri.
    User opens verification_uri and enters user_code. We poll for the token.
    """
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://github.com/login/device/code",
            data={
                "client_id": client_id,
                "scope": " ".join(PROVIDERS["github"]["scopes"]),
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise Exception(f"GitHub device flow start failed: {resp.status_code} {resp.text}")
        return resp.json()


async def github_device_flow_poll(client_id: str, device_code: str, interval: int = 5) -> Optional[Dict[str, Any]]:
    """
    Poll GitHub for device flow token. Returns token dict or None if pending.
    Raises on error (expired, access_denied, etc.)
    """
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Accept": "application/json"},
        )
        data = resp.json()

        if "access_token" in data:
            return data
        error = data.get("error")
        if error == "authorization_pending":
            return None  # Still waiting
        if error == "slow_down":
            return None  # Wait longer
        if error in ("expired_token", "access_denied"):
            raise Exception(f"GitHub auth {error}: {data.get('error_description', '')}")
        return None


# ---------------------------------------------------------------------------
# Standard OAuth2 + PKCE flow
# ---------------------------------------------------------------------------

def build_auth_url(provider: str, redirect_uri: str, client_id: str) -> Tuple[str, str]:
    """
    Build the authorization URL for a provider. Returns (auth_url, state_token).
    Stores PKCE state for callback.
    """
    prov = PROVIDERS.get(provider)
    if not prov:
        raise ValueError(f"Unknown provider: {provider}")

    state_token = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce_pair()

    params: Dict[str, str] = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state_token,
    }

    # Add scopes if any
    if prov.get("scopes"):
        params["scope"] = " ".join(prov["scopes"])

    # Add PKCE if supported
    if prov.get("supports_pkce"):
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    # Add provider-specific extra params
    if prov.get("extra_params"):
        params.update(prov["extra_params"])

    # Store pending auth state
    _pending_auth[state_token] = {
        "provider": provider,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "created_at": time.time(),
    }

    auth_url = f"{prov['auth_url']}?{urlencode(params)}"
    return auth_url, state_token


async def exchange_code_for_token(
    state_token: str,
    code: str,
) -> Dict[str, Any]:
    """
    Exchange authorization code for tokens using stored pending state.
    Handles provider-specific quirks (Notion Basic auth, Slack nested tokens, etc.)
    """
    import httpx

    pending = _pending_auth.pop(state_token, None)
    if not pending:
        raise ValueError("Invalid or expired state token")

    provider = pending["provider"]
    prov = PROVIDERS[provider]
    code_verifier = pending["code_verifier"]
    redirect_uri = pending["redirect_uri"]

    client_id = get_client_id(provider)
    client_secret = get_client_secret(provider)

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if client_secret and prov.get("token_auth") != "basic":
        token_data["client_secret"] = client_secret
    if prov.get("supports_pkce"):
        token_data["code_verifier"] = code_verifier

    headers = {"Accept": "application/json"}

    # Notion uses Basic auth for token exchange
    if prov.get("token_auth") == "basic" and client_secret:
        basic_creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {basic_creds}"
        token_data.pop("client_id", None)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            prov["token_url"],
            data=token_data,
            headers=headers,
        )
        if resp.status_code != 200:
            raise Exception(f"Token exchange failed: {resp.status_code} {resp.text[:500]}")
        tokens = resp.json()

    # Extract access_token — handle provider-specific response formats
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    # Slack nests tokens under authed_user
    if prov.get("token_path"):
        parts = prov["token_path"].split(".")
        nested = tokens
        for part in parts:
            nested = nested.get(part, {}) if isinstance(nested, dict) else {}
        if isinstance(nested, str):
            access_token = nested

    # Notion tokens don't expire
    if provider == "notion":
        expires_in = 0

    # Store tokens
    stored = _load_oauth_tokens()
    stored[provider] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_at": time.time() + expires_in if expires_in else 0,
        "scope": tokens.get("scope", ""),
        "connected_at": time.time(),
    }
    _save_oauth_tokens(stored)

    # Also store in SecureStore if available
    try:
        from orion.security.secure_store import get_secure_store
        store = get_secure_store()
        if store and access_token:
            store.set_key(f"oauth_{provider}_access_token", access_token)
            if refresh_token:
                store.set_key(f"oauth_{provider}_refresh_token", refresh_token)
    except Exception:
        pass

    return {
        "provider": provider,
        "name": prov["name"],
        "access_token": access_token is not None,
        "has_refresh": refresh_token is not None,
    }


# ---------------------------------------------------------------------------
# Token storage for guided setup (Tier 2 — user pastes a token)
# ---------------------------------------------------------------------------

def store_manual_token(provider: str, token: str) -> bool:
    """Store a manually provided token (PAT, bot token, etc.)."""
    stored = _load_oauth_tokens()
    stored[provider] = {
        "access_token": token,
        "refresh_token": None,
        "token_type": "Bearer",
        "expires_at": 0,
        "scope": "manual",
        "connected_at": time.time(),
    }
    _save_oauth_tokens(stored)
    return True


def disconnect_provider(provider: str) -> bool:
    """Remove stored tokens for a provider."""
    stored = _load_oauth_tokens()
    if provider in stored:
        del stored[provider]
        _save_oauth_tokens(stored)

    # Also clear from SecureStore
    try:
        from orion.security.secure_store import get_secure_store
        store = get_secure_store()
        if store:
            store.delete_key(f"oauth_{provider}_access_token")
            store.delete_key(f"oauth_{provider}_refresh_token")
    except Exception:
        pass

    return True


# ---------------------------------------------------------------------------
# Status / listing
# ---------------------------------------------------------------------------

def get_provider_status() -> Dict[str, Any]:
    """Get connection status for all providers."""
    stored = _load_oauth_tokens()
    result = {}

    for pid, prov in PROVIDERS.items():
        connected = pid in stored and stored[pid].get("access_token")
        needs_secret = prov["auth_type"] == "oauth_secret"
        has_client_id = get_client_id(pid) is not None
        has_client_secret = get_client_secret(pid) is not None if needs_secret else True

        result[pid] = {
            "name": prov["name"],
            "description": prov["description"],
            "icon": prov.get("icon", "🔌"),
            "auth_type": prov["auth_type"],
            "connected": bool(connected),
            "connected_at": stored.get(pid, {}).get("connected_at"),
            "configured": has_client_id and has_client_secret,
            "needs_setup": not has_client_id,
            "setup_steps": _get_setup_steps(pid, prov),
        }

    return result


def _get_setup_steps(provider_id: str, prov: Dict) -> list:
    """Get user-friendly setup steps for a provider."""
    setup_urls = {
        "google": "https://console.cloud.google.com/apis/credentials",
        "microsoft": "https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps",
    }
    url = setup_urls.get(provider_id, "")
    return [
        {"step": 1, "text": f"Create an OAuth app at {prov['name']}", "action": "open_url", "url": url},
        {"step": 2, "text": "Copy the Client ID", "action": "copy"},
        {"step": 3, "text": "Paste below, then click 'Sign In & Connect'", "action": "configure"},
    ]


# ---------------------------------------------------------------------------
# Cleanup stale pending auth states
# ---------------------------------------------------------------------------

def cleanup_pending(max_age_seconds: int = 600):
    """Remove pending auth states older than max_age_seconds."""
    now = time.time()
    expired = [k for k, v in _pending_auth.items() if now - v.get("created_at", 0) > max_age_seconds]
    for k in expired:
        del _pending_auth[k]
