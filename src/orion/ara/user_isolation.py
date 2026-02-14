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
"""Multi-user isolation — OS-user scoping for shared machines.

Ensures all ARA artifacts are scoped to the current OS user's home
directory. Validates session paths, generates per-user container names,
and prevents cross-user access.

See ARA-001 Appendix C.10 for design.
"""

from __future__ import annotations

import getpass
import logging
from pathlib import Path

logger = logging.getLogger("orion.ara.user_isolation")


class UserIsolation:
    """Enforces OS-user scoping for ARA artifacts.

    Usage::

        iso = UserIsolation()
        assert iso.validate_session_access(Path.home() / ".orion" / "sessions" / "abc")
        name = iso.get_container_name("session-123")
    """

    def __init__(self, username: str | None = None, home_dir: Path | None = None):
        self._username = username or getpass.getuser()
        self._home = home_dir or Path.home()
        self._orion_dir = self._home / ".orion"

    @property
    def username(self) -> str:
        return self._username

    @property
    def orion_dir(self) -> Path:
        return self._orion_dir

    def validate_session_access(self, session_path: Path) -> bool:
        """Check if a session path is within the current user's .orion directory."""
        try:
            resolved = session_path.resolve()
            orion_resolved = self._orion_dir.resolve()
            return resolved == orion_resolved or str(resolved).startswith(str(orion_resolved) + "\\") or str(resolved).startswith(str(orion_resolved) + "/")
        except Exception:
            return False

    def get_container_name(self, session_id: str) -> str:
        """Generate a per-user container name for Docker sandboxes."""
        safe_user = self._username.replace(" ", "_").lower()[:20]
        safe_session = session_id[:12]
        return f"orion-ara-{safe_user}-{safe_session}"

    def get_branch_name(self, session_id: str) -> str:
        """Generate a per-user sandbox branch name."""
        safe_user = self._username.replace(" ", "_").lower()[:20]
        return f"orion-ara/{safe_user}/{session_id[:12]}"

    def validate_path_not_outside_home(self, path: Path) -> bool:
        """Ensure a path doesn't escape the user's home directory."""
        try:
            resolved = path.resolve()
            home_resolved = self._home.resolve()
            return resolved == home_resolved or str(resolved).startswith(str(home_resolved) + "\\") or str(resolved).startswith(str(home_resolved) + "/")
        except Exception:
            return False
