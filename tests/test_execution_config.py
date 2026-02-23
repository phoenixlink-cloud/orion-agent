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
"""Tests for execution configuration (Phase 4A.5).

Tests EC-01 through EC-06+ validating settings loading, precedence,
and the convenience helpers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orion.ara.execution_config import (
    ExecutionSettings,
    is_command_execution_enabled,
    load_execution_settings,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".orion"
    d.mkdir()
    return d


@pytest.fixture
def global_settings(settings_dir: Path) -> Path:
    return settings_dir / "settings.json"


@pytest.fixture
def ara_settings(settings_dir: Path) -> Path:
    return settings_dir / "ara_settings.json"


# ---------------------------------------------------------------------------
# EC-01: Defaults when no config files exist
# ---------------------------------------------------------------------------


class TestDefaults:
    """EC-01: Default values when no config files exist."""

    def test_defaults_disabled(self, tmp_path: Path):
        result = load_execution_settings(
            settings_path=tmp_path / "nope.json",
            ara_settings_path=tmp_path / "nope2.json",
        )
        assert result.enabled is False
        assert result.resource_profile == "standard"
        assert result.max_feedback_retries == 3

    def test_convenience_disabled(self, tmp_path: Path):
        assert (
            is_command_execution_enabled(
                settings_path=tmp_path / "nope.json",
                ara_settings_path=tmp_path / "nope2.json",
            )
            is False
        )

    def test_dataclass_defaults(self):
        s = ExecutionSettings()
        assert s.enabled is False
        assert s.resource_profile == "standard"
        assert s.max_feedback_retries == 3


# ---------------------------------------------------------------------------
# EC-02: Global settings override defaults
# ---------------------------------------------------------------------------


class TestGlobalSettings:
    """EC-02: Global settings.json controls execution toggle."""

    def test_enabled_via_global(self, global_settings: Path, ara_settings: Path):
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": True,
                    "ara_resource_profile": "heavy",
                }
            )
        )
        result = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert result.enabled is True
        assert result.resource_profile == "heavy"

    def test_disabled_via_global(self, global_settings: Path, ara_settings: Path):
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": False,
                }
            )
        )
        result = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert result.enabled is False

    def test_invalid_profile_ignored(self, global_settings: Path, ara_settings: Path):
        global_settings.write_text(
            json.dumps(
                {
                    "ara_resource_profile": "gigantic",
                }
            )
        )
        result = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert result.resource_profile == "standard"


# ---------------------------------------------------------------------------
# EC-03: ARA settings override global settings
# ---------------------------------------------------------------------------


class TestARASettingsOverride:
    """EC-03: ARA-specific settings take precedence over global."""

    def test_ara_overrides_global(self, global_settings: Path, ara_settings: Path):
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": False,
                }
            )
        )
        ara_settings.write_text(
            json.dumps(
                {
                    "execution": {
                        "enable_command_execution": True,
                        "resource_profile": "light",
                        "max_feedback_retries": 5,
                    }
                }
            )
        )
        result = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert result.enabled is True
        assert result.resource_profile == "light"
        assert result.max_feedback_retries == 5

    def test_ara_disables_when_global_enables(self, global_settings: Path, ara_settings: Path):
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": True,
                }
            )
        )
        ara_settings.write_text(
            json.dumps(
                {
                    "execution": {
                        "enable_command_execution": False,
                    }
                }
            )
        )
        result = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert result.enabled is False


# ---------------------------------------------------------------------------
# EC-04: Convenience helper
# ---------------------------------------------------------------------------


class TestConvenienceHelper:
    """EC-04: is_command_execution_enabled() convenience wrapper."""

    def test_enabled(self, global_settings: Path, ara_settings: Path):
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": True,
                }
            )
        )
        assert (
            is_command_execution_enabled(
                settings_path=global_settings,
                ara_settings_path=ara_settings,
            )
            is True
        )

    def test_disabled(self, global_settings: Path, ara_settings: Path):
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": False,
                }
            )
        )
        assert (
            is_command_execution_enabled(
                settings_path=global_settings,
                ara_settings_path=ara_settings,
            )
            is False
        )


# ---------------------------------------------------------------------------
# EC-05: Corrupt/invalid config files
# ---------------------------------------------------------------------------


class TestCorruptConfig:
    """EC-05: Corrupt config files are handled gracefully."""

    def test_corrupt_global_settings(self, global_settings: Path, ara_settings: Path):
        global_settings.write_text("NOT VALID JSON {{{")
        result = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert result.enabled is False  # Falls back to default

    def test_corrupt_ara_settings(self, global_settings: Path, ara_settings: Path):
        global_settings.write_text(
            json.dumps(
                {
                    "ara_enable_command_execution": True,
                }
            )
        )
        ara_settings.write_text("INVALID")
        result = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert result.enabled is True  # Global still applies

    def test_execution_not_dict(self, global_settings: Path, ara_settings: Path):
        ara_settings.write_text(
            json.dumps(
                {
                    "execution": "not a dict",
                }
            )
        )
        result = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert result.enabled is False  # Ignores non-dict execution


# ---------------------------------------------------------------------------
# EC-06: Resource profiles
# ---------------------------------------------------------------------------


class TestResourceProfiles:
    """EC-06: Resource profile validation."""

    @pytest.mark.parametrize("profile", ["light", "standard", "heavy"])
    def test_valid_profiles(self, profile, global_settings: Path, ara_settings: Path):
        global_settings.write_text(
            json.dumps(
                {
                    "ara_resource_profile": profile,
                }
            )
        )
        result = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert result.resource_profile == profile

    def test_ara_profile_override(self, global_settings: Path, ara_settings: Path):
        global_settings.write_text(
            json.dumps(
                {
                    "ara_resource_profile": "heavy",
                }
            )
        )
        ara_settings.write_text(
            json.dumps(
                {
                    "execution": {"resource_profile": "light"},
                }
            )
        )
        result = load_execution_settings(
            settings_path=global_settings,
            ara_settings_path=ara_settings,
        )
        assert result.resource_profile == "light"
