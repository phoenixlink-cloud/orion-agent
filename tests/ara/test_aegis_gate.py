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
"""Tests for AEGIS Traffic Gate (ARA-001 §3.4, §C.7, §C.8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.ara.aegis_gate import AegisGate, GateDecision
from orion.ara.auth import AuthStore, RoleAuthenticator
from orion.ara.role_profile import RoleProfile
from orion.security.secret_scanner import SecretScanner
from orion.security.write_limits import WriteTracker


@pytest.fixture
def role() -> RoleProfile:
    return RoleProfile(
        name="test-gate",
        scope="coding",
        auth_method="pin",
        allowed_actions=["read_files", "write_files"],
        require_review_before_promote=True,
    )


@pytest.fixture
def no_review_role() -> RoleProfile:
    return RoleProfile(
        name="no-review",
        scope="coding",
        auth_method="pin",
        require_review_before_promote=False,
    )


@pytest.fixture
def auth(tmp_path: Path) -> RoleAuthenticator:
    store = AuthStore(store_path=tmp_path / "auth.json")
    authenticator = RoleAuthenticator(auth_store=store)
    authenticator.setup_pin("1234")
    return authenticator


@pytest.fixture
def clean_sandbox(tmp_path: Path) -> Path:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "main.py").write_text("print('hello')\n")
    (sandbox / "utils.py").write_text("def add(a, b): return a + b\n")
    return sandbox


@pytest.fixture
def dirty_sandbox(tmp_path: Path) -> Path:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "config.py").write_text('API_KEY = "AKIAIOSFODNN7EXAMPLE"\n')
    return sandbox


@pytest.fixture
def gate(role: RoleProfile, auth: RoleAuthenticator) -> AegisGate:
    return AegisGate(role=role, authenticator=auth)


class TestFullGateApproval:
    """Test full gate evaluation — all checks pass."""

    def test_approve_clean_sandbox(self, gate: AegisGate, clean_sandbox: Path):
        decision = gate.evaluate(
            sandbox_path=clean_sandbox,
            actions_performed=["read_files", "write_files"],
            credential="1234",
        )
        assert decision.approved is True
        assert len(decision.checks_passed) == 4
        assert len(decision.checks_failed) == 0

    def test_approve_no_review_role(
        self, no_review_role: RoleProfile, auth: RoleAuthenticator, clean_sandbox: Path
    ):
        gate = AegisGate(role=no_review_role, authenticator=auth)
        decision = gate.evaluate(
            sandbox_path=clean_sandbox,
            actions_performed=[],
        )
        assert decision.approved is True
        assert "auth" in decision.checks_passed


class TestSecretScanBlock:
    """Test that secrets block promotion."""

    def test_blocks_secrets(self, gate: AegisGate, dirty_sandbox: Path):
        decision = gate.evaluate(
            sandbox_path=dirty_sandbox,
            actions_performed=["read_files"],
            credential="1234",
        )
        assert decision.approved is False
        assert "secret_scan" in decision.checks_failed
        assert "secret_scan" in decision.details

    def test_secret_findings_in_details(self, gate: AegisGate, dirty_sandbox: Path):
        decision = gate.evaluate(
            sandbox_path=dirty_sandbox,
            credential="1234",
        )
        findings = decision.details.get("secret_scan", {}).get("findings", [])
        assert len(findings) >= 1


class TestRoleScopeBlock:
    """Test that out-of-scope actions block promotion."""

    def test_blocks_out_of_scope_action(self, gate: AegisGate, clean_sandbox: Path):
        decision = gate.evaluate(
            sandbox_path=clean_sandbox,
            actions_performed=["read_files", "docker_build"],
            credential="1234",
        )
        assert decision.approved is False
        assert "role_scope" in decision.checks_failed

    def test_blocks_aegis_action(self, gate: AegisGate, clean_sandbox: Path):
        decision = gate.evaluate(
            sandbox_path=clean_sandbox,
            actions_performed=["delete_repository"],
            credential="1234",
        )
        assert decision.approved is False
        assert "role_scope" in decision.checks_failed


class TestAuthBlock:
    """Test that bad auth blocks promotion."""

    def test_blocks_wrong_pin(self, gate: AegisGate, clean_sandbox: Path):
        decision = gate.evaluate(
            sandbox_path=clean_sandbox,
            actions_performed=["read_files"],
            credential="0000",
        )
        assert decision.approved is False
        assert "auth" in decision.checks_failed

    def test_blocks_missing_credential(self, gate: AegisGate, clean_sandbox: Path):
        decision = gate.evaluate(
            sandbox_path=clean_sandbox,
            actions_performed=["read_files"],
        )
        assert decision.approved is False
        assert "auth" in decision.checks_failed


class TestGateDecision:
    """Test GateDecision data class."""

    def test_summary_approved(self):
        d = GateDecision(approved=True, checks_passed=["a", "b"])
        assert "APPROVED" in d.summary

    def test_summary_blocked(self):
        d = GateDecision(approved=False, checks_failed=["auth"])
        assert "BLOCKED" in d.summary

    def test_to_dict(self):
        d = GateDecision(
            approved=True,
            checks_passed=["secret_scan", "auth"],
            details={"note": "test"},
        )
        data = d.to_dict()
        assert data["approved"] is True
        assert len(data["checks_passed"]) == 2
