"""Tests for orion.core.governance.aegis — AEGIS governance gate."""

import pytest
from dataclasses import dataclass, field
from orion.core.governance.aegis import (
    check_aegis_gate,
    AegisResult,
    _is_path_confined,
    validate_action_bundle,
)


@dataclass
class Intent:
    category: str = "analysis"
    requires_evidence: bool = False
    requires_action: bool = False
    confidence: float = 0.9
    keywords: list = field(default_factory=list)
    raw_input: str = "test"


def _make_intent(**kwargs):
    return Intent(**kwargs)


# =========================================================================
# AegisResult
# =========================================================================

class TestAegisResult:
    def test_passed_is_truthy(self):
        r = AegisResult(passed=True, violations=[], warnings=[], action_type="deliberation")
        assert bool(r) is True

    def test_failed_is_falsy(self):
        r = AegisResult(passed=False, violations=["v1"], warnings=[], action_type="deliberation")
        assert bool(r) is False


# =========================================================================
# _is_path_confined
# =========================================================================

class TestIsPathConfined:
    def test_relative_inside(self, tmp_path):
        assert _is_path_confined("sub/file.py", str(tmp_path)) is True

    def test_relative_escape(self, tmp_path):
        assert _is_path_confined("../../etc/passwd", str(tmp_path)) is False

    def test_no_workspace(self):
        assert _is_path_confined("file.py", None) is False

    def test_absolute_inside(self, tmp_path):
        target = tmp_path / "sub" / "file.py"
        assert _is_path_confined(str(target), str(tmp_path)) is True


# =========================================================================
# check_aegis_gate — INVARIANT 1: Workspace Confinement
# =========================================================================

class TestAegisInvariant1:
    def test_no_workspace_with_evidence_required(self):
        intent = _make_intent(requires_evidence=True)
        result = check_aegis_gate(intent, "safe", None, "deliberation")
        assert not result.passed
        assert any("AEGIS-1" in v for v in result.violations)

    def test_nonexistent_workspace(self, tmp_path):
        fake_path = str(tmp_path / "definitely_does_not_exist_xyz")
        intent = _make_intent(requires_evidence=True)
        result = check_aegis_gate(intent, "safe", fake_path, "deliberation")
        assert not result.passed
        assert any("AEGIS-1" in v for v in result.violations)

    def test_valid_workspace(self, tmp_path):
        intent = _make_intent(requires_evidence=True)
        result = check_aegis_gate(intent, "pro", str(tmp_path), "deliberation")
        assert result.passed


# =========================================================================
# check_aegis_gate — INVARIANT 2: Mode Enforcement
# =========================================================================

class TestAegisInvariant2:
    def test_action_in_safe_mode_blocked(self, tmp_path):
        intent = _make_intent(requires_action=True)
        result = check_aegis_gate(intent, "safe", str(tmp_path), "deliberation")
        assert not result.passed
        assert any("AEGIS-2" in v for v in result.violations)

    def test_action_in_pro_mode_allowed(self, tmp_path):
        intent = _make_intent(requires_action=True)
        result = check_aegis_gate(intent, "pro", str(tmp_path), "deliberation")
        assert result.passed

    def test_action_in_project_mode_allowed(self, tmp_path):
        intent = _make_intent(requires_action=True)
        result = check_aegis_gate(intent, "project", str(tmp_path), "deliberation")
        assert result.passed


# =========================================================================
# check_aegis_gate — INVARIANT 3: Action Scope
# =========================================================================

class TestAegisInvariant3:
    def test_path_escape_blocked(self, tmp_path):
        intent = _make_intent()
        actions = [{"operation": "CREATE", "path": "../../etc/passwd", "content": "x"}]
        result = check_aegis_gate(intent, "pro", str(tmp_path), "execution", actions)
        assert not result.passed
        assert any("AEGIS-3" in v for v in result.violations)

    def test_unknown_operation_blocked(self, tmp_path):
        intent = _make_intent()
        actions = [{"operation": "HACK", "path": "file.py"}]
        result = check_aegis_gate(intent, "pro", str(tmp_path), "execution", actions)
        assert not result.passed
        assert any("AEGIS-3" in v for v in result.violations)

    def test_valid_create_allowed(self, tmp_path):
        intent = _make_intent()
        actions = [{"operation": "CREATE", "path": "file.py", "content": "x"}]
        result = check_aegis_gate(intent, "pro", str(tmp_path), "execution", actions)
        assert result.passed


# =========================================================================
# check_aegis_gate — INVARIANT 5: Command Execution
# =========================================================================

class TestAegisInvariant5:
    def test_run_in_safe_mode_blocked(self, tmp_path):
        intent = _make_intent()
        actions = [{"operation": "RUN", "command": "dotnet build", "path": "."}]
        result = check_aegis_gate(intent, "safe", str(tmp_path), "execution", actions)
        assert not result.passed
        assert any("AEGIS-5" in v for v in result.violations)

    def test_run_in_pro_mode_blocked(self, tmp_path):
        intent = _make_intent()
        actions = [{"operation": "RUN", "command": "dotnet build", "path": "."}]
        result = check_aegis_gate(intent, "pro", str(tmp_path), "execution", actions)
        assert not result.passed
        assert any("AEGIS-5" in v for v in result.violations)

    def test_run_in_project_mode_allowed(self, tmp_path):
        intent = _make_intent()
        actions = [{"operation": "RUN", "command": "dotnet build", "path": "."}]
        result = check_aegis_gate(intent, "project", str(tmp_path), "execution", actions)
        assert result.passed

    def test_forbidden_shell_operator(self, tmp_path):
        intent = _make_intent()
        actions = [{"operation": "RUN", "command": "dotnet build && rm -rf /", "path": "."}]
        result = check_aegis_gate(intent, "project", str(tmp_path), "execution", actions)
        assert not result.passed
        assert any("AEGIS-5" in v and "&&" in v for v in result.violations)


# =========================================================================
# validate_action_bundle
# =========================================================================

class TestValidateActionBundle:
    def test_empty_actions(self, tmp_path):
        result = validate_action_bundle([], str(tmp_path))
        assert result.passed

    def test_valid_create(self, tmp_path):
        actions = [{"operation": "CREATE", "path": "file.py", "content": "x = 1"}]
        result = validate_action_bundle(actions, str(tmp_path))
        assert result.passed

    def test_missing_operation(self, tmp_path):
        actions = [{"path": "file.py", "content": "x"}]
        result = validate_action_bundle(actions, str(tmp_path))
        assert not result.passed

    def test_missing_path(self, tmp_path):
        actions = [{"operation": "CREATE", "content": "x"}]
        result = validate_action_bundle(actions, str(tmp_path))
        assert not result.passed

    def test_create_without_content(self, tmp_path):
        actions = [{"operation": "CREATE", "path": "file.py"}]
        result = validate_action_bundle(actions, str(tmp_path))
        assert not result.passed

    def test_path_escape(self, tmp_path):
        actions = [{"operation": "CREATE", "path": "../../etc/passwd", "content": "x"}]
        result = validate_action_bundle(actions, str(tmp_path))
        assert not result.passed

    def test_delete_no_content_ok(self, tmp_path):
        actions = [{"operation": "DELETE", "path": "file.py"}]
        result = validate_action_bundle(actions, str(tmp_path))
        assert result.passed
