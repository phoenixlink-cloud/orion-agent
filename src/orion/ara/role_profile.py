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
"""Role Profile — user-configurable YAML role definitions for ARA sessions.

Each role profile defines what Orion is allowed to do autonomously:
scope, auth method, working hours, allowed actions, write limits, etc.
All limits are clamped to AEGIS ceilings and validated on load.

See ARA-001 §4 for full design.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from orion.security.write_limits import WriteLimits

logger = logging.getLogger("orion.ara.role_profile")

# Required fields that every role profile must have
REQUIRED_FIELDS = frozenset({"name", "scope", "auth_method"})

# Valid auth methods
VALID_AUTH_METHODS = frozenset({"pin", "totp"})

# Valid scope values
VALID_SCOPES = frozenset({"coding", "research", "devops", "full"})

# Valid risk tolerance values
VALID_RISK_TOLERANCES = frozenset({"low", "medium", "high"})

# AEGIS-enforced action blocklist — no role can enable these
AEGIS_BLOCKED_ACTIONS = frozenset({
    "delete_repository",
    "force_push",
    "modify_ci_pipeline",
    "access_credentials_store",
    "disable_aegis",
    "modify_aegis_rules",
    "execute_as_root",
    "access_host_filesystem",
})

# Default role directory
DEFAULT_ROLES_DIR = Path.home() / ".orion" / "roles"


@dataclass
class WorkingHours:
    """When the role is allowed to operate autonomously."""

    enabled: bool = False
    start_hour: int = 22
    end_hour: int = 6
    timezone: str = "UTC"
    days: list[str] = field(default_factory=lambda: [
        "monday", "tuesday", "wednesday", "thursday", "friday",
    ])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkingHours:
        return cls(
            enabled=data.get("enabled", False),
            start_hour=data.get("start_hour", 22),
            end_hour=data.get("end_hour", 6),
            timezone=data.get("timezone", "UTC"),
            days=data.get("days", cls.__dataclass_fields__["days"].default_factory()),
        )


@dataclass
class ConfidenceThresholds:
    """Confidence levels that control execution behaviour.

    - auto_execute: confidence >= this → execute without flagging
    - execute_and_flag: confidence >= this → execute but flag for review
    - pause_and_ask: confidence < this → pause and ask user
    """

    auto_execute: float = 0.90
    execute_and_flag: float = 0.70
    pause_and_ask: float = 0.50

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfidenceThresholds:
        return cls(
            auto_execute=data.get("auto_execute", 0.90),
            execute_and_flag=data.get("execute_and_flag", 0.70),
            pause_and_ask=data.get("pause_and_ask", 0.50),
        )


@dataclass
class NotificationConfig:
    """Notification preferences for the role."""

    on_complete: bool = True
    on_error: bool = True
    on_consent_needed: bool = True
    on_checkpoint: bool = False
    providers: list[str] = field(default_factory=lambda: ["desktop"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NotificationConfig:
        return cls(
            on_complete=data.get("on_complete", True),
            on_error=data.get("on_error", True),
            on_consent_needed=data.get("on_consent_needed", True),
            on_checkpoint=data.get("on_checkpoint", False),
            providers=data.get("providers", ["desktop"]),
        )


@dataclass
class RoleProfile:
    """A validated, AEGIS-governed role configuration.

    Loaded from YAML files in ~/.orion/roles/ or data/roles/ (starter templates).
    """

    name: str
    scope: str
    auth_method: str = "pin"
    description: str = ""
    allowed_actions: list[str] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)
    # 3-tier authority model (ARA-001 §2.2)
    authority_autonomous: list[str] = field(default_factory=list)
    authority_requires_approval: list[str] = field(default_factory=list)
    authority_forbidden: list[str] = field(default_factory=list)
    competencies: list[str] = field(default_factory=list)
    confidence_thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    risk_tolerance: str = "medium"
    success_criteria: list[str] = field(default_factory=list)
    max_session_hours: float = 8.0
    max_cost_per_session: float = 5.0
    auto_checkpoint_interval_minutes: int = 15
    require_review_before_promote: bool = True
    working_hours: WorkingHours = field(default_factory=WorkingHours)
    write_limits: WriteLimits = field(default_factory=WriteLimits)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    model_override: str | None = None
    tags: list[str] = field(default_factory=list)
    assigned_skills: list[str] = field(default_factory=list)
    assigned_skill_groups: list[str] = field(default_factory=list)
    source_path: str | None = None

    def __post_init__(self):
        """Validate and enforce AEGIS constraints after initialization."""
        self._validate()

    def _validate(self):
        """Enforce all validation rules."""
        errors: list[str] = []

        if not self.name or not self.name.strip():
            errors.append("name is required and cannot be empty")

        if self.scope not in VALID_SCOPES:
            errors.append(
                f"scope '{self.scope}' is invalid. Must be one of: {', '.join(sorted(VALID_SCOPES))}"
            )

        if self.auth_method not in VALID_AUTH_METHODS:
            errors.append(
                f"auth_method '{self.auth_method}' is invalid. Must be one of: {', '.join(sorted(VALID_AUTH_METHODS))}"
            )

        if self.max_session_hours <= 0 or self.max_session_hours > 24:
            errors.append("max_session_hours must be between 0 and 24")

        if self.max_cost_per_session < 0:
            errors.append("max_cost_per_session cannot be negative")

        if self.risk_tolerance not in VALID_RISK_TOLERANCES:
            errors.append(
                f"risk_tolerance '{self.risk_tolerance}' is invalid. "
                f"Must be one of: {', '.join(sorted(VALID_RISK_TOLERANCES))}"
            )

        ct = self.confidence_thresholds
        if not (0 <= ct.pause_and_ask <= ct.execute_and_flag <= ct.auto_execute <= 1):
            errors.append(
                "confidence_thresholds must satisfy: "
                "0 <= pause_and_ask <= execute_and_flag <= auto_execute <= 1"
            )

        # Backward compat: migrate allowed_actions → authority_autonomous
        if self.allowed_actions and not self.authority_autonomous:
            self.authority_autonomous = list(self.allowed_actions)

        # AEGIS: strip forbidden actions from autonomous/approval lists
        for action in list(self.authority_autonomous):
            if action in AEGIS_BLOCKED_ACTIONS:
                self.authority_autonomous.remove(action)
                logger.warning(
                    "AEGIS: stripped blocked action '%s' from autonomous list of role '%s'",
                    action, self.name,
                )

        # Ensure AEGIS-blocked actions are in authority_forbidden
        for action in AEGIS_BLOCKED_ACTIONS:
            if action not in self.authority_forbidden:
                self.authority_forbidden.append(action)

        # AEGIS: strip any blocked actions from allowed list
        for action in list(self.allowed_actions):
            if action in AEGIS_BLOCKED_ACTIONS:
                self.allowed_actions.remove(action)
                logger.warning(
                    "AEGIS: stripped blocked action '%s' from role '%s'",
                    action, self.name,
                )

        # AEGIS: always include blocked actions
        for action in AEGIS_BLOCKED_ACTIONS:
            if action not in self.blocked_actions:
                self.blocked_actions.append(action)

        if errors:
            raise RoleValidationError(self.name, errors)

    def is_action_allowed(self, action: str) -> bool:
        """Check if an action is permitted under this role."""
        if action in AEGIS_BLOCKED_ACTIONS:
            return False
        if action in self.blocked_actions:
            return False
        if action in self.authority_forbidden:
            return False
        return not (self.allowed_actions and action not in self.allowed_actions)

    def get_action_tier(self, action: str) -> str:
        """Return the authority tier for an action.

        Returns: 'forbidden', 'requires_approval', 'autonomous', or 'unknown'.
        """
        if action in AEGIS_BLOCKED_ACTIONS or action in self.authority_forbidden:
            return "forbidden"
        if action in self.authority_requires_approval:
            return "requires_approval"
        if action in self.authority_autonomous:
            return "autonomous"
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (for saving back to YAML)."""
        return {
            "name": self.name,
            "scope": self.scope,
            "auth_method": self.auth_method,
            "description": self.description,
            "allowed_actions": self.allowed_actions,
            "blocked_actions": [
                a for a in self.blocked_actions if a not in AEGIS_BLOCKED_ACTIONS
            ],
            "authority_autonomous": self.authority_autonomous,
            "authority_requires_approval": self.authority_requires_approval,
            "authority_forbidden": [
                a for a in self.authority_forbidden if a not in AEGIS_BLOCKED_ACTIONS
            ],
            "competencies": self.competencies,
            "confidence_thresholds": {
                "auto_execute": self.confidence_thresholds.auto_execute,
                "execute_and_flag": self.confidence_thresholds.execute_and_flag,
                "pause_and_ask": self.confidence_thresholds.pause_and_ask,
            },
            "risk_tolerance": self.risk_tolerance,
            "success_criteria": self.success_criteria,
            "max_session_hours": self.max_session_hours,
            "max_cost_per_session": self.max_cost_per_session,
            "auto_checkpoint_interval_minutes": self.auto_checkpoint_interval_minutes,
            "require_review_before_promote": self.require_review_before_promote,
            "working_hours": {
                "enabled": self.working_hours.enabled,
                "start_hour": self.working_hours.start_hour,
                "end_hour": self.working_hours.end_hour,
                "timezone": self.working_hours.timezone,
                "days": self.working_hours.days,
            },
            "write_limits": {
                "max_file_size_mb": self.write_limits.max_single_file_size_mb,
                "max_files_created": self.write_limits.max_files_created,
                "max_files_modified": self.write_limits.max_files_modified,
                "max_total_write_volume_mb": self.write_limits.max_total_write_volume_mb,
                "max_single_file_lines": self.write_limits.max_single_file_lines,
            },
            "notifications": {
                "on_complete": self.notifications.on_complete,
                "on_error": self.notifications.on_error,
                "on_consent_needed": self.notifications.on_consent_needed,
                "on_checkpoint": self.notifications.on_checkpoint,
                "providers": self.notifications.providers,
            },
            "model_override": self.model_override,
            "tags": self.tags,
            "assigned_skills": self.assigned_skills,
            "assigned_skill_groups": self.assigned_skill_groups,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_path: str | None = None) -> RoleProfile:
        """Create a RoleProfile from a dictionary."""
        # Parse nested configs
        wh_data = data.get("working_hours", {})
        wl_data = data.get("write_limits", {})
        notif_data = data.get("notifications", {})

        ct_data = data.get("confidence_thresholds", {})

        return cls(
            name=data.get("name", ""),
            scope=data.get("scope", "coding"),
            auth_method=data.get("auth_method", "pin"),
            description=data.get("description", ""),
            allowed_actions=data.get("allowed_actions", []),
            blocked_actions=data.get("blocked_actions", []),
            authority_autonomous=data.get("authority_autonomous", []),
            authority_requires_approval=data.get("authority_requires_approval", []),
            authority_forbidden=data.get("authority_forbidden", []),
            competencies=data.get("competencies", []),
            confidence_thresholds=ConfidenceThresholds.from_dict(ct_data) if ct_data else ConfidenceThresholds(),
            risk_tolerance=data.get("risk_tolerance", "medium"),
            success_criteria=data.get("success_criteria", []),
            max_session_hours=data.get("max_session_hours", 8.0),
            max_cost_per_session=data.get("max_cost_per_session", 5.0),
            auto_checkpoint_interval_minutes=data.get("auto_checkpoint_interval_minutes", 15),
            require_review_before_promote=data.get("require_review_before_promote", True),
            working_hours=WorkingHours.from_dict(wh_data) if wh_data else WorkingHours(),
            write_limits=WriteLimits.from_dict(wl_data) if wl_data else WriteLimits(),
            notifications=NotificationConfig.from_dict(notif_data) if notif_data else NotificationConfig(),
            model_override=data.get("model_override"),
            tags=data.get("tags", []),
            assigned_skills=data.get("assigned_skills", []),
            assigned_skill_groups=data.get("assigned_skill_groups", []),
            source_path=source_path,
        )


class RoleValidationError(ValueError):
    """Raised when a role profile fails validation."""

    def __init__(self, role_name: str, errors: list[str]):
        self.role_name = role_name
        self.errors = errors
        msg = f"Role '{role_name}' validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(msg)


def load_role(path: Path) -> RoleProfile:
    """Load a role profile from a YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"Role file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        raise ValueError(f"Invalid role file: {path}")

    return RoleProfile.from_dict(data, source_path=str(path))


def load_all_roles(roles_dir: Path | None = None) -> dict[str, RoleProfile]:
    """Load all role profiles from a directory."""
    if roles_dir is None:
        roles_dir = DEFAULT_ROLES_DIR

    roles: dict[str, RoleProfile] = {}
    if not roles_dir.exists():
        return roles

    for path in sorted(roles_dir.glob("*.yaml")):
        try:
            role = load_role(path)
            roles[role.name] = role
            logger.info("Loaded role: %s from %s", role.name, path.name)
        except Exception as e:
            logger.warning("Failed to load role from %s: %s", path.name, e)

    for path in sorted(roles_dir.glob("*.yml")):
        try:
            role = load_role(path)
            if role.name not in roles:
                roles[role.name] = role
                logger.info("Loaded role: %s from %s", role.name, path.name)
        except Exception as e:
            logger.warning("Failed to load role from %s: %s", path.name, e)

    return roles


def save_role(role: RoleProfile, path: Path) -> None:
    """Save a role profile to a YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(role.to_dict(), f, default_flow_style=False, sort_keys=False)
    logger.info("Saved role '%s' to %s", role.name, path)


def generate_example_yaml() -> str:
    """Return an annotated example YAML template for creating a new role."""
    return '''# Orion ARA Role Profile
# Copy this file to ~/.orion/roles/<role-name>.yaml and customize.
# See ARA-001 §2 for full documentation.

# REQUIRED: Unique role name (used in 'orion work --role <name>')
name: "my-custom-role"

# REQUIRED: Scope — what domain this role operates in
# Options: coding, research, devops, full
scope: "coding"

# REQUIRED: Authentication method for promoting changes
# Options: pin (4-8 digit PIN), totp (Google Authenticator / Authy)
auth_method: "pin"

# Optional: Human-readable description
description: "A custom role for my specific workflow"

# Competencies — what this role is skilled at (informational)
competencies:
  - "Code quality and best practices"
  - "Unit and integration testing"
  - "Git workflow and version control"

# 3-tier authority model:
# autonomous — Orion does these without asking
authority_autonomous:
  - "read_files"
  - "write_files"
  - "run_tests"
  - "create_feature_branches"

# requires_approval — Orion pauses and asks before doing these
authority_requires_approval:
  - "merge_to_main"
  - "add_dependencies"
  - "change_database_schema"

# forbidden — Orion will NEVER do these (AEGIS blocks them)
authority_forbidden:
  - "deploy_to_production"
  - "delete_repositories"
  - "modify_ci_pipeline"

# Confidence thresholds (0.0 to 1.0)
confidence_thresholds:
  auto_execute: 0.90      # >= this: execute without flagging
  execute_and_flag: 0.70   # >= this: execute but mark for review
  pause_and_ask: 0.50      # < this: pause and ask the user

# Risk tolerance: low, medium, high
risk_tolerance: "medium"

# Success criteria (informational — shown in dashboard)
success_criteria:
  - "All tests pass"
  - "Code coverage > 80%"
  - "Follows project style guide"

# Session limits
max_session_hours: 8.0       # Max duration (0-24)
max_cost_per_session: 5.0    # Max API spend in USD
auto_checkpoint_interval_minutes: 15
require_review_before_promote: true

# Working hours — when autonomous execution is allowed
working_hours:
  enabled: false
  start_hour: 22
  end_hour: 6
  timezone: "UTC"
  days: ["monday", "tuesday", "wednesday", "thursday", "friday"]

# Write limits (AEGIS enforces ceilings)
write_limits:
  max_file_size_mb: 10
  max_files_created: 100
  max_files_modified: 200
  max_total_write_volume_mb: 200
  max_single_file_lines: 5000

# Notifications
notifications:
  on_complete: true
  on_error: true
  on_consent_needed: true
  on_checkpoint: false
  providers: ["desktop"]

# Optional: Override the default LLM model
# model_override: "gpt-4o"

# Optional: Tags for organizing roles
tags: ["custom"]
'''


def validate_role_file(path: Path) -> tuple[bool, list[str]]:
    """Validate a YAML role file without loading it into the system.

    Returns (valid, list_of_errors).
    """
    errors: list[str] = []
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data or not isinstance(data, dict):
            return False, ["File is empty or not a valid YAML mapping"]
        # Try to construct — validation happens in __post_init__
        RoleProfile.from_dict(data, source_path=str(path))
        return True, []
    except RoleValidationError as e:
        return False, e.errors
    except Exception as e:
        errors.append(str(e))
        return False, errors
