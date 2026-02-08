"""
Orion Agent — API Server (v6.4.0)

FastAPI server for web UI integration.
Provides REST endpoints for health, chat, settings, model config,
integrations, and WebSocket real-time chat.

Run with: uvicorn orion.api.server:app --reload --port 8000
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


class ModelConfigRequest(BaseModel):
    mode: Optional[str] = None
    builder: Optional[RoleConfigRequest] = None
    reviewer: Optional[RoleConfigRequest] = None


class PresetRequest(BaseModel):
    name: str


class SettingsUpdate(BaseModel):
    enable_table_of_three: Optional[bool] = None
    enable_file_tools: Optional[bool] = None
    enable_streaming: Optional[bool] = None
    default_mode: Optional[str] = None
    max_evidence_files: Optional[int] = None
    max_file_size_bytes: Optional[int] = None
    use_local_models: Optional[bool] = None
    gpt_model: Optional[str] = None
    claude_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_builder_model: Optional[str] = None
    ollama_reviewer_model: Optional[str] = None


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
            "builder": {"provider": cfg.builder.provider, "model": cfg.builder.model},
            "reviewer": {"provider": reviewer.provider, "model": reviewer.model},
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
            cfg.builder = RoleConfig(provider=request.builder.provider, model=request.builder.model)

        if request.reviewer:
            cfg.reviewer = RoleConfig(provider=request.reviewer.provider, model=request.reviewer.model)
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
        "enable_table_of_three": True,
        "enable_file_tools": True,
        "enable_streaming": True,
        "default_mode": "safe",
        "valid_modes": ["safe", "pro", "project"],
        "max_evidence_files": 20,
        "max_file_size_bytes": 100000,
        "use_local_models": True,
        "model_mode": "local",
        "gpt_model": "gpt-4o",
        "claude_model": "claude-sonnet-4-20250514",
        "ollama_base_url": "http://localhost:11434",
        "ollama_builder_model": "qwen2.5-coder:14b",
        "ollama_reviewer_model": "qwen2.5-coder:14b",
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
