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
Orion Agent -- Formal Plugin API (v7.4.0)

Extends the existing IntegrationBase with a composable plugin contract
inspired by a composable plugin architecture.

Architecture:
    1. MANIFEST:    plugin.json declarative metadata (name, version, hooks, commands)
    2. HOOKS:       Lifecycle events plugins can subscribe to
    3. COMMANDS:    Plugins can register custom slash commands
    4. SKILLS:      Reusable skill definitions (tool-use protocol)
    5. EVENT BUS:   Central event dispatcher for hook execution

Hook lifecycle:
    SessionStart   -> fired when Orion starts a new session
    SessionEnd     -> fired when session ends
    PreToolUse     -> fired before any tool/integration call (can block)
    PostToolUse    -> fired after any tool/integration call (can modify)
    PreEdit        -> fired before file edit (can block)
    PostEdit       -> fired after file edit (can audit)
    PrePrompt      -> fired before LLM prompt is sent (can modify)
    PostResponse   -> fired after LLM response received (can modify)
"""

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# HOOK TYPES
# ---------------------------------------------------------------------------


class HookType(Enum):
    """Lifecycle hook types that plugins can subscribe to."""

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    PRE_EDIT = "pre_edit"
    POST_EDIT = "post_edit"
    PRE_PROMPT = "pre_prompt"
    POST_RESPONSE = "post_response"


@dataclass
class HookContext:
    """Context passed to hook handlers."""

    hook_type: HookType
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    block_reason: str = ""
    modified_data: dict[str, Any] | None = None


@dataclass
class HookResult:
    """Result from a hook handler."""

    plugin_name: str
    hook_type: HookType
    success: bool
    blocked: bool = False
    block_reason: str = ""
    modified_data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0


# ---------------------------------------------------------------------------
# PLUGIN COMMAND
# ---------------------------------------------------------------------------


@dataclass
class PluginCommand:
    """A slash command registered by a plugin."""

    name: str
    description: str
    plugin_name: str
    handler: Callable | None = None
    usage: str = ""
    category: str = ""


# ---------------------------------------------------------------------------
# PLUGIN SKILL
# ---------------------------------------------------------------------------


@dataclass
class PluginSkill:
    """A reusable skill (tool-use function) registered by a plugin."""

    name: str
    description: str
    plugin_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: Callable | None = None
    category: str = ""


# ---------------------------------------------------------------------------
# PLUGIN MANIFEST
# ---------------------------------------------------------------------------


@dataclass
class PluginManifest:
    """Declarative plugin metadata -- can be loaded from plugin.json."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    hooks: list[str] = field(default_factory=list)
    commands: list[dict[str, str]] = field(default_factory=list)
    skills: list[dict[str, str]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        return cls(
            name=data.get("name", "unknown"),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            hooks=data.get("hooks", []),
            commands=data.get("commands", []),
            skills=data.get("skills", []),
            config=data.get("config", {}),
            enabled=data.get("enabled", True),
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "PluginManifest":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "hooks": self.hooks,
            "commands": [c for c in self.commands],
            "skills": [s for s in self.skills],
            "config": self.config,
            "enabled": self.enabled,
        }


# ---------------------------------------------------------------------------
# PLUGIN BASE CLASS
# ---------------------------------------------------------------------------


class PluginBase(ABC):
    """
    Formal plugin contract. Extends beyond IntegrationBase with
    hooks, commands, skills, and manifest support.
    """

    def __init__(self):
        self._manifest: PluginManifest | None = None
        self._hooks: dict[HookType, Callable] = {}
        self._commands: list[PluginCommand] = []
        self._skills: list[PluginSkill] = []

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return ""

    def on_load(self) -> bool:
        return True

    def on_unload(self) -> None:
        pass

    def register_hook(self, hook_type: HookType, handler: Callable):
        self._hooks[hook_type] = handler

    def get_hooks(self) -> dict[HookType, Callable]:
        return dict(self._hooks)

    def handles_hook(self, hook_type: HookType) -> bool:
        return hook_type in self._hooks

    def register_command(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        usage: str = "",
        category: str = "",
    ):
        self._commands.append(
            PluginCommand(
                name=name,
                description=description,
                plugin_name=self.name,
                handler=handler,
                usage=usage,
                category=category,
            )
        )

    def get_commands(self) -> list[PluginCommand]:
        return list(self._commands)

    def register_skill(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        parameters: dict | None = None,
        category: str = "",
    ):
        self._skills.append(
            PluginSkill(
                name=name,
                description=description,
                plugin_name=self.name,
                parameters=parameters or {},
                handler=handler,
                category=category,
            )
        )

    def get_skills(self) -> list[PluginSkill]:
        return list(self._skills)

    def get_manifest(self) -> PluginManifest:
        if self._manifest:
            return self._manifest
        return PluginManifest(
            name=self.name,
            version=self.version,
            description=self.description,
            hooks=[h.value for h in self._hooks],
            commands=[{"name": c.name, "description": c.description} for c in self._commands],
            skills=[{"name": s.name, "description": s.description} for s in self._skills],
        )

    def set_manifest(self, manifest: PluginManifest):
        self._manifest = manifest

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "hooks": [h.value for h in self._hooks],
            "commands": [c.name for c in self._commands],
            "skills": [s.name for s in self._skills],
            "manifest": self.get_manifest().to_dict(),
        }


# ---------------------------------------------------------------------------
# EVENT BUS
# ---------------------------------------------------------------------------


class EventBus:
    """
    Central event dispatcher for hook execution.

    Fires hooks to all subscribed plugins in registration order.
    Supports blocking (PreToolUse can prevent execution) and
    modification (PrePrompt can alter the prompt).
    """

    def __init__(self):
        self._plugins: dict[str, PluginBase] = {}
        self._hook_log: list[HookResult] = []
        self._max_log_size: int = 1000

    def register_plugin(self, plugin: PluginBase) -> bool:
        if plugin.name in self._plugins:
            return False
        self._plugins[plugin.name] = plugin
        return True

    def unregister_plugin(self, name: str) -> bool:
        if name in self._plugins:
            del self._plugins[name]
            return True
        return False

    def fire(self, hook_type: HookType, data: dict[str, Any] | None = None) -> list[HookResult]:
        context = HookContext(hook_type=hook_type, data=data or {})
        results = []
        for name, plugin in self._plugins.items():
            if not plugin.handles_hook(hook_type):
                continue
            handler = plugin.get_hooks()[hook_type]
            start = time.time()
            try:
                handler(context)
                duration_ms = (time.time() - start) * 1000
                result = HookResult(
                    plugin_name=name,
                    hook_type=hook_type,
                    success=True,
                    blocked=context.blocked,
                    block_reason=context.block_reason,
                    modified_data=context.modified_data,
                    duration_ms=duration_ms,
                )
            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                result = HookResult(
                    plugin_name=name,
                    hook_type=hook_type,
                    success=False,
                    error=str(e),
                    duration_ms=duration_ms,
                )
            results.append(result)
            self._log_result(result)
            if context.blocked and hook_type in (
                HookType.PRE_TOOL_USE,
                HookType.PRE_EDIT,
                HookType.PRE_PROMPT,
            ):
                break
        return results

    def fire_blocking(
        self, hook_type: HookType, data: dict[str, Any] | None = None
    ) -> tuple[bool, str]:
        results = self.fire(hook_type, data)
        for r in results:
            if r.blocked:
                return False, r.block_reason
        return True, ""

    def fire_modifying(self, hook_type: HookType, data: dict[str, Any]) -> dict[str, Any]:
        current_data = dict(data)
        for name, plugin in self._plugins.items():
            if not plugin.handles_hook(hook_type):
                continue
            handler = plugin.get_hooks()[hook_type]
            context = HookContext(hook_type=hook_type, data=dict(current_data))
            start = time.time()
            try:
                handler(context)
                duration_ms = (time.time() - start) * 1000
                if context.modified_data:
                    current_data.update(context.modified_data)
                result = HookResult(
                    plugin_name=name,
                    hook_type=hook_type,
                    success=True,
                    modified_data=context.modified_data,
                    duration_ms=duration_ms,
                )
            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                result = HookResult(
                    plugin_name=name,
                    hook_type=hook_type,
                    success=False,
                    error=str(e),
                    duration_ms=duration_ms,
                )
            self._log_result(result)
        return current_data

    def get_all_commands(self) -> list[PluginCommand]:
        commands = []
        for plugin in self._plugins.values():
            commands.extend(plugin.get_commands())
        return commands

    def get_all_skills(self) -> list[PluginSkill]:
        skills = []
        for plugin in self._plugins.values():
            skills.extend(plugin.get_skills())
        return skills

    def get_plugin(self, name: str) -> PluginBase | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._plugins.values()]

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)

    def get_hook_log(self, limit: int = 50) -> list[dict[str, Any]]:
        entries = self._hook_log[-limit:]
        return [
            {
                "plugin": r.plugin_name,
                "hook": r.hook_type.value,
                "success": r.success,
                "blocked": r.blocked,
                "duration_ms": round(r.duration_ms, 2),
                "error": r.error,
            }
            for r in entries
        ]

    def _log_result(self, result: HookResult):
        self._hook_log.append(result)
        if len(self._hook_log) > self._max_log_size:
            self._hook_log = self._hook_log[-self._max_log_size :]


# ---------------------------------------------------------------------------
# PLUGIN LOADER
# ---------------------------------------------------------------------------


class PluginLoader:
    """Discovers and loads plugins from a directory."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._load_errors: dict[str, str] = {}

    def load_from_manifest(self, manifest_path: str | Path) -> PluginBase | None:
        try:
            manifest = PluginManifest.from_json_file(manifest_path)
            if not manifest.enabled:
                return None
            plugin = ManifestPlugin(manifest)
            if plugin.on_load():
                self.event_bus.register_plugin(plugin)
                return plugin
            return None
        except Exception as e:
            self._load_errors[str(manifest_path)] = str(e)
            return None

    def wrap_integration(self, integration) -> PluginBase | None:
        try:
            plugin = IntegrationPluginWrapper(integration)
            if self.event_bus.register_plugin(plugin):
                return plugin
            return None
        except Exception as e:
            name = getattr(integration, "name", "unknown")
            self._load_errors[name] = str(e)
            return None

    def discover_plugins(self, plugins_dir: str | Path) -> int:
        plugins_path = Path(plugins_dir)
        if not plugins_path.is_dir():
            return 0
        count = 0
        for item in plugins_path.iterdir():
            if item.is_dir():
                manifest_file = item / "plugin.json"
                if manifest_file.exists():
                    if self.load_from_manifest(manifest_file):
                        count += 1
        return count

    def get_errors(self) -> dict[str, str]:
        return dict(self._load_errors)


# ---------------------------------------------------------------------------
# MANIFEST-ONLY PLUGIN
# ---------------------------------------------------------------------------


class ManifestPlugin(PluginBase):
    """A plugin created from a plugin.json manifest (no code)."""

    def __init__(self, manifest: PluginManifest):
        super().__init__()
        self._manifest = manifest
        self._name = manifest.name

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._manifest.version

    @property
    def description(self) -> str:
        return self._manifest.description


# ---------------------------------------------------------------------------
# INTEGRATION WRAPPER
# ---------------------------------------------------------------------------


class IntegrationPluginWrapper(PluginBase):
    """Wraps an existing IntegrationBase as a PluginBase."""

    def __init__(self, integration):
        super().__init__()
        self._integration = integration
        self._name = integration.name

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return getattr(self._integration, "version", "1.0.0")

    @property
    def description(self) -> str:
        return getattr(self._integration, "description", "")

    @property
    def integration(self):
        return self._integration


# ---------------------------------------------------------------------------
# SINGLETON
# ---------------------------------------------------------------------------

_event_bus: EventBus | None = None
_plugin_loader: PluginLoader | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def get_plugin_loader() -> PluginLoader:
    global _plugin_loader
    if _plugin_loader is None:
        _plugin_loader = PluginLoader(get_event_bus())
    return _plugin_loader
