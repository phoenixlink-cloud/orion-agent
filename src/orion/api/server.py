"""
Orion Agent — API Server (v6.4.0)

FastAPI server for web UI integration.
Provides REST endpoints for health, chat, settings, model config,
integrations, and WebSocket real-time chat.

Run with: uvicorn orion.api.server:app --reload --port 8000
"""

import os
import json
import time
import hashlib
import base64
import secrets
import string
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode, quote_plus

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger("orion.api.server")

app = FastAPI(
    title="Orion Agent API",
    description="REST + WebSocket API for Orion Agent",
    version="6.4.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ChatRequest(BaseModel):
    message: str
    workspace: str = ""
    mode: str = "safe"


class ModelModeRequest(BaseModel):
    mode: str  # "local" or "cloud"


class RoleConfigRequest(BaseModel):
    provider: str
    model: str
    light_model: Optional[str] = ""
    use_tiers: Optional[bool] = False


class ModelConfigRequest(BaseModel):
    mode: Optional[str] = None
    builder: Optional[RoleConfigRequest] = None
    reviewer: Optional[RoleConfigRequest] = None


class PresetRequest(BaseModel):
    name: str


class APIKeySetRequest(BaseModel):
    provider: str
    key: str


class OAuthConfigureRequest(BaseModel):
    provider: str
    client_id: str
    client_secret: Optional[str] = None


class OAuthLoginRequest(BaseModel):
    provider: str
    redirect_uri: Optional[str] = None


class OAuthRevokeRequest(BaseModel):
    provider: str


class OAuthCallbackRequest(BaseModel):
    provider: str
    code: str
    state: str


class ProviderToggleRequest(BaseModel):
    provider: str
    enabled: bool


class SettingsUpdate(BaseModel):
    # Core Features
    enable_table_of_three: Optional[bool] = None
    enable_file_tools: Optional[bool] = None
    enable_passive_memory: Optional[bool] = None
    enable_intelligent_orion: Optional[bool] = None
    enable_streaming: Optional[bool] = None
    # Intelligent Orion
    quality_threshold: Optional[float] = None
    max_refinement_iterations: Optional[int] = None
    # Governance
    default_mode: Optional[str] = None
    aegis_strict_mode: Optional[bool] = None
    # Command Execution
    enable_command_execution: Optional[bool] = None
    command_timeout_seconds: Optional[int] = None
    # Limits
    max_evidence_files: Optional[int] = None
    max_file_size_bytes: Optional[int] = None
    max_evidence_retry: Optional[int] = None
    # Web Access
    enable_web_access: Optional[bool] = None
    web_cache_ttl: Optional[int] = None
    allowed_domains: Optional[str] = None
    # Image Generation
    image_provider: Optional[str] = None
    sdxl_enabled: Optional[bool] = None
    sdxl_endpoint: Optional[str] = None
    flux_enabled: Optional[bool] = None
    dalle_enabled: Optional[bool] = None
    dalle_model: Optional[str] = None
    # Models (legacy)
    use_local_models: Optional[bool] = None
    gpt_model: Optional[str] = None
    claude_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_builder_model: Optional[str] = None
    ollama_reviewer_model: Optional[str] = None
    # Paths
    data_dir: Optional[str] = None
    ledger_file: Optional[str] = None


# =============================================================================
# SETTINGS PERSISTENCE
# =============================================================================

SETTINGS_DIR = Path.home() / ".orion"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


def _load_user_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_user_settings(settings: dict):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


# =============================================================================
# HEALTH
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint (K8s compatible)."""
    return {"status": "healthy", "version": "6.4.0"}


@app.get("/ready")
async def readiness_check():
    """Readiness probe."""
    return {"status": "ready", "version": "6.4.0"}


# =============================================================================
# CHAT (REST)
# =============================================================================

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """REST endpoint for chat (non-streaming)."""
    if not request.message:
        raise HTTPException(status_code=400, detail="No message provided")
    if not request.workspace:
        raise HTTPException(status_code=400, detail="No workspace specified")

    try:
        from orion.core.agents.router import RequestRouter
        router = RequestRouter(
            request.workspace,
            stream_output=False,
            sandbox_enabled=False,
        )
        import asyncio
        result = await router.handle_request(request.message)
        return {
            "success": result.get("success", False),
            "response": result.get("response", ""),
            "route": result.get("route", "unknown"),
            "actions": result.get("actions", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# WEBSOCKET CHAT
# =============================================================================

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time chat with Orion."""
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            user_input = data.get("message", "")
            workspace = data.get("workspace", "")
            mode = data.get("mode", "safe")

            if not user_input:
                await websocket.send_json({"type": "error", "message": "No message provided"})
                continue
            if not workspace:
                await websocket.send_json({"type": "error", "message": "No workspace specified"})
                continue

            try:
                from orion.core.agents.router import RequestRouter
                router = RequestRouter(workspace, stream_output=True, sandbox_enabled=False)

                await websocket.send_json({
                    "type": "status",
                    "message": "Processing request..."
                })

                result = await router.handle_request(user_input)

                await websocket.send_json({
                    "type": "complete",
                    "success": result.get("success", False),
                    "response": result.get("response", ""),
                    "route": result.get("route", "unknown"),
                    "actions": result.get("actions", []),
                })
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": f"WebSocket error: {e}"})
        except Exception:
            pass


# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

@app.get("/api/models/config")
async def get_model_config_endpoint():
    """Get current flexible model configuration."""
    try:
        from orion.core.llm.config import get_model_config
        cfg = get_model_config()
        reviewer = cfg.get_reviewer()
        return {
            "mode": cfg.mode,
            "builder": {
                "provider": cfg.builder.provider,
                "model": cfg.builder.model,
                "light_model": cfg.builder.light_model,
                "use_tiers": cfg.builder.use_tiers,
            },
            "reviewer": {
                "provider": reviewer.provider,
                "model": reviewer.model,
                "light_model": reviewer.light_model,
                "use_tiers": reviewer.use_tiers,
            },
            "governor": "orion (hardcoded)",
            "required_keys": cfg.get_required_keys(),
            "summary": cfg.summary(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/models/config")
async def set_model_config_endpoint(request: ModelConfigRequest):
    """Update flexible model configuration."""
    try:
        from orion.core.llm.config import (
            get_model_config, save_model_config, RoleConfig
        )
        cfg = get_model_config()

        if request.mode:
            if request.mode not in ("single", "dual"):
                raise HTTPException(status_code=400, detail="Mode must be 'single' or 'dual'")
            cfg.mode = request.mode

        if request.builder:
            cfg.builder = RoleConfig(
                provider=request.builder.provider,
                model=request.builder.model,
                light_model=request.builder.light_model or "",
                use_tiers=request.builder.use_tiers or False,
            )

        if request.reviewer:
            cfg.reviewer = RoleConfig(
                provider=request.reviewer.provider,
                model=request.reviewer.model,
                light_model=request.reviewer.light_model or "",
                use_tiers=request.reviewer.use_tiers or False,
            )
            if cfg.mode == "single" and request.builder is None:
                cfg.mode = "dual"

        errors = cfg.validate()
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))

        if save_model_config(cfg):
            return {"status": "success", "config": cfg.to_dict()}
        raise HTTPException(status_code=500, detail="Failed to save model config")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/providers")
async def get_providers():
    """Get all supported providers and their models."""
    try:
        from orion.core.llm.config import PROVIDERS, is_provider_enabled
        result = {}
        for key, info in PROVIDERS.items():
            result[key] = {**info, "enabled": is_provider_enabled(key)}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/presets")
async def get_presets():
    """Get all available model presets."""
    try:
        from orion.core.llm.config import PRESETS
        result = {}
        for name, cfg in PRESETS.items():
            reviewer = cfg.get_reviewer()
            result[name] = {
                "mode": cfg.mode,
                "builder": {"provider": cfg.builder.provider, "model": cfg.builder.model},
                "reviewer": {"provider": reviewer.provider, "model": reviewer.model},
                "required_keys": cfg.get_required_keys(),
            }
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/models/preset")
async def apply_preset_endpoint(request: PresetRequest):
    """Apply a named model preset."""
    try:
        from orion.core.llm.config import apply_preset, PRESETS
        cfg = apply_preset(request.name)
        if cfg:
            return {"status": "success", "config": cfg.to_dict(), "summary": cfg.summary()}
        raise HTTPException(
            status_code=400,
            detail=f"Unknown preset: {request.name}. Available: {list(PRESETS.keys())}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# API KEY MANAGEMENT
# =============================================================================

API_KEY_PROVIDERS = [
    {"provider": "openai", "description": "OpenAI (GPT models)"},
    {"provider": "anthropic", "description": "Anthropic (Claude models)"},
    {"provider": "google", "description": "Google (Gemini models)"},
    {"provider": "groq", "description": "Groq (fast inference)"},
]


def _get_secure_store():
    """Get SecureStore singleton. Falls back to legacy plaintext if unavailable."""
    try:
        from orion.security.store import get_secure_store
        store = get_secure_store()
        if store.is_available:
            return store
    except Exception as e:
        logger.debug(f"SecureStore unavailable: {e}")
    return None


def _load_api_keys_legacy() -> dict:
    """Legacy plaintext key loading — used only as fallback."""
    keys_file = SETTINGS_DIR / "api_keys.json"
    if keys_file.exists():
        try:
            return json.loads(keys_file.read_text())
        except Exception:
            pass
    return {}


@app.get("/api/keys/status")
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


@app.post("/api/keys/set")
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


@app.delete("/api/keys/{provider}")
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


@app.post("/api/keys/migrate")
async def migrate_legacy_keys():
    """Migrate plaintext API keys to secure store."""
    store = _get_secure_store()
    if not store:
        raise HTTPException(status_code=503, detail="No secure storage backend available")
    migrated = store.migrate_plaintext_keys()
    return {"status": "success", "migrated": migrated}


@app.get("/api/keys/store-status")
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


@app.get("/api/oauth/status")
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


@app.post("/api/oauth/configure")
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


@app.post("/api/oauth/login")
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
        "scope": " ".join(platform["scopes"]),
        "state": state_token,
    }
    if platform["supports_pkce"]:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    auth_url = f"{platform['auth_url']}?{urlencode(params)}"
    return {
        "status": "redirect",
        "auth_url": auth_url,
        "provider": request.provider,
        "state": state_token,
    }


@app.get("/api/oauth/callback")
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
    if platform["supports_pkce"]:
        token_data["code_verifier"] = code_verifier

    headers = {"Accept": "application/json"}

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

    # Store tokens
    oauth_state = _load_oauth_state()
    oauth_state[provider] = {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_at": time.time() + tokens.get("expires_in", 3600),
        "scope": tokens.get("scope", ""),
    }
    _save_oauth_state(oauth_state)

    # Also store access token in secure store for other modules
    if store and tokens.get("access_token"):
        store.set_key(f"oauth_{provider}_access_token", tokens["access_token"])
        if tokens.get("refresh_token"):
            store.set_key(f"oauth_{provider}_refresh_token", tokens["refresh_token"])

    # Return HTML that closes the popup and signals the parent
    return HTMLResponse(
        f"""<html>
<head><title>Orion — OAuth Success</title></head>
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


@app.post("/api/oauth/revoke")
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
# PROVIDER TOGGLE
# =============================================================================

@app.post("/api/models/providers/toggle")
async def toggle_provider(request: ProviderToggleRequest):
    """Enable or disable an LLM provider."""
    try:
        from orion.core.llm.config import set_provider_enabled, PROVIDERS
        if request.provider not in PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")
        set_provider_enabled(request.provider, request.enabled)
        return {"status": "success", "provider": request.provider, "enabled": request.enabled}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# INTEGRATIONS
# =============================================================================

@app.get("/api/integrations")
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


@app.get("/api/integrations/health")
async def integration_health():
    """Run integration health checks."""
    try:
        from orion.integrations.health import IntegrationHealthChecker
        checker = IntegrationHealthChecker()
        return checker.get_dashboard()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/integrations/discover")
async def discover_integrations():
    """Run integration auto-discovery."""
    try:
        from orion.integrations.registry import get_registry
        reg = get_registry()
        count = reg.discover()
        return {"discovered": count, "total": reg.count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SETTINGS
# =============================================================================

@app.get("/api/settings")
async def get_all_settings() -> Dict[str, Any]:
    """Get all current settings."""
    user_settings = _load_user_settings()
    defaults = {
        # Core Features
        "enable_table_of_three": True,
        "enable_file_tools": True,
        "enable_passive_memory": True,
        "enable_intelligent_orion": True,
        "enable_streaming": True,
        # Intelligent Orion
        "quality_threshold": 0.7,
        "max_refinement_iterations": 3,
        # Governance
        "default_mode": "safe",
        "valid_modes": ["safe", "pro", "project"],
        "aegis_strict_mode": True,
        # Command Execution
        "enable_command_execution": False,
        "command_timeout_seconds": 30,
        # Limits
        "max_evidence_files": 20,
        "max_file_size_bytes": 100000,
        "max_evidence_retry": 2,
        # Web Access
        "enable_web_access": False,
        "web_cache_ttl": 3600,
        "allowed_domains": "github.com, docs.python.org",
        # Image Generation
        "image_provider": "auto",
        "sdxl_enabled": False,
        "sdxl_endpoint": "http://localhost:8188",
        "flux_enabled": False,
        "dalle_enabled": False,
        "dalle_model": "dall-e-3",
        # Models (legacy)
        "use_local_models": True,
        "model_mode": "local",
        "gpt_model": "gpt-4o",
        "claude_model": "claude-sonnet-4-20250514",
        "ollama_base_url": "http://localhost:11434",
        "ollama_builder_model": "qwen2.5-coder:14b",
        "ollama_reviewer_model": "qwen2.5-coder:14b",
        # Paths
        "data_dir": "data",
        "ledger_file": "data/ledger.jsonl",
        # Workspace
        "workspace": "",
    }
    merged = {**defaults, **user_settings}
    return merged


@app.post("/api/settings")
async def update_settings(settings: SettingsUpdate):
    """Update settings."""
    user_settings = _load_user_settings()
    update_dict = settings.dict(exclude_unset=True, exclude_none=True)

    if "use_local_models" in update_dict:
        user_settings["model_mode"] = "local" if update_dict["use_local_models"] else "cloud"

    for key, value in update_dict.items():
        user_settings[key] = value

    _save_user_settings(user_settings)
    return {"status": "success", "updated": list(update_dict.keys())}


@app.post("/api/settings/workspace")
async def set_workspace(workspace: str):
    """Set the current workspace path."""
    user_settings = _load_user_settings()
    user_settings["workspace"] = workspace
    _save_user_settings(user_settings)
    return {"status": "success", "workspace": workspace}


# =============================================================================
# CONTEXT (repo map, quality)
# =============================================================================

@app.get("/api/context/map")
async def get_repo_map(workspace: str, max_tokens: int = 2048):
    """Get repository map for a workspace."""
    try:
        from orion.core.context.repo_map import generate_repo_map
        return {"map": generate_repo_map(workspace, max_tokens)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/context/quality")
async def get_quality_report(workspace: str):
    """Get code quality report for a workspace."""
    try:
        from orion.core.context.quality import analyze_workspace
        report = analyze_workspace(workspace)
        return {
            "grade": report.grade,
            "score": report.avg_score,
            "summary": report.summary(),
            "files": len(report.files),
            "issues": report.total_issues,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/context/stats")
async def get_context_stats(workspace: str):
    """Get context statistics (repo map + python analysis)."""
    stats = {}
    try:
        from orion.core.context.repo_map import RepoMap
        rm = RepoMap(workspace)
        stats["repo_map"] = rm.get_stats()
        rm.close()
    except Exception:
        stats["repo_map"] = {"error": "not available"}
    try:
        from orion.core.context.python_ast import get_python_context
        ctx = get_python_context(workspace)
        stats["python"] = ctx.get_stats()
    except Exception:
        stats["python"] = {"error": "not available"}
    return stats


# =============================================================================
# GDPR COMPLIANCE
# =============================================================================

GDPR_CONSENTS_FILE = SETTINGS_DIR / "gdpr_consents.json"
GDPR_AUDIT_FILE = SETTINGS_DIR / "gdpr_audit.jsonl"


def _load_gdpr_consents() -> dict:
    if GDPR_CONSENTS_FILE.exists():
        try:
            return json.loads(GDPR_CONSENTS_FILE.read_text())
        except Exception:
            pass
    return {"consents": {}, "policy_version": "1.0.0"}


def _save_gdpr_consents(data: dict):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    GDPR_CONSENTS_FILE.write_text(json.dumps(data, indent=2))


def _append_audit_log(action: str, data_type: str, details: str = None):
    from datetime import datetime
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({
        "action": action,
        "data_type": data_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "details": details,
    })
    with open(GDPR_AUDIT_FILE, "a") as f:
        f.write(entry + "\n")


@app.get("/api/gdpr/consents")
async def get_gdpr_consents():
    """Get GDPR consent statuses."""
    return _load_gdpr_consents()


@app.post("/api/gdpr/consent/{consent_type}")
async def set_gdpr_consent(consent_type: str, granted: bool = True):
    """Set a GDPR consent."""
    data = _load_gdpr_consents()
    data["consents"][consent_type] = granted
    _save_gdpr_consents(data)
    _append_audit_log("consent_update", consent_type, f"granted={granted}")
    return {"status": "success", "consent_type": consent_type, "granted": granted}


@app.get("/api/gdpr/export")
async def export_all_data():
    """Export all user data (GDPR right to data portability)."""
    _append_audit_log("data_export", "all", "User requested full data export")
    export = {
        "settings": _load_user_settings(),
        "api_keys_configured": [
            p["provider"] for p in (await get_api_key_status())
            if p["configured"]
        ],
        "oauth_state": _load_oauth_state(),
        "gdpr_consents": _load_gdpr_consents(),
    }
    # Include model config
    try:
        model_config_file = SETTINGS_DIR / "model_config.json"
        if model_config_file.exists():
            export["model_config"] = json.loads(model_config_file.read_text())
    except Exception:
        pass
    return export


@app.delete("/api/gdpr/data")
async def delete_all_data():
    """Delete all user data (GDPR right to erasure)."""
    _append_audit_log("data_deletion", "all", "User requested full data deletion")

    # Clear secure store
    store = _get_secure_store()
    if store:
        for provider in store.list_providers():
            try:
                store.delete_key(provider)
            except Exception:
                pass

    files_to_delete = [
        SETTINGS_FILE,
        SETTINGS_DIR / "api_keys.json",
        SETTINGS_DIR / "api_keys.json.migrated",
        SETTINGS_DIR / "oauth_state.json",
        SETTINGS_DIR / "oauth_tokens.json",
        SETTINGS_DIR / "model_config.json",
        SETTINGS_DIR / "provider_settings.json",
        SETTINGS_DIR / "security" / "vault.enc",
        SETTINGS_DIR / "security" / "vault.salt",
        SETTINGS_DIR / "security" / "credentials.meta.json",
        SETTINGS_DIR / "security" / "audit.log",
        GDPR_CONSENTS_FILE,
    ]
    deleted = []
    for f in files_to_delete:
        if f.exists():
            try:
                f.unlink()
                deleted.append(f.name)
            except Exception:
                pass
    return {"status": "success", "deleted_files": deleted}


@app.get("/api/gdpr/audit")
async def get_audit_log(limit: int = 100):
    """Get GDPR audit log."""
    entries = []
    if GDPR_AUDIT_FILE.exists():
        try:
            lines = GDPR_AUDIT_FILE.read_text().strip().split("\n")
            for line in lines[-limit:]:
                if line.strip():
                    entries.append(json.loads(line))
        except Exception:
            pass
    return {"audit_log": entries}


# =============================================================================
# RUNTIME INFO
# =============================================================================

@app.get("/api/runtime")
async def get_runtime_info():
    """Get runtime information."""
    runtime_path = Path.home() / ".orion" / "runtime.json"
    if runtime_path.exists():
        try:
            return json.loads(runtime_path.read_text())
        except Exception:
            pass
    return {
        "api_port": 8000,
        "web_port": 3001,
        "api_url": "http://localhost:8000",
        "web_url": "http://localhost:3001",
        "version": "6.4.0",
    }


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
