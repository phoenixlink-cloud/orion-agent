"""Tests for orion.core.editing — safety, formats, validator."""

import os
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from orion.core.editing.formats import (
    EditFormat,
    ModelProfile,
    get_model_profile,
    select_edit_format,
    get_format_instructions,
    MODEL_PROFILES,
    DEFAULT_PROFILE,
)


# =========================================================================
# EDIT FORMAT SELECTOR
# =========================================================================

class TestEditFormat:
    def test_enum_values(self):
        assert EditFormat.WHOLE_FILE.value == "whole_file"
        assert EditFormat.SEARCH_REPLACE.value == "search_replace"
        assert EditFormat.UNIFIED_DIFF.value == "unified_diff"
        assert EditFormat.ARCHITECT.value == "architect"


class TestModelProfile:
    def test_default_profile(self):
        assert DEFAULT_PROFILE is not None
        assert DEFAULT_PROFILE.preferred_format in EditFormat

    def test_model_profiles_exist(self):
        assert len(MODEL_PROFILES) > 0

    def test_gpt4o_profile(self):
        profile = get_model_profile("gpt-4o")
        assert profile is not None
        assert isinstance(profile, ModelProfile)

    def test_unknown_model_returns_default(self):
        profile = get_model_profile("totally-unknown-model-xyz")
        assert profile == DEFAULT_PROFILE


class TestSelectEditFormat:
    def test_single_file_small(self):
        decision = select_edit_format("gpt-4o", file_size_lines=50, change_size="small")
        assert isinstance(decision.format, EditFormat)

    def test_single_file_medium(self):
        decision = select_edit_format("gpt-4o", file_size_lines=200, change_size="medium")
        assert isinstance(decision.format, EditFormat)

    def test_large_file_edit(self):
        decision = select_edit_format("gpt-4o", file_size_lines=5000, change_size="large")
        assert isinstance(decision.format, EditFormat)


class TestFormatInstructions:
    def test_whole_file_instructions(self):
        decision = select_edit_format("gpt-4o", file_size_lines=50, change_size="small")
        instructions = get_format_instructions(decision)
        assert len(instructions) > 0

    def test_format_instructions_for_model(self):
        from orion.core.editing.formats import get_format_instructions_for_model
        fmt, instructions = get_format_instructions_for_model("gpt-4o")
        assert isinstance(fmt, EditFormat)
        assert len(instructions) > 0

    def test_all_models_produce_instructions(self):
        from orion.core.editing.formats import get_format_instructions_for_model
        for model in ["gpt-4o", "claude-sonnet-4-20250514", "qwen2.5-coder:14b"]:
            fmt, instructions = get_format_instructions_for_model(model)
            assert len(instructions) > 0, f"No instructions for {model}"
