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
"""Tests for ARA Role Profile (ARA-001 §4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.ara.role_profile import (
    AEGIS_BLOCKED_ACTIONS,
    RoleProfile,
    RoleValidationError,
    WorkingHours,
    load_all_roles,
    load_role,
    save_role,
)


@pytest.fixture
def minimal_role() -> RoleProfile:
    return RoleProfile(name="test-role", scope="coding")


@pytest.fixture
def full_role() -> RoleProfile:
    return RoleProfile(
        name="full-test",
        scope="full",
        auth_method="totp",
        description="A fully configured test role",
        allowed_actions=["read_files", "write_files", "run_tests"],
        max_session_hours=4.0,
        max_cost_per_session=2.0,
        tags=["test"],
    )


class TestRoleCreation:
    """Test basic role creation and defaults."""

    def test_minimal_role(self, minimal_role: RoleProfile):
        assert minimal_role.name == "test-role"
        assert minimal_role.scope == "coding"
        assert minimal_role.auth_method == "pin"
        assert minimal_role.max_session_hours == 8.0
        assert minimal_role.require_review_before_promote is True

    def test_full_role(self, full_role: RoleProfile):
        assert full_role.auth_method == "totp"
        assert full_role.max_session_hours == 4.0
        assert len(full_role.allowed_actions) == 3

    def test_from_dict(self):
        data = {
            "name": "dict-role",
            "scope": "research",
            "auth_method": "pin",
            "max_session_hours": 6,
        }
        role = RoleProfile.from_dict(data)
        assert role.name == "dict-role"
        assert role.scope == "research"
        assert role.max_session_hours == 6

    def test_to_dict_roundtrip(self, full_role: RoleProfile):
        data = full_role.to_dict()
        restored = RoleProfile.from_dict(data)
        assert restored.name == full_role.name
        assert restored.scope == full_role.scope
        assert restored.auth_method == full_role.auth_method
        assert restored.max_session_hours == full_role.max_session_hours


class TestValidation:
    """Test role validation rules."""

    def test_rejects_empty_name(self):
        with pytest.raises(RoleValidationError):
            RoleProfile(name="", scope="coding")

    def test_rejects_invalid_scope(self):
        with pytest.raises(RoleValidationError):
            RoleProfile(name="test", scope="hacking")

    def test_rejects_invalid_auth_method(self):
        with pytest.raises(RoleValidationError):
            RoleProfile(name="test", scope="coding", auth_method="password")

    def test_rejects_invalid_session_hours(self):
        with pytest.raises(RoleValidationError):
            RoleProfile(name="test", scope="coding", max_session_hours=0)
        with pytest.raises(RoleValidationError):
            RoleProfile(name="test", scope="coding", max_session_hours=25)

    def test_rejects_negative_cost(self):
        with pytest.raises(RoleValidationError):
            RoleProfile(name="test", scope="coding", max_cost_per_session=-1)

    def test_validation_error_has_details(self):
        with pytest.raises(RoleValidationError) as exc_info:
            RoleProfile(name="", scope="invalid")
        err = exc_info.value
        assert len(err.errors) >= 2
        assert err.role_name == ""


class TestAEGISEnforcement:
    """Test that AEGIS constraints are always enforced."""

    def test_strips_blocked_actions(self):
        role = RoleProfile(
            name="test",
            scope="coding",
            allowed_actions=["read_files", "delete_repository", "write_files"],
        )
        assert "delete_repository" not in role.allowed_actions
        assert "read_files" in role.allowed_actions

    def test_blocked_actions_always_present(self, minimal_role: RoleProfile):
        for action in AEGIS_BLOCKED_ACTIONS:
            assert action in minimal_role.blocked_actions

    def test_is_action_allowed(self, minimal_role: RoleProfile):
        # AEGIS blocked actions always denied
        assert minimal_role.is_action_allowed("delete_repository") is False
        assert minimal_role.is_action_allowed("force_push") is False
        # Other actions allowed when no allowlist
        assert minimal_role.is_action_allowed("read_files") is True

    def test_is_action_allowed_with_allowlist(self, full_role: RoleProfile):
        assert full_role.is_action_allowed("read_files") is True
        assert full_role.is_action_allowed("run_tests") is True
        # Not in allowlist
        assert full_role.is_action_allowed("docker_build") is False


class TestWorkingHours:
    """Test working hours configuration."""

    def test_default_disabled(self):
        wh = WorkingHours()
        assert wh.enabled is False

    def test_from_dict(self):
        wh = WorkingHours.from_dict(
            {
                "enabled": True,
                "start_hour": 20,
                "end_hour": 8,
                "timezone": "US/Eastern",
            }
        )
        assert wh.enabled is True
        assert wh.start_hour == 20
        assert wh.timezone == "US/Eastern"


class TestYAMLPersistence:
    """Test YAML load/save."""

    def test_save_and_load(self, full_role: RoleProfile, tmp_path: Path):
        path = tmp_path / "test-role.yaml"
        save_role(full_role, path)
        assert path.exists()

        loaded = load_role(path)
        assert loaded.name == full_role.name
        assert loaded.scope == full_role.scope
        assert loaded.auth_method == full_role.auth_method

    def test_load_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_role(tmp_path / "missing.yaml")

    def test_load_all_roles(self, tmp_path: Path):
        for i in range(3):
            role = RoleProfile(name=f"role-{i}", scope="coding")
            save_role(role, tmp_path / f"role-{i}.yaml")

        roles = load_all_roles(tmp_path)
        assert len(roles) == 3
        assert "role-0" in roles
        assert "role-2" in roles

    def test_load_all_empty_dir(self, tmp_path: Path):
        roles = load_all_roles(tmp_path)
        assert len(roles) == 0


class TestStarterTemplates:
    """Test that all starter role templates load and validate."""

    TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "data" / "roles"

    def test_all_templates_exist(self):
        assert self.TEMPLATES_DIR.exists()
        templates = list(self.TEMPLATES_DIR.glob("*.yaml"))
        assert len(templates) >= 4

    def test_all_templates_valid(self):
        for path in self.TEMPLATES_DIR.glob("*.yaml"):
            role = load_role(path)
            assert role.name
            assert role.scope
            assert role.auth_method in ("pin", "totp")

    def test_night_coder_template(self):
        role = load_role(self.TEMPLATES_DIR / "night-coder.yaml")
        assert role.name == "night-coder"
        assert role.scope == "coding"
        assert role.working_hours.enabled is True

    def test_researcher_template(self):
        role = load_role(self.TEMPLATES_DIR / "researcher.yaml")
        assert role.name == "researcher"
        assert role.scope == "research"

    def test_devops_runner_template(self):
        role = load_role(self.TEMPLATES_DIR / "devops-runner.yaml")
        assert role.name == "devops-runner"
        assert role.scope == "devops"
        assert role.auth_method == "totp"

    def test_full_auto_template(self):
        role = load_role(self.TEMPLATES_DIR / "full-auto.yaml")
        assert role.name == "full-auto"
        assert role.scope == "full"
        assert role.auth_method == "totp"
