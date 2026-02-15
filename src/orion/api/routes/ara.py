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
"""ARA API Routes — FastAPI wrapper for ARA operations.

Exposes ARA session control, role management, dashboard, and goal queue
as REST endpoints for the web UI.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("orion.api.routes.ara")

router = APIRouter(prefix="/api/ara", tags=["ARA"])


# =============================================================================
# Request/Response Models
# =============================================================================


class WorkRequest(BaseModel):
    role_name: str
    goal: str
    workspace_path: str | None = None


class FeedbackRequest(BaseModel):
    session_id: str
    rating: int
    comment: str | None = None


class RoleCreateRequest(BaseModel):
    name: str
    scope: str = "coding"
    auth_method: str = "pin"
    description: str = ""


class ARASettingsUpdate(BaseModel):
    settings: dict[str, Any]


# =============================================================================
# Session Control
# =============================================================================


@router.get("/status")
async def get_status():
    """Get current ARA session status."""
    try:
        from orion.ara.cli_commands import cmd_status

        result = cmd_status()
        return {"success": result.success, "message": result.message, "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/work")
async def post_work(req: WorkRequest):
    """Start a new autonomous work session."""
    try:
        from orion.ara.cli_commands import cmd_work

        result = cmd_work(
            role_name=req.role_name,
            goal=req.goal,
            workspace_path=req.workspace_path,
        )
        if result.success:
            return {"success": True, "message": result.message, "data": result.data}
        raise HTTPException(status_code=409, detail=result.message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pause")
async def post_pause():
    """Pause the running session."""
    try:
        from orion.ara.cli_commands import cmd_pause

        result = cmd_pause()
        return {"success": result.success, "message": result.message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume")
async def post_resume():
    """Resume a paused session."""
    try:
        from orion.ara.cli_commands import cmd_resume

        result = cmd_resume()
        return {"success": result.success, "message": result.message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel")
async def post_cancel():
    """Cancel the running session."""
    try:
        from orion.ara.cli_commands import cmd_cancel

        result = cmd_cancel()
        return {"success": result.success, "message": result.message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Sessions
# =============================================================================


@router.get("/sessions")
async def get_sessions():
    """List all sessions."""
    try:
        from orion.ara.cli_commands import cmd_sessions

        result = cmd_sessions()
        return {"success": result.success, "message": result.message, "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/cleanup")
async def cleanup_sessions(max_age_days: int = 30):
    """Clean up old sessions."""
    try:
        from orion.ara.cli_commands import cmd_sessions_cleanup

        result = cmd_sessions_cleanup(max_age_days=max_age_days)
        return {"success": result.success, "message": result.message, "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Roles
# =============================================================================


@router.get("/roles")
async def get_roles():
    """List all available roles."""
    try:
        from orion.ara.cli_commands import cmd_role_list

        result = cmd_role_list()
        return {"success": result.success, "message": result.message, "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roles/{role_name}")
async def get_role(role_name: str):
    """Get details for a specific role."""
    try:
        from orion.ara.cli_commands import cmd_role_show

        result = cmd_role_show(role_name)
        if result.success:
            return {"success": True, "message": result.message, "data": result.data}
        raise HTTPException(status_code=404, detail=result.message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roles/example/yaml")
async def get_role_example():
    """Get an annotated example role YAML."""
    try:
        from orion.ara.cli_commands import cmd_role_example

        result = cmd_role_example()
        return {"success": True, "yaml": result.message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/roles")
async def create_role(req: RoleCreateRequest):
    """Create a new role."""
    try:
        from orion.ara.cli_commands import cmd_role_create

        result = cmd_role_create(
            name=req.name,
            scope=req.scope,
            auth_method=req.auth_method,
            description=req.description,
        )
        if result.success:
            return {"success": True, "message": result.message, "data": result.data}
        raise HTTPException(status_code=409, detail=result.message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/roles/{role_name}")
async def delete_role(role_name: str):
    """Delete a user role."""
    try:
        from orion.ara.cli_commands import cmd_role_delete

        result = cmd_role_delete(role_name)
        if result.success:
            return {"success": True, "message": result.message}
        raise HTTPException(status_code=404, detail=result.message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Dashboard
# =============================================================================


@router.get("/dashboard")
async def get_dashboard(session_id: str | None = None):
    """Get morning dashboard data."""
    try:
        from orion.ara.dashboard import MorningDashboard

        dash = MorningDashboard()
        pending = dash.check_pending_reviews()

        sections: list[dict[str, Any]] = []
        rendered = ""

        if session_id:
            data = dash.gather_data(session_id)
            rendered = dash.render_data(data)
            sections = [
                {
                    "title": s.title,
                    "content": "\n".join(s.content) if isinstance(s.content, list) else str(s.content),
                    "style": "info",
                }
                for s in data.sections
            ]
        elif pending:
            # Show pending reviews as sections
            for p in pending:
                sections.append({
                    "title": f"Pending Review: {p.get('goal', 'Unknown')}",
                    "content": f"Session {p['session_id'][:12]} by role '{p.get('role', '?')}' — {p.get('tasks', 0)} tasks completed.",
                    "style": "warning",
                })
            rendered = dash.get_startup_message() or ""

        return {
            "success": True,
            "rendered": rendered,
            "data": {
                "sections": sections,
                "pending_count": len(pending),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Setup & Settings
# =============================================================================


@router.get("/setup")
async def get_setup():
    """Run ARA setup check and return results."""
    try:
        from orion.ara.cli_commands import cmd_setup

        result = cmd_setup()
        return {"success": result.success, "message": result.message, "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings")
async def get_ara_settings():
    """Get ARA-specific settings."""
    try:
        from orion.ara.cli_commands import cmd_settings_ara

        result = cmd_settings_ara()
        return {"success": result.success, "message": result.message, "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings")
async def update_ara_settings(req: ARASettingsUpdate):
    """Update ARA-specific settings."""
    try:
        from orion.ara.cli_commands import cmd_settings_ara

        result = cmd_settings_ara(settings=req.settings)
        return {"success": result.success, "message": result.message, "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Plan & Rollback
# =============================================================================


@router.get("/plan")
async def get_plan(session_id: str | None = None):
    """Review the current task plan."""
    try:
        from orion.ara.cli_commands import cmd_plan_review

        result = cmd_plan_review(session_id=session_id)
        return {"success": result.success, "message": result.message, "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rollback/{checkpoint_id}")
async def post_rollback(checkpoint_id: str, session_id: str | None = None):
    """Rollback to a specific checkpoint."""
    try:
        from orion.ara.cli_commands import cmd_rollback

        result = cmd_rollback(checkpoint_id, session_id=session_id)
        if result.success:
            return {"success": True, "message": result.message}
        raise HTTPException(status_code=400, detail=result.message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Review (promotion)
# =============================================================================


@router.post("/review")
async def post_review(session_id: str | None = None, credential: str | None = None):
    """Review sandbox changes for promotion."""
    try:
        from orion.ara.cli_commands import cmd_review

        result = cmd_review(session_id=session_id, credential=credential)
        return {"success": result.success, "message": result.message, "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
