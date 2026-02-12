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
"""
Orion Agent -- API Server (v7.1.0)

FastAPI server for web UI integration.
Routes are organized into modules under orion.api.routes/.

Run with: uvicorn orion.api.server:app --reload --port 8001
"""

import asyncio as _aio
import logging
import time
import uuid as _uuid
from dataclasses import dataclass as _dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from orion._version import __version__
from orion.api._shared import _PROJECT_ROOT, _get_orion_log

logger = logging.getLogger("orion.api.server")

# =============================================================================
# APP CREATION
# =============================================================================

app = FastAPI(
    title="Orion Agent API",
    description="REST + WebSocket API for Orion Agent",
    version=__version__,
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

# Rate limiting + optional auth (W7)
from orion.api.middleware import OptionalAuthMiddleware, RateLimitMiddleware

app.add_middleware(RateLimitMiddleware, requests_per_minute=120, burst=20)
app.add_middleware(OptionalAuthMiddleware)


# =============================================================================
# LIFECYCLE -- startup and shutdown logging
# =============================================================================


@app.on_event("startup")
async def _on_startup():
    log = _get_orion_log()
    if log:
        log.server_start(host="0.0.0.0", port=8001, version=__version__, project_root=_PROJECT_ROOT)


@app.on_event("shutdown")
async def _on_shutdown():
    log = _get_orion_log()
    if log:
        log.server_stop()


# =============================================================================
# AEGIS INVARIANT 6: Web Approval Queue (HARDCODED -- NOT CONFIGURABLE)
# =============================================================================
# This queue bridges PlatformService's approval gate to the web frontend.
# When Orion tries a write operation, it's held here until the human
# approves or denies via the UI modal.
# =============================================================================


@_dataclass
class _PendingApproval:
    """A write operation waiting for human approval."""

    id: str
    prompt: str
    event: _aio.Event
    approved: bool = False
    responded: bool = False
    created_at: float = 0.0


# Global approval queue -- shared between PlatformService callback and REST endpoints
_pending_approvals: dict[str, _PendingApproval] = {}


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

    logger.info(f"AEGIS-6: Approval request {approval_id} queued -- waiting for human")

    try:
        # Wait up to 120 seconds for human response
        await _aio.wait_for(event.wait(), timeout=120.0)
    except _aio.TimeoutError:
        logger.warning(f"AEGIS-6: Approval {approval_id} timed out -- denied by default")
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
        logger.info("AEGIS Invariant 6 active -- external writes require human approval via web UI")
    except Exception as e:
        logger.warning(f"Could not wire AEGIS approval callback: {e}")


class AegisApprovalResponse(BaseModel):
    approved: bool


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
            pending.append(
                {
                    "id": p.id,
                    "prompt": p.prompt,
                    "age_seconds": round(now - p.created_at, 1),
                }
            )
    return {"pending": pending, "count": len(pending)}


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
# INCLUDE ROUTE MODULES
# =============================================================================

from orion.api.routes.auth import router as auth_router
from orion.api.routes.chat import router as chat_router
from orion.api.routes.gdpr import router as gdpr_router
from orion.api.routes.health import router as health_router
from orion.api.routes.models import router as models_router
from orion.api.routes.platforms import router as platforms_router
from orion.api.routes.settings import router as settings_router
from orion.api.routes.tools import router as tools_router
from orion.api.routes.training import router as training_router

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(models_router)
app.include_router(settings_router)
app.include_router(auth_router)
app.include_router(platforms_router)
app.include_router(tools_router)
app.include_router(training_router)
app.include_router(gdpr_router)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
