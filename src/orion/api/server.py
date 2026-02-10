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

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

logger = logging.getLogger("orion.api.server")

# Resolve project root (two levels up from src/orion/api/server.py)
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)

app = FastAPI(
    title="Orion Agent API",
    description="REST + WebSocket API for Orion Agent",
    version="7.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# ORION LOGGER — comprehensive logging from startup to shutdown
# =============================================================================

_orion_log = None

def _get_orion_log():
    """Lazy-init the OrionLogger with project-local log mirror."""
    global _orion_log
    if _orion_log is None:
        try:
            from orion.core.logging import get_logger
            _orion_log = get_logger(project_dir=_PROJECT_ROOT)
        except Exception:
            pass
    return _orion_log


# =============================================================================
# HTTP REQUEST LOGGING MIDDLEWARE
# =============================================================================

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with method, path, status, and latency."""
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        latency_ms = int((time.time() - start) * 1000)
        log = _get_orion_log()
        if log:
            # Skip noisy health checks from log
            path = request.url.path
            if path not in ("/api/health",):
                log.http_request(
                    method=request.method,
                    path=path,
                    status=response.status_code,
                    latency_ms=latency_ms,
                )
        return response

app.add_middleware(RequestLoggingMiddleware)


# =============================================================================
# LIFECYCLE — startup and shutdown logging
# =============================================================================

@app.on_event("startup")
async def _on_startup():
    log = _get_orion_log()
    if log:
        log.server_start(host="0.0.0.0", port=8001, version="7.0.0",
                         project_root=_PROJECT_ROOT)

@app.on_event("shutdown")
async def _on_shutdown():
    log = _get_orion_log()
    if log:
        log.server_stop()


# =============================================================================
# AEGIS INVARIANT 6: Web Approval Queue (HARDCODED — NOT CONFIGURABLE)
# =============================================================================
# This queue bridges PlatformService's approval gate to the web frontend.
# When Orion tries a write operation, it's held here until the human
# approves or denies via the UI modal.
# =============================================================================

import asyncio as _aio
import uuid as _uuid
from dataclasses import dataclass as _dataclass, field as _field
from typing import Dict as _Dict

@_dataclass
class _PendingApproval:
    """A write operation waiting for human approval."""
    id: str
    prompt: str
    event: _aio.Event
    approved: bool = False
    responded: bool = False
    created_at: float = 0.0

# Global approval queue — shared between PlatformService callback and REST endpoints
_pending_approvals: _Dict[str, _PendingApproval] = {}

async def _web_approval_callback(prompt: str) -> bool:
    """
    AEGIS Invariant 6: Async approval callback for web mode.

    Creates a pending approval, waits for the frontend to respond,
    then returns the human's decision. Times out after 120 seconds.
    """
    approval_id = str(_uuid.uuid4())[:8]
    event = _aio.Event()
    pending = _PendingApproval(
        id=approval_id,
        prompt=prompt,
        event=event,
        created_at=time.time(),
    )
    _pending_approvals[approval_id] = pending

    logger.info(f"AEGIS-6: Approval request {approval_id} queued — waiting for human")

    try:
        # Wait up to 120 seconds for human response
        await _aio.wait_for(event.wait(), timeout=120.0)
    except _aio.TimeoutError:
        logger.warning(f"AEGIS-6: Approval {approval_id} timed out — denied by default")
        pending.approved = False
    finally:
        _pending_approvals.pop(approval_id, None)

    return pending.approved

# Wire PlatformService with the web approval callback at startup
@app.on_event("startup")
async def _wire_aegis_approval():
    """Wire AEGIS Invariant 6 approval callback into PlatformService."""
    try:
        from orion.integrations.platform_service import get_platform_service
        svc = get_platform_service()
        svc.set_approval_callback(_web_approval_callback)
        logger.info("AEGIS Invariant 6 active — external writes require human approval via web UI")
    except Exception as e:
        logger.warning(f"Could not wire AEGIS approval callback: {e}")


@app.get("/api/aegis/pending")
async def get_pending_approvals():
    """
    AEGIS Invariant 6: List pending approval requests.

    The frontend polls this endpoint to detect when Orion needs
    human approval for a write operation.
    """
    now = time.time()
    pending = []
    for p in _pending_approvals.values():
        if not p.responded:
            pending.append({
                "id": p.id,
                "prompt": p.prompt,
                "age_seconds": round(now - p.created_at, 1),
            })
    return {"pending": pending, "count": len(pending)}


class AegisApprovalResponse(BaseModel):
    approved: bool


@app.post("/api/aegis/respond/{approval_id}")
async def respond_to_approval(approval_id: str, response: AegisApprovalResponse):
    """
    AEGIS Invariant 6: Human responds to an approval request.

    The frontend calls this with approved=true or approved=false
    to unblock the waiting PlatformService.api_call().
    """
    pending = _pending_approvals.get(approval_id)
    if not pending:
        raise HTTPException(status_code=404, detail=f"No pending approval with id '{approval_id}'")

    pending.approved = response.approved
    pending.responded = True
    pending.event.set()  # Unblock the waiting api_call()

    action = "APPROVED" if response.approved else "DENIED"
    logger.info(f"AEGIS-6: Approval {approval_id} {action} by human via web UI")

    return {"id": approval_id, "action": action}


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
    # Workspace
    workspace: Optional[str] = None


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
    """
    WebSocket endpoint for real-time chat with Orion.

    Features (v6.7.0):
    - Persistent Router + MemoryEngine per connection (not per message)
    - Token-by-token streaming via FastPath.execute_streaming()
    - Council phase updates (Builder → Reviewer → Governor)
    - Memory recording + optional user feedback
    - Full logging to ~/.orion/logs/orion.log
    """
    await websocket.accept()

    # Per-connection state
    router = None
    memory_engine = None
    current_workspace = None
    log = _get_orion_log()
    ws_request_count = 0

    if log:
        client_host = websocket.client.host if websocket.client else "unknown"
        log.ws_connect(client=client_host)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            # Handle feedback messages
            if msg_type == "feedback":
                rating = data.get("rating", 0)
                task_desc = data.get("task_description", "")
                if memory_engine and rating and 1 <= rating <= 5:
                    import uuid as _feedback_uuid
                    task_id = str(_feedback_uuid.uuid4())[:8]
                    memory_engine.record_approval(
                        task_id=task_id,
                        task_description=task_desc[:300],
                        rating=rating,
                        feedback=f"User rated {rating}/5 via web",
                        quality_score=rating / 5.0,
                    )
                    if log:
                        log.approval(task_id=task_id, rating=rating, promoted=(rating >= 4 or rating <= 2))
                    await websocket.send_json({
                        "type": "feedback_ack",
                        "rating": rating,
                        "pattern": "positive" if rating >= 4 else ("anti" if rating <= 2 else "neutral"),
                    })
                continue

            # Chat message
            ws_request_count += 1
            user_input = data.get("message", "")
            workspace = data.get("workspace", "")
            mode = data.get("mode", "safe")

            if not user_input:
                await websocket.send_json({"type": "error", "message": "No message provided"})
                continue
            if not workspace:
                await websocket.send_json({"type": "error", "message": "No workspace specified"})
                continue

            # Initialize or re-initialize Router + Memory if workspace changed
            if router is None or workspace != current_workspace:
                current_workspace = workspace
                try:
                    from orion.core.memory.engine import get_memory_engine
                    if memory_engine:
                        memory_engine.end_session()
                    memory_engine = get_memory_engine(workspace)
                    memory_engine.start_session()
                except Exception:
                    memory_engine = None

                try:
                    from orion.core.agents.router import RequestRouter
                    router = RequestRouter(
                        workspace,
                        stream_output=False,  # We handle streaming ourselves
                        sandbox_enabled=False,
                        memory_engine=memory_engine,
                    )
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"Router init failed: {e}"})
                    continue

                if log:
                    log.session_start(workspace=workspace, mode=mode)

            try:
                # Scout classification
                report = None
                route_name = "FAST_PATH"
                if router.scout:
                    report = router.scout.analyze(user_input)
                    from orion.core.agents.scout import Route
                    route_name = report.route.name

                    await websocket.send_json({
                        "type": "routing",
                        "route": route_name,
                        "reasoning": report.reasoning,
                        "files": report.relevant_files[:5],
                        "complexity": report.complexity_score,
                        "risk": report.risk_level,
                    })

                # Streaming for FastPath
                if route_name == "FAST_PATH" and router.fast_path:
                    # Inject memory context
                    memory_ctx = router._get_memory_context(user_input)
                    if memory_ctx:
                        router.fast_path._memory_context = memory_ctx

                    await websocket.send_json({"type": "status", "message": "Thinking..."})

                    collected = []
                    try:
                        async for token in router.fast_path.execute_streaming(user_input, report):
                            collected.append(token)
                            await websocket.send_json({"type": "token", "content": token})
                        full_response = "".join(collected)
                    except Exception:
                        # Fallback to non-streaming
                        result = await router.fast_path.execute(user_input, report)
                        full_response = result.response
                        await websocket.send_json({"type": "token", "content": full_response})

                    await websocket.send_json({
                        "type": "complete",
                        "success": True,
                        "response": full_response,
                        "route": route_name,
                    })

                # Council path (Builder → Reviewer → Governor)
                elif route_name == "COUNCIL" and router.council:
                    await websocket.send_json({"type": "status", "message": "Council deliberating..."})
                    await websocket.send_json({"type": "council_phase", "phase": "builder", "message": "Builder generating proposal..."})

                    result = await router.handle_request(user_input)
                    full_response = result.get("response", "")

                    await websocket.send_json({"type": "council_phase", "phase": "complete", "message": "Council complete"})
                    await websocket.send_json({
                        "type": "complete",
                        "success": result.get("success", False),
                        "response": full_response,
                        "route": route_name,
                        "actions": result.get("actions", []),
                        "execution_time_ms": result.get("execution_time_ms", 0),
                    })

                # Escalation
                elif route_name == "ESCALATION":
                    await websocket.send_json({
                        "type": "escalation",
                        "message": f"This request was flagged for escalation.",
                        "reason": report.reasoning if report else "Unknown",
                    })
                    full_response = "Request escalated — requires human approval."

                # Fallback
                else:
                    result = await router.handle_request(user_input)
                    full_response = result.get("response", "")
                    await websocket.send_json({
                        "type": "complete",
                        "success": result.get("success", False),
                        "response": full_response,
                        "route": route_name,
                    })

                # Record interaction in memory
                if router:
                    router.record_interaction(user_input, full_response, route_name)

                if log:
                    log.route(route_name, user_input,
                              complexity=report.complexity_score if report else 0,
                              risk=report.risk_level if report else "")

            except Exception as e:
                if log:
                    log.error("WebSocket", f"Request failed: {e}", request=user_input[:100])
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        # Clean up session
        if memory_engine:
            try:
                memory_engine.end_session()
            except Exception:
                pass
        if log:
            client_host = websocket.client.host if websocket.client else "unknown"
            log.ws_disconnect(client=client_host, requests=ws_request_count)
            log.session_end()
    except Exception as e:
        if log:
            log.error("WebSocket", f"Unhandled error: {e}")
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

    # Extract access_token — different providers return it in different places
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
# ONE-CLICK OAUTH (new — uses oauth_manager module)
# =============================================================================

@app.get("/api/oauth/providers")
async def list_oauth_providers():
    """List all OAuth providers with connection status and setup steps."""
    try:
        from orion.integrations.oauth_manager import get_provider_status
        return get_provider_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/oauth/connect/{provider}")
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

        # GitHub Device Flow — best UX for desktop apps
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

        # PKCE or oauth_secret — redirect to auth URL
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


@app.post("/api/oauth/device-poll/{provider}")
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

        # Got token — store it
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


@app.post("/api/oauth/token/{provider}")
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


@app.post("/api/oauth/disconnect/{provider}")
async def oauth_disconnect(provider: str):
    """Disconnect a provider — remove all stored tokens."""
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


@app.post("/api/oauth/setup/{provider}")
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
# PLATFORMS (Comprehensive service registry)
# =============================================================================

@app.get("/api/platforms")
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


@app.get("/api/platforms/connected")
async def list_connected_platforms():
    """List only connected platforms."""
    try:
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        return {"platforms": registry.list_connected()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/platforms/capabilities")
async def list_platform_capabilities():
    """List all available capabilities from connected platforms."""
    try:
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        return {"capabilities": registry.list_capabilities()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/platforms/{platform_id}")
async def get_platform(platform_id: str):
    """Get details for a specific platform."""
    from orion.integrations.platforms import get_platform_registry
    registry = get_platform_registry()
    platform = registry.get(platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform_id}")
    return registry._serialize(platform)


class PlatformConnectRequest(BaseModel):
    platform_id: str
    token: Optional[str] = None
    api_key: Optional[str] = None


@app.post("/api/platforms/connect")
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


@app.post("/api/platforms/disconnect")
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


@app.post("/api/platforms/{platform_id}/oauth-connect")
async def oauth_connect_platform(platform_id: str):
    """
    Simplified OAuth connect — one-click flow.

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
# GIT OPERATIONS (Phase 1A — closing CLI-only gap)
# =============================================================================

class GitCommitRequest(BaseModel):
    workspace: str
    message: str = "orion: automated changes"


class GitUndoRequest(BaseModel):
    workspace: str
    subcommand: str = ""  # "", "all", "stack", "history"


@app.get("/api/git/diff")
async def git_diff(workspace: str):
    """Get pending git diff for a workspace."""
    if not workspace or not Path(workspace).is_dir():
        raise HTTPException(status_code=400, detail="Invalid workspace path")
    try:
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=workspace, capture_output=True, text=True, timeout=10
        )
        diff_full = subprocess.run(
            ["git", "diff"],
            cwd=workspace, capture_output=True, text=True, timeout=10
        )
        return {
            "stat": result.stdout,
            "diff": diff_full.stdout[:50000],  # Cap at 50KB
            "has_changes": bool(result.stdout.strip()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/git/commit")
async def git_commit(request: GitCommitRequest):
    """Commit all changes in a workspace."""
    if not request.workspace or not Path(request.workspace).is_dir():
        raise HTTPException(status_code=400, detail="Invalid workspace path")
    try:
        import subprocess
        subprocess.run(["git", "add", "-A"], cwd=request.workspace, check=True, timeout=10)
        result = subprocess.run(
            ["git", "commit", "-m", request.message],
            cwd=request.workspace, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            # Get commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=request.workspace, capture_output=True, text=True, timeout=5
            )
            return {
                "status": "success",
                "message": request.message,
                "hash": hash_result.stdout.strip(),
            }
        return {"status": "nothing_to_commit", "message": result.stdout.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/git/undo")
async def git_undo(request: GitUndoRequest):
    """Undo changes using git safety net."""
    if not request.workspace or not Path(request.workspace).is_dir():
        raise HTTPException(status_code=400, detail="Invalid workspace path")
    try:
        from orion.core.editing.safety import get_git_safety
        safety = get_git_safety(request.workspace)

        if request.subcommand == "all":
            result = safety.undo_all()
            return {"status": "success" if result.success else "error", "message": result.message}
        elif request.subcommand == "stack":
            return {"stack": safety.get_undo_stack()}
        elif request.subcommand == "history":
            return {"history": safety.get_edit_history()[:20]}
        else:
            if safety.get_savepoint_count() > 0:
                result = safety.undo()
                return {
                    "status": "success" if result.success else "error",
                    "message": result.message,
                    "files_restored": getattr(result, 'files_restored', 0),
                }
            return {"status": "nothing", "message": "No savepoints to undo"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# DOCTOR DIAGNOSTICS (Phase 1A — closing CLI-only gap)
# =============================================================================

@app.get("/api/doctor")
async def run_doctor_endpoint(workspace: str = ""):
    """Run system diagnostics (same as /doctor CLI command)."""
    try:
        from orion.cli.doctor import run_doctor
        report = await run_doctor(console=None, workspace=workspace or ".")
        results = report.checks
        passed = sum(1 for r in results if r.status == "pass")
        warned = sum(1 for r in results if r.status == "warn")
        failed = sum(1 for r in results if r.status == "fail")
        return {
            "checks": [
                {
                    "name": r.name,
                    "status": r.status,
                    "icon": r.icon,
                    "message": r.message,
                    "remedy": r.remedy,
                    "details": r.details,
                }
                for r in results
            ],
            "summary": {
                "total": len(results),
                "passed": passed,
                "warned": warned,
                "failed": failed,
                "score": round(passed / max(len(results), 1) * 100),
            },
        }
    except ImportError:
        # Fallback if run_checks not available — run basic checks
        checks = []
        # Python version
        import sys
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        checks.append({"name": "Python", "status": "pass", "message": py_ver})
        # Workspace
        if workspace and Path(workspace).is_dir():
            checks.append({"name": "Workspace", "status": "pass", "message": workspace})
        else:
            checks.append({"name": "Workspace", "status": "warn", "message": "Not set"})
        return {"checks": checks, "summary": {"total": len(checks), "passed": len(checks)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# MODE SWITCH (Phase 1A — closing CLI-only gap)
# =============================================================================

class ModeRequest(BaseModel):
    mode: str  # "safe", "pro", "project"


@app.post("/api/mode")
async def set_mode(request: ModeRequest):
    """Switch Orion's operating mode."""
    valid_modes = {"safe", "pro", "project"}
    if request.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Use: {', '.join(sorted(valid_modes))}")
    # Persist to settings
    user_settings = _load_user_settings()
    user_settings["default_mode"] = request.mode
    _save_user_settings(user_settings)
    return {"status": "success", "mode": request.mode}


@app.get("/api/mode")
async def get_mode():
    """Get current operating mode."""
    settings = _load_user_settings()
    return {"mode": settings.get("default_mode", "safe")}


# =============================================================================
# CONTEXT FILES (Phase 1A — closing CLI-only gap)
# =============================================================================

class ContextFilesRequest(BaseModel):
    workspace: str
    files: List[str]


# In-memory context file store (per-session, like CLI)
_context_files: Dict[str, List[str]] = {}


@app.get("/api/context/files")
async def get_context_files(workspace: str):
    """Get current context files for a workspace."""
    return {"files": _context_files.get(workspace, []), "workspace": workspace}


@app.post("/api/context/files")
async def add_context_files(request: ContextFilesRequest):
    """Add files to the context for a workspace."""
    if not request.workspace or not Path(request.workspace).is_dir():
        raise HTTPException(status_code=400, detail="Invalid workspace path")
    import glob
    current = _context_files.setdefault(request.workspace, [])
    added = []
    for pattern in request.files:
        full = os.path.join(request.workspace, pattern)
        matches = glob.glob(full, recursive=True)
        for m in matches:
            rel = os.path.relpath(m, request.workspace)
            if rel not in current:
                current.append(rel)
                added.append(rel)
    return {"added": added, "total": len(current), "files": current}


@app.delete("/api/context/files")
async def remove_context_files(workspace: str, file: str = ""):
    """Remove files from context. If file is empty, clear all."""
    current = _context_files.get(workspace, [])
    if not file:
        _context_files[workspace] = []
        return {"status": "cleared", "removed": len(current)}
    if file in current:
        current.remove(file)
        return {"status": "removed", "file": file, "total": len(current)}
    raise HTTPException(status_code=404, detail=f"File not in context: {file}")


# =============================================================================
# EVOLUTION / LEARNING (Phase 1A — closing CLI-only gap)
# =============================================================================

@app.get("/api/evolution/snapshot")
async def get_evolution_snapshot():
    """Get Orion's learning evolution snapshot."""
    try:
        from orion.core.learning.evolution import get_evolution_engine
        from dataclasses import asdict
        engine = get_evolution_engine()
        summary = engine.get_evolution_summary()
        return {
            "summary": summary if isinstance(summary, dict) else str(summary),
        }
    except Exception as e:
        return {"summary": f"Evolution engine not available: {e}"}


@app.get("/api/evolution/recommendations")
async def get_evolution_recommendations():
    """Get self-improvement recommendations."""
    try:
        from orion.core.learning.evolution import get_evolution_engine
        engine = get_evolution_engine()
        return {"recommendations": engine.get_recommendations()}
    except Exception as e:
        return {"recommendations": [], "error": str(e)}


# =============================================================================
# MEMORY ENGINE (Phase 1C — closing BOTH-MISSING gap)
# =============================================================================

@app.get("/api/memory/stats")
async def get_memory_stats():
    """Get three-tier memory system statistics."""
    try:
        from orion.core.memory.engine import MemoryEngine
        from dataclasses import asdict
        settings = _load_user_settings()
        engine = MemoryEngine(workspace_path=settings.get("workspace"))
        stats = engine.get_stats()
        if hasattr(stats, '__dataclass_fields__'):
            return asdict(stats)
        return stats if isinstance(stats, dict) else {"raw": str(stats)}
    except Exception as e:
        return {"error": str(e), "tier1": 0, "tier2": 0, "tier3": 0}


@app.get("/api/memory/recall")
async def recall_memories(q: str, max_results: int = 10):
    """Recall relevant memories for a query."""
    try:
        from orion.core.memory.engine import MemoryEngine
        settings = _load_user_settings()
        engine = MemoryEngine(workspace_path=settings.get("workspace"))
        memories = engine.recall(q, max_results=max_results)
        return {
            "query": q,
            "count": len(memories),
            "memories": [
                {
                    "content": m.content,
                    "tier": m.tier,
                    "category": m.category,
                    "confidence": m.confidence,
                    "source": m.source,
                }
                for m in memories
            ],
        }
    except Exception as e:
        return {"query": q, "count": 0, "memories": [], "error": str(e)}


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
    log = _get_orion_log()
    if log:
        log.settings_change(changed_keys=list(update_dict.keys()))
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
