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
"""Stack Detector — automatically detect the project stack from workspace files.

Scans the workspace directory for well-known project files and returns
the best-matching stack name for selecting the correct Docker image.

Supported stacks:
  - python  (requirements.txt, setup.py, pyproject.toml, Pipfile, *.py)
  - node    (package.json, yarn.lock, *.js, *.ts)
  - go      (go.mod, go.sum, *.go)
  - rust    (Cargo.toml, Cargo.lock, *.rs)
  - base    (fallback — generic Ubuntu with shell tools)

See Phase 4A.4 specification.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("orion.security.stack_detector")

# ---------------------------------------------------------------------------
# Stack definitions: marker files → stack name
# ---------------------------------------------------------------------------

# Each entry: (stack_name, marker_files, file_extensions, priority)
# Higher priority wins when multiple stacks match.
_STACK_SIGNATURES: list[tuple[str, list[str], list[str], int]] = [
    (
        "python",
        ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile", "setup.cfg", "poetry.lock"],
        [".py"],
        10,
    ),
    (
        "node",
        ["package.json", "yarn.lock", "pnpm-lock.yaml", ".nvmrc"],
        [".js", ".ts", ".jsx", ".tsx"],
        10,
    ),
    (
        "go",
        ["go.mod", "go.sum"],
        [".go"],
        10,
    ),
    (
        "rust",
        ["Cargo.toml", "Cargo.lock"],
        [".rs"],
        10,
    ),
]

# Valid stack names (must have a matching Dockerfile in docker/stacks/)
VALID_STACKS = frozenset({"base", "python", "node", "go", "rust"})

# Docker image name pattern
IMAGE_PREFIX = "orion-stack-"


def detect_stack(workspace_path: Path | str) -> str:
    """Detect the project stack from files in the workspace directory.

    Args:
        workspace_path: Path to the project workspace directory.

    Returns:
        Stack name string (e.g. ``"python"``, ``"node"``).
        Falls back to ``"base"`` if no stack can be determined.
    """
    workspace = Path(workspace_path)
    if not workspace.exists() or not workspace.is_dir():
        logger.debug("Workspace does not exist or is not a directory: %s", workspace)
        return "base"

    scores: dict[str, int] = {}

    # Scan top-level files (not recursive for marker files)
    top_level_files = {f.name for f in workspace.iterdir() if f.is_file()}

    for stack_name, markers, extensions, priority in _STACK_SIGNATURES:
        score = 0

        # Check marker files
        for marker in markers:
            if marker in top_level_files:
                score += priority

        # Check file extensions (scan one level deep for speed)
        if extensions:
            for f in workspace.iterdir():
                if f.is_file() and f.suffix in extensions:
                    score += 2
                    break  # One match is enough for extension signal

        if score > 0:
            scores[stack_name] = score

    if not scores:
        logger.debug("No stack detected in %s, using base", workspace)
        return "base"

    # Return highest-scoring stack
    best = max(scores, key=lambda k: scores[k])
    logger.info("Detected stack: %s (score=%d) in %s", best, scores[best], workspace)
    return best


def detect_stack_from_goal(goal: str) -> str:
    """Infer stack from the goal description text.

    Used as a fallback when workspace is empty (new project).

    Args:
        goal: The user's goal text.

    Returns:
        Stack name or ``"base"`` if no stack can be inferred.
    """
    lower = goal.lower()

    _goal_keywords: dict[str, list[str]] = {
        "python": ["python", "flask", "django", "fastapi", "pip", "pytest", "pandas"],
        "node": [
            "node",
            "javascript",
            "typescript",
            "react",
            "vue",
            "angular",
            "npm",
            "yarn",
            "express",
            "next.js",
        ],
        "go": ["golang", "go ", " go,", "gin", "echo framework"],
        "rust": ["rust", "cargo", "tokio", "actix"],
    }

    for stack, keywords in _goal_keywords.items():
        for kw in keywords:
            if kw in lower:
                logger.debug("Stack %s inferred from goal keyword '%s'", stack, kw)
                return stack

    return "base"


def image_name(stack: str) -> str:
    """Return the Docker image name for a stack.

    Args:
        stack: Stack name (e.g. ``"python"``).

    Returns:
        Docker image tag (e.g. ``"orion-stack-python:latest"``).
    """
    if stack not in VALID_STACKS:
        stack = "base"
    return f"{IMAGE_PREFIX}{stack}:latest"


def dockerfile_path(stack: str) -> str:
    """Return the relative path to the Dockerfile for a stack.

    Args:
        stack: Stack name.

    Returns:
        Relative path like ``"docker/stacks/Dockerfile.python"``.
    """
    if stack not in VALID_STACKS:
        stack = "base"
    return f"docker/stacks/Dockerfile.{stack}"
