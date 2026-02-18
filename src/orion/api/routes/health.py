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
"""Orion Agent -- Health & Runtime Routes."""

import json
from pathlib import Path

from fastapi import APIRouter

from orion._version import __version__

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint (K8s compatible)."""
    result = {"status": "healthy", "version": __version__}

    # Include sandbox status if available
    try:
        from orion.security.sandbox_lifecycle import get_sandbox_lifecycle

        lifecycle = get_sandbox_lifecycle()
        result["sandbox"] = lifecycle.get_status()
    except Exception:
        result["sandbox"] = {"available": False, "phase": "not_started", "reason": "lifecycle not loaded"}

    return result


@router.get("/ready")
async def readiness_check():
    """Readiness probe."""
    return {"status": "ready", "version": __version__}


@router.get("/api/runtime")
async def get_runtime_info():
    """Get runtime information."""
    runtime_path = Path.home() / ".orion" / "runtime.json"
    if runtime_path.exists():
        try:
            return json.loads(runtime_path.read_text())
        except Exception:
            pass
    return {
        "api_port": 8001,
        "web_port": 3001,
        "api_url": "http://localhost:8001",
        "web_url": "http://localhost:3001",
        "version": __version__,
    }
