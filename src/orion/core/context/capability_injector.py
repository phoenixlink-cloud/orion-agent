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
Orion Agent -- Capability Injector (v7.4.0)

Builds a prompt section describing available integration capabilities
so the LLM knows what tools/services it can use when responding.

Checks connected platforms and injects their capabilities into the
system prompt dynamically.
"""

import logging

logger = logging.getLogger("orion.context.capabilities")


def build_capability_prompt() -> str:
    """
    Build a prompt section listing available capabilities from connected platforms.

    Returns:
        str: Prompt text describing available capabilities, or empty string if none.
    """
    capabilities: list[str] = []

    # Check connected platforms
    try:
        from orion.integrations.platforms import get_platform_registry

        registry = get_platform_registry()
        connected = registry.list_connected()

        for platform in connected:
            pid = (
                platform.get("id", "")
                if isinstance(platform, dict)
                else getattr(platform, "id", "")
            )
            name = (
                platform.get("name", pid)
                if isinstance(platform, dict)
                else getattr(platform, "name", pid)
            )
            caps = (
                platform.get("capabilities", [])
                if isinstance(platform, dict)
                else getattr(platform, "capabilities", [])
            )

            if caps:
                cap_list = ", ".join(caps) if isinstance(caps, list) else str(caps)
                capabilities.append(f"- **{name}**: {cap_list}")
            elif pid:
                capabilities.append(f"- **{name}**: connected")
    except Exception as e:
        logger.debug("Could not load platform capabilities: %s", e)

    # Check image generation
    try:
        from orion.integrations.image import list_image_providers

        providers = list_image_providers()
        if providers:
            names = [
                p.get("name", p.get("id", "?")) if isinstance(p, dict) else str(p)
                for p in providers
            ]
            capabilities.append(f"- **Image Generation**: {', '.join(names)}")
    except Exception:
        pass

    # Check voice
    try:
        from orion.integrations.voice import list_tts_providers

        providers = list_tts_providers()
        if providers:
            capabilities.append(f"- **Text-to-Speech**: {len(providers)} provider(s) available")
    except Exception:
        pass

    if not capabilities:
        return ""

    header = "\n\n## AVAILABLE INTEGRATIONS\nYou have access to the following connected services:\n"
    return header + "\n".join(capabilities)


__all__ = ["build_capability_prompt"]
