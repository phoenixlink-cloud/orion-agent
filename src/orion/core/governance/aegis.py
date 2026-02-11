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
Orion Agent -- AEGIS Governance (v6.5.0)

AEGIS is a HARD GATE, not a feature system.

All functions must be:
- Pure
- Stateless
- Side-effect free

Required checks:
- Workspace confinement
- SAFE vs PRO mode
- Action scope validation
- Risk validation
- Command execution scope
- External access control (credential + API)

AEGIS must NOT:
- Drive flow
- Own tools
- Speak unless blocking
"""

from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
import os
import re
import logging

logger = logging.getLogger("orion.governance.aegis")


@dataclass
class Intent:
    """Classified user intent."""
    category: str
    requires_evidence: bool
    requires_action: bool
    confidence: float
    keywords: List[str]
    raw_input: str


@dataclass
class AegisResult:
    """Result of AEGIS governance check."""
    passed: bool
    violations: List[str]
    warnings: List[str]
    action_type: str  # "deliberation", "execution", or "external_access"
    requires_approval: bool = False  # True = MUST get human confirmation before proceeding
    approval_prompt: str = ""       # Human-readable description of what needs approval

    def __bool__(self):
        return self.passed


@dataclass
class ExternalAccessRequest:
    """Request to access an external platform via API."""
    platform_id: str          # e.g. "github", "slack"
    method: str               # HTTP method: GET, POST, PUT, DELETE, PATCH
    url: str                  # Target URL
    description: str = ""     # Human-readable description of the action
    is_read_only: bool = False  # Computed by classify_external_access()


def check_aegis_gate(
    intent: Intent,
    mode: str,
    workspace_path: Optional[str],
    action_type: str,
    proposed_actions: Optional[List[dict]] = None
) -> AegisResult:
    """
    Check AEGIS governance gate.

    This is a PURE FUNCTION with no side effects.

    Args:
        intent: Classified user intent
        mode: Current mode ("safe" or "pro")
        workspace_path: Current workspace path (may be None)
        action_type: "deliberation" or "execution"
        proposed_actions: List of proposed file actions (for execution check)

    Returns:
        AegisResult indicating pass/fail and any violations
    """
    violations = []
    warnings = []

    # ==========================================================================
    # INVARIANT 1: Workspace Confinement
    # ==========================================================================
    if intent.requires_evidence and not workspace_path:
        violations.append("AEGIS-1: No workspace set. File operations require a workspace.")

    if workspace_path and not Path(workspace_path).exists():
        violations.append(f"AEGIS-1: Workspace does not exist: {workspace_path}")

    # ==========================================================================
    # INVARIANT 2: Mode Enforcement
    # ==========================================================================
    if intent.requires_action and mode not in ["pro", "project"]:
        violations.append("AEGIS-2: File modifications require PRO or PROJECT mode. Use /mode pro or /mode project")

    # ==========================================================================
    # INVARIANT 3: Action Scope Validation
    # ==========================================================================
    if action_type == "execution" and proposed_actions:
        for action in proposed_actions:
            action_path = action.get("path", "")
            if action_path:
                if not _is_path_confined(action_path, workspace_path):
                    violations.append(f"AEGIS-3: Path escapes workspace: {action_path}")

            action_op = action.get("operation", "").upper()
            allowed_ops = {"CREATE", "OVERWRITE", "PATCH", "DELETE", "RUN", "VALIDATE"}
            if action_op and action_op not in allowed_ops:
                violations.append(f"AEGIS-3: Unknown operation: {action_op}")

    # ==========================================================================
    # INVARIANT 4: Risk Validation
    # ==========================================================================
    if action_type == "execution" and proposed_actions:
        for action in proposed_actions:
            action_op = action.get("operation", "").upper()
            action_path = action.get("path", "")

            if action_op == "DELETE":
                important_patterns = [
                    'main.py', 'app.py', 'index.js', 'package.json',
                    'requirements.txt', '.env', 'config.py'
                ]
                for pattern in important_patterns:
                    if pattern in action_path.lower():
                        warnings.append(f"AEGIS-4: Deleting important file: {action_path}")

            if action_op == "OVERWRITE":
                warnings.append(f"AEGIS-4: Overwriting file: {action_path}")

    # ==========================================================================
    # INVARIANT 5: Command Execution (PROJECT mode only)
    # ==========================================================================
    if proposed_actions:
        for action in proposed_actions:
            action_op = action.get("operation", "").upper()
            if action_op == "RUN":
                if mode != "project":
                    violations.append("AEGIS-5: Command execution requires PROJECT mode. Use /mode project")
                else:
                    command = action.get("command", "")
                    if command:
                        forbidden_ops = ['&&', '||', ';', '|', '>', '<', '`', '$(', '${']
                        for op in forbidden_ops:
                            if op in command:
                                violations.append(f"AEGIS-5: Forbidden shell operator in command: {op}")

    return AegisResult(
        passed=len(violations) == 0,
        violations=violations,
        warnings=warnings,
        action_type=action_type
    )


# =============================================================================
# INVARIANT 6: External Access Control (HARDCODED -- NOT CONFIGURABLE)
# =============================================================================
#
# This is the gate that prevents Orion from using stored credentials
# to make external API calls without human approval.
#
# Rules (IMMUTABLE):
#   - READ operations (GET) -> auto-approved, logged
#   - WRITE operations (POST, PUT, PATCH, DELETE) -> BLOCKED until human approves
#   - Credential reads -> always logged in audit trail
#   - No code path may bypass this gate
#
# This function is PURE -- it classifies and returns a result.
# Enforcement happens in PlatformService.
# =============================================================================

# HTTP methods that NEVER modify external state
_READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# HTTP methods that CAN modify external state -- REQUIRE human approval
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Write endpoints that are safe to auto-approve (search via POST, etc.)
_SAFE_WRITE_URLS = frozenset({
    "https://api.notion.com/v1/search",       # Notion search uses POST but is read-only
    "https://slack.com/api/conversations.list",  # Listing channels
    "https://slack.com/api/users.list",        # Listing users
})


def check_external_access(request: ExternalAccessRequest) -> AegisResult:
    """
    AEGIS Invariant 6: External Access Control.

    This is a PURE FUNCTION. It classifies an external API request
    and determines whether human approval is required.

    HARDCODED RULES (not configurable -- this is a security invariant):
      - GET/HEAD/OPTIONS -> auto-approved (read-only)
      - POST/PUT/PATCH/DELETE -> requires human approval (write/mutate)
      - Exceptions: known safe POST endpoints (e.g. search)

    Returns:
        AegisResult with requires_approval=True if human must confirm.
    """
    method = request.method.upper()
    violations = []
    warnings = []

    # Classify the request
    if method in _READ_ONLY_METHODS:
        request.is_read_only = True
        return AegisResult(
            passed=True,
            violations=[],
            warnings=[],
            action_type="external_access",
            requires_approval=False,
            approval_prompt="",
        )

    # Check if this is a known-safe write endpoint
    if request.url in _SAFE_WRITE_URLS:
        request.is_read_only = True
        return AegisResult(
            passed=True,
            violations=[],
            warnings=[f"AEGIS-6: POST to {request.url} auto-approved (known read-only)"],
            action_type="external_access",
            requires_approval=False,
            approval_prompt="",
        )

    # WRITE operation -- REQUIRES human approval
    platform_name = request.platform_id.title()
    action_desc = request.description or f"{method} {request.url}"

    return AegisResult(
        passed=True,  # Not a violation -- but requires approval
        violations=[],
        warnings=[f"AEGIS-6: Write operation on {platform_name} requires human approval"],
        action_type="external_access",
        requires_approval=True,
        approval_prompt=(
            f"Orion wants to perform a WRITE action on {platform_name}:\n"
            f"  Action: {action_desc}\n"
            f"  Method: {method}\n"
            f"  URL: {request.url}\n"
            f"\nApprove this action? (y/n)"
        ),
    )


def classify_credential_access(provider: str, caller: str) -> AegisResult:
    """
    AEGIS Invariant 6b: Credential Access Audit.

    Every credential read is logged. This function classifies the access
    and returns warnings if the access pattern is unusual.

    Args:
        provider: The credential being accessed (e.g. "openai", "github")
        caller: Who is requesting it (e.g. "fast_path", "platform_service")

    Returns:
        AegisResult -- always passes (reads are allowed) but logs the access.
    """
    logger.info(f"AEGIS-6: Credential access -- provider={provider}, caller={caller}")

    return AegisResult(
        passed=True,
        violations=[],
        warnings=[f"AEGIS-6: Credential read for '{provider}' by {caller}"],
        action_type="credential_access",
        requires_approval=False,
    )


# Windows reserved device names -- opening these as files has special OS
# behaviour regardless of directory, so they must always be blocked.
_WIN_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def _is_path_confined(path: str, workspace_path: str) -> bool:
    """
    Check if *path* is confined within *workspace_path*.

    Hardened against:
      1. Case-insensitive filesystems (Windows)
      2. String-prefix false positives  (/workspace vs /workspace-evil)
      3. Null-byte injection
      4. Windows reserved device names  (CON, NUL, AUX â€¦)
      5. NTFS Alternate Data Streams    (file.txt:hidden)
      6. Symlink / junction traversal   (resolved before comparison)
    """
    if not workspace_path or not path:
        return False

    # â”€â”€ 3. Null-byte injection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if "\x00" in path or "\x00" in workspace_path:
        return False

    # â”€â”€ 5. NTFS Alternate Data Streams â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if ":" in path.replace("\\", "/").split("/", 1)[-1]:
        # Allow drive letter colon (C:\â€¦) but reject ADS colons in
        # any path *component* after an optional drive prefix.
        return False

    # â”€â”€ 4. Windows reserved device names â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    for part in Path(path).parts:
        stem = part.split(".")[0].upper()
        if stem in _WIN_RESERVED_NAMES:
            return False

    try:
        # resolve() canonicalises case on Windows AND follows
        # symlinks/junctions, defeating traversal via link.
        workspace = Path(workspace_path).resolve()
        target = (workspace / path).resolve()

        # â”€â”€ 1 + 2. Use os.path.normcase (lowercases on Windows,
        #     no-op elsewhere) then Path.relative_to() which is immune
        #     to the /workspace vs /workspace-evil prefix bug.
        norm_workspace = Path(os.path.normcase(str(workspace)))
        norm_target = Path(os.path.normcase(str(target)))

        norm_target.relative_to(norm_workspace)
        return True

    except (ValueError, OSError, TypeError):
        return False


def validate_action_bundle(actions: List[dict], workspace_path: str) -> AegisResult:
    """Validate a bundle of actions before execution."""
    violations = []
    warnings = []

    if not actions:
        return AegisResult(
            passed=True, violations=[], warnings=["No actions to validate"],
            action_type="execution"
        )

    for i, action in enumerate(actions):
        op = action.get("operation", "UNKNOWN").upper()
        path = action.get("path", "")

        if not op or op == "UNKNOWN":
            violations.append(f"Action {i+1}: Missing operation")

        if not path:
            violations.append(f"Action {i+1}: Missing path")

        if path and not _is_path_confined(path, workspace_path):
            violations.append(f"Action {i+1}: Path escapes workspace: {path}")

        if op in {"CREATE", "OVERWRITE"} and not action.get("content"):
            violations.append(f"Action {i+1}: {op} requires content")

    return AegisResult(
        passed=len(violations) == 0,
        violations=violations,
        warnings=warnings,
        action_type="execution"
    )
