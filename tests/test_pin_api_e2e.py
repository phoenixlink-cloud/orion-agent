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
"""E2E tests for PIN management API endpoints.

Tests the full request → AuthStore → response cycle via FastAPI TestClient.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_auth(tmp_path, monkeypatch):
    """Redirect AuthStore to a temp file so tests never touch ~/.orion/auth.json."""
    auth_file = tmp_path / "auth.json"
    import orion.ara.auth as auth_mod

    monkeypatch.setattr(auth_mod, "AUTH_STORE_PATH", auth_file)
    return auth_file


@pytest.fixture()
def client(tmp_auth):
    """FastAPI test client with ARA routes mounted."""
    from orion.api.routes.ara import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════
# GET /api/ara/auth/pin/status
# ═══════════════════════════════════════════════════════════════════════


class TestPinStatus:
    """GET /api/ara/auth/pin/status."""

    def test_no_pin_configured(self, client):
        resp = client.get("/api/ara/auth/pin/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_pin_configured_after_set(self, client):
        # Set a PIN first
        client.post("/api/ara/auth/pin", json={"new_pin": "5678"})
        resp = client.get("/api/ara/auth/pin/status")
        assert resp.status_code == 200
        assert resp.json()["configured"] is True


# ═══════════════════════════════════════════════════════════════════════
# POST /api/ara/auth/pin  (set / change)
# ═══════════════════════════════════════════════════════════════════════


class TestPinSet:
    """POST /api/ara/auth/pin — set and change PIN."""

    def test_set_new_pin(self, client):
        resp = client.post("/api/ara/auth/pin", json={"new_pin": "1234"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "successfully" in data["message"].lower()

    def test_set_pin_then_status_shows_configured(self, client):
        client.post("/api/ara/auth/pin", json={"new_pin": "1234"})
        status = client.get("/api/ara/auth/pin/status").json()
        assert status["configured"] is True

    def test_change_pin_requires_current(self, client):
        # Set initial PIN
        client.post("/api/ara/auth/pin", json={"new_pin": "1234"})
        # Try to change without current_pin
        resp = client.post("/api/ara/auth/pin", json={"new_pin": "5678"})
        assert resp.status_code == 400
        assert "current" in resp.json()["detail"].lower()

    def test_change_pin_wrong_current(self, client):
        client.post("/api/ara/auth/pin", json={"new_pin": "1234"})
        resp = client.post(
            "/api/ara/auth/pin",
            json={"new_pin": "5678", "current_pin": "9999"},
        )
        assert resp.status_code == 403

    def test_change_pin_correct_current(self, client):
        client.post("/api/ara/auth/pin", json={"new_pin": "1234"})
        resp = client.post(
            "/api/ara/auth/pin",
            json={"new_pin": "5678", "current_pin": "1234"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_new_pin_works_after_change(self, client):
        client.post("/api/ara/auth/pin", json={"new_pin": "1234"})
        client.post(
            "/api/ara/auth/pin",
            json={"new_pin": "5678", "current_pin": "1234"},
        )
        # Verify new PIN works
        resp = client.post("/api/ara/auth/pin/verify", params={"credential": "5678"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_old_pin_fails_after_change(self, client):
        client.post("/api/ara/auth/pin", json={"new_pin": "1234"})
        client.post(
            "/api/ara/auth/pin",
            json={"new_pin": "5678", "current_pin": "1234"},
        )
        # Old PIN should fail
        resp = client.post("/api/ara/auth/pin/verify", params={"credential": "1234"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_pin_too_short(self, client):
        resp = client.post("/api/ara/auth/pin", json={"new_pin": "12"})
        assert resp.status_code == 400

    def test_pin_non_digits(self, client):
        resp = client.post("/api/ara/auth/pin", json={"new_pin": "abcd"})
        assert resp.status_code == 400

    def test_pin_max_length(self, client):
        resp = client.post("/api/ara/auth/pin", json={"new_pin": "12345678"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_pin_over_max_length(self, client):
        resp = client.post("/api/ara/auth/pin", json={"new_pin": "123456789"})
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# POST /api/ara/auth/pin/verify
# ═══════════════════════════════════════════════════════════════════════


class TestPinVerify:
    """POST /api/ara/auth/pin/verify."""

    def test_verify_correct_pin(self, client):
        client.post("/api/ara/auth/pin", json={"new_pin": "4321"})
        resp = client.post("/api/ara/auth/pin/verify", params={"credential": "4321"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_verify_wrong_pin(self, client):
        client.post("/api/ara/auth/pin", json={"new_pin": "4321"})
        resp = client.post("/api/ara/auth/pin/verify", params={"credential": "0000"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["remaining_attempts"] is not None

    def test_verify_no_pin_set(self, client):
        resp = client.post("/api/ara/auth/pin/verify", params={"credential": "1234"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


# ═══════════════════════════════════════════════════════════════════════
# Full flow: set → verify → change → verify new
# ═══════════════════════════════════════════════════════════════════════


class TestPinFullFlow:
    """End-to-end happy path through the entire PIN lifecycle."""

    def test_full_lifecycle(self, client):
        # 1. No PIN configured
        status = client.get("/api/ara/auth/pin/status").json()
        assert status["configured"] is False

        # 2. Set initial PIN
        resp = client.post("/api/ara/auth/pin", json={"new_pin": "1234"})
        assert resp.status_code == 200

        # 3. Status now shows configured
        status = client.get("/api/ara/auth/pin/status").json()
        assert status["configured"] is True

        # 4. Verify the PIN
        verify = client.post("/api/ara/auth/pin/verify", params={"credential": "1234"}).json()
        assert verify["success"] is True

        # 5. Change PIN (provide current)
        resp = client.post(
            "/api/ara/auth/pin",
            json={"new_pin": "8888", "current_pin": "1234"},
        )
        assert resp.status_code == 200

        # 6. Old PIN no longer works
        verify = client.post("/api/ara/auth/pin/verify", params={"credential": "1234"}).json()
        assert verify["success"] is False

        # 7. New PIN works
        verify = client.post("/api/ara/auth/pin/verify", params={"credential": "8888"}).json()
        assert verify["success"] is True
