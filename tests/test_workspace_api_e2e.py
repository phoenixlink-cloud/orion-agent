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
"""E2E tests for Workspace decision API endpoints.

Tests the full request → cli_commands → response cycle via FastAPI TestClient.
Covers: GET /api/ara/workspace, DELETE /api/ara/workspace,
        POST /api/ara/work with project_mode.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def workspace(tmp_path):
    """Create a temp workspace with a few files."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "main.py").write_text("print('hello')")
    (ws / "utils.py").write_text("def helper(): pass")
    return ws


@pytest.fixture()
def empty_workspace(tmp_path):
    """Create an empty temp workspace."""
    ws = tmp_path / "empty_ws"
    ws.mkdir()
    return ws


@pytest.fixture()
def settings_file(tmp_path, workspace):
    """Write a settings.json pointing to the workspace fixture."""
    orion_dir = tmp_path / ".orion"
    orion_dir.mkdir(exist_ok=True)
    sf = orion_dir / "settings.json"
    sf.write_text(json.dumps({"default_workspace": str(workspace)}))
    return sf


@pytest.fixture()
def client(tmp_path, monkeypatch, settings_file):
    """FastAPI test client with ARA routes and workspace pointing to tmp."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Redirect auth store so tests don't touch real ~/.orion/auth.json
    import orion.ara.auth as auth_mod

    monkeypatch.setattr(auth_mod, "AUTH_STORE_PATH", tmp_path / "auth.json")

    from orion.api.routes.ara import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════
# GET /api/ara/workspace
# ═══════════════════════════════════════════════════════════════════════


class TestGetWorkspace:
    def test_lists_files(self, client, workspace):
        r = client.get("/api/ara/workspace")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "main.py" in body["data"]["files"]
        assert "utils.py" in body["data"]["files"]

    def test_empty_workspace(self, client, tmp_path, monkeypatch, empty_workspace):
        orion_dir = tmp_path / ".orion"
        (orion_dir / "settings.json").write_text(
            json.dumps({"default_workspace": str(empty_workspace)})
        )
        r = client.get("/api/ara/workspace")
        assert r.status_code == 200
        assert r.json()["data"]["files"] == []


# ═══════════════════════════════════════════════════════════════════════
# DELETE /api/ara/workspace
# ═══════════════════════════════════════════════════════════════════════


class TestDeleteWorkspace:
    def test_clears_files(self, client, workspace):
        # Verify files exist first
        assert (workspace / "main.py").exists()
        r = client.delete("/api/ara/workspace")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["data"]["removed"] == 2
        assert not (workspace / "main.py").exists()
        assert not (workspace / "utils.py").exists()

    def test_preserves_git(self, client, workspace):
        git_dir = workspace / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main")
        r = client.delete("/api/ara/workspace")
        assert r.status_code == 200
        assert (git_dir / "HEAD").exists()


# ═══════════════════════════════════════════════════════════════════════
# POST /api/ara/work — project_mode flow
# ═══════════════════════════════════════════════════════════════════════


class TestWorkProjectMode:
    """Test that POST /api/ara/work returns needs_decision when files exist."""

    def test_auto_mode_triggers_decision(self, client, workspace):
        # Use a PIN-auth role so auth auto-provisions (TOTP roles would fail)
        r = client.post(
            "/api/ara/work",
            json={
                "role_name": "junior-developer",
                "goal": "Build API",
                "workspace_path": str(workspace),
                "project_mode": "auto",
            },
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.json()}"
        body = r.json()
        assert body.get("needs_decision") is True
        assert "main.py" in body["data"]["workspace_files"]
