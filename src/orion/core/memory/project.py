# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
#    You may use, modify, and distribute this file under AGPL-3.0.
#    See LICENSE for the full text.
#
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#    For proprietary use, SaaS deployment, or enterprise licensing.
#    See LICENSE-ENTERPRISE.md or contact info@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- Tier 2: Project Memory (v7.4.0)

Project-scoped memory that persists within a workspace.
Provides full project context instead of chunked evidence.

Migrated from Orion_MVP/memory/project_memory.py.

Location: {workspace}/.orion/project_memory.json
Duration: Days to weeks (lifetime of project)
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class FileContext:
    """Context for a single file in the project."""

    path: str
    content_hash: str
    size: int
    language: str
    last_modified: str
    summary: str | None = None


@dataclass
class ProjectDecision:
    """A decision made in this project."""

    action: str
    outcome: str
    quality: float
    timestamp: str
    context: str | None = None


# ── Language detection map ────────────────────────────────────────────────

_CODE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "react",
    ".tsx": "react-typescript",
    ".cs": "csharp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c-header",
    ".hpp": "cpp-header",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".md": "markdown",
    ".txt": "text",
    ".sh": "shell",
    ".bat": "batch",
    ".ps1": "powershell",
    ".xaml": "xaml",
    ".csproj": "msbuild",
    ".sln": "solution",
}

_SKIP_DIRS = {
    ".git",
    ".orion",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "bin",
    "obj",
    "dist",
    "build",
    ".next",
    ".pytest_cache",
    ".mypy_cache",
}


class ProjectMemory:
    """
    Layer 2: Project Memory (Days – Weeks)

    Project-scoped memory that provides full context for the current workspace.
    Persists across sessions within the same project.

    Stored at {workspace}/.orion/project_memory.json
    """

    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path)
        self.orion_dir = self.workspace_path / ".orion"
        self.memory_file = self.orion_dir / "project_memory.json"

        self.files: dict[str, FileContext] = {}
        self.decisions: list[ProjectDecision] = []
        self.project_patterns: list[str] = []
        self.metadata: dict[str, Any] = {}

        self._load()

    # ── Persistence ──────────────────────────────────────────────────────

    def _load(self):
        if self.memory_file.exists():
            try:
                with open(self.memory_file, encoding="utf-8") as f:
                    data = json.load(f)
                self.files = {p: FileContext(**fc) for p, fc in data.get("files", {}).items()}
                self.decisions = [ProjectDecision(**d) for d in data.get("decisions", [])]
                self.project_patterns = data.get("project_patterns", [])
                self.metadata = data.get("metadata", {})
            except Exception:
                self._init_empty()
        else:
            self._init_empty()

    def _init_empty(self):
        self.files = {}
        self.decisions = []
        self.project_patterns = []
        self.metadata = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "workspace_path": str(self.workspace_path),
        }

    def _save(self):
        self.orion_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "files": {
                p: {
                    "path": fc.path,
                    "content_hash": fc.content_hash,
                    "size": fc.size,
                    "language": fc.language,
                    "last_modified": fc.last_modified,
                    "summary": fc.summary,
                }
                for p, fc in self.files.items()
            },
            "decisions": [
                {
                    "action": d.action,
                    "outcome": d.outcome,
                    "quality": d.quality,
                    "timestamp": d.timestamp,
                    "context": d.context,
                }
                for d in self.decisions
            ],
            "project_patterns": self.project_patterns,
            "metadata": self.metadata,
        }
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ── Workspace scanning ───────────────────────────────────────────────

    def update_from_workspace(self):
        """Scan workspace and update file index."""
        new_files: dict[str, FileContext] = {}

        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for filename in files:
                filepath = Path(root) / filename
                ext = filepath.suffix.lower()
                if ext not in _CODE_EXTENSIONS:
                    continue
                rel_path = str(filepath.relative_to(self.workspace_path))
                try:
                    stat = filepath.stat()
                    with open(filepath, "rb") as f:
                        content_hash = hashlib.md5(f.read()).hexdigest()[:12]
                    existing = self.files.get(rel_path)
                    new_files[rel_path] = FileContext(
                        path=rel_path,
                        content_hash=content_hash,
                        size=stat.st_size,
                        language=_CODE_EXTENSIONS[ext],
                        last_modified=datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                        summary=existing.summary if existing else None,
                    )
                except Exception:
                    continue

        self.files = new_files
        self.metadata["last_scan"] = datetime.now(timezone.utc).isoformat()
        self._save()

    # ── Decision tracking ────────────────────────────────────────────────

    def record_decision(
        self, action: str, outcome: str, quality: float, context: str | None = None
    ):
        """Record a decision made in this project."""
        self.decisions.append(
            ProjectDecision(
                action=action,
                outcome=outcome,
                quality=quality,
                timestamp=datetime.now(timezone.utc).isoformat(),
                context=context,
            )
        )
        if len(self.decisions) > 100:
            self.decisions = self.decisions[-100:]
        self._save()

    def get_relevant_decisions(self, task: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get past decisions relevant to current task."""
        recent = self.decisions[-limit:]
        return [
            {
                "action": d.action,
                "outcome": d.outcome,
                "quality": d.quality,
                "timestamp": d.timestamp,
            }
            for d in recent
        ]

    # ── Context for LLM consumption ──────────────────────────────────────

    def get_full_context(self) -> str:
        """Get full project context for model consumption."""
        lines = [f"## Project: {self.workspace_path.name}"]
        lines.append(f"Files: {len(self.files)}")

        by_language: dict[str, list[str]] = {}
        for path, fc in self.files.items():
            by_language.setdefault(fc.language, []).append(path)

        lines.append("\n### Project Structure")
        for lang, paths in sorted(by_language.items()):
            lines.append(f"- {lang}: {len(paths)} files")
            for path in sorted(paths)[:5]:
                lines.append(f"  - {path}")
            if len(paths) > 5:
                lines.append(f"  - ... and {len(paths) - 5} more")

        if self.decisions:
            lines.append("\n### Recent Decisions")
            for d in self.decisions[-5:]:
                q = "✓" if d.quality >= 0.8 else "○" if d.quality >= 0.5 else "✗"
                lines.append(f"- {q} {d.action[:50]}")

        return "\n".join(lines)

    # ── Query helpers ────────────────────────────────────────────────────

    def get_file_list(self) -> list[str]:
        return list(self.files.keys())

    def get_file_context(self, path: str) -> FileContext | None:
        return self.files.get(path)

    def add_project_pattern(self, pattern: str):
        if pattern not in self.project_patterns:
            self.project_patterns.append(pattern)
            self._save()

    def get_statistics(self) -> dict[str, Any]:
        by_language: dict[str, int] = {}
        total_size = 0
        for fc in self.files.values():
            by_language[fc.language] = by_language.get(fc.language, 0) + 1
            total_size += fc.size
        return {
            "workspace": str(self.workspace_path),
            "total_files": len(self.files),
            "total_size_bytes": total_size,
            "files_by_language": by_language,
            "decisions_recorded": len(self.decisions),
            "project_patterns": len(self.project_patterns),
            "last_scan": self.metadata.get("last_scan", "never"),
        }

    def clear(self):
        self._init_empty()
        self._save()
