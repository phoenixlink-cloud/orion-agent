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
Orion Agent -- Plugin System

Re-exports everything from orion.plugins.api so that both import paths
(``from orion.plugins import â€¦`` and ``from orion.plugins.api import â€¦``)
resolve to the **same** classes, singletons, and factory functions.
"""

from orion.plugins.api import (  # noqa: F401
    HookType,
    HookContext,
    HookResult,
    PluginCommand,
    PluginSkill,
    PluginManifest,
    PluginBase,
    EventBus,
    ManifestPlugin,
    IntegrationPluginWrapper,
    PluginLoader,
    get_event_bus,
    get_plugin_loader,
)
