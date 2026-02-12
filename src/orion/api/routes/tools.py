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
"""Orion Agent -- Git, Doctor, Context Routes."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from orion.api._shared import (
    ContextFilesRequest,
    GitCommitRequest,
    GitUndoRequest,
)

router = APIRouter()

# In-memory context file store (per-session, like CLI)
_context_files: dict[str, list[str]] = {}


# =============================================================================
# GIT OPERATIONS (Phase 1A -- closing CLI-only gap)
# =============================================================================


@router.get("/api/git/diff")
async def git_diff(workspace: str):
    """Get pending git diff for a workspace."""
    if not workspace or not Path(workspace).is_dir():
        raise HTTPException(status_code=400, detail="Invalid workspace path")
    try:
        import subprocess

        result = subprocess.run(
            ["git", "diff", "--stat"], cwd=workspace, capture_output=True, text=True, timeout=10
        )
        diff_full = subprocess.run(
            ["git", "diff"], cwd=workspace, capture_output=True, text=True, timeout=10
        )
        return {
            "stat": result.stdout,
            "diff": diff_full.stdout[:50000],  # Cap at 50KB
            "has_changes": bool(result.stdout.strip()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/git/commit")
async def git_commit(request: GitCommitRequest):
    """Commit all changes in a workspace."""
    if not request.workspace or not Path(request.workspace).is_dir():
        raise HTTPException(status_code=400, detail="Invalid workspace path")
    try:
        import subprocess

        subprocess.run(["git", "add", "-A"], cwd=request.workspace, check=True, timeout=10)
        result = subprocess.run(
            ["git", "commit", "-m", request.message],
            cwd=request.workspace,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Get commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=request.workspace,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return {
                "status": "success",
                "message": request.message,
                "hash": hash_result.stdout.strip(),
            }
        return {"status": "nothing_to_commit", "message": result.stdout.strip()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/git/undo")
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
                    "files_restored": getattr(result, "files_restored", 0),
                }
            return {"status": "nothing", "message": "No savepoints to undo"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# DOCTOR DIAGNOSTICS (Phase 1A -- closing CLI-only gap)
# =============================================================================


@router.get("/api/doctor")
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
        # Fallback if run_checks not available -- run basic checks
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
# CONTEXT FILES (Phase 1A -- closing CLI-only gap)
# =============================================================================


@router.get("/api/context/files")
async def get_context_files(workspace: str):
    """Get current context files for a workspace."""
    return {"files": _context_files.get(workspace, []), "workspace": workspace}


@router.post("/api/context/files")
async def add_context_files(request: ContextFilesRequest):
    """Add files to the context for a workspace."""
    if not request.workspace or not Path(request.workspace).is_dir():
        raise HTTPException(status_code=400, detail="Invalid workspace path")
    import glob as _glob

    current = _context_files.setdefault(request.workspace, [])
    added = []
    for pattern in request.files:
        full = os.path.join(request.workspace, pattern)
        matches = _glob.glob(full, recursive=True)
        for m in matches:
            rel = os.path.relpath(m, request.workspace)
            if rel not in current:
                current.append(rel)
                added.append(rel)
    return {"added": added, "total": len(current), "files": current}


@router.delete("/api/context/files")
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
# CONTEXT (repo map, quality)
# =============================================================================


@router.get("/api/context/map")
async def get_repo_map(workspace: str, max_tokens: int = 2048):
    """Get repository map for a workspace."""
    try:
        from orion.core.context.repo_map import generate_repo_map

        return {"map": generate_repo_map(workspace, max_tokens)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/context/quality")
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


@router.get("/api/context/stats")
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
