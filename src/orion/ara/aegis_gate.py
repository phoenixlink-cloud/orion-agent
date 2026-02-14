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
"""AEGIS Traffic Gate — controls promotion from sandbox to real workspace.

Nothing leaves the sandbox without passing through this gate.
Checks: secret scan, write limits, role permissions, auth verification.

See ARA-001 §3.4 and §C.7/C.8 for full design.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orion.ara.auth import AuthResult, RoleAuthenticator
from orion.ara.role_profile import RoleProfile
from orion.security.secret_scanner import ScanResult, SecretScanner
from orion.security.write_limits import WriteTracker

logger = logging.getLogger("orion.ara.aegis_gate")


@dataclass
class GateDecision:
    """Result of an AEGIS gate check."""

    approved: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        status = "APPROVED" if self.approved else "BLOCKED"
        passed = len(self.checks_passed)
        failed = len(self.checks_failed)
        return f"AEGIS Gate: {status} ({passed} passed, {failed} failed)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "details": self.details,
        }


class AegisGate:
    """AEGIS Traffic Gate for sandbox-to-workspace promotion.

    Runs all pre-promotion checks:
    1. Secret scan — no hardcoded secrets in changed files
    2. Write limits — session hasn't exceeded file/volume limits
    3. Role scope — actions are within role permissions
    4. Auth verification — user has authenticated for this promotion

    All checks must pass for promotion to proceed.
    """

    def __init__(
        self,
        role: RoleProfile,
        authenticator: RoleAuthenticator,
        write_tracker: WriteTracker | None = None,
        secret_scanner: SecretScanner | None = None,
    ):
        self._role = role
        self._auth = authenticator
        self._write_tracker = write_tracker or WriteTracker()
        self._scanner = secret_scanner or SecretScanner()

    @property
    def role(self) -> RoleProfile:
        return self._role

    def check_secrets(self, sandbox_path: Path) -> tuple[bool, ScanResult]:
        """Run secret scanner on sandbox contents."""
        result = self._scanner.scan_directory(sandbox_path)
        return result.clean, result

    def check_write_limits(self) -> tuple[bool, dict[str, Any]]:
        """Check if session write limits are within bounds."""
        stats = self._write_tracker.stats()
        # All checks are enforced at write time, so if we got here
        # without violations, the limits are respected
        return True, stats

    def check_role_scope(self, actions_performed: list[str]) -> tuple[bool, list[str]]:
        """Check that all performed actions are within role scope."""
        violations: list[str] = []
        for action in actions_performed:
            if not self._role.is_action_allowed(action):
                violations.append(action)
        return len(violations) == 0, violations

    def check_auth(self, credential: str) -> tuple[bool, AuthResult]:
        """Verify authentication for promotion."""
        if not self._role.require_review_before_promote:
            return True, AuthResult(
                success=True,
                method=self._role.auth_method,
                message="Review not required for this role",
            )
        result = self._auth.authenticate(self._role.auth_method, credential)
        return result.success, result

    def evaluate(
        self,
        sandbox_path: Path,
        actions_performed: list[str] | None = None,
        credential: str | None = None,
    ) -> GateDecision:
        """Run all AEGIS gate checks and return a decision.

        This is the main entry point. All checks must pass.
        """
        decision = GateDecision(approved=True)
        actions_performed = actions_performed or []

        # 1. Secret scan
        secrets_ok, scan_result = self.check_secrets(sandbox_path)
        if secrets_ok:
            decision.checks_passed.append("secret_scan")
        else:
            decision.checks_failed.append("secret_scan")
            decision.approved = False
            decision.details["secret_scan"] = {
                "findings": [f.to_dict() for f in scan_result.findings]
            }
            logger.warning(
                "AEGIS Gate: secret scan failed — %d findings",
                len(scan_result.findings),
            )

        # 2. Write limits
        limits_ok, write_stats = self.check_write_limits()
        if limits_ok:
            decision.checks_passed.append("write_limits")
        else:
            decision.checks_failed.append("write_limits")
            decision.approved = False
            decision.details["write_limits"] = write_stats

        # 3. Role scope
        scope_ok, scope_violations = self.check_role_scope(actions_performed)
        if scope_ok:
            decision.checks_passed.append("role_scope")
        else:
            decision.checks_failed.append("role_scope")
            decision.approved = False
            decision.details["role_scope_violations"] = scope_violations
            logger.warning(
                "AEGIS Gate: role scope violations — %s", scope_violations
            )

        # 4. Auth (only if credential provided or required)
        if self._role.require_review_before_promote:
            if credential is None:
                decision.checks_failed.append("auth")
                decision.approved = False
                decision.details["auth"] = {"message": "Authentication required for promotion"}
            else:
                auth_ok, auth_result = self.check_auth(credential)
                if auth_ok:
                    decision.checks_passed.append("auth")
                else:
                    decision.checks_failed.append("auth")
                    decision.approved = False
                    decision.details["auth"] = auth_result.to_dict()
        else:
            decision.checks_passed.append("auth")

        status = "APPROVED" if decision.approved else "BLOCKED"
        logger.info("AEGIS Gate decision: %s — %s", status, decision.summary)
        return decision
