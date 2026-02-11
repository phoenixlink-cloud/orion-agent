# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
#    You may use, modify, and distribute this file under AGPL-3.0.
#    See LICENSE for the full text.
#
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#    For proprietary use, SaaS deployment, or enterprise licensing.
#    See LICENSE-ENTERPRISE.md or contact info@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- Flexible Model Configuration (v7.4.0)

Users choose 1 or 2 AI models for Builder and Reviewer roles.
Governor is ALWAYS Orion's internal logic -- never user-configurable.

Modes:
  - single: One model for both Builder and Reviewer
  - dual:   Different models for Builder and Reviewer

Each role can use any supported provider:
  - openai, anthropic, ollama, google, cohere, aws_bedrock,
    azure_openai, together, mistral, openrouter, groq
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict


# =============================================================================
# SUPPORTED PROVIDERS
# =============================================================================

PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "auth": "api_key",
        "models": [
            {"id": "gpt-5.2", "label": "GPT-5.2 (Latest Flagship)", "tier": "heavy", "context": 400000},
            {"id": "gpt-5.2-pro", "label": "GPT-5.2 Pro", "tier": "heavy", "context": 400000},
            {"id": "gpt-5.2-codex", "label": "GPT-5.2 Codex (Coding)", "tier": "heavy", "context": 400000},
            {"id": "gpt-5.1", "label": "GPT-5.1", "tier": "heavy", "context": 128000},
            {"id": "gpt-5.1-codex", "label": "GPT-5.1 Codex (Coding)", "tier": "heavy", "context": 400000},
            {"id": "gpt-5.1-codex-mini", "label": "GPT-5.1 Codex Mini", "tier": "light", "context": 400000},
            {"id": "gpt-5", "label": "GPT-5", "tier": "heavy", "context": 400000},
            {"id": "gpt-5-mini", "label": "GPT-5 Mini", "tier": "light", "context": 400000},
            {"id": "gpt-5-nano", "label": "GPT-5 Nano", "tier": "light", "context": 400000},
            {"id": "gpt-4.1", "label": "GPT-4.1", "tier": "heavy", "context": 1000000},
            {"id": "gpt-4.1-mini", "label": "GPT-4.1 Mini", "tier": "light", "context": 1000000},
            {"id": "gpt-4.1-nano", "label": "GPT-4.1 Nano", "tier": "light", "context": 1000000},
            {"id": "o3", "label": "o3 (Deep Reasoning)", "tier": "heavy", "context": 200000},
            {"id": "o3-pro", "label": "o3-pro (Max Reasoning)", "tier": "heavy", "context": 200000},
            {"id": "o4-mini", "label": "o4-mini (Fast Reasoning)", "tier": "light", "context": 200000},
            {"id": "o3-mini", "label": "o3-mini (Budget Reasoning)", "tier": "light", "context": 200000},
            {"id": "o1", "label": "o1 (Reasoning)", "tier": "heavy", "context": 200000},
            {"id": "gpt-4o", "label": "GPT-4o", "tier": "heavy", "context": 128000},
            {"id": "gpt-4o-mini", "label": "GPT-4o Mini", "tier": "light", "context": 128000},
            {"id": "gpt-4-turbo", "label": "GPT-4 Turbo", "tier": "heavy", "context": 128000},
        ],
        "default_light": "gpt-4o-mini",
        "default_heavy": "gpt-4o",
        "cost": "paid",
    },
    "anthropic": {
        "name": "Anthropic",
        "auth": "api_key",
        "models": [
            {"id": "claude-opus-4-5-20251101", "label": "Claude Opus 4.5 (Flagship)", "tier": "heavy", "context": 200000},
            {"id": "claude-sonnet-4-5-20250929", "label": "Claude Sonnet 4.5", "tier": "heavy", "context": 200000},
            {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5", "tier": "light", "context": 200000},
            {"id": "claude-opus-4-1-20250805", "label": "Claude Opus 4.1", "tier": "heavy", "context": 200000},
            {"id": "claude-opus-4-20250514", "label": "Claude Opus 4", "tier": "heavy", "context": 200000},
            {"id": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4", "tier": "heavy", "context": 200000},
            {"id": "claude-3-7-sonnet-20250219", "label": "Claude 3.7 Sonnet", "tier": "heavy", "context": 200000},
            {"id": "claude-3-5-sonnet-20241022", "label": "Claude 3.5 Sonnet", "tier": "heavy", "context": 200000},
            {"id": "claude-3-5-haiku-20241022", "label": "Claude 3.5 Haiku", "tier": "light", "context": 200000},
            {"id": "claude-3-opus-20240229", "label": "Claude 3 Opus", "tier": "heavy", "context": 200000},
        ],
        "default_light": "claude-haiku-4-5-20251001",
        "default_heavy": "claude-sonnet-4-20250514",
        "cost": "paid",
    },
    "ollama": {
        "name": "Ollama (Local)",
        "auth": "none",
        "models": [
            {"id": "qwen3:32b", "label": "Qwen 3 32B", "tier": "heavy", "context": 131072},
            {"id": "qwen2.5:14b", "label": "Qwen 2.5 14B", "tier": "heavy", "context": 32768},
            {"id": "qwen2.5-coder:14b", "label": "Qwen 2.5 Coder 14B", "tier": "heavy", "context": 32768},
            {"id": "deepseek-coder-v2:16b", "label": "DeepSeek Coder V2 16B", "tier": "heavy", "context": 128000},
            {"id": "llama3.3:70b", "label": "Llama 3.3 70B", "tier": "heavy", "context": 131072},
            {"id": "codellama:13b", "label": "Code Llama 13B", "tier": "heavy", "context": 16384},
            {"id": "qwen3:8b", "label": "Qwen 3 8B", "tier": "light", "context": 131072},
            {"id": "qwen2.5:7b", "label": "Qwen 2.5 7B", "tier": "light", "context": 32768},
            {"id": "qwen2.5-coder:7b", "label": "Qwen 2.5 Coder 7B", "tier": "light", "context": 32768},
            {"id": "llama3.1:8b", "label": "Llama 3.1 8B", "tier": "light", "context": 131072},
            {"id": "mistral:7b", "label": "Mistral 7B", "tier": "light", "context": 32768},
            {"id": "deepseek-coder:6.7b", "label": "DeepSeek Coder 6.7B", "tier": "light", "context": 16384},
            {"id": "phi3:3.8b", "label": "Phi-3 3.8B", "tier": "light", "context": 128000},
        ],
        "default_light": "qwen2.5:7b",
        "default_heavy": "qwen2.5:14b",
        "cost": "free",
    },
    "google": {
        "name": "Google Gemini",
        "auth": "api_key",
        "models": [
            {"id": "gemini-3-pro-preview", "label": "Gemini 3 Pro (Latest)", "tier": "heavy", "context": 1048576},
            {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash", "tier": "light", "context": 1048576},
            {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "tier": "heavy", "context": 1048576},
            {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "tier": "light", "context": 1048576},
            {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash-Lite", "tier": "light", "context": 1048576},
            {"id": "gemini-2.0-flash", "label": "Gemini 2.0 Flash", "tier": "light", "context": 1048576},
            {"id": "gemini-1.5-pro", "label": "Gemini 1.5 Pro", "tier": "heavy", "context": 2097152},
            {"id": "gemini-1.5-flash", "label": "Gemini 1.5 Flash", "tier": "light", "context": 1048576},
        ],
        "default_light": "gemini-2.5-flash",
        "default_heavy": "gemini-2.5-pro",
        "cost": "free_tier",
    },
    "groq": {
        "name": "Groq",
        "auth": "api_key",
        "models": [
            {"id": "openai/gpt-oss-120b", "label": "GPT-OSS 120B (Flagship)", "tier": "heavy", "context": 131072},
            {"id": "openai/gpt-oss-20b", "label": "GPT-OSS 20B", "tier": "light", "context": 131072},
            {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B", "tier": "heavy", "context": 131072},
            {"id": "llama-3.1-8b-instant", "label": "Llama 3.1 8B Instant", "tier": "light", "context": 131072},
        ],
        "default_light": "llama-3.1-8b-instant",
        "default_heavy": "openai/gpt-oss-120b",
        "cost": "free_tier",
    },
}


# =============================================================================
# PROVIDER ENABLE / DISABLE
# =============================================================================

PROVIDER_SETTINGS_FILE = Path.home() / ".orion" / "provider_settings.json"


def _load_provider_settings() -> Dict[str, Any]:
    if PROVIDER_SETTINGS_FILE.exists():
        try:
            with open(PROVIDER_SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_provider_settings(settings: Dict[str, Any]):
    PROVIDER_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROVIDER_SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def is_provider_enabled(provider: str) -> bool:
    if provider not in PROVIDERS:
        return False
    settings = _load_provider_settings()
    return settings.get("disabled", {}).get(provider, False) is False


def set_provider_enabled(provider: str, enabled: bool) -> bool:
    if provider not in PROVIDERS:
        return False
    settings = _load_provider_settings()
    if "disabled" not in settings:
        settings["disabled"] = {}
    if enabled:
        settings["disabled"].pop(provider, None)
    else:
        settings["disabled"][provider] = True
    _save_provider_settings(settings)
    return True


def get_enabled_providers() -> Dict[str, Any]:
    return {k: v for k, v in PROVIDERS.items() if is_provider_enabled(k)}


def get_all_provider_status() -> Dict[str, bool]:
    return {k: is_provider_enabled(k) for k in PROVIDERS}


def get_model_ids(provider: str) -> list:
    p = PROVIDERS.get(provider, {})
    return [m["id"] for m in p.get("models", [])]


def get_models_by_tier(provider: str, tier: str) -> list:
    p = PROVIDERS.get(provider, {})
    return [m for m in p.get("models", []) if m["tier"] == tier]


# =============================================================================
# MODEL ROLE ASSIGNMENT
# =============================================================================

@dataclass
class RoleConfig:
    """Configuration for a single role (Builder or Reviewer)."""
    provider: str = "ollama"
    model: str = "qwen2.5:14b"
    light_model: str = ""
    use_tiers: bool = False

    def validate(self) -> List[str]:
        errors = []
        if self.provider not in PROVIDERS:
            errors.append(f"Unknown provider: {self.provider}. Supported: {list(PROVIDERS.keys())}")
        else:
            model_ids = get_model_ids(self.provider)
            if self.model not in model_ids:
                if self.provider != "ollama":
                    errors.append(f"Unknown model '{self.model}' for {self.provider}.")
            if self.use_tiers and self.light_model:
                if self.light_model not in model_ids and self.provider != "ollama":
                    errors.append(f"Unknown light model '{self.light_model}' for {self.provider}.")
        return errors

    def get_model_for_task(self, complexity: str = "heavy") -> str:
        if self.use_tiers and complexity == "light" and self.light_model:
            return self.light_model
        return self.model


@dataclass
class ModelConfiguration:
    """
    Full model configuration for Orion.
    Governor is ALWAYS Orion -- not configurable.
    """
    mode: str = "single"
    builder: RoleConfig = field(default_factory=RoleConfig)
    reviewer: RoleConfig = field(default_factory=RoleConfig)

    def validate(self) -> List[str]:
        errors = []
        if self.mode not in ("single", "dual"):
            errors.append(f"Invalid mode: {self.mode}. Must be 'single' or 'dual'.")
        errors.extend(self.builder.validate())
        if self.mode == "dual":
            errors.extend(self.reviewer.validate())
        return errors

    def get_builder(self) -> RoleConfig:
        return self.builder

    def get_reviewer(self) -> RoleConfig:
        if self.mode == "single":
            return self.builder
        return self.reviewer

    def requires_api_key(self, provider: str) -> bool:
        return PROVIDERS.get(provider, {}).get("auth") == "api_key"

    def get_required_keys(self) -> List[str]:
        needed = set()
        if self.requires_api_key(self.builder.provider):
            needed.add(self.builder.provider)
        reviewer = self.get_reviewer()
        if self.requires_api_key(reviewer.provider):
            needed.add(reviewer.provider)
        return sorted(needed)

    def summary(self) -> str:
        reviewer = self.get_reviewer()
        lines = [
            f"Mode: {self.mode}",
            f"Builder:  {self.builder.provider}/{self.builder.model}",
        ]
        if self.builder.use_tiers and self.builder.light_model:
            lines.append(f"  Light:  {self.builder.provider}/{self.builder.light_model}")
        lines.append(f"Reviewer: {reviewer.provider}/{reviewer.model}")
        if reviewer.use_tiers and reviewer.light_model:
            lines.append(f"  Light:  {reviewer.provider}/{reviewer.light_model}")
        lines.append("Governor: Orion (hardcoded)")
        keys = self.get_required_keys()
        if keys:
            lines.append(f"API keys needed: {', '.join(keys)}")
        else:
            lines.append("API keys needed: none (fully local)")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "builder": asdict(self.builder),
            "reviewer": asdict(self.reviewer),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelConfiguration":
        return cls(
            mode=data.get("mode", "single"),
            builder=RoleConfig(**data.get("builder", {})),
            reviewer=RoleConfig(**data.get("reviewer", {})),
        )


# =============================================================================
# PRESET CONFIGURATIONS
# =============================================================================

PRESETS = {
    "local_free": ModelConfiguration(
        mode="single",
        builder=RoleConfig(provider="ollama", model="qwen2.5:14b", light_model="qwen2.5:7b", use_tiers=True),
        reviewer=RoleConfig(provider="ollama", model="qwen2.5:14b", light_model="qwen2.5:7b", use_tiers=True),
    ),
    "power_user": ModelConfiguration(
        mode="dual",
        builder=RoleConfig(provider="openai", model="gpt-5.2", light_model="gpt-4o-mini", use_tiers=True),
        reviewer=RoleConfig(provider="anthropic", model="claude-opus-4-5-20251101", light_model="claude-haiku-4-5-20251001", use_tiers=True),
    ),
    "cloud_budget": ModelConfiguration(
        mode="dual",
        builder=RoleConfig(provider="openai", model="gpt-4o", light_model="gpt-4o-mini", use_tiers=True),
        reviewer=RoleConfig(provider="anthropic", model="claude-sonnet-4-20250514", light_model="claude-haiku-4-5-20251001", use_tiers=True),
    ),
    "cloud_dual": ModelConfiguration(
        mode="dual",
        builder=RoleConfig(provider="openai", model="gpt-4o"),
        reviewer=RoleConfig(provider="anthropic", model="claude-sonnet-4-20250514"),
    ),
    "cloud_openai_only": ModelConfiguration(
        mode="single",
        builder=RoleConfig(provider="openai", model="gpt-4o", light_model="gpt-4o-mini", use_tiers=True),
        reviewer=RoleConfig(provider="openai", model="gpt-4o", light_model="gpt-4o-mini", use_tiers=True),
    ),
    "cloud_anthropic_only": ModelConfiguration(
        mode="single",
        builder=RoleConfig(provider="anthropic", model="claude-sonnet-4-20250514", light_model="claude-haiku-4-5-20251001", use_tiers=True),
        reviewer=RoleConfig(provider="anthropic", model="claude-sonnet-4-20250514", light_model="claude-haiku-4-5-20251001", use_tiers=True),
    ),
    "google_free": ModelConfiguration(
        mode="single",
        builder=RoleConfig(provider="google", model="gemini-2.5-pro", light_model="gemini-2.5-flash", use_tiers=True),
        reviewer=RoleConfig(provider="google", model="gemini-2.5-pro", light_model="gemini-2.5-flash", use_tiers=True),
    ),
    "hybrid_budget": ModelConfiguration(
        mode="dual",
        builder=RoleConfig(provider="ollama", model="qwen2.5:14b", light_model="qwen2.5:7b", use_tiers=True),
        reviewer=RoleConfig(provider="anthropic", model="claude-sonnet-4-20250514", light_model="claude-haiku-4-5-20251001", use_tiers=True),
    ),
}


# =============================================================================
# PERSISTENCE
# =============================================================================

CONFIG_FILE = Path.home() / ".orion" / "model_config.json"


def load_model_config() -> ModelConfiguration:
    """Load model configuration from disk, or return default."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            cfg = ModelConfiguration.from_dict(data)
            errors = cfg.validate()
            if not errors:
                return cfg
        except Exception:
            pass

    # Default: check env var for local preference
    use_local = os.environ.get("ORION_USE_LOCAL_MODELS", "false").lower() in ("true", "1", "yes")
    if use_local:
        return PRESETS["local_free"]
    else:
        return PRESETS["cloud_dual"]


def save_model_config(cfg: ModelConfiguration) -> bool:
    """Save model configuration to disk."""
    errors = cfg.validate()
    if errors:
        return False
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg.to_dict(), f, indent=2)
        return True
    except Exception:
        return False


def get_model_config() -> ModelConfiguration:
    """Get the current model configuration."""
    return load_model_config()


def apply_preset(preset_name: str) -> Optional[ModelConfiguration]:
    """Apply a named preset. Returns the config or None if invalid."""
    cfg = PRESETS.get(preset_name)
    if cfg:
        save_model_config(cfg)
    return cfg
