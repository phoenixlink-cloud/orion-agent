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
"""Centralized data directory resolver for Orion Agent.

Locates the ``data/`` directory shipped with Orion regardless of
whether the code is running from the source tree or from an installed
package (wheel/pip).

Source tree layout:
    orion-agent/
        src/orion/data_path.py    <-- this file
        data/                      <-- target
            roles/
            seed/skills/
            seed/curriculum.json
            oauth_defaults.json

Installed package layout (wheel):
    site-packages/
        orion/
            data_path.py           <-- this file
            _data/                 <-- force-included by hatch
                roles/
                seed/skills/
                ...
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("orion.data_path")


@lru_cache(maxsize=1)
def get_data_dir() -> Path:
    """Return the absolute path to Orion's ``data/`` directory.

    Checks in order:
    1. Source tree: ``<project_root>/data/`` (development)
    2. Installed package: ``<package_root>/_data/`` (pip install)
    3. Falls back to source tree path (will be missing but logged)
    """
    this_file = Path(__file__).resolve()

    # 1. Source tree: src/orion/data_path.py -> parents[2] = project root
    source_data = this_file.parents[2] / "data"
    if source_data.is_dir() and (source_data / "seed").is_dir():
        logger.debug("Data directory (source tree): %s", source_data)
        return source_data

    # 2. Installed package: orion/data_path.py -> parent = orion package
    pkg_data = this_file.parent / "_data"
    if pkg_data.is_dir():
        logger.debug("Data directory (installed): %s", pkg_data)
        return pkg_data

    # 3. Fallback — return source path even if missing (callers check .exists())
    logger.warning(
        "Data directory not found at %s or %s — seed skills/roles unavailable",
        source_data,
        pkg_data,
    )
    return source_data


def get_seed_skills_dir() -> Path:
    """Path to ``data/seed/skills/``."""
    return get_data_dir() / "seed" / "skills"


def get_seed_roles_dir() -> Path:
    """Path to ``data/roles/``."""
    return get_data_dir() / "roles"


def get_seed_file(relative: str) -> Path:
    """Path to a specific file under ``data/``.

    Example: ``get_seed_file("seed/curriculum.json")``
    """
    return get_data_dir() / relative
