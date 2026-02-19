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
"""Tests for Google OAuth app credential configuration.

Covers:
- save / load / clear / validate / status / resolve_client_id / resolve_client_secret
- Credential resolution order (env > config file > oauth_clients)
- File permissions (0600)
- Validation of client_id / client_secret formats
- No hardcoded secrets in the entire source tree
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Redirect google_oauth_config paths to a temp directory."""
    import orion.security.egress.google_oauth_config as mod

    settings_dir = tmp_path / ".orion"
    settings_dir.mkdir()
    config_path = settings_dir / "google_oauth.json"

    monkeypatch.setattr(mod, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(mod, "CONFIG_PATH", config_path)

    # Clear env vars to avoid interference
    monkeypatch.delenv("ORION_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("ORION_GOOGLE_CLIENT_SECRET", raising=False)

    return config_path


VALID_CLIENT_ID = "123456789012-abcdefghijklmnopqrst.apps.googleusercontent.com"
VALID_CLIENT_SECRET = "GOCSPX-abcdefghijklmnopqrst1234"


# =========================================================================
# validate()
# =========================================================================


class TestValidate:
    def test_valid_client_id(self):
        from orion.security.egress.google_oauth_config import validate

        ok, reason = validate(VALID_CLIENT_ID)
        assert ok is True
        assert reason == ""

    def test_valid_with_secret(self):
        from orion.security.egress.google_oauth_config import validate

        ok, reason = validate(VALID_CLIENT_ID, VALID_CLIENT_SECRET)
        assert ok is True

    def test_empty_client_id(self):
        from orion.security.egress.google_oauth_config import validate

        ok, reason = validate("")
        assert ok is False
        assert "empty" in reason.lower()

    def test_invalid_format(self):
        from orion.security.egress.google_oauth_config import validate

        ok, reason = validate("not-a-valid-id")
        assert ok is False
        assert "format" in reason.lower()

    def test_invalid_secret_format(self):
        from orion.security.egress.google_oauth_config import validate

        ok, reason = validate(VALID_CLIENT_ID, "bad-secret")
        assert ok is False
        assert "GOCSPX" in reason

    def test_empty_secret_is_ok(self):
        from orion.security.egress.google_oauth_config import validate

        ok, _ = validate(VALID_CLIENT_ID, "")
        assert ok is True


# =========================================================================
# save() / load() / clear()
# =========================================================================


class TestSaveLoadClear:
    def test_save_creates_file(self, tmp_config):
        from orion.security.egress.google_oauth_config import load, save

        path = save(VALID_CLIENT_ID, VALID_CLIENT_SECRET)
        assert path.exists()

        data = load()
        assert data["client_id"] == VALID_CLIENT_ID
        assert data["client_secret"] == VALID_CLIENT_SECRET

    def test_save_without_secret(self, tmp_config):
        from orion.security.egress.google_oauth_config import load, save

        save(VALID_CLIENT_ID)
        data = load()
        assert data["client_id"] == VALID_CLIENT_ID
        assert data["client_secret"] == ""

    def test_save_rejects_empty_id(self, tmp_config):
        from orion.security.egress.google_oauth_config import save

        with pytest.raises(ValueError, match="empty"):
            save("")

    def test_save_rejects_invalid_id(self, tmp_config):
        from orion.security.egress.google_oauth_config import save

        with pytest.raises(ValueError, match="format"):
            save("not-valid")

    def test_save_file_permissions(self, tmp_config):
        from orion.security.egress.google_oauth_config import save

        path = save(VALID_CLIENT_ID)
        if sys.platform != "win32":
            mode = stat.S_IMODE(path.stat().st_mode)
            assert mode == 0o600

    def test_load_missing_file(self, tmp_config):
        from orion.security.egress.google_oauth_config import load

        data = load()
        assert data == {}

    def test_load_corrupt_file(self, tmp_config):
        from orion.security.egress.google_oauth_config import load

        tmp_config.write_text("not json {{{")
        data = load()
        assert data == {}

    def test_clear_removes_file(self, tmp_config):
        from orion.security.egress.google_oauth_config import clear, save

        save(VALID_CLIENT_ID)
        assert tmp_config.exists()

        result = clear()
        assert result is True
        assert not tmp_config.exists()

    def test_clear_nonexistent(self, tmp_config):
        from orion.security.egress.google_oauth_config import clear

        result = clear()
        assert result is False


# =========================================================================
# resolve_client_id() / resolve_client_secret() — resolution order
# =========================================================================


class TestResolve:
    def test_env_wins_over_file(self, tmp_config, monkeypatch):
        from orion.security.egress.google_oauth_config import resolve_client_id, save

        save(VALID_CLIENT_ID)
        env_id = "999999999-env.apps.googleusercontent.com"
        monkeypatch.setenv("ORION_GOOGLE_CLIENT_ID", env_id)

        assert resolve_client_id() == env_id

    def test_file_used_when_no_env(self, tmp_config):
        from orion.security.egress.google_oauth_config import resolve_client_id, save

        save(VALID_CLIENT_ID)
        assert resolve_client_id() == VALID_CLIENT_ID

    def test_returns_none_when_nothing_configured(self, tmp_config):
        from orion.security.egress.google_oauth_config import resolve_client_id

        with patch(
            "orion.integrations.oauth_manager.get_client_id",
            return_value=None,
        ):
            result = resolve_client_id()
        assert result is None

    def test_resolve_secret_from_env(self, tmp_config, monkeypatch):
        from orion.security.egress.google_oauth_config import resolve_client_secret

        monkeypatch.setenv("ORION_GOOGLE_CLIENT_SECRET", "GOCSPX-envtest123")
        assert resolve_client_secret() == "GOCSPX-envtest123"

    def test_resolve_secret_from_file(self, tmp_config):
        from orion.security.egress.google_oauth_config import resolve_client_secret, save

        save(VALID_CLIENT_ID, VALID_CLIENT_SECRET)
        assert resolve_client_secret() == VALID_CLIENT_SECRET


# =========================================================================
# status()
# =========================================================================


class TestStatus:
    def test_not_configured(self, tmp_config):
        from orion.security.egress.google_oauth_config import status

        s = status()
        assert s["configured"] is False
        assert s["source"] is None
        assert s["client_id_masked"] is None

    def test_configured_from_file(self, tmp_config):
        from orion.security.egress.google_oauth_config import save, status

        save(VALID_CLIENT_ID, VALID_CLIENT_SECRET)
        s = status()
        assert s["configured"] is True
        assert s["source"] == "config_file"
        assert s["has_client_secret"] is True
        # Masked — must NOT contain the full client_id
        assert s["client_id_masked"] != VALID_CLIENT_ID
        assert "***" in s["client_id_masked"]

    def test_configured_from_env(self, tmp_config, monkeypatch):
        from orion.security.egress.google_oauth_config import status

        monkeypatch.setenv("ORION_GOOGLE_CLIENT_ID", VALID_CLIENT_ID)
        s = status()
        assert s["configured"] is True
        assert s["source"] == "environment"


# =========================================================================
# No Hardcoded Secrets — Regression Guard
# =========================================================================


class TestNoHardcodedSecrets:
    """Scan the source tree for patterns that look like real Google credentials.

    This is a regression test to prevent accidentally committing real
    client_id, client_secret, or API keys.
    """

    @staticmethod
    def _get_source_files() -> list[Path]:
        """Collect all Python, JSON, YAML, TOML, and TS/TSX source files."""
        repo_root = Path(__file__).resolve().parent.parent
        extensions = {".py", ".json", ".yaml", ".yml", ".toml", ".ts", ".tsx"}
        files = []
        for ext in extensions:
            files.extend(repo_root.rglob(f"*{ext}"))
        # Exclude node_modules, .git, __pycache__, dist, build
        exclude_dirs = {"node_modules", ".git", "__pycache__", "dist", "build", ".next"}
        return [f for f in files if not any(part in exclude_dirs for part in f.parts)]

    def test_no_real_google_client_id_in_source(self):
        """No file should contain a real-looking Google OAuth client_id."""
        import re

        pattern = re.compile(r"\d{10,14}-[a-zA-Z0-9_]{20,}\.apps\.googleusercontent\.com")
        violations = []
        for f in self._get_source_files():
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            # Skip this test file itself (it has a fake ID in constants)
            if f.name == "test_google_oauth_config.py":
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    # Allow commented-out placeholders in .env.example and docs
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith("//"):
                        continue
                    # Allow regex pattern definitions (validation code)
                    if "re.compile" in line or "_PATTERN" in line:
                        continue
                    # Allow docs/markdown examples
                    if f.suffix == ".md":
                        continue
                    violations.append(f"{f}:{i}: {line.strip()[:120]}")

        assert violations == [], (
            "Found real-looking Google client_id in source files:\n" + "\n".join(violations)
        )

    def test_no_real_google_client_secret_in_source(self):
        """No file should contain a real-looking Google client_secret (GOCSPX-...)."""
        import re

        # Match GOCSPX- followed by 20+ chars (real secrets are ~24 chars)
        pattern = re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}")
        violations = []
        for f in self._get_source_files():
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if f.name == "test_google_oauth_config.py":
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith("//"):
                        continue
                    if "re.compile" in line or "_PATTERN" in line:
                        continue
                    if f.suffix == ".md":
                        continue
                    violations.append(f"{f}:{i}: {line.strip()[:120]}")

        assert violations == [], (
            "Found real-looking Google client_secret in source files:\n" + "\n".join(violations)
        )

    def test_no_google_api_key_in_source(self):
        """No file should contain a real-looking Google API key (AIza...)."""
        import re

        # Real Google API keys start with AIza and are 39 chars total
        pattern = re.compile(r"AIza[A-Za-z0-9_-]{35}")
        violations = []
        for f in self._get_source_files():
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith("//"):
                        continue
                    # Allow runtime-constructed fake keys in tests
                    if "AIza" in line and (
                        "+" in line
                        or "join" in line
                        or "prefix" in line
                        or "FAKE" in line.upper()
                        or "construct" in line.lower()
                    ):
                        continue
                    # Allow regex/pattern definitions
                    if "re.compile" in line or "_PATTERN" in line or "pattern" in line.lower():
                        continue
                    if f.suffix == ".md":
                        continue
                    violations.append(f"{f}:{i}: {line.strip()[:120]}")

        assert violations == [], "Found real-looking Google API key in source files:\n" + "\n".join(
            violations
        )

    def test_oauth_defaults_has_empty_client_ids(self):
        """data/oauth_defaults.json must NOT ship with real client_ids."""
        repo_root = Path(__file__).resolve().parent.parent
        defaults_path = repo_root / "data" / "oauth_defaults.json"
        if not defaults_path.exists():
            pytest.skip("oauth_defaults.json not found")

        data = json.loads(defaults_path.read_text())
        for provider, cfg in data.items():
            if provider.startswith("_"):
                continue
            client_id = cfg.get("client_id", "")
            assert client_id == "", (
                f"data/oauth_defaults.json has non-empty client_id for '{provider}': "
                f"{client_id[:20]}..."
            )


# =========================================================================
# API endpoint tests (google_configure)
# =========================================================================


class TestGoogleConfigureEndpoints:
    """Test the /api/google/configure endpoints via FastAPI TestClient."""

    @pytest.fixture
    def client(self, tmp_config):
        """Create a FastAPI test client with google routes."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from orion.api.routes.google import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_configure_post_valid(self, client, tmp_config):
        resp = client.post(
            "/api/google/configure",
            json={"client_id": VALID_CLIENT_ID, "client_secret": VALID_CLIENT_SECRET},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "configured"
        assert data["configured"] is True
        assert "***" in data["client_id_masked"]

    def test_configure_post_invalid(self, client, tmp_config):
        resp = client.post(
            "/api/google/configure",
            json={"client_id": "bad-id"},
        )
        assert resp.status_code == 400

    def test_configure_get_not_configured(self, client, tmp_config):
        resp = client.get("/api/google/configure")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_configure_get_after_save(self, client, tmp_config):
        client.post(
            "/api/google/configure",
            json={"client_id": VALID_CLIENT_ID},
        )
        resp = client.get("/api/google/configure")
        data = resp.json()
        assert data["configured"] is True
        assert data["source"] == "config_file"

    def test_configure_delete(self, client, tmp_config):
        client.post(
            "/api/google/configure",
            json={"client_id": VALID_CLIENT_ID},
        )
        resp = client.delete("/api/google/configure")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"

        # Verify it's gone
        resp2 = client.get("/api/google/configure")
        assert resp2.json()["configured"] is False

    def test_configure_delete_nonexistent(self, client, tmp_config):
        resp = client.delete("/api/google/configure")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_found"
