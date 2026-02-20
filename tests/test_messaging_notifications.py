# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""Unit tests for Phase 4E.2 — Outbound Session Events to Messaging.

Minimum 10 tests covering:
  1. MessagingProvider construction and properties
  2. MessagingProvider.send — success, no platform, no channel, missing adapter
  3. NotificationManager.enable_messaging wiring
  4. NotificationManager.messaging_provider property
  5. Session events delivered via messaging channel
  6. Rate limiting still applies with messaging
  7. SessionState source_platform / source_user_id fields
  8. MessageBridge wires enable_messaging on new task creation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.ara.message_bridge import InboundMessage, MessageBridge
from orion.ara.notifications import (
    MAX_NOTIFICATIONS_PER_SESSION,
    MessagingProvider,
    Notification,
    NotificationManager,
    TEMPLATES,
)
from orion.ara.session import SessionState


# =========================================================================
# 1. MessagingProvider construction
# =========================================================================


class TestMessagingProviderConstruction:
    def test_defaults(self):
        mp = MessagingProvider()
        assert mp.platform == ""
        assert mp.channel == ""
        assert mp.provider_name == "messaging"

    def test_with_platform(self):
        mp = MessagingProvider(platform="telegram", channel="u123")
        assert mp.platform == "telegram"
        assert mp.channel == "u123"
        assert mp.provider_name == "messaging:telegram"


# =========================================================================
# 2. MessagingProvider.send
# =========================================================================


class TestMessagingProviderSend:
    def test_send_no_platform_returns_false(self):
        mp = MessagingProvider(platform="", channel="u1")
        n = Notification(template="session_started", params={"session_id": "s1", "role_name": "r", "goal": "g"})
        assert mp.send(n) is False

    def test_send_no_channel_returns_false(self):
        mp = MessagingProvider(platform="slack", channel="")
        n = Notification(template="session_started", params={"session_id": "s1", "role_name": "r", "goal": "g"})
        assert mp.send(n) is False

    def test_send_missing_adapter_returns_false(self):
        mp = MessagingProvider(platform="nonexistent_platform", channel="u1")
        n = Notification(template="session_started", params={"session_id": "s1", "role_name": "r", "goal": "g"})
        with patch("orion.integrations.messaging.get_messaging_provider", return_value=None):
            assert mp.send(n) is False

    def test_send_success_with_running_loop(self):
        mock_provider = MagicMock()
        mock_provider.send_message = AsyncMock(return_value={"ok": True})

        mp = MessagingProvider(platform="telegram", channel="u1")
        n = Notification(template="session_started", params={"session_id": "s1", "role_name": "r", "goal": "g"})

        with patch("orion.integrations.messaging.get_messaging_provider", return_value=mock_provider):
            # When no running loop, asyncio.run is used
            result = mp.send(n)
            assert result is True

    def test_send_exception_returns_false(self):
        mp = MessagingProvider(platform="telegram", channel="u1")
        n = Notification(template="session_started", params={"session_id": "s1", "role_name": "r", "goal": "g"})
        with patch("orion.integrations.messaging.get_messaging_provider", side_effect=RuntimeError("boom")):
            assert mp.send(n) is False


# =========================================================================
# 3. NotificationManager.enable_messaging
# =========================================================================


class TestNotificationManagerMessaging:
    def test_enable_messaging_adds_provider(self):
        nm = NotificationManager()
        mp = nm.enable_messaging("slack", "C123")
        assert isinstance(mp, MessagingProvider)
        assert mp.platform == "slack"
        assert mp.channel == "C123"
        assert nm.messaging_provider is mp

    def test_messaging_provider_none_by_default(self):
        nm = NotificationManager()
        assert nm.messaging_provider is None

    def test_notify_with_messaging_provider(self):
        nm = NotificationManager()
        mp = nm.enable_messaging("telegram", "u1")

        with patch.object(mp, "send", return_value=True) as mock_send:
            result = nm.notify("session_started", {
                "session_id": "s1", "role_name": "r", "goal": "g"
            })
            assert result is True
            mock_send.assert_called_once()
            notification = mock_send.call_args[0][0]
            assert "s1" in notification.message
            assert isinstance(notification, Notification)

    def test_rate_limit_still_applies(self):
        nm = NotificationManager(max_per_session=2)
        mp = nm.enable_messaging("telegram", "u1")

        with patch.object(mp, "send", return_value=True):
            nm.notify("session_started", {"session_id": "s1", "role_name": "r", "goal": "g"})
            nm.notify("session_completed", {
                "session_id": "s1", "tasks_completed": 5, "tasks_total": 5, "elapsed": "2m"
            })
            # 3rd call should be rate-limited
            result = nm.notify("checkpoint_created", {"session_id": "s1", "checkpoint_number": 1})
            assert result is False
            assert nm.sent_count == 2

    def test_reset_clears_messaging_history(self):
        nm = NotificationManager()
        nm.enable_messaging("slack", "u1")
        with patch.object(nm.messaging_provider, "send", return_value=True):
            nm.notify("session_started", {"session_id": "s1", "role_name": "r", "goal": "g"})
        assert nm.sent_count == 1
        nm.reset()
        assert nm.sent_count == 0
        assert nm.history == []


# =========================================================================
# 4. SessionState source fields
# =========================================================================


class TestSessionStateSourceFields:
    def test_source_platform_default_none(self):
        ss = SessionState()
        assert ss.source_platform is None
        assert ss.source_user_id is None

    def test_source_platform_set(self):
        ss = SessionState(source_platform="telegram", source_user_id="u456")
        assert ss.source_platform == "telegram"
        assert ss.source_user_id == "u456"


# =========================================================================
# 5. MessageBridge wires enable_messaging on new task
# =========================================================================


class TestMessageBridgeWiresMessaging:
    @pytest.mark.asyncio
    async def test_new_task_wires_messaging(self):
        engine = MagicMock()
        engine.create_session = MagicMock(return_value=MagicMock(session_id="sess1234abcd"))

        nm = NotificationManager()
        bridge = MessageBridge(session_engine=engine, notification_manager=nm)

        msg = InboundMessage(platform="discord", user_id="u99", text="Build an API")
        await bridge.handle_message(msg)

        # Notification manager should now have a messaging provider for discord/u99
        mp = nm.messaging_provider
        assert mp is not None
        assert mp.platform == "discord"
        assert mp.channel == "u99"
