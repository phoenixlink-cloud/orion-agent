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
"""ARA Lifecycle Manager — resource cleanup, TTL, and checkpoint pruning.

Manages the lifecycle of ARA sessions:
- Sandbox directory cleanup after session completion
- Checkpoint pruning based on age and count
- Stale session detection and cleanup
- Resource inventory and health reporting

See ARA-001 §C.2 for full design.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.ara.lifecycle")

# Default paths
SESSIONS_DIR = Path.home() / ".orion" / "sessions"
CHECKPOINTS_DIR = Path.home() / ".orion" / "checkpoints"

# TTL defaults
DEFAULT_SESSION_TTL_HOURS = 168  # 7 days
DEFAULT_CHECKPOINT_TTL_HOURS = 72  # 3 days
DEFAULT_MAX_CHECKPOINTS_PER_SESSION = 20


@dataclass
class CleanupStats:
    """Result of a cleanup operation."""

    sessions_cleaned: int = 0
    checkpoints_pruned: int = 0
    bytes_freed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def mb_freed(self) -> float:
        return self.bytes_freed / (1024 * 1024)

    def summary(self) -> str:
        return (
            f"Cleanup: {self.sessions_cleaned} sessions, "
            f"{self.checkpoints_pruned} checkpoints, "
            f"{self.mb_freed:.1f}MB freed"
        )


@dataclass
class SessionInfo:
    """Lightweight info about a stored session."""

    session_id: str
    role_name: str
    status: str
    created_at: float
    updated_at: float
    directory: Path
    size_bytes: int = 0

    @property
    def age_hours(self) -> float:
        return (time.time() - self.created_at) / 3600

    @property
    def idle_hours(self) -> float:
        return (time.time() - self.updated_at) / 3600

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "role_name": self.role_name,
            "status": self.status,
            "age_hours": round(self.age_hours, 1),
            "idle_hours": round(self.idle_hours, 1),
            "size_mb": round(self.size_bytes / (1024 * 1024), 2),
        }


class LifecycleManager:
    """Manages ARA resource lifecycle: cleanup, pruning, health checks."""

    def __init__(
        self,
        sessions_dir: Path | None = None,
        checkpoints_dir: Path | None = None,
        session_ttl_hours: float = DEFAULT_SESSION_TTL_HOURS,
        checkpoint_ttl_hours: float = DEFAULT_CHECKPOINT_TTL_HOURS,
        max_checkpoints_per_session: int = DEFAULT_MAX_CHECKPOINTS_PER_SESSION,
    ):
        self._sessions_dir = sessions_dir or SESSIONS_DIR
        self._checkpoints_dir = checkpoints_dir or CHECKPOINTS_DIR
        self._session_ttl = session_ttl_hours
        self._checkpoint_ttl = checkpoint_ttl_hours
        self._max_checkpoints = max_checkpoints_per_session

    def _dir_size(self, path: Path) -> int:
        """Calculate total size of a directory in bytes."""
        total = 0
        try:
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        except Exception:
            pass
        return total

    def list_sessions(self) -> list[SessionInfo]:
        """List all stored sessions with their info."""
        sessions: list[SessionInfo] = []
        if not self._sessions_dir.exists():
            return sessions

        for session_dir in self._sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            meta_path = session_dir / "session.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                sessions.append(
                    SessionInfo(
                        session_id=meta.get("session_id", session_dir.name),
                        role_name=meta.get("role_name", "unknown"),
                        status=meta.get("status", "unknown"),
                        created_at=meta.get("created_at", 0),
                        updated_at=meta.get("updated_at", 0),
                        directory=session_dir,
                        size_bytes=self._dir_size(session_dir),
                    )
                )
            except Exception as e:
                logger.warning("Failed to read session %s: %s", session_dir.name, e)

        return sessions

    def find_stale_sessions(self) -> list[SessionInfo]:
        """Find sessions that have exceeded their TTL."""
        stale: list[SessionInfo] = []
        for session in self.list_sessions():
            if session.status in ("completed", "cancelled", "failed"):
                if session.idle_hours > self._session_ttl:
                    stale.append(session)
        return stale

    def cleanup_session(self, session_dir: Path) -> int:
        """Remove a session directory. Returns bytes freed."""
        if not session_dir.exists():
            return 0
        size = self._dir_size(session_dir)
        try:
            shutil.rmtree(session_dir)
            logger.info("Cleaned up session: %s (%d bytes)", session_dir.name, size)
            return size
        except Exception as e:
            logger.warning("Failed to clean session %s: %s", session_dir.name, e)
            return 0

    def list_checkpoints(self, session_id: str) -> list[Path]:
        """List checkpoint directories for a session, sorted by age (oldest first)."""
        cp_dir = self._checkpoints_dir / session_id
        if not cp_dir.exists():
            return []
        checkpoints = sorted(
            [d for d in cp_dir.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
        )
        return checkpoints

    def prune_checkpoints(self, session_id: str) -> tuple[int, int]:
        """Prune old checkpoints for a session.

        Returns (count_pruned, bytes_freed).
        Keeps the most recent `max_checkpoints_per_session` checkpoints
        and removes any older than `checkpoint_ttl_hours`.
        """
        checkpoints = self.list_checkpoints(session_id)
        if not checkpoints:
            return 0, 0

        now = time.time()
        pruned_count = 0
        bytes_freed = 0

        # Remove checkpoints exceeding max count (keep newest)
        if len(checkpoints) > self._max_checkpoints:
            to_remove = checkpoints[: len(checkpoints) - self._max_checkpoints]
            for cp in to_remove:
                size = self._dir_size(cp)
                try:
                    shutil.rmtree(cp)
                    pruned_count += 1
                    bytes_freed += size
                except Exception as e:
                    logger.warning("Failed to prune checkpoint %s: %s", cp.name, e)
            checkpoints = checkpoints[len(to_remove) :]

        # Remove checkpoints older than TTL
        for cp in list(checkpoints):
            try:
                mtime = cp.stat().st_mtime
                age_hours = (now - mtime) / 3600
                if age_hours > self._checkpoint_ttl:
                    size = self._dir_size(cp)
                    shutil.rmtree(cp)
                    pruned_count += 1
                    bytes_freed += size
            except Exception as e:
                logger.warning("Failed to prune checkpoint %s: %s", cp.name, e)

        if pruned_count:
            logger.info(
                "Pruned %d checkpoints for session %s (%.1fMB freed)",
                pruned_count,
                session_id,
                bytes_freed / (1024 * 1024),
            )
        return pruned_count, bytes_freed

    def run_cleanup(self, dry_run: bool = False) -> CleanupStats:
        """Run full lifecycle cleanup: stale sessions + checkpoint pruning.

        If dry_run=True, report what would be cleaned without deleting.
        """
        stats = CleanupStats()

        # 1. Clean stale sessions
        stale = self.find_stale_sessions()
        for session in stale:
            if dry_run:
                stats.sessions_cleaned += 1
                stats.bytes_freed += session.size_bytes
            else:
                freed = self.cleanup_session(session.directory)
                if freed > 0:
                    stats.sessions_cleaned += 1
                    stats.bytes_freed += freed

        # 2. Prune checkpoints for all sessions
        if self._checkpoints_dir.exists():
            for session_dir in self._checkpoints_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                try:
                    count, freed = self.prune_checkpoints(session_dir.name)
                    stats.checkpoints_pruned += count
                    stats.bytes_freed += freed
                except Exception as e:
                    stats.errors.append(f"Checkpoint prune failed for {session_dir.name}: {e}")

        logger.info(stats.summary())
        return stats

    def health_report(self) -> dict[str, Any]:
        """Generate a health report of ARA resources."""
        sessions = self.list_sessions()
        total_size = sum(s.size_bytes for s in sessions)
        active = [s for s in sessions if s.status in ("running", "paused")]
        stale = self.find_stale_sessions()

        return {
            "total_sessions": len(sessions),
            "active_sessions": len(active),
            "stale_sessions": len(stale),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "sessions": [s.to_dict() for s in sessions],
        }
