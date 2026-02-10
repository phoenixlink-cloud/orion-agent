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
"""Orion Agent -- Model Configuration Routes."""

from fastapi import APIRouter, HTTPException

from orion.api._shared import (
    ModelConfigRequest, PresetRequest, ProviderToggleRequest,
)

router = APIRouter()


@router.get("/api/models/config")
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


@router.post("/api/models/config")
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


@router.get("/api/models/providers")
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


@router.get("/api/models/presets")
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


@router.post("/api/models/preset")
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


@router.post("/api/models/providers/toggle")
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
