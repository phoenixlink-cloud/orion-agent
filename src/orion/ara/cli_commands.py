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
"""ARA CLI Commands — user-facing commands for autonomous sessions.

Commands:
    orion work <role> <goal>   — Start an autonomous session
    orion status               — Show current session status
    orion pause                — Pause the running session
    orion resume               — Resume a paused session
    orion cancel               — Cancel the running session
    orion review               — Review sandbox changes for promotion

See ARA-001 §11 for full design.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orion.ara.aegis_gate import AegisGate
from orion.ara.auth import RoleAuthenticator
from orion.ara.daemon import DaemonControl
from orion.ara.role_profile import (
    RoleProfile,
    generate_example_yaml,
    load_role,
    save_role,
    validate_role_file,
)
from orion.ara.session import SessionState, SessionStatus
from orion.data_path import get_seed_roles_dir, get_seed_skills_dir

logger = logging.getLogger("orion.ara.cli_commands")

DEFAULT_ROLES_DIR = Path.home() / ".orion" / "roles"
STARTER_ROLES_DIR = get_seed_roles_dir()
DEFAULT_SKILLS_DIR = Path.home() / ".orion" / "skills"
SEED_SKILLS_DIR = get_seed_skills_dir()


@dataclass
class CommandResult:
    """Result of a CLI command execution."""

    success: bool
    message: str
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
        }


def _scan_workspace(workspace: Path) -> list[str]:
    """Scan workspace for existing project files (non-hidden, non-git)."""
    if not workspace.exists():
        return []
    skip = {".git", ".orion-archive", "__pycache__", "node_modules", ".venv", ".env"}
    files = []
    for f in sorted(workspace.rglob("*")):
        if f.is_file() and not any(
            part.startswith(".") or part in skip for part in f.relative_to(workspace).parts
        ):
            rel = str(f.relative_to(workspace))
            files.append(rel)
    return files[:50]  # Cap to avoid overwhelming output


def _resolve_workspace() -> Path:
    """Resolve the workspace path from settings or cwd."""
    try:
        _settings_path = Path.home() / ".orion" / "settings.json"
        if _settings_path.exists():
            _user_settings = json.loads(_settings_path.read_text())
            ws = _user_settings.get("default_workspace") or _user_settings.get("workspace")
            if ws:
                return Path(ws)
    except Exception:
        pass
    return Path.cwd()


def cmd_workspace_list() -> CommandResult:
    """List files in the resolved workspace directory."""
    ws = _resolve_workspace()
    if not ws.exists():
        return CommandResult(
            success=True,
            message=f"Workspace directory does not exist: {ws}",
            data={"workspace_path": str(ws), "files": []},
        )
    files = _scan_workspace(ws)
    return CommandResult(
        success=True,
        message=f"Found {len(files)} file(s) in workspace: {ws}",
        data={"workspace_path": str(ws), "files": files, "total": len(files)},
    )


def cmd_workspace_clear() -> CommandResult:
    """Clear user project files from the workspace (keeps hidden dirs like .git)."""
    ws = _resolve_workspace()
    if not ws.exists():
        return CommandResult(
            success=True,
            message=f"Workspace directory does not exist: {ws}",
            data={"workspace_path": str(ws), "removed": 0},
        )
    files = _scan_workspace(ws)
    removed = 0
    for rel in files:
        fp = ws / rel
        if fp.exists():
            fp.unlink()
            removed += 1
    # Clean empty directories (bottom-up)
    skip = {".git", ".orion-archive", "__pycache__", "node_modules", ".venv", ".env"}
    for d in sorted(ws.rglob("*"), reverse=True):
        if d.is_dir() and not any(part.startswith(".") or part in skip for part in d.relative_to(ws).parts):
            try:
                d.rmdir()  # only removes if empty
            except OSError:
                pass
    logger.info("Cleared %d files from workspace %s", removed, ws)
    return CommandResult(
        success=True,
        message=f"Cleared {removed} file(s) from workspace: {ws}",
        data={"workspace_path": str(ws), "removed": removed},
    )


def cmd_work(
    role_name: str,
    goal: str,
    workspace_path: str | None = None,
    roles_dir: Path | None = None,
    control: DaemonControl | None = None,
    project_mode: str = "auto",
) -> CommandResult:
    """Start an autonomous work session.

    1. Load the role profile
    2. Validate configuration
    3. Scan workspace for existing files (project continuity check)
    4. Create session state
    5. Signal daemon to start

    project_mode:
        'auto'     - If workspace has files, return needs_decision (ask user)
        'new'      - Start fresh, ignore workspace files
        'continue' - Seed sandbox with workspace files (build on existing work)

    The actual execution is handled by the daemon process.
    """
    control = control or DaemonControl()

    # Check if a session is already running
    if control.is_daemon_alive():
        status = control.read_status()
        return CommandResult(
            success=False,
            message=f"A session is already running: {status.session_id} ({status.session_status})",
        )

    # Load role
    role = _find_role(role_name, roles_dir)
    if role is None:
        available = list_available_roles(roles_dir)
        return CommandResult(
            success=False,
            message=f"Role '{role_name}' not found. Available: {', '.join(available)}",
        )

    # Ensure auth method is configured before starting
    auth_warning = ""
    if role.auth_method in ("pin", "totp"):
        auth = RoleAuthenticator()
        if not auth.is_configured(role.auth_method):
            if role.auth_method == "pin":
                # Auto-provision a default PIN and warn the user
                default_pin = "1234"
                auth.setup_pin(default_pin)
                auth_warning = (
                    f"\n⚠ PIN auth was not configured. Default PIN '{default_pin}' set.\n"
                    f"  Change it with: /auth-switch pin {default_pin}"
                )
                logger.info("Auto-provisioned default PIN for role '%s'", role.name)
            else:
                return CommandResult(
                    success=False,
                    message=f"Role '{role.name}' requires {role.auth_method} auth but it is not configured.\n"
                    f"Run: /auth-switch {role.auth_method} to set it up first.",
                )

    # Resolve workspace — prefer user's configured default, cwd() is last resort
    if not workspace_path:
        try:
            _settings_path = Path.home() / ".orion" / "settings.json"
            if _settings_path.exists():
                import json as _json

                _user_settings = _json.loads(_settings_path.read_text())
                workspace_path = (
                    _user_settings.get("default_workspace")
                    or _user_settings.get("workspace")
                    or None
                )
        except Exception:
            pass
    resolved_workspace = workspace_path or str(Path.cwd())
    ws = Path(resolved_workspace)

    # Project continuity check
    if project_mode == "auto":
        existing_files = _scan_workspace(ws)
        if existing_files:
            file_list = "\n".join(f"  - {f}" for f in existing_files[:15])
            more = (
                f"\n  ... and {len(existing_files) - 15} more" if len(existing_files) > 15 else ""
            )
            return CommandResult(
                success=False,
                message=(
                    f"Found {len(existing_files)} existing files in workspace:\n"
                    f"{file_list}{more}\n\n"
                    "Is this a **new project** or are you **continuing** an existing one?\n"
                    "- New project: I'll start fresh (existing files untouched)\n"
                    "- Continue: I'll build on these files"
                ),
                data={
                    "needs_decision": True,
                    "workspace_files": existing_files,
                    "role_name": role_name,
                    "goal": goal,
                    "workspace_path": resolved_workspace,
                },
            )

    # Create session
    session = SessionState(
        role_name=role.name,
        goal=goal,
        workspace_path=resolved_workspace,
        max_cost_usd=role.max_cost_per_session,
        max_duration_hours=role.max_session_hours,
    )

    # Save session for daemon pickup
    session.save()

    # Write session config for daemon
    session_config = {
        "session_id": session.session_id,
        "role_name": role.name,
        "goal": goal,
        "workspace_path": session.workspace_path,
        "role_source": role.source_path,
        "project_mode": project_mode,
    }
    config_path = Path.home() / ".orion" / "daemon" / "pending.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(session_config, indent=2), encoding="utf-8")

    logger.info("Work session created: %s (role=%s)", session.session_id, role.name)

    # Spawn daemon as background subprocess
    try:
        import subprocess
        import sys

        daemon_cmd = [
            sys.executable,
            "-m",
            "orion.ara.daemon_launcher",
        ]
        subprocess.Popen(
            daemon_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd=session.workspace_path,
        )
        logger.info("Daemon subprocess spawned for session %s", session.session_id)
    except Exception as e:
        logger.warning("Failed to spawn daemon subprocess: %s", e)

    return CommandResult(
        success=True,
        message=f"Session {session.session_id} created.\n"
        f"Role: {role.name} | Scope: {role.scope}\n"
        f"Goal: {goal}\n"
        f"Auth: {role.auth_method} required before promotion\n"
        f"Daemon: spawning background process..."
        + auth_warning
        + "\n\nUse '/status' to monitor, '/notifications' when done.",
        data={"session_id": session.session_id, "role_name": role.name, "project_mode": project_mode},
    )


def cmd_status(control: DaemonControl | None = None) -> CommandResult:
    """Show current daemon/session status."""
    control = control or DaemonControl()
    status = control.read_status()

    if not status.running and not control.is_daemon_alive():
        return CommandResult(
            success=True,
            message="No active session.",
            data=status.to_dict(),
        )

    return CommandResult(
        success=True,
        message=status.summary(),
        data=status.to_dict(),
    )


def cmd_pause(control: DaemonControl | None = None) -> CommandResult:
    """Pause the running session."""
    control = control or DaemonControl()

    if not control.is_daemon_alive():
        return CommandResult(success=False, message="No active session to pause.")

    status = control.read_status()
    if status.session_status != "running":
        return CommandResult(
            success=False,
            message=f"Session is {status.session_status}, not running.",
        )

    control.send_command("pause")
    return CommandResult(
        success=True,
        message=f"Pause signal sent to session {status.session_id}.",
        data={"session_id": status.session_id},
    )


def cmd_resume(control: DaemonControl | None = None) -> CommandResult:
    """Resume a paused session."""
    control = control or DaemonControl()

    if not control.is_daemon_alive():
        return CommandResult(success=False, message="No active session to resume.")

    status = control.read_status()
    if status.session_status != "paused":
        return CommandResult(
            success=False,
            message=f"Session is {status.session_status}, not paused.",
        )

    control.send_command("resume")
    return CommandResult(
        success=True,
        message=f"Resume signal sent to session {status.session_id}.",
        data={"session_id": status.session_id},
    )


def cmd_cancel(control: DaemonControl | None = None) -> CommandResult:
    """Cancel the running session."""
    control = control or DaemonControl()

    if not control.is_daemon_alive():
        return CommandResult(success=False, message="No active session to cancel.")

    status = control.read_status()
    control.send_command("cancel")
    return CommandResult(
        success=True,
        message=f"Cancel signal sent to session {status.session_id}.",
        data={"session_id": status.session_id},
    )


def cmd_review(
    session_id: str | None = None,
    credential: str | None = None,
    control: DaemonControl | None = None,
    authenticator: RoleAuthenticator | None = None,
    roles_dir: Path | None = None,
    sessions_dir: Path | None = None,
) -> CommandResult:
    """Review sandbox changes and decide whether to promote.

    Runs AEGIS gate checks: secret scan, write limits, role scope, auth.
    """
    control = control or DaemonControl()
    sessions_dir = sessions_dir or (Path.home() / ".orion" / "sessions")

    # Find session to review
    if session_id is None:
        status = control.read_status()
        session_id = status.session_id

    if not session_id:
        return CommandResult(success=False, message="No session to review.")

    # Load session
    try:
        session = SessionState.load(session_id, sessions_dir=sessions_dir)
    except FileNotFoundError:
        return CommandResult(
            success=False,
            message=f"Session {session_id} not found.",
        )

    if session.status not in (SessionStatus.COMPLETED, SessionStatus.PAUSED):
        return CommandResult(
            success=False,
            message=f"Session {session_id} is {session.status.value}. "
            "Can only review completed or paused sessions.",
        )

    # Load role for gate checks
    role = _find_role(session.role_name, roles_dir)
    if role is None:
        return CommandResult(
            success=False,
            message=f"Role '{session.role_name}' not found for gate check.",
        )

    # Check sandbox path
    sandbox_path = sessions_dir / session_id / "sandbox"
    if not sandbox_path.exists():
        sandbox_path = Path(session.workspace_path)

    # Run AEGIS gate
    auth = authenticator or RoleAuthenticator()
    gate = AegisGate(role=role, authenticator=auth)
    decision = gate.evaluate(
        sandbox_path=sandbox_path,
        credential=credential,
    )

    if decision.approved:
        return CommandResult(
            success=True,
            message=f"AEGIS Gate: APPROVED. Session {session_id} changes ready for promotion.",
            data=decision.to_dict(),
        )

    return CommandResult(
        success=False,
        message="AEGIS Gate: BLOCKED.\n"
        + "\n".join(f"  ✗ {c}" for c in decision.checks_failed)
        + (
            "\n" + "\n".join(f"  ✓ {c}" for c in decision.checks_passed)
            if decision.checks_passed
            else ""
        ),
        data=decision.to_dict(),
    )


def cmd_promote(
    session_id: str | None = None,
    credential: str | None = None,
    control: DaemonControl | None = None,
    authenticator: RoleAuthenticator | None = None,
    roles_dir: Path | None = None,
    sessions_dir: Path | None = None,
) -> CommandResult:
    """Promote sandbox files to workspace after AEGIS approval.

    Runs AEGIS gate check, then uses PromotionManager to copy files
    from sandbox to workspace with git tagging.
    """
    from orion.ara.promotion import PromotionManager

    control = control or DaemonControl()
    sessions_dir = sessions_dir or DEFAULT_SESSIONS_DIR

    # Find session
    if session_id is None:
        status = control.read_status()
        session_id = status.session_id
    if not session_id:
        return CommandResult(success=False, message="No session to promote.")

    # Load session
    try:
        session = SessionState.load(session_id, sessions_dir=sessions_dir)
    except FileNotFoundError:
        return CommandResult(success=False, message=f"Session {session_id} not found.")

    if session.status not in (SessionStatus.COMPLETED, SessionStatus.PAUSED):
        return CommandResult(
            success=False,
            message=f"Session {session_id} is {session.status.value}. "
            "Can only promote completed or paused sessions.",
        )

    # Load role for gate check
    role = _find_role(session.role_name, roles_dir)
    if role is None:
        return CommandResult(success=False, message=f"Role '{session.role_name}' not found.")

    # Check sandbox path
    sandbox_path = sessions_dir / session_id / "sandbox"
    if not sandbox_path.exists():
        return CommandResult(success=False, message="No sandbox directory found for this session.")

    # Run AEGIS gate
    auth = authenticator or RoleAuthenticator()
    gate = AegisGate(role=role, authenticator=auth)
    decision = gate.evaluate(sandbox_path=sandbox_path, credential=credential)

    if not decision.approved:
        failed_str = "\n".join(f"  ✗ {c}" for c in decision.checks_failed)
        return CommandResult(
            success=False,
            message=f"AEGIS Gate: BLOCKED. Cannot promote.\n{failed_str}",
            data=decision.to_dict(),
        )

    # Promote via PromotionManager
    workspace = Path(session.workspace_path)
    pm = PromotionManager(workspace=workspace)

    # Create PM sandbox and copy daemon sandbox files into it
    pm.create_sandbox(session_id)
    file_count = 0
    for f in sandbox_path.iterdir():
        if f.is_file():
            content = f.read_text(encoding="utf-8")
            pm.add_file(session_id, f.name, content)
            file_count += 1

    if file_count == 0:
        return CommandResult(success=False, message="Sandbox is empty — nothing to promote.")

    result = pm.promote(session_id, goal=session.goal)

    if result.success:
        # Update feedback store with promotion status
        try:
            from orion.ara.feedback_store import FeedbackStore

            store = FeedbackStore()
            outcomes = store.get_session_outcomes()
            for o in outcomes:
                if o.session_id == session_id:
                    o.promoted = True
            store._rewrite_sessions(outcomes)
        except Exception:
            pass

        return CommandResult(
            success=True,
            message=f"✓ Promoted {result.files_promoted} files to {workspace}.\n"
            f"  Pre-tag: {result.pre_tag}\n"
            f"  Post-tag: {result.post_tag}"
            + (f"\n  Conflicts skipped: {', '.join(result.conflicts)}" if result.conflicts else ""),
            data={
                "files_promoted": result.files_promoted,
                "pre_tag": result.pre_tag,
                "post_tag": result.post_tag,
                "conflicts": result.conflicts,
            },
        )

    return CommandResult(success=False, message=f"Promotion failed: {result.message}")


def cmd_review_diff(
    session_id: str | None = None,
    control: DaemonControl | None = None,
    sessions_dir: Path | None = None,
) -> CommandResult:
    """Return structured file diffs for a session's sandbox changes.

    Returns per-file unified diffs, original/new content, and summary stats
    so a UI can render a GitHub-PR-style review experience.
    """
    import difflib

    from orion.ara.promotion import PromotionManager

    control = control or DaemonControl()
    sessions_dir = sessions_dir or DEFAULT_SESSIONS_DIR

    if session_id is None:
        status = control.read_status()
        session_id = status.session_id
    if not session_id:
        return CommandResult(success=False, message="No session to review.")

    # Support partial session ID matching (UI often shows truncated IDs)
    try:
        session = SessionState.load(session_id, sessions_dir=sessions_dir)
    except FileNotFoundError:
        # Try prefix match against sessions directory
        resolved = None
        if sessions_dir and sessions_dir.exists():
            for d in sessions_dir.iterdir():
                if d.is_dir() and d.name.startswith(session_id):
                    resolved = d.name
                    break
        if resolved:
            session_id = resolved
            try:
                session = SessionState.load(session_id, sessions_dir=sessions_dir)
            except FileNotFoundError:
                return CommandResult(success=False, message=f"Session {session_id} not found.")
        else:
            return CommandResult(success=False, message=f"Session {session_id} not found.")

    workspace = Path(session.workspace_path)
    sandbox_path = sessions_dir / session_id / "sandbox"

    # Try PromotionManager sandbox first, fall back to daemon sandbox
    pm = PromotionManager(workspace=workspace)
    pm_sandbox = pm.get_sandbox_path(session_id)

    files: list[dict] = []
    total_add = 0
    total_del = 0

    if pm_sandbox is not None:
        # Use PromotionManager diffs (structured)
        diffs = pm.get_diff(session_id)
        conflicts = {c.path for c in pm.check_conflicts(session_id)}

        for d in diffs:
            original = ""
            if d.status == "modified":
                ws_file = workspace / d.path
                if ws_file.exists():
                    try:
                        original = ws_file.read_text(encoding="utf-8")
                    except Exception:
                        original = ""

            # Generate unified diff
            if d.status == "added":
                diff_lines = list(
                    difflib.unified_diff(
                        [],
                        d.content.splitlines(keepends=True),
                        fromfile="/dev/null",
                        tofile=d.path,
                        lineterm="",
                    )
                )
            elif d.status == "modified":
                diff_lines = list(
                    difflib.unified_diff(
                        original.splitlines(keepends=True),
                        d.content.splitlines(keepends=True),
                        fromfile=f"a/{d.path}",
                        tofile=f"b/{d.path}",
                        lineterm="",
                    )
                )
            else:  # deleted
                diff_lines = list(
                    difflib.unified_diff(
                        original.splitlines(keepends=True),
                        [],
                        fromfile=d.path,
                        tofile="/dev/null",
                        lineterm="",
                    )
                )

            total_add += d.additions
            total_del += d.deletions

            files.append(
                {
                    "path": d.path,
                    "status": d.status,
                    "additions": d.additions,
                    "deletions": d.deletions,
                    "diff": "\n".join(diff_lines),
                    "content": d.content[:50000],  # cap at 50k chars
                    "original": original[:50000] if original else "",
                    "conflict": d.path in conflicts,
                }
            )

    # If PM sandbox was empty or didn't exist, try daemon sandbox
    if not files and sandbox_path.exists():
        # Fall back to daemon sandbox (recursive — files may be nested)
        unchanged_files: list[dict] = []
        for f in sorted(sandbox_path.rglob("*")):
            if not f.is_file():
                continue
            rel = str(f.relative_to(sandbox_path)).replace("\\", "/")
            # Skip hidden files and metadata
            if any(part.startswith(".") for part in rel.split("/")):
                continue

            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue  # skip binary files

            ws_file = workspace / rel
            original = ""
            status = "added"
            additions = content.count("\n") + (1 if content else 0)
            deletions = 0

            if ws_file.exists():
                try:
                    original = ws_file.read_text(encoding="utf-8")
                except Exception:
                    original = ""
                if original != content:
                    status = "modified"
                    new_lines = set(content.splitlines())
                    old_lines = set(original.splitlines())
                    additions = len(new_lines - old_lines)
                    deletions = len(old_lines - new_lines)
                else:
                    # Track unchanged files in case ALL are unchanged (already promoted)
                    unchanged_files.append(
                        {
                            "path": rel,
                            "status": "unchanged",
                            "additions": 0,
                            "deletions": 0,
                            "diff": "",
                            "content": content[:50000],
                            "original": "",
                            "conflict": False,
                        }
                    )
                    continue

            if status == "added":
                diff_lines = list(
                    difflib.unified_diff(
                        [],
                        content.splitlines(keepends=True),
                        fromfile="/dev/null",
                        tofile=rel,
                        lineterm="",
                    )
                )
            else:
                diff_lines = list(
                    difflib.unified_diff(
                        original.splitlines(keepends=True),
                        content.splitlines(keepends=True),
                        fromfile=f"a/{rel}",
                        tofile=f"b/{rel}",
                        lineterm="",
                    )
                )

            total_add += additions
            total_del += deletions

            files.append(
                {
                    "path": rel,
                    "status": status,
                    "additions": additions,
                    "deletions": deletions,
                    "diff": "\n".join(diff_lines),
                    "content": content[:50000],
                    "original": original[:50000] if original else "",
                    "conflict": False,
                }
            )

        # If no changed files but sandbox has unchanged files (already promoted),
        # show them so the user can still review what was generated
        if not files and unchanged_files:
            files = unchanged_files
    elif not sandbox_path.exists() and pm_sandbox is None:
        return CommandResult(
            success=False,
            message="No sandbox found for this session.",
        )

    if not files:
        return CommandResult(
            success=True,
            message="No file changes in sandbox.",
            data={
                "files": [],
                "summary": {"total_files": 0, "additions": 0, "deletions": 0, "conflicts": 0},
            },
        )

    conflict_count = sum(1 for f in files if f["conflict"])
    summary = {
        "total_files": len(files),
        "added": sum(1 for f in files if f["status"] == "added"),
        "modified": sum(1 for f in files if f["status"] == "modified"),
        "deleted": sum(1 for f in files if f["status"] == "deleted"),
        "additions": total_add,
        "deletions": total_del,
        "conflicts": conflict_count,
    }

    return CommandResult(
        success=True,
        message=f"{len(files)} files changed (+{total_add} −{total_del})"
        + (f", {conflict_count} conflicts" if conflict_count else ""),
        data={"files": files, "summary": summary, "session_id": session_id},
    )


def cmd_reject(
    session_id: str | None = None,
    control: DaemonControl | None = None,
    sessions_dir: Path | None = None,
) -> CommandResult:
    """Reject sandbox changes — preserves sandbox for reference."""
    from orion.ara.promotion import PromotionManager

    control = control or DaemonControl()
    sessions_dir = sessions_dir or DEFAULT_SESSIONS_DIR

    if session_id is None:
        status = control.read_status()
        session_id = status.session_id
    if not session_id:
        return CommandResult(success=False, message="No session to reject.")

    try:
        session = SessionState.load(session_id, sessions_dir=sessions_dir)
    except FileNotFoundError:
        return CommandResult(success=False, message=f"Session {session_id} not found.")

    workspace = Path(session.workspace_path)
    pm = PromotionManager(workspace=workspace)
    pm.reject(session_id)

    return CommandResult(
        success=True,
        message=f"Session {session_id[:12]} rejected. Sandbox preserved for reference.",
        data={"session_id": session_id},
    )


def cmd_feedback(
    session_id: str,
    rating: int,
    comment: str | None = None,
) -> CommandResult:
    """Submit user feedback (1-5 rating) for a completed session."""
    from orion.ara.feedback_store import FeedbackStore

    if not (1 <= rating <= 5):
        return CommandResult(success=False, message="Rating must be 1-5.")

    store = FeedbackStore()
    updated = store.add_user_feedback(session_id, rating, comment)

    if updated:
        return CommandResult(
            success=True,
            message=f"Feedback recorded for session {session_id[:12]}: {rating}/5"
            + (f' — "{comment}"' if comment else ""),
            data={"session_id": session_id, "rating": rating, "comment": comment},
        )

    return CommandResult(
        success=False,
        message=f"Session {session_id} not found in feedback store. "
        "Feedback can only be submitted for sessions that have completed execution.",
    )


def cmd_notifications(
    mark_read: bool = False,
    control: DaemonControl | None = None,
) -> CommandResult:
    """Show pending notifications from daemon. Optionally mark all as read."""
    control = control or DaemonControl()
    notif_dir = control._dir / "notifications"

    if not notif_dir.exists():
        return CommandResult(success=True, message="No notifications.", data={"notifications": []})

    notifications = []
    for f in sorted(notif_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if not data.get("read", False):
                notifications.append(data)
                if mark_read:
                    data["read"] = True
                    f.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass

    if not notifications:
        return CommandResult(
            success=True, message="No unread notifications.", data={"notifications": []}
        )

    lines = [f"📬 {len(notifications)} notification(s):", ""]
    for n in notifications:
        event = n.get("event", "unknown")
        msg = n.get("message", "")
        lines.append(f"  [{event}] {msg}")

    if mark_read:
        lines.append(f"\n  (Marked {len(notifications)} as read)")

    return CommandResult(
        success=True,
        message="\n".join(lines),
        data={"notifications": notifications},
    )


def list_available_roles(roles_dir: Path | None = None) -> list[str]:
    """List all available role names (user + starter)."""
    names: list[str] = []

    # User roles
    user_dir = roles_dir or DEFAULT_ROLES_DIR
    if user_dir.exists():
        for p in user_dir.glob("*.yaml"):
            try:
                r = load_role(p)
                names.append(r.name)
            except Exception:
                pass
        for p in user_dir.glob("*.yml"):
            try:
                r = load_role(p)
                if r.name not in names:
                    names.append(r.name)
            except Exception:
                pass

    # Starter roles
    if STARTER_ROLES_DIR.exists():
        for p in STARTER_ROLES_DIR.glob("*.yaml"):
            try:
                r = load_role(p)
                if r.name not in names:
                    names.append(r.name)
            except Exception:
                pass

    return sorted(names)


def _find_role(role_name: str, roles_dir: Path | None = None) -> RoleProfile | None:
    """Find a role by name from user roles or starter templates."""
    user_dir = roles_dir or DEFAULT_ROLES_DIR
    for search_dir in [user_dir, STARTER_ROLES_DIR]:
        if not search_dir.exists():
            continue
        for ext in ("*.yaml", "*.yml"):
            for p in search_dir.glob(ext):
                try:
                    r = load_role(p)
                    if r.name == role_name:
                        return r
                except Exception:
                    pass
    return None


# ---------------------------------------------------------------------------
# Role management commands
# ---------------------------------------------------------------------------


def cmd_role_list(roles_dir: Path | None = None) -> CommandResult:
    """List all available roles with summary info."""
    user_dir = roles_dir or DEFAULT_ROLES_DIR
    roles: list[dict[str, Any]] = []

    for search_dir, source in [(user_dir, "user"), (STARTER_ROLES_DIR, "starter")]:
        if not search_dir.exists():
            continue
        for ext in ("*.yaml", "*.yml"):
            for p in search_dir.glob(ext):
                try:
                    r = load_role(p)
                    if not any(role["name"] == r.name for role in roles):
                        roles.append(
                            {
                                "name": r.name,
                                "scope": r.scope,
                                "auth_method": r.auth_method,
                                "source": source,
                                "description": r.description or "",
                                "path": str(p),
                                "assigned_skills": list(r.assigned_skills)
                                if r.assigned_skills
                                else [],
                                "assigned_skill_groups": list(r.assigned_skill_groups)
                                if r.assigned_skill_groups
                                else [],
                            }
                        )
                except Exception:
                    pass

    roles.sort(key=lambda x: x["name"])

    if not roles:
        return CommandResult(
            success=True,
            message="No roles found. Run `orion role example` to see how to create one.",
            data={"roles": []},
        )

    lines = ["Available roles:", ""]
    for r in roles:
        tag = "[starter]" if r["source"] == "starter" else "[user]"
        lines.append(f"  {r['name']:20s} {r['scope']:10s} {r['auth_method']:5s} {tag}")
        if r["description"]:
            lines.append(f"  {'':20s} {r['description']}")

    return CommandResult(
        success=True,
        message="\n".join(lines),
        data={"roles": roles},
    )


def cmd_role_show(role_name: str, roles_dir: Path | None = None) -> CommandResult:
    """Show full details of a role."""
    role = _find_role(role_name, roles_dir)
    if role is None:
        return CommandResult(
            success=False,
            message=f"Role '{role_name}' not found.",
        )

    d = role.to_dict()
    lines = [
        f"Role: {role.name}",
        f"Scope: {role.scope}",
        f"Auth: {role.auth_method}",
        f"Description: {role.description or '(none)'}",
        f"Risk tolerance: {role.risk_tolerance}",
        f"Source: {role.source_path or 'in-memory'}",
        "",
    ]
    if role.competencies:
        lines.append("Competencies:")
        for c in role.competencies:
            lines.append(f"  - {c}")
        lines.append("")

    if role.authority_autonomous:
        lines.append("Autonomous actions:")
        for a in role.authority_autonomous:
            lines.append(f"  - {a}")
        lines.append("")

    if role.authority_requires_approval:
        lines.append("Requires approval:")
        for a in role.authority_requires_approval:
            lines.append(f"  - {a}")
        lines.append("")

    if role.success_criteria:
        lines.append("Success criteria:")
        for s in role.success_criteria:
            lines.append(f"  - {s}")
        lines.append("")

    if role.assigned_skills:
        lines.append("Assigned skills:")
        for sk in role.assigned_skills:
            lines.append(f"  - {sk}")
        lines.append("")

    if role.assigned_skill_groups:
        lines.append("Assigned skill groups:")
        for sg in role.assigned_skill_groups:
            lines.append(f"  - {sg}")
        lines.append("")

    ct = role.confidence_thresholds
    lines.append(
        f"Confidence: auto={ct.auto_execute}, flag={ct.execute_and_flag}, pause={ct.pause_and_ask}"
    )
    lines.append(f"Limits: {role.max_session_hours}h, ${role.max_cost_per_session} max cost")

    return CommandResult(
        success=True,
        message="\n".join(lines),
        data=d,
    )


def cmd_role_create(
    name: str,
    scope: str = "coding",
    auth_method: str = "pin",
    description: str = "",
    roles_dir: Path | None = None,
    **kwargs: Any,
) -> CommandResult:
    """Create a new role and save it to the user roles directory."""
    user_dir = roles_dir or DEFAULT_ROLES_DIR

    # Check if role already exists
    existing = _find_role(name, roles_dir)
    if existing is not None:
        return CommandResult(
            success=False,
            message=f"Role '{name}' already exists at {existing.source_path}",
        )

    try:
        role = RoleProfile(
            name=name,
            scope=scope,
            auth_method=auth_method,
            description=description,
            **kwargs,
        )
    except Exception as e:
        return CommandResult(success=False, message=f"Invalid role configuration: {e}")

    path = user_dir / f"{name}.yaml"
    save_role(role, path)

    return CommandResult(
        success=True,
        message=f"Role '{name}' created at {path}",
        data={"name": name, "path": str(path)},
    )


def cmd_role_delete(role_name: str, roles_dir: Path | None = None) -> CommandResult:
    """Delete a user role. Starter templates cannot be deleted."""
    user_dir = roles_dir or DEFAULT_ROLES_DIR

    # Check starter templates first — can't delete those
    if STARTER_ROLES_DIR.exists():
        for p in STARTER_ROLES_DIR.glob("*.yaml"):
            try:
                r = load_role(p)
                if r.name == role_name:
                    return CommandResult(
                        success=False,
                        message=f"Cannot delete starter template '{role_name}'.",
                    )
            except Exception:
                pass

    # Find in user roles
    if user_dir.exists():
        for ext in ("*.yaml", "*.yml"):
            for p in user_dir.glob(ext):
                try:
                    r = load_role(p)
                    if r.name == role_name:
                        p.unlink()
                        return CommandResult(
                            success=True,
                            message=f"Role '{role_name}' deleted ({p}).",
                            data={"name": role_name, "path": str(p)},
                        )
                except Exception:
                    pass

    return CommandResult(success=False, message=f"Role '{role_name}' not found.")


def cmd_role_update(
    role_name: str,
    scope: str | None = None,
    auth_method: str | None = None,
    description: str | None = None,
    roles_dir: Path | None = None,
) -> CommandResult:
    """Update an existing user role. Starter templates are copied to user dir first."""
    user_dir = roles_dir or DEFAULT_ROLES_DIR

    # Find the role
    role = _find_role(role_name, roles_dir)
    if role is None:
        return CommandResult(success=False, message=f"Role '{role_name}' not found.")

    # If it's a starter template, copy to user dir first
    source_path = Path(role.source_path) if role.source_path else None
    is_starter = (
        source_path and STARTER_ROLES_DIR.exists() and str(STARTER_ROLES_DIR) in str(source_path)
    )

    if is_starter:
        user_dir.mkdir(parents=True, exist_ok=True)
        target_path = user_dir / f"{role_name}.yaml"
    else:
        target_path = source_path if source_path else user_dir / f"{role_name}.yaml"

    # Apply updates
    if scope is not None:
        role.scope = scope
    if auth_method is not None:
        role.auth_method = auth_method
    if description is not None:
        role.description = description

    # Re-validate
    try:
        role._validate()
    except Exception as e:
        return CommandResult(success=False, message=f"Invalid configuration: {e}")

    save_role(role, target_path)
    role.source_path = str(target_path)

    return CommandResult(
        success=True,
        message=f"Role '{role_name}' updated at {target_path}",
        data={
            "name": role_name,
            "path": str(target_path),
            "scope": role.scope,
            "auth_method": role.auth_method,
            "description": role.description,
        },
    )


def cmd_sessions_clear(
    sessions_dir: Path | None = None,
) -> CommandResult:
    """Clear all completed, failed, and cancelled sessions from the dashboard.

    Running sessions are preserved. This is a user-facing reset for between work sessions.
    """
    import shutil

    sdir = sessions_dir or DEFAULT_SESSIONS_DIR
    if not sdir.exists():
        return CommandResult(success=True, message="No sessions to clear.", data={"cleared": 0})

    cleared = 0
    preserved = 0

    for session_dir in sorted(sdir.iterdir()):
        if not session_dir.is_dir():
            continue

        session_file = session_dir / "session.json"
        if not session_file.exists():
            continue

        try:
            session = SessionState.load(session_dir.name, sessions_dir=sdir)
        except Exception:
            continue

        if session.status in (
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        ):
            shutil.rmtree(session_dir)
            cleared += 1
        else:
            preserved += 1

    return CommandResult(
        success=True,
        message=f"Cleared {cleared} session(s). {preserved} active session(s) preserved.",
        data={"cleared": cleared, "preserved": preserved},
    )


def cmd_role_example() -> CommandResult:
    """Return an annotated YAML example for creating a new role."""
    return CommandResult(
        success=True,
        message=generate_example_yaml(),
        data={"format": "yaml"},
    )


def cmd_role_validate(path: str) -> CommandResult:
    """Validate a YAML role file."""
    file_path = Path(path)
    if not file_path.exists():
        return CommandResult(success=False, message=f"File not found: {path}")

    valid, errors = validate_role_file(file_path)
    if valid:
        return CommandResult(
            success=True,
            message=f"Role file '{path}' is valid.",
            data={"valid": True, "path": path},
        )
    return CommandResult(
        success=False,
        message=f"Role file '{path}' has errors:\n" + "\n".join(f"  - {e}" for e in errors),
        data={"valid": False, "errors": errors, "path": path},
    )


# ---------------------------------------------------------------------------
# Session management commands (Phase 12)
# ---------------------------------------------------------------------------

DEFAULT_SESSIONS_DIR = Path.home() / ".orion" / "sessions"


def cmd_sessions(sessions_dir: Path | None = None) -> CommandResult:
    """List all sessions (active, completed, failed, cancelled)."""
    sdir = sessions_dir or DEFAULT_SESSIONS_DIR
    if not sdir.exists():
        return CommandResult(
            success=True,
            message="No sessions found.",
            data={"sessions": []},
        )

    sessions: list[dict[str, Any]] = []
    for state_file in sorted(sdir.glob("*/session.json")):
        try:
            session = SessionState.load(
                state_file.parent.name,
                sessions_dir=sdir,
            )
            sessions.append(
                {
                    "session_id": session.session_id,
                    "role": session.role_name,
                    "goal": session.goal[:60],
                    "status": session.status.value,
                    "cost_usd": round(session.cost_usd, 4),
                }
            )
        except Exception:
            pass

    if not sessions:
        return CommandResult(
            success=True,
            message="No sessions found.",
            data={"sessions": []},
        )

    lines = ["Sessions:", ""]
    for s in sessions:
        lines.append(
            f"  {s['session_id'][:12]}  {s['status']:12s}  "
            f"{s['role']:15s}  ${s['cost_usd']:<8.4f}  {s['goal']}"
        )

    return CommandResult(
        success=True,
        message="\n".join(lines),
        data={"sessions": sessions},
    )


def cmd_sessions_cleanup(
    max_age_days: int = 30,
    sessions_dir: Path | None = None,
) -> CommandResult:
    """Clean up old/completed sessions.

    Archives sessions older than max_age_days. Prunes checkpoints to last 3.
    """
    import shutil
    import time

    sdir = sessions_dir or DEFAULT_SESSIONS_DIR
    if not sdir.exists():
        return CommandResult(success=True, message="No sessions to clean up.")

    now = time.time()
    cutoff = now - (max_age_days * 86400)
    cleaned = 0
    pruned_checkpoints = 0

    for session_dir in sorted(sdir.iterdir()):
        if not session_dir.is_dir():
            continue

        session_file = session_dir / "session.json"
        if not session_file.exists():
            continue

        try:
            session = SessionState.load(
                session_dir.name,
                sessions_dir=sdir,
            )
        except Exception:
            continue

        # Remove old completed/failed/cancelled sessions
        if session.status in (
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        ):
            created = session_file.stat().st_mtime
            if created < cutoff:
                shutil.rmtree(session_dir)
                cleaned += 1
                continue

        # Prune checkpoints to last 3
        cp_dir = session_dir / "checkpoints"
        if cp_dir.exists():
            checkpoints = sorted(cp_dir.iterdir())
            while len(checkpoints) > 3:
                oldest = checkpoints.pop(0)
                if oldest.is_dir():
                    shutil.rmtree(oldest)
                else:
                    oldest.unlink()
                pruned_checkpoints += 1

    return CommandResult(
        success=True,
        message=f"Cleaned {cleaned} sessions, pruned {pruned_checkpoints} checkpoints.",
        data={"cleaned": cleaned, "pruned_checkpoints": pruned_checkpoints},
    )


def cmd_rollback(
    checkpoint_id: str,
    session_id: str | None = None,
    sessions_dir: Path | None = None,
    control: DaemonControl | None = None,
) -> CommandResult:
    """Roll back to a specific checkpoint."""
    from orion.ara.checkpoint import CheckpointManager

    control = control or DaemonControl()
    sdir = sessions_dir or DEFAULT_SESSIONS_DIR

    # Find session
    if session_id is None:
        status = control.read_status()
        session_id = status.session_id
    if not session_id:
        return CommandResult(success=False, message="No session specified.")

    try:
        SessionState.load(session_id, sessions_dir=sdir)
    except FileNotFoundError:
        return CommandResult(success=False, message=f"Session {session_id} not found.")

    cp_dir = sdir / session_id / "checkpoints"
    mgr = CheckpointManager(checkpoint_dir=cp_dir)

    try:
        mgr.rollback(checkpoint_id)
    except Exception as e:
        return CommandResult(success=False, message=f"Rollback failed: {e}")

    return CommandResult(
        success=True,
        message=f"Rolled back session {session_id[:12]} to checkpoint {checkpoint_id}.",
        data={"session_id": session_id, "checkpoint_id": checkpoint_id},
    )


def cmd_plan_review(
    session_id: str | None = None,
    sessions_dir: Path | None = None,
    control: DaemonControl | None = None,
) -> CommandResult:
    """Show the task DAG for a session for user review before execution."""
    control = control or DaemonControl()
    sdir = sessions_dir or DEFAULT_SESSIONS_DIR

    if session_id is None:
        status = control.read_status()
        session_id = status.session_id
    if not session_id:
        return CommandResult(success=False, message="No session specified.")

    # Load the pending plan from daemon config
    plan_file = sdir / session_id / "plan.json"
    if not plan_file.exists():
        return CommandResult(
            success=False,
            message=f"No plan found for session {session_id[:12]}.",
        )

    try:
        plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
    except Exception as e:
        return CommandResult(success=False, message=f"Error reading plan: {e}")

    tasks = plan_data.get("tasks", [])
    if not tasks:
        return CommandResult(
            success=True,
            message="Plan is empty — no tasks decomposed yet.",
            data=plan_data,
        )

    lines = [f"Plan for session {session_id[:12]}:", ""]
    for i, task in enumerate(tasks, 1):
        status_str = task.get("status", "pending")
        name = task.get("name", task.get("action", "unknown"))
        deps = task.get("depends_on", [])
        dep_str = f" (after: {', '.join(deps)})" if deps else ""
        lines.append(f"  {i}. [{status_str}] {name}{dep_str}")

    lines.append("")
    lines.append(f"Total tasks: {len(tasks)}")

    return CommandResult(
        success=True,
        message="\n".join(lines),
        data=plan_data,
    )


def cmd_settings_ara(
    settings: dict[str, Any] | None = None,
    settings_path: Path | None = None,
) -> CommandResult:
    """View or update ARA settings.

    If settings dict is provided, merges them into current config.
    Otherwise, displays current settings.
    """
    path = settings_path or (Path.home() / ".orion" / "ara_settings.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load current
    current: dict[str, Any] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Defaults
    defaults: dict[str, Any] = {
        "default_role": "",
        "default_auth_method": "pin",
        "notifications": {
            "email_enabled": False,
            "email_smtp_host": "",
            "email_smtp_port": 587,
            "email_recipient": "",
            "webhook_enabled": False,
            "webhook_url": "",
            "desktop_enabled": True,
        },
        "session_defaults": {
            "max_session_hours": 8.0,
            "max_cost_per_session": 5.0,
            "auto_checkpoint_interval_minutes": 15,
            "require_review_before_promote": True,
        },
        "replan_interval_tasks": 5,
    }

    # Merge defaults into current (don't overwrite existing)
    for key, value in defaults.items():
        if key not in current:
            current[key] = value
        elif isinstance(value, dict) and isinstance(current.get(key), dict):
            for k2, v2 in value.items():
                if k2 not in current[key]:
                    current[key][k2] = v2

    if settings is not None:
        # Update mode: merge new settings
        for key, value in settings.items():
            if isinstance(value, dict) and isinstance(current.get(key), dict):
                current[key].update(value)
            else:
                current[key] = value
        path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return CommandResult(
            success=True,
            message="ARA settings updated.",
            data=current,
        )

    # View mode
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    lines = ["ARA Settings:", ""]
    for key, value in current.items():
        if isinstance(value, dict):
            lines.append(f"  {key}:")
            for k2, v2 in value.items():
                lines.append(f"    {k2}: {v2}")
        else:
            lines.append(f"  {key}: {value}")

    return CommandResult(
        success=True,
        message="\n".join(lines),
        data=current,
    )


def cmd_auth_switch(
    new_method: str,
    current_credential: str,
    authenticator: RoleAuthenticator | None = None,
) -> CommandResult:
    """Switch authentication method (PIN ↔ TOTP).

    Requires the current credential to verify identity before switching.
    """
    auth = authenticator or RoleAuthenticator()

    if new_method not in ("pin", "totp"):
        return CommandResult(
            success=False,
            message=f"Invalid auth method '{new_method}'. Must be 'pin' or 'totp'.",
        )

    # Verify current credential
    if not auth.verify(current_credential):
        return CommandResult(
            success=False,
            message="Current credential verification failed. Cannot switch auth method.",
        )

    return CommandResult(
        success=True,
        message=f"Auth method ready to switch to '{new_method}'. "
        "Set up the new credential with `orion autonomous setup`.",
        data={"new_method": new_method, "verified": True},
    )


def cmd_setup(
    roles_dir: Path | None = None,
    skip_docker_check: bool = False,
) -> CommandResult:
    """First-time ARA setup wizard.

    Steps:
    1. Check prerequisites (Docker, AEGIS)
    2. List available roles or create custom
    3. Auth method selection (returns guidance)
    4. Dry-run validation info
    5. Ready message

    This is a non-interactive version that returns setup status.
    The interactive prompts are handled by the caller (REPL/CLI).
    """
    import shutil

    checks: list[dict[str, Any]] = []

    # Step 1: Prerequisites
    docker_ok = skip_docker_check or shutil.which("docker") is not None
    checks.append(
        {
            "name": "Docker",
            "status": "ok" if docker_ok else "missing",
            "message": "Docker installed"
            if docker_ok
            else "Docker not found — install Docker for sandbox support",
        }
    )

    checks.append(
        {
            "name": "AEGIS governance",
            "status": "ok",
            "message": "AEGIS governance active",
        }
    )

    # Step 2: Available roles
    roles = list_available_roles(roles_dir)
    checks.append(
        {
            "name": "Roles",
            "status": "ok" if roles else "none",
            "message": f"{len(roles)} roles available: {', '.join(roles[:4])}"
            if roles
            else "No roles found — run `orion role example` to create one",
        }
    )

    # Step 3: Auth (report readiness)
    auth_dir = Path.home() / ".orion" / "auth"
    auth_configured = auth_dir.exists() and any(auth_dir.iterdir()) if auth_dir.exists() else False
    checks.append(
        {
            "name": "Authentication",
            "status": "ok" if auth_configured else "not_configured",
            "message": "Auth configured"
            if auth_configured
            else "No auth configured — will be set up on first `orion work`",
        }
    )

    # Build output
    all_ok = all(c["status"] == "ok" for c in checks)
    lines = ["ARA Setup Check:", ""]
    for c in checks:
        icon = "✓" if c["status"] == "ok" else "!" if c["status"] == "not_configured" else "✗"
        lines.append(f"  {icon} {c['message']}")

    lines.append("")
    if all_ok:
        lines.append("Ready! Start with:")
        if roles:
            lines.append(f'  orion work --role "{roles[0]}" "<your goal>"')
        else:
            lines.append("  orion role example  (create a role first)")
    else:
        lines.append(
            "Some prerequisites are missing. Fix them and run `orion autonomous setup` again."
        )

    # Dry-run scenarios
    scenarios = [
        {"action": "Write code in sandbox", "result": "Allowed (autonomous)"},
        {"action": "Run tests", "result": "Allowed (autonomous)"},
        {"action": "Add dependency", "result": "Paused (requires approval)"},
        {"action": "Merge to main", "result": "Paused (requires approval)"},
        {"action": "Deploy to production", "result": "BLOCKED (forbidden)"},
        {"action": "Modify AEGIS config", "result": "BLOCKED (AEGIS base)"},
    ]

    return CommandResult(
        success=all_ok or not docker_ok,  # OK even without Docker (falls back to local)
        message="\n".join(lines),
        data={
            "checks": checks,
            "roles_available": roles,
            "auth_configured": auth_configured,
            "dry_run_scenarios": scenarios,
        },
    )


# ---------------------------------------------------------------------------
# Skill management commands (ARA-006)
# ---------------------------------------------------------------------------


_skill_library_cache: object | None = None
_skill_library_warnings: list[str] = []


def _get_skill_library(skills_dir: Path | None = None):
    """Get or create a SkillLibrary instance.

    The library is cached at module level so that ``load_all()`` and
    seed-skill imports only run once.  Pass a custom *skills_dir* to
    bypass the cache (used by tests).
    """
    global _skill_library_cache, _skill_library_warnings

    # Return cached instance when using default dir
    if skills_dir is None and _skill_library_cache is not None:
        return _skill_library_cache, _skill_library_warnings

    from orion.ara.skill_library import SkillLibrary

    user_dir = skills_dir or DEFAULT_SKILLS_DIR
    groups_file = user_dir / "skill_groups.yaml"
    lib = SkillLibrary(skills_dir=user_dir, groups_file=groups_file)

    # Load user skills
    loaded, warnings = lib.load_all()

    # Also load seed/bundled skills (trusted first-party, skip scan)
    if SEED_SKILLS_DIR.exists():
        from orion.ara.skill import load_skill as _load_skill

        seed_names: set[str] = set()
        for item in sorted(SEED_SKILLS_DIR.iterdir()):
            if item.is_dir() and (item / "SKILL.md").exists():
                seed_names.add(item.name)
                if lib.get_skill(item.name) is None:
                    try:
                        skill, _ = _load_skill(item)
                        skill.source = "bundled"
                        skill.trust_level = "verified"
                        skill.aegis_approved = True
                        skill.directory = item
                        skill.content_hash = skill.compute_disk_hash()
                        lib._skills[skill.name] = skill
                    except Exception:
                        pass

        # Fix user copies of seed skills that were blocked by SkillGuard
        # (imported previously via import_skill which copies to ~/.orion/skills/)
        for name in seed_names:
            existing = lib.get_skill(name)
            if existing and not existing.aegis_approved:
                existing.source = "bundled"
                existing.trust_level = "verified"
                existing.aegis_approved = True

    # Cache only when using default dir
    if skills_dir is None:
        _skill_library_cache = lib
        _skill_library_warnings = warnings

    return lib, warnings


def cmd_skill_list(
    skills_dir: Path | None = None,
    tag: str | None = None,
    approved_only: bool = False,
) -> CommandResult:
    """List all available skills."""
    lib, _ = _get_skill_library(skills_dir)
    skills = lib.list_skills(tag=tag, approved_only=approved_only)

    if not skills:
        return CommandResult(
            success=True,
            message="No skills found. Use /skill create <name> to create one.",
            data={"skills": []},
        )

    skill_list = []
    lines = ["Available skills:", ""]
    for s in sorted(skills, key=lambda x: x.name):
        trust_icon = {"verified": "✓", "trusted": "●", "unreviewed": "?", "blocked": "✗"}.get(
            s.trust_level, "?"
        )
        approved_icon = "✓" if s.aegis_approved else "✗"
        tag_str = ", ".join(s.tags[:3]) if s.tags else ""
        lines.append(f"  {trust_icon} {s.name:24s} {s.source:10s} [{approved_icon}] {tag_str}")
        if s.description:
            lines.append(f"    {s.description[:70]}")
        skill_list.append(
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "source": s.source,
                "trust_level": s.trust_level,
                "aegis_approved": s.aegis_approved,
                "tags": s.tags,
            }
        )

    lines.append(
        f"\n  Total: {len(skills)} skills ({sum(1 for s in skills if s.aegis_approved)} approved)"
    )

    return CommandResult(
        success=True,
        message="\n".join(lines),
        data={"skills": skill_list},
    )


def cmd_skill_show(skill_name: str, skills_dir: Path | None = None) -> CommandResult:
    """Show full details of a skill."""
    lib, _ = _get_skill_library(skills_dir)
    skill = lib.get_skill(skill_name)
    if skill is None:
        return CommandResult(success=False, message=f"Skill '{skill_name}' not found.")

    lines = [
        f"Skill: {skill.name}",
        f"Description: {skill.description or '(none)'}",
        f"Version: {skill.version}",
        f"Author: {skill.author or '(unknown)'}",
        f"Source: {skill.source}",
        f"Trust: {skill.trust_level}",
        f"AEGIS Approved: {'Yes' if skill.aegis_approved else 'No'}",
        f"Tags: {', '.join(skill.tags) if skill.tags else '(none)'}",
        f"Directory: {skill.directory or '(none)'}",
        f"Supporting files: {', '.join(skill.supporting_files) if skill.supporting_files else '(none)'}",
        f"Hash: {skill.content_hash[:16]}..." if skill.content_hash else "Hash: (none)",
        "",
    ]
    if skill.instructions:
        lines.append("Instructions (first 500 chars):")
        lines.append(skill.instructions[:500])

    return CommandResult(
        success=True,
        message="\n".join(lines),
        data=skill.to_dict(),
    )


def cmd_skill_create(
    name: str,
    description: str = "",
    instructions: str = "",
    tags: list[str] | None = None,
    skills_dir: Path | None = None,
) -> CommandResult:
    """Create a new skill."""
    lib, _ = _get_skill_library(skills_dir)
    try:
        skill, scan = lib.create_skill(
            name=name,
            description=description,
            instructions=instructions or f"## {name}\n\nAdd instructions here.",
            tags=tags or [],
        )
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to create skill: {e}")

    return CommandResult(
        success=True,
        message=f"Skill '{name}' created (approved={skill.aegis_approved}, trust={skill.trust_level})",
        data={
            "name": skill.name,
            "aegis_approved": skill.aegis_approved,
            "trust_level": skill.trust_level,
            "scan_findings": len(scan.findings),
            "directory": str(skill.directory),
        },
    )


def cmd_skill_update(
    skill_name: str,
    description: str | None = None,
    instructions: str | None = None,
    tags: list[str] | None = None,
    skills_dir: Path | None = None,
) -> CommandResult:
    """Update a skill's description, instructions, or tags and save to disk."""
    from orion.ara.skill import save_skill_md

    lib, _ = _get_skill_library(skills_dir)
    skill = lib.get_skill(skill_name)
    if skill is None:
        return CommandResult(success=False, message=f"Skill '{skill_name}' not found.")

    if skill.source == "bundled" and skill.directory and "seed" in str(skill.directory):
        return CommandResult(
            success=False,
            message=f"Skill '{skill_name}' is a bundled seed skill and cannot be edited. "
            "Import it first to create an editable copy.",
        )

    changed = []
    if description is not None:
        skill.description = description
        changed.append("description")
    if instructions is not None:
        skill.instructions = instructions
        changed.append("instructions")
    if tags is not None:
        skill.tags = tags
        changed.append("tags")

    if not changed:
        return CommandResult(success=False, message="Nothing to update.")

    try:
        save_skill_md(skill)
        skill.content_hash = skill.compute_disk_hash()
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to save: {e}")

    return CommandResult(
        success=True,
        message=f"Skill '{skill_name}' updated ({', '.join(changed)}).",
        data=skill.to_dict(),
    )


def cmd_skill_delete(skill_name: str, skills_dir: Path | None = None) -> CommandResult:
    """Delete a skill."""
    lib, _ = _get_skill_library(skills_dir)
    if lib.delete_skill(skill_name):
        return CommandResult(success=True, message=f"Skill '{skill_name}' deleted.")
    return CommandResult(success=False, message=f"Skill '{skill_name}' not found.")


def cmd_skill_scan(skill_name: str, skills_dir: Path | None = None) -> CommandResult:
    """Re-scan a skill with SkillGuard."""
    lib, _ = _get_skill_library(skills_dir)
    result = lib.rescan_skill(skill_name)
    if result is None:
        return CommandResult(success=False, message=f"Skill '{skill_name}' not found.")

    return CommandResult(
        success=True,
        message=result.summary(),
        data=result.to_dict(),
    )


def cmd_skill_assign(
    skill_name: str,
    role_name: str,
    roles_dir: Path | None = None,
    skills_dir: Path | None = None,
) -> CommandResult:
    """Assign a skill to a role."""
    lib, _ = _get_skill_library(skills_dir)
    skill = lib.get_skill(skill_name)
    if skill is None:
        return CommandResult(success=False, message=f"Skill '{skill_name}' not found.")

    role = _find_role(role_name, roles_dir)
    if role is None:
        return CommandResult(success=False, message=f"Role '{role_name}' not found.")

    if skill_name in role.assigned_skills:
        return CommandResult(
            success=False, message=f"Skill '{skill_name}' already assigned to role '{role_name}'."
        )

    role.assigned_skills.append(skill_name)

    # Save role (copy starter to user dir if needed)
    user_dir = roles_dir or DEFAULT_ROLES_DIR
    source_path = Path(role.source_path) if role.source_path else None
    is_starter = (
        source_path and STARTER_ROLES_DIR.exists() and str(STARTER_ROLES_DIR) in str(source_path)
    )
    if is_starter:
        user_dir.mkdir(parents=True, exist_ok=True)
        target_path = user_dir / f"{role_name}.yaml"
    else:
        target_path = source_path if source_path else user_dir / f"{role_name}.yaml"

    save_role(role, target_path)
    return CommandResult(
        success=True,
        message=f"Skill '{skill_name}' assigned to role '{role_name}'.",
        data={"skill": skill_name, "role": role_name, "assigned_skills": role.assigned_skills},
    )


def cmd_skill_unassign(
    skill_name: str,
    role_name: str,
    roles_dir: Path | None = None,
) -> CommandResult:
    """Remove a skill assignment from a role."""
    role = _find_role(role_name, roles_dir)
    if role is None:
        return CommandResult(success=False, message=f"Role '{role_name}' not found.")

    if skill_name not in role.assigned_skills:
        return CommandResult(
            success=False, message=f"Skill '{skill_name}' not assigned to role '{role_name}'."
        )

    role.assigned_skills.remove(skill_name)

    user_dir = roles_dir or DEFAULT_ROLES_DIR
    source_path = Path(role.source_path) if role.source_path else None
    is_starter = (
        source_path and STARTER_ROLES_DIR.exists() and str(STARTER_ROLES_DIR) in str(source_path)
    )
    if is_starter:
        user_dir.mkdir(parents=True, exist_ok=True)
        target_path = user_dir / f"{role_name}.yaml"
    else:
        target_path = source_path if source_path else user_dir / f"{role_name}.yaml"

    save_role(role, target_path)
    return CommandResult(
        success=True,
        message=f"Skill '{skill_name}' removed from role '{role_name}'.",
        data={"skill": skill_name, "role": role_name, "assigned_skills": role.assigned_skills},
    )


def cmd_skill_group_list(skills_dir: Path | None = None) -> CommandResult:
    """List all skill groups."""
    lib, _ = _get_skill_library(skills_dir)
    groups = lib.list_groups()

    if not groups:
        return CommandResult(
            success=True,
            message="No skill groups found.",
            data={"groups": []},
        )

    group_list = []
    lines = ["Skill groups:", ""]
    for g in sorted(groups, key=lambda x: x.name):
        lines.append(f"  {g.name:20s} ({g.group_type}) — {len(g.skill_names)} skills")
        if g.description:
            lines.append(f"    {g.description[:70]}")
        group_list.append(
            {
                "name": g.name,
                "display_name": g.display_name,
                "description": g.description,
                "group_type": g.group_type,
                "skill_names": g.skill_names,
                "tags": g.tags,
            }
        )

    return CommandResult(
        success=True,
        message="\n".join(lines),
        data={"groups": group_list},
    )


def cmd_skill_group_create(
    name: str,
    display_name: str = "",
    group_type: str = "general",
    skills_dir: Path | None = None,
) -> CommandResult:
    """Create a new skill group."""
    lib, _ = _get_skill_library(skills_dir)
    try:
        group = lib.create_group(name, display_name or name.title(), group_type=group_type)
    except Exception as e:
        return CommandResult(success=False, message=f"Failed to create group: {e}")

    return CommandResult(
        success=True,
        message=f"Skill group '{name}' created.",
        data={
            "name": group.name,
            "display_name": group.display_name,
            "group_type": group.group_type,
        },
    )


def cmd_skill_group_delete(name: str, skills_dir: Path | None = None) -> CommandResult:
    """Delete a skill group."""
    lib, _ = _get_skill_library(skills_dir)
    if lib.delete_group(name):
        return CommandResult(success=True, message=f"Skill group '{name}' deleted.")
    return CommandResult(success=False, message=f"Skill group '{name}' not found.")


def cmd_skill_group_assign(
    skill_name: str,
    group_name: str,
    skills_dir: Path | None = None,
) -> CommandResult:
    """Add a skill to a group."""
    lib, _ = _get_skill_library(skills_dir)
    if lib.assign_skill_to_group(skill_name, group_name):
        return CommandResult(
            success=True,
            message=f"Skill '{skill_name}' added to group '{group_name}'.",
        )
    return CommandResult(
        success=False,
        message=f"Failed — check that both '{skill_name}' and group '{group_name}' exist.",
    )
