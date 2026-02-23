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
"""Orion Agent -- Settings & Mode Routes."""

from typing import Any

from fastapi import APIRouter, HTTPException

from orion.api._shared import (
    ModeRequest,
    SettingsUpdate,
    _get_orion_log,
    _load_user_settings,
    _save_user_settings,
)

router = APIRouter()


@router.get("/api/settings")
async def get_all_settings() -> dict[str, Any]:
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
        # ARA (Autonomous Role Architecture)
        "ara_enabled": True,
        "ara_default_auth": "pin",
        "ara_max_cost_usd": 5.0,
        "ara_max_session_hours": 8.0,
        "ara_sandbox_mode": "branch",
        "ara_prompt_guard": True,
        "ara_audit_log": True,
        "ara_enable_command_execution": False,
        "ara_resource_profile": "standard",
    }
    merged = {**defaults, **user_settings}
    return merged


@router.post("/api/settings")
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


@router.post("/api/settings/workspace")
async def set_workspace(workspace: str):
    """Set the current workspace path."""
    user_settings = _load_user_settings()
    user_settings["workspace"] = workspace
    _save_user_settings(user_settings)
    return {"status": "success", "workspace": workspace}


@router.post("/api/mode")
async def set_mode(request: ModeRequest):
    """Switch Orion's operating mode."""
    valid_modes = {"safe", "pro", "project"}
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=400, detail=f"Invalid mode. Use: {', '.join(sorted(valid_modes))}"
        )
    # Persist to settings
    user_settings = _load_user_settings()
    user_settings["default_mode"] = request.mode
    _save_user_settings(user_settings)
    return {"status": "success", "mode": request.mode}


@router.get("/api/mode")
async def get_mode():
    """Get current operating mode."""
    settings = _load_user_settings()
    return {"mode": settings.get("default_mode", "safe")}
