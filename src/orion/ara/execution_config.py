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
"""Execution configuration helpers for Phase 4.

Provides a single source of truth for whether command execution is
enabled, which resource profile to use, and how many feedback retries
are allowed. Reads from both:

- Global settings (``~/.orion/settings.json``) — ``ara_enable_command_execution``
- ARA settings (``~/.orion/ara_settings.json``) — ``execution.enable_command_execution``

The ARA-specific setting takes precedence when present.

See Phase 4A.5 specification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("orion.ara.execution_config")

# Default paths
_ORION_DIR = Path.home() / ".orion"
_SETTINGS_FILE = _ORION_DIR / "settings.json"
_ARA_SETTINGS_FILE = _ORION_DIR / "ara_settings.json"


@dataclass
class ExecutionSettings:
    """Resolved execution settings."""

    enabled: bool = False
    resource_profile: str = "standard"
    max_feedback_retries: int = 3


def load_execution_settings(
    settings_path: Path | None = None,
    ara_settings_path: Path | None = None,
) -> ExecutionSettings:
    """Load and resolve execution settings from config files.

    Priority (highest to lowest):
    1. ARA settings ``execution.enable_command_execution``
    2. Global settings ``ara_enable_command_execution``
    3. Hardcoded defaults (disabled)

    Args:
        settings_path: Override path to global settings.json.
        ara_settings_path: Override path to ara_settings.json.

    Returns:
        Resolved ExecutionSettings.
    """
    global_path = settings_path or _SETTINGS_FILE
    ara_path = ara_settings_path or _ARA_SETTINGS_FILE

    global_settings = _load_json(global_path)
    ara_settings = _load_json(ara_path)

    # Start with defaults
    result = ExecutionSettings()

    # Layer 1: global settings
    if "ara_enable_command_execution" in global_settings:
        result.enabled = bool(global_settings["ara_enable_command_execution"])
    if "ara_resource_profile" in global_settings:
        profile = global_settings["ara_resource_profile"]
        if profile in ("light", "standard", "heavy"):
            result.resource_profile = profile

    # Layer 2: ARA-specific settings (override)
    execution = ara_settings.get("execution", {})
    if isinstance(execution, dict):
        if "enable_command_execution" in execution:
            result.enabled = bool(execution["enable_command_execution"])
        if "resource_profile" in execution:
            profile = execution["resource_profile"]
            if profile in ("light", "standard", "heavy"):
                result.resource_profile = profile
        if "max_feedback_retries" in execution:
            result.max_feedback_retries = int(execution["max_feedback_retries"])

    logger.debug(
        "Execution settings: enabled=%s, profile=%s, retries=%d",
        result.enabled,
        result.resource_profile,
        result.max_feedback_retries,
    )
    return result


def is_command_execution_enabled(
    settings_path: Path | None = None,
    ara_settings_path: Path | None = None,
) -> bool:
    """Quick check: is command execution enabled?

    Convenience wrapper around load_execution_settings().
    """
    return load_execution_settings(settings_path, ara_settings_path).enabled


def _load_json(path: Path) -> dict:
    """Load a JSON file, returning empty dict on any error."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
