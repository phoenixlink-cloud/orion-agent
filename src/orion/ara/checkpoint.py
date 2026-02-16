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
"""ARA Checkpoint — git-based snapshot and rollback for session state.

Creates lightweight snapshots of the sandbox workspace and session state.
Supports rollback to any previous checkpoint.

See ARA-001 §10 for full design.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.ara.checkpoint")

CHECKPOINTS_DIR = Path.home() / ".orion" / "checkpoints"


@dataclass
class CheckpointInfo:
    """Metadata for a single checkpoint."""

    checkpoint_id: str
    session_id: str
    created_at: float
    task_index: int
    tasks_completed: int
    description: str = ""
    directory: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "task_index": self.task_index,
            "tasks_completed": self.tasks_completed,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], directory: Path | None = None) -> CheckpointInfo:
        return cls(
            checkpoint_id=data["checkpoint_id"],
            session_id=data["session_id"],
            created_at=data.get("created_at", 0),
            task_index=data.get("task_index", 0),
            tasks_completed=data.get("tasks_completed", 0),
            description=data.get("description", ""),
            directory=directory,
        )


class CheckpointManager:
    """Manages checkpoint creation, listing, and rollback."""

    def __init__(
        self,
        session_id: str,
        checkpoints_dir: Path | None = None,
    ):
        self._session_id = session_id
        self._base_dir = (checkpoints_dir or CHECKPOINTS_DIR) / session_id
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._counter = self._detect_counter()

    def _detect_counter(self) -> int:
        """Find the next checkpoint number."""
        existing = sorted(self._base_dir.glob("cp-*"))
        if not existing:
            return 0
        try:
            last = existing[-1].name.split("-")[1]
            return int(last) + 1
        except (IndexError, ValueError):
            return len(existing)

    def create(
        self,
        session_state: dict[str, Any],
        dag_state: dict[str, Any],
        sandbox_path: Path | None = None,
        description: str = "",
    ) -> CheckpointInfo:
        """Create a new checkpoint.

        Saves session state, DAG state, and optionally copies the sandbox workspace.
        """
        cp_id = f"cp-{self._counter:04d}"
        cp_dir = self._base_dir / cp_id
        cp_dir.mkdir(parents=True, exist_ok=True)

        # Save session state
        (cp_dir / "session.json").write_text(json.dumps(session_state, indent=2), encoding="utf-8")

        # Save DAG state
        (cp_dir / "dag.json").write_text(json.dumps(dag_state, indent=2), encoding="utf-8")

        # Copy sandbox workspace if provided
        if sandbox_path and sandbox_path.exists():
            ws_backup = cp_dir / "workspace"
            shutil.copytree(sandbox_path, ws_backup, dirs_exist_ok=True)

        # Save checkpoint metadata
        info = CheckpointInfo(
            checkpoint_id=cp_id,
            session_id=self._session_id,
            created_at=time.time(),
            task_index=self._counter,
            tasks_completed=dag_state.get("completed_count", 0),
            description=description,
            directory=cp_dir,
        )
        (cp_dir / "checkpoint.json").write_text(
            json.dumps(info.to_dict(), indent=2), encoding="utf-8"
        )

        self._counter += 1
        logger.info("Checkpoint created: %s (%s)", cp_id, description or "auto")
        return info

    def list_checkpoints(self) -> list[CheckpointInfo]:
        """List all checkpoints for this session, ordered by creation."""
        checkpoints: list[CheckpointInfo] = []
        for cp_dir in sorted(self._base_dir.glob("cp-*")):
            meta_path = cp_dir / "checkpoint.json"
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    checkpoints.append(CheckpointInfo.from_dict(data, directory=cp_dir))
                except Exception as e:
                    logger.warning("Failed to load checkpoint %s: %s", cp_dir.name, e)
        return checkpoints

    def get_latest(self) -> CheckpointInfo | None:
        """Get the most recent checkpoint."""
        cps = self.list_checkpoints()
        return cps[-1] if cps else None

    def rollback(self, checkpoint_id: str) -> tuple[dict[str, Any], dict[str, Any], Path | None]:
        """Rollback to a specific checkpoint.

        Returns (session_state, dag_state, workspace_path_or_None).
        """
        cp_dir = self._base_dir / checkpoint_id
        if not cp_dir.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")

        session_data = json.loads((cp_dir / "session.json").read_text(encoding="utf-8"))
        dag_data = json.loads((cp_dir / "dag.json").read_text(encoding="utf-8"))

        ws_path = cp_dir / "workspace"
        workspace = ws_path if ws_path.exists() else None

        logger.info("Rolled back to checkpoint: %s", checkpoint_id)
        return session_data, dag_data, workspace

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a specific checkpoint."""
        cp_dir = self._base_dir / checkpoint_id
        if not cp_dir.exists():
            return False
        shutil.rmtree(cp_dir)
        logger.info("Deleted checkpoint: %s", checkpoint_id)
        return True

    @property
    def checkpoint_count(self) -> int:
        return len(self.list_checkpoints())
