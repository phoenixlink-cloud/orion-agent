# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Phase 14: UserIsolation — multi-user OS-user scoping."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.ara.user_isolation import UserIsolation


@pytest.fixture
def iso(tmp_path: Path) -> UserIsolation:
    return UserIsolation(username="testuser", home_dir=tmp_path)


class TestUserIsolation:
    def test_username(self, iso: UserIsolation):
        assert iso.username == "testuser"

    def test_orion_dir(self, iso: UserIsolation, tmp_path: Path):
        assert iso.orion_dir == tmp_path / ".orion"

    def test_validate_session_inside(self, iso: UserIsolation, tmp_path: Path):
        orion = tmp_path / ".orion" / "sessions" / "abc"
        orion.mkdir(parents=True)
        assert iso.validate_session_access(orion) is True

    def test_validate_session_outside(self, iso: UserIsolation, tmp_path: Path):
        outside = tmp_path / "other" / "sessions"
        outside.mkdir(parents=True)
        assert iso.validate_session_access(outside) is False

    def test_validate_session_exact_orion(self, iso: UserIsolation, tmp_path: Path):
        orion = tmp_path / ".orion"
        orion.mkdir(parents=True)
        assert iso.validate_session_access(orion) is True

    def test_container_name(self, iso: UserIsolation):
        name = iso.get_container_name("session-12345678")
        assert name.startswith("orion-ara-testuser-")
        assert "session-1234" in name

    def test_container_name_spaces(self):
        iso = UserIsolation(username="John Doe", home_dir=Path("/tmp"))
        name = iso.get_container_name("abc")
        assert "john_doe" in name

    def test_branch_name(self, iso: UserIsolation):
        name = iso.get_branch_name("sess-abc123")
        assert name.startswith("orion-ara/testuser/")

    def test_path_inside_home(self, iso: UserIsolation, tmp_path: Path):
        inside = tmp_path / "projects" / "my-app"
        inside.mkdir(parents=True)
        assert iso.validate_path_not_outside_home(inside) is True

    def test_path_outside_home(self, iso: UserIsolation):
        outside = Path("/etc/passwd")
        assert iso.validate_path_not_outside_home(outside) is False

    def test_default_username(self):
        iso = UserIsolation()
        assert iso.username  # Should be non-empty
