"""
Orion Agent — AEGIS Governance (v6.4.0)

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

AEGIS must NOT:
- Drive flow
- Own tools
- Speak unless blocking
"""

from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path


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
    action_type: str  # "deliberation" or "execution"

    def __bool__(self):
        return self.passed


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


def _is_path_confined(path: str, workspace_path: str) -> bool:
    """Check if a path is confined within the workspace."""
    if not workspace_path:
        return False

    try:
        workspace = Path(workspace_path).resolve()
        target = (workspace / path).resolve()
        return str(target).startswith(str(workspace))
    except Exception:
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
