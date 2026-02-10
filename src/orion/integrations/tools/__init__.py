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
#    See LICENSE-ENTERPRISE.md or contact licensing@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- Tool Integrations (v6.4.0)

Base class and provider registry for developer tool platforms.
Providers: GitHub, GitLab, Jira, Linear, Notion, etc.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orion.integrations.tools")


class ToolProviderBase(ABC):
    """Base class for developer tool integrations."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def auth_type(self) -> str:
        """'pat' (personal access token), 'oauth', or 'bot_token'."""
        return "pat"

    @abstractmethod
    async def api_call(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an authenticated API call to the tool."""
        ...

    async def health_check(self) -> bool:
        return True


class GitHubProvider(ToolProviderBase):
    """GitHub API integration via PAT or CLI auth."""

    @property
    def name(self) -> str:
        return "github"

    def _get_token(self) -> Optional[str]:
        try:
            from orion.security.store import SecureStore
            return SecureStore().get_key("github")
        except Exception:
            return None

    async def api_call(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        import httpx

        token = self._get_token()
        if not token:
            return {"success": False, "error": "GitHub token not configured. Use /key set github <token>."}

        base = "https://api.github.com"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method.upper(), f"{base}{endpoint}", headers=headers, **kwargs)
            if resp.status_code >= 400:
                return {"success": False, "status": resp.status_code, "error": resp.text[:500]}
            return {"success": True, "status": resp.status_code, "data": resp.json()}

    async def health_check(self) -> bool:
        result = await self.api_call("GET", "/user")
        return result.get("success", False)


class NotionProvider(ToolProviderBase):
    """Notion API integration via bot token."""

    @property
    def name(self) -> str:
        return "notion"

    @property
    def auth_type(self) -> str:
        return "bot_token"

    def _get_token(self) -> Optional[str]:
        try:
            from orion.security.store import SecureStore
            return SecureStore().get_key("notion")
        except Exception:
            return None

    async def api_call(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        import httpx

        token = self._get_token()
        if not token:
            return {"success": False, "error": "Notion token not configured. Use /key set notion <token>."}

        base = "https://api.notion.com/v1"
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method.upper(), f"{base}{endpoint}", headers=headers, **kwargs)
            if resp.status_code >= 400:
                return {"success": False, "status": resp.status_code, "error": resp.text[:500]}
            return {"success": True, "status": resp.status_code, "data": resp.json()}


# ── Provider registry ────────────────────────────────────────────────────

_PROVIDERS: Dict[str, ToolProviderBase] = {}


def register_tool_provider(provider: ToolProviderBase):
    _PROVIDERS[provider.name] = provider


def get_tool_provider(name: str) -> Optional[ToolProviderBase]:
    return _PROVIDERS.get(name)


def list_tool_providers() -> List[str]:
    return list(_PROVIDERS.keys())


# Auto-register default providers
register_tool_provider(GitHubProvider())
register_tool_provider(NotionProvider())
