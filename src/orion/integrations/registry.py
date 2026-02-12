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
Orion Agent -- Integration Registry (v7.4.0)

Discovers, registers, and manages all integrations.
Provides a central point for querying available capabilities
and invoking integration features.
"""

import contextlib
import importlib
import pkgutil
from typing import Any

from orion.integrations.base import (
    IntegrationBase,
    IntegrationStatus,
)


class IntegrationRegistry:
    """
    Central registry for all Orion integrations.

    Discovers integration plugins from the integrations/ package,
    registers them, and provides lookup by name or capability.
    """

    def __init__(self):
        self._integrations: dict[str, IntegrationBase] = {}
        self._capabilities: dict[str, list[str]] = {}  # capability -> [integration_names]
        self._errors: dict[str, str] = {}

    def register(self, integration: IntegrationBase) -> bool:
        """
        Register a single integration instance.

        Returns True if registration succeeded.
        """
        name = integration.name
        if name in self._integrations:
            return False

        try:
            if integration.setup():
                self._integrations[name] = integration
                # Index capabilities
                for cap in integration.get_capabilities():
                    if cap.name not in self._capabilities:
                        self._capabilities[cap.name] = []
                    self._capabilities[cap.name].append(name)
                return True
            else:
                self._errors[name] = "setup() returned False"
                return False
        except Exception as e:
            self._errors[name] = str(e)
            return False

    def unregister(self, name: str) -> bool:
        """Unregister an integration by name."""
        if name not in self._integrations:
            return False

        integration = self._integrations[name]
        with contextlib.suppress(Exception):
            integration.teardown()

        # Remove capability index entries
        for cap_name, providers in list(self._capabilities.items()):
            if name in providers:
                providers.remove(name)
                if not providers:
                    del self._capabilities[cap_name]

        del self._integrations[name]
        return True

    def discover(self) -> int:
        """
        Auto-discover integrations from sub-packages.

        Looks for modules under orion.integrations that define a
        `create_integration()` factory function.

        Returns the number of newly registered integrations.
        """
        import orion.integrations as pkg

        count = 0
        for _importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
            if modname.startswith("_") or modname in ("base", "registry", "health"):
                continue

            full_name = f"orion.integrations.{modname}"

            try:
                mod = importlib.import_module(full_name)
                factory = getattr(mod, "create_integration", None)
                if factory is None and ispkg:
                    try:
                        init_mod = importlib.import_module(f"{full_name}")
                        factory = getattr(init_mod, "create_integration", None)
                    except Exception:
                        pass

                if factory and callable(factory):
                    integration = factory()
                    if isinstance(integration, IntegrationBase):
                        if self.register(integration):
                            count += 1
                    elif isinstance(integration, list):
                        for item in integration:
                            if isinstance(item, IntegrationBase):
                                if self.register(item):
                                    count += 1
            except Exception as e:
                self._errors[modname] = f"Discovery error: {e}"

        return count

    def get(self, name: str) -> IntegrationBase | None:
        """Get an integration by name."""
        return self._integrations.get(name)

    def list_integrations(self) -> list[str]:
        """List all registered integration names."""
        return list(self._integrations.keys())

    def list_all(self) -> list[dict[str, Any]]:
        """List all registered integrations with their info."""
        return [i.to_dict() for i in self._integrations.values()]

    def list_available(self) -> list[dict[str, Any]]:
        """List only integrations that are currently available."""
        return [
            i.to_dict()
            for i in self._integrations.values()
            if i.get_status() in (IntegrationStatus.AVAILABLE, IntegrationStatus.AUTHENTICATED)
        ]

    def list_capabilities(self) -> dict[str, list[str]]:
        """Return mapping of capability_name -> [integration_names]."""
        return dict(self._capabilities)

    def find_by_capability(self, capability: str) -> list[IntegrationBase]:
        """Find all integrations that provide a given capability."""
        names = self._capabilities.get(capability, [])
        return [self._integrations[n] for n in names if n in self._integrations]

    def get_errors(self) -> dict[str, str]:
        """Return any errors encountered during registration/discovery."""
        return dict(self._errors)

    @property
    def count(self) -> int:
        """Number of registered integrations."""
        return len(self._integrations)

    def to_dict(self) -> dict[str, Any]:
        """Full registry state for API responses."""
        return {
            "integrations": self.list_all(),
            "capabilities": self.list_capabilities(),
            "errors": self.get_errors(),
            "count": self.count,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry: IntegrationRegistry | None = None


def get_registry() -> IntegrationRegistry:
    """Get or create the global integration registry."""
    global _registry
    if _registry is None:
        _registry = IntegrationRegistry()
    return _registry
