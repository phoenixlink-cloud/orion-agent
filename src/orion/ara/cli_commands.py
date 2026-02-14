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

logger = logging.getLogger("orion.ara.cli_commands")

DEFAULT_ROLES_DIR = Path.home() / ".orion" / "roles"
STARTER_ROLES_DIR = Path(__file__).resolve().parents[3] / "data" / "roles"


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


def cmd_work(
    role_name: str,
    goal: str,
    workspace_path: str | None = None,
    roles_dir: Path | None = None,
    control: DaemonControl | None = None,
) -> CommandResult:
    """Start an autonomous work session.

    1. Load the role profile
    2. Validate configuration
    3. Create session state
    4. Signal daemon to start

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

    # Create session
    session = SessionState(
        role_name=role.name,
        goal=goal,
        workspace_path=workspace_path or str(Path.cwd()),
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
    }
    config_path = Path.home() / ".orion" / "daemon" / "pending.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(session_config, indent=2), encoding="utf-8")

    logger.info("Work session created: %s (role=%s)", session.session_id, role.name)
    return CommandResult(
        success=True,
        message=f"Session {session.session_id} created.\n"
        f"Role: {role.name} | Scope: {role.scope}\n"
        f"Goal: {goal}\n"
        f"Auth: {role.auth_method} required before execution",
        data={"session_id": session.session_id, "role_name": role.name},
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
        + ("\n" + "\n".join(f"  ✓ {c}" for c in decision.checks_passed) if decision.checks_passed else ""),
        data=decision.to_dict(),
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
                        roles.append({
                            "name": r.name,
                            "scope": r.scope,
                            "auth": r.auth_method,
                            "source": source,
                            "description": r.description[:60] if r.description else "",
                            "path": str(p),
                        })
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
        lines.append(f"  {r['name']:20s} {r['scope']:10s} {r['auth']:5s} {tag}")
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

    ct = role.confidence_thresholds
    lines.append(f"Confidence: auto={ct.auto_execute}, flag={ct.execute_and_flag}, pause={ct.pause_and_ask}")
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
