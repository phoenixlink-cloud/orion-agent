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
Orion Agent -- Messaging Integrations (v7.4.0)

Base class and provider registry for messaging platforms.
Providers: Slack, Discord, Telegram, Teams, WhatsApp.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orion.integrations.messaging")


class MessagingProviderBase(ABC):
    """Base class for messaging platform integrations."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def send_message(self, channel: str, text: str, **kwargs) -> Dict[str, Any]:
        """Send a message to a channel/conversation."""
        ...

    async def list_channels(self) -> List[Dict[str, str]]:
        """List available channels."""
        return []

    async def health_check(self) -> bool:
        return True


class SlackProvider(MessagingProviderBase):
    """Slack messaging via Bot Token + Web API."""

    def __init__(self, bot_token: Optional[str] = None):
        self._token = bot_token

    @property
    def name(self) -> str:
        return "slack"

    def _get_token(self) -> Optional[str]:
        if self._token:
            return self._token
        try:
            from orion.security.store import SecureStore
            return SecureStore().get_key("slack")
        except Exception:
            return None

    async def send_message(self, channel: str, text: str, **kwargs) -> Dict[str, Any]:
        import httpx

        token = self._get_token()
        if not token:
            return {"success": False, "error": "Slack bot token not configured."}

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"channel": channel, "text": text}
        if kwargs.get("thread_ts"):
            payload["thread_ts"] = kwargs["thread_ts"]

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload)
            data = resp.json()

        if data.get("ok"):
            return {"success": True, "ts": data.get("ts"), "channel": data.get("channel")}
        return {"success": False, "error": data.get("error", "Unknown Slack error")}

    async def list_channels(self) -> List[Dict[str, str]]:
        import httpx

        token = self._get_token()
        if not token:
            return []

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get("https://slack.com/api/conversations.list", headers=headers)
            data = resp.json()

        if not data.get("ok"):
            return []
        return [{"id": ch["id"], "name": ch.get("name", "")} for ch in data.get("channels", [])]


# ── Provider registry ────────────────────────────────────────────────────

_PROVIDERS: Dict[str, MessagingProviderBase] = {}


def register_messaging_provider(provider: MessagingProviderBase):
    _PROVIDERS[provider.name] = provider


def get_messaging_provider(name: str) -> Optional[MessagingProviderBase]:
    return _PROVIDERS.get(name)


def list_messaging_providers() -> List[str]:
    return list(_PROVIDERS.keys())


# Auto-register default provider
register_messaging_provider(SlackProvider())
