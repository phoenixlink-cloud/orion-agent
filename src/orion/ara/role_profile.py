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
    max_session_hours: float = 8.0
    max_cost_per_session: float = 5.0
    auto_checkpoint_interval_minutes: int = 15
    require_review_before_promote: bool = True
    working_hours: WorkingHours = field(default_factory=WorkingHours)
    write_limits: WriteLimits = field(default_factory=WriteLimits)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    model_override: str | None = None
    tags: list[str] = field(default_factory=list)
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
        return not (self.allowed_actions and action not in self.allowed_actions)

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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], source_path: str | None = None) -> RoleProfile:
        """Create a RoleProfile from a dictionary."""
        # Parse nested configs
        wh_data = data.get("working_hours", {})
        wl_data = data.get("write_limits", {})
        notif_data = data.get("notifications", {})

        return cls(
            name=data.get("name", ""),
            scope=data.get("scope", "coding"),
            auth_method=data.get("auth_method", "pin"),
            description=data.get("description", ""),
            allowed_actions=data.get("allowed_actions", []),
            blocked_actions=data.get("blocked_actions", []),
            max_session_hours=data.get("max_session_hours", 8.0),
            max_cost_per_session=data.get("max_cost_per_session", 5.0),
            auto_checkpoint_interval_minutes=data.get("auto_checkpoint_interval_minutes", 15),
            require_review_before_promote=data.get("require_review_before_promote", True),
            working_hours=WorkingHours.from_dict(wh_data) if wh_data else WorkingHours(),
            write_limits=WriteLimits.from_dict(wl_data) if wl_data else WriteLimits(),
            notifications=NotificationConfig.from_dict(notif_data) if notif_data else NotificationConfig(),
            model_override=data.get("model_override"),
            tags=data.get("tags", []),
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
