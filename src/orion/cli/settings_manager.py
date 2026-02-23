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
Orion Agent -- /settings CLI Management Module (v9.0.0)

Interactive CLI settings viewer and editor.

Provides:
  - View all current settings grouped by category
  - Edit individual settings interactively
  - Reset to defaults
  - Import/export settings
  - Migrate legacy plaintext API keys to secure store

Usage:
    from orion.cli.settings_manager import run_settings
    await run_settings(console)
"""

import contextlib
import json
import os
from pathlib import Path
from typing import Any

SETTINGS_DIR = Path.home() / ".orion"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

# Setting definitions with metadata for display
SETTING_CATEGORIES = {
    "Governance": {
        "default_mode": {
            "label": "Default Mode",
            "type": "choice",
            "choices": ["safe", "pro", "project"],
            "default": "safe",
            "description": "Controls what Orion is allowed to do",
        },
        "aegis_strict_mode": {
            "label": "AEGIS Strict Mode",
            "type": "bool",
            "default": True,
            "description": "Enforce strict safety checks on all operations",
        },
    },
    "Core Features": {
        "enable_table_of_three": {
            "label": "Table of Three",
            "type": "bool",
            "default": True,
            "description": "Multi-agent deliberation for complex tasks",
        },
        "enable_file_tools": {
            "label": "File Tools",
            "type": "bool",
            "default": True,
            "description": "Allow reading and writing files in workspace",
        },
        "enable_passive_memory": {
            "label": "Passive Memory",
            "type": "bool",
            "default": True,
            "description": "Learn from your coding patterns over time",
        },
        "enable_streaming": {
            "label": "Streaming Output",
            "type": "bool",
            "default": True,
            "description": "Show responses as they're generated",
        },
    },
    "Command Execution": {
        "enable_command_execution": {
            "label": "Command Execution",
            "type": "bool",
            "default": False,
            "description": "Allow running shell commands (requires project mode)",
        },
        "command_timeout_seconds": {
            "label": "Command Timeout",
            "type": "int",
            "default": 30,
            "min": 5,
            "max": 300,
            "description": "Maximum seconds a command can run",
        },
    },
    "Sandbox": {
        "sandbox_mode": {
            "label": "Sandbox Mode",
            "type": "choice",
            "choices": ["auto", "docker", "local"],
            "default": "auto",
            "description": "Code execution isolation: auto (try Docker, fall back to local), docker (requires Docker), local (temp directory)",
        },
        "sandbox_timeout": {
            "label": "Sandbox Timeout",
            "type": "int",
            "default": 60,
            "min": 5,
            "max": 600,
            "description": "Maximum seconds for sandbox code execution",
        },
        "sandbox_network": {
            "label": "Sandbox Network Access",
            "type": "bool",
            "default": False,
            "description": "Allow sandbox containers to access the network (Docker mode only)",
        },
    },
    "Limits": {
        "max_evidence_files": {
            "label": "Max Evidence Files",
            "type": "int",
            "default": 20,
            "min": 1,
            "max": 100,
            "description": "Maximum files to include as context",
        },
        "max_file_size_bytes": {
            "label": "Max File Size",
            "type": "int",
            "default": 100000,
            "min": 1000,
            "max": 10000000,
            "description": "Maximum file size to read (bytes)",
        },
    },
    "Web Access": {
        "enable_web_access": {
            "label": "Web Access",
            "type": "bool",
            "default": False,
            "description": "Allow fetching web pages for research",
        },
        "web_cache_ttl": {
            "label": "Web Cache TTL",
            "type": "int",
            "default": 3600,
            "min": 0,
            "max": 86400,
            "description": "How long to cache web results (seconds)",
        },
    },
    "Models": {
        "use_local_models": {
            "label": "Prefer Local Models",
            "type": "bool",
            "default": True,
            "description": "Use Ollama local models when available",
        },
        "ollama_base_url": {
            "label": "Ollama URL",
            "type": "str",
            "default": "http://localhost:11434",
            "description": "Ollama server address",
        },
        "ollama_builder_model": {
            "label": "Ollama Builder Model",
            "type": "str",
            "default": "qwen2.5-coder:14b",
            "description": "Model for code generation tasks",
        },
    },
    "Autonomous Roles (ARA)": {
        "ara_enabled": {
            "label": "ARA Enabled",
            "type": "bool",
            "default": True,
            "description": "Enable the Autonomous Role Architecture for background tasks",
        },
        "ara_default_auth": {
            "label": "Default Auth Method",
            "type": "choice",
            "choices": ["pin", "totp", "none"],
            "default": "pin",
            "description": "Authentication method for autonomous sessions",
        },
        "ara_max_cost_usd": {
            "label": "Max Cost Per Session",
            "type": "int",
            "default": 5,
            "min": 1,
            "max": 100,
            "description": "Maximum USD cost per autonomous session",
        },
        "ara_max_session_hours": {
            "label": "Max Session Duration",
            "type": "int",
            "default": 8,
            "min": 1,
            "max": 24,
            "description": "Maximum hours an autonomous session can run",
        },
        "ara_sandbox_mode": {
            "label": "ARA Sandbox",
            "type": "choice",
            "choices": ["docker", "branch", "local"],
            "default": "branch",
            "description": "Isolation strategy for autonomous work (docker, branch, or local)",
        },
        "ara_prompt_guard": {
            "label": "Prompt Guard",
            "type": "bool",
            "default": True,
            "description": "Enable prompt injection defence for ARA sessions",
        },
        "ara_audit_log": {
            "label": "Audit Log",
            "type": "bool",
            "default": True,
            "description": "Enable tamper-proof audit logging for ARA sessions",
        },
        "ara_enable_command_execution": {
            "label": "Command Execution",
            "type": "bool",
            "default": False,
            "description": "Allow ARA sessions to run commands inside Docker sandbox containers",
        },
        "ara_resource_profile": {
            "label": "Resource Profile",
            "type": "choice",
            "choices": ["light", "standard", "heavy"],
            "default": "standard",
            "description": "Docker container resource limits for ARA command execution",
        },
    },
}


def _load_settings() -> dict[str, Any]:
    """Load current settings with defaults."""
    user_settings = {}
    if SETTINGS_FILE.exists():
        with contextlib.suppress(Exception):
            user_settings = json.loads(SETTINGS_FILE.read_text())

    # Merge with defaults
    result = {}
    for _category, settings in SETTING_CATEGORIES.items():
        for key, meta in settings.items():
            result[key] = user_settings.get(key, meta["default"])
    # Include any extra user settings not in our schema
    for key, value in user_settings.items():
        if key not in result:
            result[key] = value
    return result


def _save_settings(settings: dict[str, Any]):
    """Save settings to file."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


async def run_settings(console=None, action: str = "view") -> dict[str, Any]:
    """
    Run the settings manager.

    Args:
        console: OrionConsole for output
        action: "view", "reset", or "export"

    Returns:
        Current settings dict
    """
    settings = _load_settings()

    def _print(text: str, style: str = ""):
        if console and hasattr(console, "print"):
            console.print(text, style=style)
        elif console and hasattr(console, "status"):
            console.status(text)
        else:
            print(text)

    if action == "reset":
        return await _reset_settings(console)
    elif action == "export":
        return await _export_settings(console)

    # View mode -- display all settings grouped by category
    _print("\n  Orion Settings\n", "bold cyan")
    _print("  " + "─" * 50)

    for category, category_settings in SETTING_CATEGORIES.items():
        _print(f"\n  [{category}]", "bold")
        for key, meta in category_settings.items():
            value = settings.get(key, meta["default"])
            is_default = value == meta["default"]
            value_str = _format_value(value, meta)
            default_marker = "" if not is_default else " (default)"
            _print(f"    {meta['label']}: {value_str}{default_marker}")
            _print(f"      {meta['description']}", "dim")

    # Show API key status
    _print("\n  [API Keys]", "bold")
    try:
        from orion.security.store import get_secure_store

        store = get_secure_store()
        providers = store.list_providers()
        api_providers = [p for p in providers if not p.startswith("oauth_")]
        if api_providers:
            for p in api_providers:
                _print(f"    {p}: configured ({store.backend_name})")
        else:
            _print("    No API keys stored")
    except Exception:
        # Check environment variables
        for name, env in [("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")]:
            if os.environ.get(env):
                _print(f"    {name}: configured (environment)")

    _print("\n  " + "─" * 50)
    _print("  Tip: Edit settings in the Web UI or modify ~/.orion/settings.json\n", "dim")

    return settings


async def _reset_settings(console=None) -> dict[str, Any]:
    """Reset all settings to defaults."""
    defaults = {}
    for _category, settings in SETTING_CATEGORIES.items():
        for key, meta in settings.items():
            defaults[key] = meta["default"]

    _save_settings(defaults)

    if console:
        if hasattr(console, "print"):
            console.print("  Settings reset to defaults.", "green")
        elif hasattr(console, "status"):
            console.status("Settings reset to defaults.")

    return defaults


async def _export_settings(console=None) -> dict[str, Any]:
    """Export settings to a portable format."""
    settings = _load_settings()
    export_path = SETTINGS_DIR / "settings_export.json"
    export_path.write_text(json.dumps(settings, indent=2))

    if console:
        msg = f"  Settings exported to: {export_path}"
        if hasattr(console, "print"):
            console.print(msg, "green")
        elif hasattr(console, "status"):
            console.status(msg)

    return settings


def _format_value(value: Any, meta: dict) -> str:
    """Format a setting value for display."""
    if meta["type"] == "bool":
        return "enabled" if value else "disabled"
    elif meta["type"] == "choice":
        return str(value)
    elif meta["type"] == "int":
        if "max_file_size" in meta.get("label", "").lower() or value > 10000:
            if value >= 1_000_000:
                return f"{value / 1_000_000:.1f} MB"
            elif value >= 1000:
                return f"{value / 1000:.0f} KB"
        return str(value)
    return str(value)
