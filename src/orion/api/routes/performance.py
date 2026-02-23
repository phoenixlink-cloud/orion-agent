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
"""Performance API Routes — REST endpoints for the Web UI performance panel.

Exposes execution performance metrics as JSON for the frontend dashboard.

    GET /api/performance              — Overview metrics snapshot
    GET /api/performance/trends       — Improvement/regression trends
    GET /api/performance/hotspots     — Error category hotspots
    GET /api/performance/stacks       — Per-stack comparison

See Phase 4D.5 specification.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

logger = logging.getLogger("orion.api.routes.performance")

router = APIRouter(prefix="/api/performance", tags=["Performance"])


def _get_performance_metrics():
    """Try to build a PerformanceMetrics instance from global state."""
    try:
        from orion.ara.execution_memory import ExecutionMemory
        from orion.ara.performance_metrics import PerformanceMetrics
        from orion.core.memory.engine import get_memory_engine

        engine = get_memory_engine()
        em = ExecutionMemory(memory_engine=engine)
        return PerformanceMetrics(execution_memory=em)
    except Exception:
        return None


@router.get("")
async def get_metrics(
    stack: str = Query("", description="Filter by stack"),
    session_id: str = Query("", description="Filter by session"),
    limit: int = Query(0, description="Max lessons to consider"),
):
    """Get aggregated performance metrics snapshot."""
    pm = _get_performance_metrics()
    if pm is None:
        return {"success": True, "data": None, "message": "No execution data available"}

    m = pm.compute_metrics(stack=stack, session_id=session_id, limit=limit)
    return {"success": True, "data": m.to_dict()}


@router.get("/trends")
async def get_trends(
    stack: str = Query("", description="Filter by stack"),
    current_window: int = Query(10, description="Current window size"),
    previous_window: int = Query(10, description="Previous window size"),
):
    """Get performance trends (current vs previous window)."""
    pm = _get_performance_metrics()
    if pm is None:
        return {"success": True, "data": [], "message": "No execution data available"}

    trends = pm.compute_trends(
        stack=stack,
        current_window=current_window,
        previous_window=previous_window,
    )
    return {"success": True, "data": [t.to_dict() for t in trends]}


@router.get("/hotspots")
async def get_hotspots(
    stack: str = Query("", description="Filter by stack"),
    limit: int = Query(5, description="Max hotspots to return"),
):
    """Get error category hotspots."""
    pm = _get_performance_metrics()
    if pm is None:
        return {"success": True, "data": [], "message": "No execution data available"}

    hotspots = pm.get_error_hotspots(stack=stack, limit=limit)
    return {"success": True, "data": hotspots}


@router.get("/stacks")
async def get_stacks():
    """Get per-stack performance comparison."""
    pm = _get_performance_metrics()
    if pm is None:
        return {"success": True, "data": [], "message": "No execution data available"}

    comparison = pm.get_stack_comparison()
    return {"success": True, "data": comparison}
