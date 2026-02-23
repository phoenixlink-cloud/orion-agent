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
"""Tests for StackDetector — automatic project stack detection.

Tests SD-01 through SD-06+ as specified in Phase 4A.4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.security.stack_detector import (
    VALID_STACKS,
    detect_stack,
    detect_stack_from_goal,
    dockerfile_path,
    image_name,
)

# ---------------------------------------------------------------------------
# SD-01: Python stack detection
# ---------------------------------------------------------------------------


class TestDetectPython:
    """SD-01: Python projects are detected correctly."""

    def test_requirements_txt(self, tmp_path: Path):
        (tmp_path / "requirements.txt").write_text("flask\n")
        assert detect_stack(tmp_path) == "python"

    def test_pyproject_toml(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        assert detect_stack(tmp_path) == "python"

    def test_setup_py(self, tmp_path: Path):
        (tmp_path / "setup.py").write_text("from setuptools import setup\n")
        assert detect_stack(tmp_path) == "python"

    def test_pipfile(self, tmp_path: Path):
        (tmp_path / "Pipfile").write_text("[packages]\n")
        assert detect_stack(tmp_path) == "python"

    def test_py_extension(self, tmp_path: Path):
        (tmp_path / "app.py").write_text("print('hello')\n")
        assert detect_stack(tmp_path) == "python"


# ---------------------------------------------------------------------------
# SD-02: Node stack detection
# ---------------------------------------------------------------------------


class TestDetectNode:
    """SD-02: Node.js projects are detected correctly."""

    def test_package_json(self, tmp_path: Path):
        (tmp_path / "package.json").write_text('{"name":"app"}\n')
        assert detect_stack(tmp_path) == "node"

    def test_yarn_lock(self, tmp_path: Path):
        (tmp_path / "yarn.lock").write_text("# yarn lock\n")
        assert detect_stack(tmp_path) == "node"

    def test_js_extension(self, tmp_path: Path):
        (tmp_path / "index.js").write_text("console.log('hi')\n")
        assert detect_stack(tmp_path) == "node"

    def test_ts_extension(self, tmp_path: Path):
        (tmp_path / "app.ts").write_text("const x: number = 1;\n")
        assert detect_stack(tmp_path) == "node"


# ---------------------------------------------------------------------------
# SD-03: Go stack detection
# ---------------------------------------------------------------------------


class TestDetectGo:
    """SD-03: Go projects are detected correctly."""

    def test_go_mod(self, tmp_path: Path):
        (tmp_path / "go.mod").write_text("module example.com/app\n")
        assert detect_stack(tmp_path) == "go"

    def test_go_extension(self, tmp_path: Path):
        (tmp_path / "main.go").write_text("package main\n")
        assert detect_stack(tmp_path) == "go"


# ---------------------------------------------------------------------------
# SD-04: Rust stack detection
# ---------------------------------------------------------------------------


class TestDetectRust:
    """SD-04: Rust projects are detected correctly."""

    def test_cargo_toml(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text('[package]\nname="app"\n')
        assert detect_stack(tmp_path) == "rust"

    def test_rs_extension(self, tmp_path: Path):
        (tmp_path / "main.rs").write_text("fn main() {}\n")
        assert detect_stack(tmp_path) == "rust"


# ---------------------------------------------------------------------------
# SD-05: Base fallback
# ---------------------------------------------------------------------------


class TestDetectBase:
    """SD-05: Unknown/empty projects fall back to base."""

    def test_empty_directory(self, tmp_path: Path):
        assert detect_stack(tmp_path) == "base"

    def test_no_known_files(self, tmp_path: Path):
        (tmp_path / "readme.md").write_text("# Hello\n")
        (tmp_path / "data.csv").write_text("a,b\n1,2\n")
        assert detect_stack(tmp_path) == "base"

    def test_nonexistent_dir(self, tmp_path: Path):
        assert detect_stack(tmp_path / "nonexistent") == "base"


# ---------------------------------------------------------------------------
# SD-06: Goal-based detection
# ---------------------------------------------------------------------------


class TestDetectFromGoal:
    """SD-06: detect_stack_from_goal infers stack from goal text."""

    def test_python_goal(self):
        assert detect_stack_from_goal("Build a Flask REST API") == "python"

    def test_node_goal(self):
        assert detect_stack_from_goal("Create a React dashboard") == "node"

    def test_go_goal(self):
        assert detect_stack_from_goal("Write a golang microservice") == "go"

    def test_rust_goal(self):
        assert detect_stack_from_goal("Build a CLI tool in Rust") == "rust"

    def test_unknown_goal(self):
        assert detect_stack_from_goal("Do something interesting") == "base"

    def test_django_keyword(self):
        assert detect_stack_from_goal("Create a Django web app") == "python"

    def test_express_keyword(self):
        assert detect_stack_from_goal("Build an Express API server") == "node"


# ---------------------------------------------------------------------------
# SD-07: image_name and dockerfile_path helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """SD-07: image_name and dockerfile_path return correct values."""

    def test_image_name_python(self):
        assert image_name("python") == "orion-stack-python:latest"

    def test_image_name_base(self):
        assert image_name("base") == "orion-stack-base:latest"

    def test_image_name_invalid_falls_back(self):
        assert image_name("fortran") == "orion-stack-base:latest"

    def test_dockerfile_path_node(self):
        assert dockerfile_path("node") == "docker/stacks/Dockerfile.node"

    def test_dockerfile_path_invalid_falls_back(self):
        assert dockerfile_path("cobol") == "docker/stacks/Dockerfile.base"

    def test_valid_stacks_set(self):
        assert "python" in VALID_STACKS
        assert "node" in VALID_STACKS
        assert "go" in VALID_STACKS
        assert "rust" in VALID_STACKS
        assert "base" in VALID_STACKS


# ---------------------------------------------------------------------------
# SD-08: Multi-stack priority (highest score wins)
# ---------------------------------------------------------------------------


class TestMultiStackPriority:
    """SD-08: When multiple stacks match, highest score wins."""

    def test_python_beats_node_with_more_markers(self, tmp_path: Path):
        """Python wins when it has more marker files."""
        (tmp_path / "requirements.txt").write_text("flask\n")
        (tmp_path / "setup.py").write_text("setup()\n")
        (tmp_path / "package.json").write_text("{}\n")
        assert detect_stack(tmp_path) == "python"

    def test_node_wins_with_more_markers(self, tmp_path: Path):
        """Node wins when it has more markers."""
        (tmp_path / "package.json").write_text("{}\n")
        (tmp_path / "yarn.lock").write_text("# lock\n")
        (tmp_path / "app.py").write_text("x = 1\n")
        # Node: 10 (package.json) + 10 (yarn.lock) = 20
        # Python: 2 (app.py extension only)
        assert detect_stack(tmp_path) == "node"
