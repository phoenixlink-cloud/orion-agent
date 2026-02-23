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
"""Package registry whitelist for install-phase egress.

During the install phase, SessionContainer temporarily connects the
container to the egress proxy network.  This module defines which
package registry domains are auto-allowed during that phase.

The registries are grouped by stack so that only the relevant registries
are opened for a given session.  For example, a Python session only
needs ``pypi.org`` and ``files.pythonhosted.org``; it should NOT have
access to ``registry.npmjs.org``.

Security design:
  - Registries are hardcoded (not user-configurable) to prevent
    supply-chain attacks via custom registries.
  - Users can add extra registries via ``~/.orion/ara_settings.json``
    under ``execution.extra_registries`` (validated at load time).
  - Only HTTPS is allowed.
  - Write access is always False (GET-only downloads).

See Phase 4B.2 specification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("orion.security.registry_whitelist")

# ---------------------------------------------------------------------------
# Hardcoded registry domains per stack
# ---------------------------------------------------------------------------

REGISTRY_DOMAINS: dict[str, list[str]] = {
    "python": [
        "pypi.org",
        "files.pythonhosted.org",
    ],
    "node": [
        "registry.npmjs.org",
        "registry.yarnpkg.com",
    ],
    "go": [
        "proxy.golang.org",
        "sum.golang.org",
        "storage.googleapis.com",
    ],
    "rust": [
        "crates.io",
        "static.crates.io",
        "index.crates.io",
    ],
    "base": [],
}

# Domains allowed for ALL stacks (common infrastructure)
COMMON_REGISTRY_DOMAINS: list[str] = [
    "github.com",
    "objects.githubusercontent.com",
]


# ---------------------------------------------------------------------------
# RegistryRule dataclass
# ---------------------------------------------------------------------------


@dataclass
class RegistryRule:
    """A single registry domain rule for install-phase egress."""

    domain: str
    stack: str = "common"
    description: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_registry_domains(stack: str) -> list[str]:
    """Return all allowed registry domains for a given stack.

    Includes stack-specific registries plus common registries.

    Args:
        stack: Stack name (e.g. "python", "node", "go", "rust", "base").

    Returns:
        Sorted, deduplicated list of allowed domains.
    """
    stack_domains = REGISTRY_DOMAINS.get(stack, [])
    all_domains = set(stack_domains + COMMON_REGISTRY_DOMAINS)
    return sorted(all_domains)


def get_registry_rules(stack: str) -> list[RegistryRule]:
    """Return RegistryRule objects for a given stack.

    Args:
        stack: Stack name.

    Returns:
        List of RegistryRule objects for use with egress proxy.
    """
    rules = []
    for domain in REGISTRY_DOMAINS.get(stack, []):
        rules.append(
            RegistryRule(
                domain=domain,
                stack=stack,
                description=f"{stack} package registry",
            )
        )
    for domain in COMMON_REGISTRY_DOMAINS:
        rules.append(
            RegistryRule(
                domain=domain,
                stack="common",
                description="Common source hosting",
            )
        )
    return rules


def get_all_registry_domains() -> list[str]:
    """Return all known registry domains across all stacks.

    Useful for documentation and audit purposes.

    Returns:
        Sorted, deduplicated list of all known registry domains.
    """
    all_domains: set[str] = set(COMMON_REGISTRY_DOMAINS)
    for domains in REGISTRY_DOMAINS.values():
        all_domains.update(domains)
    return sorted(all_domains)


def load_extra_registries(
    ara_settings_path: Path | None = None,
) -> list[str]:
    """Load user-configured extra registry domains from ARA settings.

    Reads ``execution.extra_registries`` from ``~/.orion/ara_settings.json``.
    Validates that entries are non-empty strings. Does NOT allow
    arbitrary domains — only well-formed hostnames.

    Args:
        ara_settings_path: Override path to ara_settings.json.

    Returns:
        List of validated extra registry domains.
    """
    path = ara_settings_path or (Path.home() / ".orion" / "ara_settings.json")
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    execution = data.get("execution", {})
    if not isinstance(execution, dict):
        return []

    raw = execution.get("extra_registries", [])
    if not isinstance(raw, list):
        return []

    validated: list[str] = []
    for entry in raw:
        if isinstance(entry, str) and _is_valid_hostname(entry):
            validated.append(entry.strip().lower())

    return validated


def get_install_phase_domains(
    stack: str,
    ara_settings_path: Path | None = None,
) -> list[str]:
    """Return the full set of domains allowed during install phase.

    Combines hardcoded registries, common domains, and user extras.

    Args:
        stack: Stack name.
        ara_settings_path: Override path to ara_settings.json.

    Returns:
        Sorted, deduplicated list of all install-phase allowed domains.
    """
    domains = set(get_registry_domains(stack))
    extras = load_extra_registries(ara_settings_path)
    domains.update(extras)
    return sorted(domains)


def _is_valid_hostname(hostname: str) -> bool:
    """Basic hostname validation."""
    hostname = hostname.strip().lower()
    if not hostname:
        return False
    if len(hostname) > 253:
        return False
    # Must have at least one dot (TLD)
    if "." not in hostname:
        return False
    # No spaces or special chars
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789.-")
    return all(c in allowed for c in hostname)
