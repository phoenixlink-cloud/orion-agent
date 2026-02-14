# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Phase 9: Role Schema Expansion + Management CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.ara import cli_commands
from orion.ara.cli_commands import (
    cmd_role_create,
    cmd_role_delete,
    cmd_role_example,
    cmd_role_list,
    cmd_role_show,
    cmd_role_validate,
)
from orion.ara.role_profile import (
    AEGIS_BLOCKED_ACTIONS,
    ConfidenceThresholds,
    RoleProfile,
    RoleValidationError,
    generate_example_yaml,
    load_role,
    save_role,
    validate_role_file,
)


@pytest.fixture
def roles_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "roles"
    d.mkdir()
    # Isolate from real starter templates so tests are predictable
    empty_starter = tmp_path / "no_starters"
    empty_starter.mkdir()
    monkeypatch.setattr(cli_commands, "STARTER_ROLES_DIR", empty_starter)
    return d


def _make_role(roles_dir: Path, name: str, **kwargs) -> Path:
    """Helper to create a role YAML file."""
    role = RoleProfile(name=name, scope="coding", **kwargs)
    path = roles_dir / f"{name}.yaml"
    save_role(role, path)
    return path


# ---------------------------------------------------------------------------
# ConfidenceThresholds
# ---------------------------------------------------------------------------


class TestConfidenceThresholds:
    def test_defaults(self):
        ct = ConfidenceThresholds()
        assert ct.auto_execute == 0.90
        assert ct.execute_and_flag == 0.70
        assert ct.pause_and_ask == 0.50

    def test_from_dict(self):
        ct = ConfidenceThresholds.from_dict({
            "auto_execute": 0.95,
            "execute_and_flag": 0.80,
            "pause_and_ask": 0.60,
        })
        assert ct.auto_execute == 0.95
        assert ct.execute_and_flag == 0.80

    def test_invalid_order_rejected(self):
        with pytest.raises(RoleValidationError):
            RoleProfile(
                name="bad-ct",
                scope="coding",
                confidence_thresholds=ConfidenceThresholds(
                    auto_execute=0.50,
                    execute_and_flag=0.90,
                    pause_and_ask=0.70,
                ),
            )


# ---------------------------------------------------------------------------
# Expanded RoleProfile schema
# ---------------------------------------------------------------------------


class TestExpandedSchema:
    def test_3tier_authority(self):
        role = RoleProfile(
            name="3tier",
            scope="coding",
            authority_autonomous=["read_files", "write_files"],
            authority_requires_approval=["merge_to_main"],
            authority_forbidden=["deploy_to_production"],
        )
        assert role.get_action_tier("read_files") == "autonomous"
        assert role.get_action_tier("merge_to_main") == "requires_approval"
        assert role.get_action_tier("deploy_to_production") == "forbidden"
        assert role.get_action_tier("unknown_action") == "unknown"

    def test_aegis_actions_always_forbidden(self):
        role = RoleProfile(
            name="aegis-test",
            scope="coding",
            authority_autonomous=["delete_repository"],  # AEGIS should strip this
        )
        assert role.get_action_tier("delete_repository") == "forbidden"
        assert "delete_repository" not in role.authority_autonomous
        assert "delete_repository" in role.authority_forbidden

    def test_competencies(self):
        role = RoleProfile(
            name="comp-test",
            scope="coding",
            competencies=["Code quality", "Testing", "Git"],
        )
        assert len(role.competencies) == 3

    def test_risk_tolerance_valid(self):
        for rt in ("low", "medium", "high"):
            role = RoleProfile(name=f"rt-{rt}", scope="coding", risk_tolerance=rt)
            assert role.risk_tolerance == rt

    def test_risk_tolerance_invalid(self):
        with pytest.raises(RoleValidationError):
            RoleProfile(name="bad-rt", scope="coding", risk_tolerance="extreme")

    def test_success_criteria(self):
        role = RoleProfile(
            name="sc-test",
            scope="coding",
            success_criteria=["All tests pass", "Coverage > 80%"],
        )
        assert len(role.success_criteria) == 2

    def test_backward_compat_allowed_to_autonomous(self):
        role = RoleProfile(
            name="compat",
            scope="coding",
            allowed_actions=["read_files", "write_files"],
        )
        assert "read_files" in role.authority_autonomous
        assert "write_files" in role.authority_autonomous

    def test_to_dict_includes_new_fields(self):
        role = RoleProfile(
            name="dict-test",
            scope="coding",
            competencies=["Testing"],
            authority_autonomous=["read_files"],
            authority_requires_approval=["merge"],
            risk_tolerance="low",
            success_criteria=["Pass"],
        )
        d = role.to_dict()
        assert d["competencies"] == ["Testing"]
        assert d["authority_autonomous"] == ["read_files"]
        assert d["authority_requires_approval"] == ["merge"]
        assert d["risk_tolerance"] == "low"
        assert d["success_criteria"] == ["Pass"]
        assert "confidence_thresholds" in d

    def test_roundtrip_yaml(self, tmp_path: Path):
        role = RoleProfile(
            name="roundtrip",
            scope="devops",
            auth_method="totp",
            competencies=["Docker", "CI/CD"],
            authority_autonomous=["read_files"],
            authority_requires_approval=["deploy"],
            confidence_thresholds=ConfidenceThresholds(0.95, 0.80, 0.60),
            risk_tolerance="low",
            success_criteria=["Pipeline green"],
        )
        path = tmp_path / "roundtrip.yaml"
        save_role(role, path)
        loaded = load_role(path)
        assert loaded.name == "roundtrip"
        assert loaded.competencies == ["Docker", "CI/CD"]
        assert loaded.confidence_thresholds.auto_execute == 0.95
        assert loaded.risk_tolerance == "low"
        assert loaded.success_criteria == ["Pipeline green"]


# ---------------------------------------------------------------------------
# Role management CLI commands
# ---------------------------------------------------------------------------


class TestCmdRoleList:
    def test_list_empty(self, roles_dir: Path):
        result = cmd_role_list(roles_dir=roles_dir)
        assert result.success is True
        assert result.data["roles"] == []

    def test_list_with_roles(self, roles_dir: Path):
        _make_role(roles_dir, "alpha", description="First role")
        _make_role(roles_dir, "beta", description="Second role")
        result = cmd_role_list(roles_dir=roles_dir)
        assert result.success is True
        assert len(result.data["roles"]) == 2
        names = [r["name"] for r in result.data["roles"]]
        assert "alpha" in names
        assert "beta" in names

    def test_list_shows_source(self, roles_dir: Path):
        _make_role(roles_dir, "user-role")
        result = cmd_role_list(roles_dir=roles_dir)
        assert result.data["roles"][0]["source"] == "user"

    def test_list_includes_starters(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """When starter dir has roles, they appear with source='starter'."""
        user_dir = tmp_path / "user_roles"
        user_dir.mkdir()
        starter_dir = tmp_path / "starter_roles"
        starter_dir.mkdir()
        _make_role(starter_dir, "starter-role")
        monkeypatch.setattr(cli_commands, "STARTER_ROLES_DIR", starter_dir)
        result = cmd_role_list(roles_dir=user_dir)
        assert any(r["source"] == "starter" for r in result.data["roles"])


class TestCmdRoleShow:
    def test_show_existing(self, roles_dir: Path):
        _make_role(
            roles_dir, "show-test",
            description="Test role",
            competencies=["Coding"],
            authority_autonomous=["read_files"],
        )
        result = cmd_role_show("show-test", roles_dir=roles_dir)
        assert result.success is True
        assert "show-test" in result.message
        assert "Coding" in result.message

    def test_show_nonexistent(self, roles_dir: Path):
        result = cmd_role_show("nonexistent", roles_dir=roles_dir)
        assert result.success is False


class TestCmdRoleCreate:
    def test_create_basic(self, roles_dir: Path):
        result = cmd_role_create("new-role", scope="coding", roles_dir=roles_dir)
        assert result.success is True
        assert (roles_dir / "new-role.yaml").exists()

    def test_create_with_options(self, roles_dir: Path):
        result = cmd_role_create(
            "advanced",
            scope="devops",
            auth_method="totp",
            description="Advanced role",
            roles_dir=roles_dir,
            competencies=["Docker"],
            risk_tolerance="low",
        )
        assert result.success is True
        loaded = load_role(roles_dir / "advanced.yaml")
        assert loaded.scope == "devops"
        assert loaded.auth_method == "totp"
        assert loaded.competencies == ["Docker"]

    def test_create_duplicate_rejected(self, roles_dir: Path):
        _make_role(roles_dir, "existing")
        result = cmd_role_create("existing", roles_dir=roles_dir)
        assert result.success is False
        assert "already exists" in result.message

    def test_create_invalid_rejected(self, roles_dir: Path):
        result = cmd_role_create("bad", scope="invalid_scope", roles_dir=roles_dir)
        assert result.success is False


class TestCmdRoleDelete:
    def test_delete_user_role(self, roles_dir: Path):
        _make_role(roles_dir, "deleteme")
        assert (roles_dir / "deleteme.yaml").exists()
        result = cmd_role_delete("deleteme", roles_dir=roles_dir)
        assert result.success is True
        assert not (roles_dir / "deleteme.yaml").exists()

    def test_delete_nonexistent(self, roles_dir: Path):
        result = cmd_role_delete("nope", roles_dir=roles_dir)
        assert result.success is False


class TestCmdRoleExample:
    def test_returns_yaml(self):
        result = cmd_role_example()
        assert result.success is True
        assert "name:" in result.message
        assert "scope:" in result.message
        assert "authority_autonomous:" in result.message
        assert "confidence_thresholds:" in result.message
        assert "competencies:" in result.message


class TestCmdRoleValidate:
    def test_validate_good_file(self, roles_dir: Path):
        path = _make_role(roles_dir, "valid-role")
        result = cmd_role_validate(str(path))
        assert result.success is True

    def test_validate_bad_file(self, tmp_path: Path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("name: ''\nscope: invalid\nauth_method: none\n")
        result = cmd_role_validate(str(bad))
        assert result.success is False
        assert len(result.data["errors"]) > 0

    def test_validate_missing_file(self):
        result = cmd_role_validate("/nonexistent/file.yaml")
        assert result.success is False


class TestGenerateExampleYaml:
    def test_contains_all_fields(self):
        yaml_str = generate_example_yaml()
        assert "name:" in yaml_str
        assert "scope:" in yaml_str
        assert "auth_method:" in yaml_str
        assert "competencies:" in yaml_str
        assert "authority_autonomous:" in yaml_str
        assert "authority_requires_approval:" in yaml_str
        assert "authority_forbidden:" in yaml_str
        assert "confidence_thresholds:" in yaml_str
        assert "risk_tolerance:" in yaml_str
        assert "success_criteria:" in yaml_str
        assert "working_hours:" in yaml_str
        assert "write_limits:" in yaml_str
        assert "notifications:" in yaml_str


class TestValidateRoleFile:
    def test_valid_file(self, roles_dir: Path):
        path = _make_role(roles_dir, "file-valid")
        valid, errors = validate_role_file(path)
        assert valid is True
        assert errors == []

    def test_invalid_file(self, tmp_path: Path):
        bad = tmp_path / "invalid.yaml"
        bad.write_text("not_a_mapping: true\n")
        valid, errors = validate_role_file(bad)
        assert valid is False

    def test_empty_file(self, tmp_path: Path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        valid, errors = validate_role_file(empty)
        assert valid is False
