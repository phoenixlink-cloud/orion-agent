"""Tests for orion.core.llm.config -- Flexible model configuration."""

from unittest.mock import patch

from orion.core.llm.config import (
    PRESETS,
    ModelConfiguration,
    RoleConfig,
    apply_preset,
    load_model_config,
    save_model_config,
)


class TestRoleConfig:
    def test_default(self):
        rc = RoleConfig()
        assert rc.provider == "ollama"
        assert rc.model == "qwen2.5:14b"

    def test_custom(self):
        rc = RoleConfig(provider="openai", model="gpt-4o")
        assert rc.provider == "openai"
        assert rc.model == "gpt-4o"

    def test_validate_valid(self):
        rc = RoleConfig(provider="openai", model="gpt-4o")
        assert rc.validate() == []

    def test_validate_unknown_provider(self):
        rc = RoleConfig(provider="unknown_provider", model="x")
        errors = rc.validate()
        assert len(errors) == 1
        assert "Unknown provider" in errors[0]

    def test_validate_unknown_model_cloud(self):
        rc = RoleConfig(provider="openai", model="gpt-99-turbo")
        errors = rc.validate()
        assert len(errors) == 1
        assert "Unknown model" in errors[0]

    def test_validate_ollama_allows_custom_models(self):
        rc = RoleConfig(provider="ollama", model="my-custom-model:latest")
        assert rc.validate() == []


class TestModelConfiguration:
    def test_default_single_mode(self):
        cfg = ModelConfiguration()
        assert cfg.mode == "single"
        assert cfg.get_reviewer().provider == cfg.builder.provider

    def test_single_mode_reviewer_equals_builder(self):
        cfg = ModelConfiguration(
            mode="single",
            builder=RoleConfig(provider="openai", model="gpt-4o"),
            reviewer=RoleConfig(provider="anthropic", model="claude-sonnet-4-20250514"),
        )
        assert cfg.get_reviewer().provider == "openai"

    def test_dual_mode_separate_roles(self):
        cfg = ModelConfiguration(
            mode="dual",
            builder=RoleConfig(provider="openai", model="gpt-4o"),
            reviewer=RoleConfig(provider="anthropic", model="claude-sonnet-4-20250514"),
        )
        assert cfg.get_builder().provider == "openai"
        assert cfg.get_reviewer().provider == "anthropic"

    def test_validate_valid(self):
        cfg = PRESETS["cloud_dual"]
        assert cfg.validate() == []

    def test_validate_invalid_mode(self):
        cfg = ModelConfiguration(mode="triple")
        errors = cfg.validate()
        assert any("Invalid mode" in e for e in errors)

    def test_requires_api_key(self):
        cfg = ModelConfiguration()
        assert cfg.requires_api_key("openai") is True
        assert cfg.requires_api_key("anthropic") is True
        assert cfg.requires_api_key("ollama") is False

    def test_get_required_keys_local(self):
        cfg = PRESETS["local_free"]
        assert cfg.get_required_keys() == []

    def test_get_required_keys_cloud_dual(self):
        cfg = PRESETS["cloud_dual"]
        keys = cfg.get_required_keys()
        assert "openai" in keys
        assert "anthropic" in keys


class TestPresets:
    def test_all_presets_validate(self):
        for name, preset in PRESETS.items():
            errors = preset.validate()
            assert errors == [], f"Preset '{name}' has validation errors: {errors}"

    def test_apply_preset_valid(self, tmp_path):
        with patch("orion.core.llm.config.CONFIG_FILE", tmp_path / "model_config.json"):
            cfg = apply_preset("local_free")
            assert cfg is not None
            assert cfg.builder.provider == "ollama"

    def test_apply_preset_invalid(self):
        cfg = apply_preset("nonexistent_preset")
        assert cfg is None


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        config_path = tmp_path / "model_config.json"
        with patch("orion.core.llm.config.CONFIG_FILE", config_path):
            cfg = ModelConfiguration(
                mode="dual",
                builder=RoleConfig(provider="openai", model="gpt-4o"),
                reviewer=RoleConfig(provider="anthropic", model="claude-sonnet-4-20250514"),
            )
            assert save_model_config(cfg) is True
            loaded = load_model_config()
            assert loaded.mode == "dual"
            assert loaded.builder.provider == "openai"
            assert loaded.reviewer.provider == "anthropic"
