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
"""Configurable resource profiles for Docker sandbox containers.

Provides a single source of truth for container resource limits
(memory, CPUs, PIDs) with three tiers:

1. **Built-in defaults** — hardcoded light/standard/heavy profiles.
2. **User overrides** — from ``~/.orion/ara_settings.json`` under
   ``execution.resource_profiles``.
3. **Runtime query** — ``get_profile(name)`` merges both layers.

The ``SessionContainer`` references this module instead of its own
hardcoded ``PROFILES`` dict so that users can tune limits without
editing source code.

See Phase 4B.3 specification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.security.sandbox_config")


# ---------------------------------------------------------------------------
# Built-in defaults (same values as session_container.PROFILES)
# ---------------------------------------------------------------------------

DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "light": {"memory": "512m", "cpus": "1", "pids": 128},
    "standard": {"memory": "2g", "cpus": "2", "pids": 256},
    "heavy": {"memory": "4g", "cpus": "4", "pids": 512},
}

VALID_PROFILE_NAMES = frozenset(DEFAULT_PROFILES.keys())


# ---------------------------------------------------------------------------
# ResourceProfile dataclass
# ---------------------------------------------------------------------------


@dataclass
class ResourceProfile:
    """Resolved resource profile for a Docker container."""

    name: str = "standard"
    memory: str = "2g"
    cpus: str = "2"
    pids: int = 256

    def to_docker_args(self) -> list[str]:
        """Convert to Docker CLI flags for ``docker run``."""
        return [
            f"--memory={self.memory}",
            f"--cpus={self.cpus}",
            f"--pids-limit={self.pids}",
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "memory": self.memory,
            "cpus": self.cpus,
            "pids": self.pids,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_profile(
    name: str = "standard",
    ara_settings_path: Path | None = None,
) -> ResourceProfile:
    """Resolve a resource profile by name.

    Merges built-in defaults with any user overrides from ARA settings.

    Args:
        name: Profile name — ``light``, ``standard``, or ``heavy``.
        ara_settings_path: Override path to ara_settings.json.

    Returns:
        ResourceProfile with resolved values.
    """
    if name not in VALID_PROFILE_NAMES:
        logger.warning("Unknown profile '%s', falling back to 'standard'", name)
        name = "standard"

    base = DEFAULT_PROFILES[name]
    overrides = _load_user_overrides(name, ara_settings_path)

    return ResourceProfile(
        name=name,
        memory=overrides.get("memory", base["memory"]),
        cpus=overrides.get("cpus", base["cpus"]),
        pids=int(overrides.get("pids", base["pids"])),
    )


def list_profiles(
    ara_settings_path: Path | None = None,
) -> list[ResourceProfile]:
    """Return all available profiles with user overrides applied.

    Args:
        ara_settings_path: Override path to ara_settings.json.

    Returns:
        List of ResourceProfile for light, standard, heavy.
    """
    return [get_profile(name, ara_settings_path) for name in ("light", "standard", "heavy")]


def validate_memory(value: str) -> bool:
    """Check that a memory value is a valid Docker memory string.

    Examples: ``512m``, ``2g``, ``1024m``.
    """
    if not value:
        return False
    suffix = value[-1].lower()
    if suffix not in ("m", "g"):
        return False
    try:
        num = int(value[:-1])
        return num > 0
    except ValueError:
        return False


def validate_cpus(value: str) -> bool:
    """Check that a cpus value is valid (positive number as string)."""
    try:
        return float(value) > 0
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Internal: load user overrides
# ---------------------------------------------------------------------------


def _load_user_overrides(
    profile_name: str,
    ara_settings_path: Path | None = None,
) -> dict[str, Any]:
    """Load user-configured profile overrides from ARA settings.

    Reads ``execution.resource_profiles.<name>`` from ara_settings.json.
    Only returns validated fields.
    """
    path = ara_settings_path or (Path.home() / ".orion" / "ara_settings.json")
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    execution = data.get("execution", {})
    if not isinstance(execution, dict):
        return {}

    profiles = execution.get("resource_profiles", {})
    if not isinstance(profiles, dict):
        return {}

    overrides_raw = profiles.get(profile_name, {})
    if not isinstance(overrides_raw, dict):
        return {}

    # Validate each field
    result: dict[str, Any] = {}
    if "memory" in overrides_raw and validate_memory(str(overrides_raw["memory"])):
        result["memory"] = str(overrides_raw["memory"])
    if "cpus" in overrides_raw and validate_cpus(str(overrides_raw["cpus"])):
        result["cpus"] = str(overrides_raw["cpus"])
    if "pids" in overrides_raw:
        try:
            pids = int(overrides_raw["pids"])
            if 16 <= pids <= 4096:
                result["pids"] = pids
        except (ValueError, TypeError):
            pass

    return result
