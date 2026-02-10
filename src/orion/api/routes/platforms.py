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
"""Orion Agent -- Platform & Integration Routes."""

import os
import json
import time
import secrets
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException

from orion.api._shared import (
    PlatformConnectRequest, SETTINGS_DIR, _get_secure_store,
)
from orion.api.routes.auth import (
    OAUTH_PLATFORMS, _oauth_pending, _generate_pkce_pair,
)

router = APIRouter()


# =============================================================================
# PLATFORMS (Comprehensive service registry)
# =============================================================================

@router.get("/api/platforms")
async def list_platforms():
    """List ALL platforms Orion can connect to, grouped by category."""
    try:
        from orion.integrations.platforms import get_platform_registry, CATEGORY_LABELS
        registry = get_platform_registry()
        by_category = registry.list_by_category()
        return {
            "categories": CATEGORY_LABELS,
            "platforms": by_category,
            "total": sum(len(v) for v in by_category.values()),
            "connected": len(registry.list_connected()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/platforms/connected")
async def list_connected_platforms():
    """List only connected platforms."""
    try:
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        return {"platforms": registry.list_connected()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/platforms/capabilities")
async def list_platform_capabilities():
    """List all available capabilities from connected platforms."""
    try:
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        return {"capabilities": registry.list_capabilities()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/platforms/{platform_id}")
async def get_platform(platform_id: str):
    """Get details for a specific platform."""
    from orion.integrations.platforms import get_platform_registry
    registry = get_platform_registry()
    platform = registry.get(platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform_id}")
    return registry._serialize(platform)


@router.post("/api/platforms/connect")
async def connect_platform(request: PlatformConnectRequest):
    """
    Connect a platform by storing its token/key in SecureStore.

    For OAuth platforms: use /api/oauth/login instead (opens browser popup).
    For API key / token platforms: provide the key here.
    """
    from orion.integrations.platforms import get_platform_registry
    registry = get_platform_registry()
    platform = registry.get(request.platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {request.platform_id}")

    credential = request.token or request.api_key
    if not credential:
        # For OAuth platforms, redirect to OAuth flow
        if platform.oauth_provider:
            return {
                "status": "redirect",
                "message": f"Use OAuth to connect {platform.name}",
                "oauth_provider": platform.oauth_provider,
                "action": "oauth_login",
            }
        raise HTTPException(status_code=400, detail="Provide a token or api_key")

    if len(credential) < 4:
        raise HTTPException(status_code=400, detail="Token/key too short")

    store = _get_secure_store()
    if not store:
        raise HTTPException(status_code=503, detail="No secure storage backend available")

    backend = store.set_key(platform.secure_store_key or platform.id, credential)

    # Also set env var for current session
    if platform.env_var:
        os.environ[platform.env_var] = credential

    registry.refresh()
    return {
        "status": "success",
        "platform": platform.id,
        "name": platform.name,
        "backend": backend,
    }


@router.post("/api/platforms/disconnect")
async def disconnect_platform(request: PlatformConnectRequest):
    """Disconnect a platform by removing its credentials."""
    from orion.integrations.platforms import get_platform_registry
    registry = get_platform_registry()
    platform = registry.get(request.platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {request.platform_id}")

    store = _get_secure_store()

    # Remove from SecureStore
    if store:
        store.delete_key(platform.secure_store_key or platform.id)
        if platform.oauth_provider:
            store.delete_key(f"oauth_{platform.oauth_provider}_access_token")
            store.delete_key(f"oauth_{platform.oauth_provider}_refresh_token")

    # Remove from env
    if platform.env_var:
        os.environ.pop(platform.env_var, None)

    registry.refresh()
    return {"status": "success", "platform": platform.id}


@router.post("/api/platforms/{platform_id}/oauth-connect")
async def oauth_connect_platform(platform_id: str):
    """
    Simplified OAuth connect -- one-click flow.

    Returns an auth_url that the frontend opens in a popup.
    The OAuth callback handler closes the popup automatically.
    """
    from orion.integrations.platforms import get_platform_registry
    registry = get_platform_registry()
    platform = registry.get(platform_id)
    if not platform or not platform.oauth_provider:
        raise HTTPException(status_code=400, detail=f"Platform '{platform_id}' doesn't support OAuth")

    provider = platform.oauth_provider
    if provider not in OAUTH_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"OAuth provider '{provider}' not configured")

    oauth_platform = OAUTH_PLATFORMS[provider]
    store = _get_secure_store()

    # Check if client_id is configured
    client_id = None
    if store:
        client_id = store.get_key(f"oauth_{provider}_client_id")
    if not client_id:
        # Check legacy
        legacy_file = SETTINGS_DIR / "oauth_state.json"
        if legacy_file.exists():
            try:
                legacy = json.loads(legacy_file.read_text())
                client_id = legacy.get(provider, {}).get("client_id")
            except Exception:
                pass

    if not client_id:
        # Return setup instructions instead of error
        return {
            "status": "setup_required",
            "platform": platform_id,
            "provider": provider,
            "message": f"OAuth app not configured yet for {platform.name}.",
            "setup_url": platform.setup_url,
            "setup_instructions": platform.setup_instructions,
            "fields_needed": ["client_id"],
            "hint": f"Create an OAuth app at {platform.setup_url}, then enter the Client ID below.",
        }

    # Generate PKCE and auth URL
    code_verifier, code_challenge = _generate_pkce_pair()
    state_token = secrets.token_urlsafe(32)

    _oauth_pending[state_token] = {
        "provider": provider,
        "code_verifier": code_verifier,
        "created_at": str(time.time()),
    }

    redirect_uri = "http://localhost:8000/api/oauth/callback"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state_token,
    }

    # Add scopes (some providers like Notion have no explicit scopes)
    scopes = oauth_platform.get("scopes", [])
    if scopes:
        params["scope"] = " ".join(scopes)

    # PKCE support
    if oauth_platform.get("supports_pkce"):
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    # Atlassian requires audience parameter
    if oauth_platform.get("audience"):
        params["audience"] = oauth_platform["audience"]
        params["prompt"] = "consent"

    # Notion uses owner=user
    if oauth_platform.get("owner"):
        params["owner"] = oauth_platform["owner"]

    auth_url = f"{oauth_platform['auth_url']}?{urlencode(params)}"
    return {
        "status": "redirect",
        "auth_url": auth_url,
        "provider": provider,
        "platform": platform_id,
        "state": state_token,
    }


# =============================================================================
# INTEGRATIONS
# =============================================================================

@router.get("/api/integrations")
async def list_integrations():
    """List all registered integrations."""
    try:
        from orion.integrations.registry import get_registry
        reg = get_registry()
        if reg.count == 0:
            reg.discover()
        return reg.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/integrations/health")
async def integration_health():
    """Run integration health checks."""
    try:
        from orion.integrations.health import IntegrationHealthChecker
        checker = IntegrationHealthChecker()
        return checker.get_dashboard()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/integrations/discover")
async def discover_integrations():
    """Run integration auto-discovery."""
    try:
        from orion.integrations.registry import get_registry
        reg = get_registry()
        count = reg.discover()
        return {"discovered": count, "total": reg.count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
