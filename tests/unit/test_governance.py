"""Tests for orion.core.governance.aegis -- AEGIS governance gate."""

import sys
from dataclasses import dataclass, field

import pytest

from orion.core.governance.aegis import (
    AegisResult,
    _is_path_confined,
    check_aegis_gate,
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
    # --- Original tests (still valid) ---
    def test_relative_inside(self, tmp_path):
        assert _is_path_confined("sub/file.py", str(tmp_path)) is True

    def test_relative_escape(self, tmp_path):
        assert _is_path_confined("../../etc/passwd", str(tmp_path)) is False

    def test_no_workspace(self):
        assert _is_path_confined("file.py", None) is False

    def test_absolute_inside(self, tmp_path):
        target = tmp_path / "sub" / "file.py"
        assert _is_path_confined(str(target), str(tmp_path)) is True

    # --- Bypass vector 1: Case-insensitive filesystem (Windows) ---
    @pytest.mark.skipif(sys.platform != "win32", reason="Case-insensitive paths are Windows-only")
    def test_case_mismatch_workspace(self, tmp_path):
        """Same directory, different casing -- must still be confined."""
        ws = str(tmp_path)
        target = tmp_path / "sub" / "file.py"
        # Flip case on the workspace path
        ws_upper = ws.upper()
        assert _is_path_confined(str(target), ws_upper) is True

    def test_case_mismatch_target(self, tmp_path):
        """Target with uppercase, workspace lowercase -- still confined."""
        target = str(tmp_path / "SUB" / "FILE.PY")
        assert _is_path_confined(target, str(tmp_path)) is True

    # --- Bypass vector 2: String-prefix false positive ---
    def test_prefix_collision_blocked(self, tmp_path):
        """/workspace-evil is NOT inside /workspace."""
        evil_dir = str(tmp_path) + "-evil"
        import os

        os.makedirs(evil_dir, exist_ok=True)
        evil_file = os.path.join(evil_dir, "steal.py")
        assert _is_path_confined(evil_file, str(tmp_path)) is False

    # --- Bypass vector 3: Null-byte injection ---
    def test_null_byte_in_path(self, tmp_path):
        assert _is_path_confined("file\x00../../etc/passwd", str(tmp_path)) is False

    def test_null_byte_in_workspace(self, tmp_path):
        assert _is_path_confined("file.py", str(tmp_path) + "\x00evil") is False

    # --- Bypass vector 4: Windows reserved device names ---
    def test_reserved_device_CON(self, tmp_path):
        assert _is_path_confined("CON", str(tmp_path)) is False

    def test_reserved_device_NUL(self, tmp_path):
        assert _is_path_confined("NUL", str(tmp_path)) is False

    def test_reserved_device_AUX(self, tmp_path):
        assert _is_path_confined("AUX", str(tmp_path)) is False

    def test_reserved_device_COM1(self, tmp_path):
        assert _is_path_confined("COM1", str(tmp_path)) is False

    def test_reserved_device_LPT1(self, tmp_path):
        assert _is_path_confined("LPT1", str(tmp_path)) is False

    def test_reserved_device_in_subpath(self, tmp_path):
        assert _is_path_confined("sub/CON/file.txt", str(tmp_path)) is False

    def test_reserved_device_with_extension(self, tmp_path):
        """CON.txt is still a reserved device on Windows."""
        assert _is_path_confined("CON.txt", str(tmp_path)) is False

    # --- Bypass vector 5: NTFS Alternate Data Streams ---
    def test_ads_colon_blocked(self, tmp_path):
        assert _is_path_confined("file.txt:hidden_stream", str(tmp_path)) is False

    def test_ads_in_subpath(self, tmp_path):
        assert _is_path_confined("sub/file.txt:$DATA", str(tmp_path)) is False

    # --- Bypass vector 6: Symlink traversal ---
    def test_symlink_escape(self, tmp_path):
        """Symlink inside workspace pointing outside must be blocked."""
        import os

        target_outside = tmp_path.parent / "outside_target"
        target_outside.mkdir(exist_ok=True)
        secret = target_outside / "secret.txt"
        secret.write_text("secret")

        link_path = tmp_path / "evil_link"
        try:
            os.symlink(str(target_outside), str(link_path))
        except OSError:
            pytest.skip("Symlink creation not supported (needs admin on Windows)")

        # The symlink resolves outside the workspace
        assert _is_path_confined("evil_link/secret.txt", str(tmp_path)) is False

    # --- Edge cases ---
    def test_empty_path(self, tmp_path):
        assert _is_path_confined("", str(tmp_path)) is False

    def test_empty_workspace(self):
        assert _is_path_confined("file.py", "") is False

    def test_dot_path(self, tmp_path):
        """'.' resolves to workspace root itself -- should be allowed."""
        assert _is_path_confined(".", str(tmp_path)) is True

    def test_deeply_nested(self, tmp_path):
        assert _is_path_confined("a/b/c/d/e/f/g.py", str(tmp_path)) is True

    @pytest.mark.skipif(sys.platform != "win32", reason="Backslash is not a path separator on Linux")
    def test_backslash_traversal(self, tmp_path):
        assert _is_path_confined("..\\..\\etc\\passwd", str(tmp_path)) is False


# =========================================================================
# check_aegis_gate -- INVARIANT 1: Workspace Confinement
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
# check_aegis_gate -- INVARIANT 2: Mode Enforcement
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
# check_aegis_gate -- INVARIANT 3: Action Scope
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
# check_aegis_gate -- INVARIANT 5: Command Execution
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
