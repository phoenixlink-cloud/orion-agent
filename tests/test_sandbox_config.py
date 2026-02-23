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
"""Tests for configurable resource profiles (Phase 4B.3).

Tests SC-01 through SC-08 validating profile resolution, user overrides,
validation, and Docker arg generation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orion.security.sandbox_config import (
    DEFAULT_PROFILES,
    ResourceProfile,
    get_profile,
    list_profiles,
    validate_cpus,
    validate_memory,
)


# ---------------------------------------------------------------------------
# SC-01: Default profiles
# ---------------------------------------------------------------------------


class TestDefaultProfiles:
    """SC-01: Built-in profiles return correct defaults."""

    def test_light(self):
        p = get_profile("light")
        assert p.name == "light"
        assert p.memory == "512m"
        assert p.cpus == "1"
        assert p.pids == 128

    def test_standard(self):
        p = get_profile("standard")
        assert p.name == "standard"
        assert p.memory == "2g"
        assert p.cpus == "2"
        assert p.pids == 256

    def test_heavy(self):
        p = get_profile("heavy")
        assert p.name == "heavy"
        assert p.memory == "4g"
        assert p.cpus == "4"
        assert p.pids == 512

    def test_unknown_falls_back_to_standard(self):
        p = get_profile("ultra")
        assert p.name == "standard"
        assert p.memory == "2g"


# ---------------------------------------------------------------------------
# SC-02: User overrides
# ---------------------------------------------------------------------------


class TestUserOverrides:
    """SC-02: User overrides from ARA settings merge with defaults."""

    def test_override_memory(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps({"execution": {"resource_profiles": {"standard": {"memory": "8g"}}}})
        )
        p = get_profile("standard", settings)
        assert p.memory == "8g"
        assert p.cpus == "2"  # Unchanged default
        assert p.pids == 256  # Unchanged default

    def test_override_all_fields(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps(
                {
                    "execution": {
                        "resource_profiles": {"light": {"memory": "1g", "cpus": "2", "pids": 200}}
                    }
                }
            )
        )
        p = get_profile("light", settings)
        assert p.memory == "1g"
        assert p.cpus == "2"
        assert p.pids == 200

    def test_invalid_override_ignored(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps(
                {
                    "execution": {
                        "resource_profiles": {
                            "standard": {
                                "memory": "invalid",
                                "cpus": "bad",
                                "pids": -5,
                            }
                        }
                    }
                }
            )
        )
        p = get_profile("standard", settings)
        assert p.memory == "2g"  # Defaults preserved
        assert p.cpus == "2"
        assert p.pids == 256

    def test_no_settings_file(self, tmp_path: Path):
        p = get_profile("standard", tmp_path / "nope.json")
        assert p.memory == "2g"

    def test_corrupt_json(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text("NOT JSON")
        p = get_profile("standard", settings)
        assert p.memory == "2g"


# ---------------------------------------------------------------------------
# SC-03: Docker args
# ---------------------------------------------------------------------------


class TestDockerArgs:
    """SC-03: ResourceProfile.to_docker_args() generates correct flags."""

    def test_standard_args(self):
        p = ResourceProfile(name="standard", memory="2g", cpus="2", pids=256)
        args = p.to_docker_args()
        assert "--memory=2g" in args
        assert "--cpus=2" in args
        assert "--pids-limit=256" in args

    def test_heavy_args(self):
        p = get_profile("heavy")
        args = p.to_docker_args()
        assert "--memory=4g" in args
        assert "--cpus=4" in args


# ---------------------------------------------------------------------------
# SC-04: list_profiles
# ---------------------------------------------------------------------------


class TestListProfiles:
    """SC-04: list_profiles returns all three profiles."""

    def test_returns_three(self):
        profiles = list_profiles()
        assert len(profiles) == 3
        names = [p.name for p in profiles]
        assert "light" in names
        assert "standard" in names
        assert "heavy" in names

    def test_with_overrides(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps({"execution": {"resource_profiles": {"heavy": {"memory": "16g"}}}})
        )
        profiles = list_profiles(settings)
        heavy = [p for p in profiles if p.name == "heavy"][0]
        assert heavy.memory == "16g"


# ---------------------------------------------------------------------------
# SC-05: Validation helpers
# ---------------------------------------------------------------------------


class TestValidation:
    """SC-05: validate_memory and validate_cpus."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("512m", True),
            ("2g", True),
            ("1024m", True),
            ("1g", True),
            ("", False),
            ("0m", False),
            ("-1g", False),
            ("abc", False),
            ("2", False),
            ("2t", False),
        ],
    )
    def test_validate_memory(self, value, expected):
        assert validate_memory(value) is expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("1", True),
            ("2", True),
            ("0.5", True),
            ("4", True),
            ("0", False),
            ("-1", False),
            ("abc", False),
        ],
    )
    def test_validate_cpus(self, value, expected):
        assert validate_cpus(value) is expected


# ---------------------------------------------------------------------------
# SC-06: Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """SC-06: ResourceProfile.to_dict() roundtrip."""

    def test_to_dict(self):
        p = ResourceProfile(name="light", memory="512m", cpus="1", pids=128)
        d = p.to_dict()
        assert d == {"name": "light", "memory": "512m", "cpus": "1", "pids": 128}

    def test_all_profiles_serializable(self):
        for p in list_profiles():
            d = p.to_dict()
            assert isinstance(d["name"], str)
            assert isinstance(d["pids"], int)


# ---------------------------------------------------------------------------
# SC-07: PID limits bounds
# ---------------------------------------------------------------------------


class TestPidBounds:
    """SC-07: PID override must be within 16-4096."""

    def test_too_low(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps({"execution": {"resource_profiles": {"standard": {"pids": 5}}}})
        )
        p = get_profile("standard", settings)
        assert p.pids == 256  # Default preserved

    def test_too_high(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps({"execution": {"resource_profiles": {"standard": {"pids": 10000}}}})
        )
        p = get_profile("standard", settings)
        assert p.pids == 256  # Default preserved

    def test_valid_boundary(self, tmp_path: Path):
        settings = tmp_path / "ara_settings.json"
        settings.write_text(
            json.dumps({"execution": {"resource_profiles": {"standard": {"pids": 4096}}}})
        )
        p = get_profile("standard", settings)
        assert p.pids == 4096
