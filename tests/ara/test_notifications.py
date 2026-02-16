# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA Notifications (ARA-001 §12 / Appendix C.11)."""

from __future__ import annotations

import pytest

from orion.ara.notifications import (
    TEMPLATES,
    DesktopProvider,
    EmailProvider,
    Notification,
    NotificationManager,
    NotificationProvider,
    WebhookProvider,
)


class MockProvider(NotificationProvider):
    """Test provider that records calls."""

    def __init__(self, succeed: bool = True):
        self._succeed = succeed
        self.calls: list[Notification] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    def send(self, notification: Notification) -> bool:
        self.calls.append(notification)
        return self._succeed


class TestNotification:
    def test_renders_template(self):
        n = Notification(
            template="session_started",
            params={"session_id": "s1", "role_name": "coder", "goal": "build"},
        )
        assert "s1" in n.message
        assert "coder" in n.message

    def test_unknown_template_passthrough(self):
        n = Notification(template="custom message here")
        assert n.message == "custom message here"

    def test_to_dict(self):
        n = Notification(
            template="session_completed",
            params={
                "session_id": "s1",
                "tasks_completed": 5,
                "tasks_total": 10,
                "elapsed": "1.5h",
            },
        )
        d = n.to_dict()
        assert d["template"] == "session_completed"
        assert "s1" in d["message"]

    def test_all_templates_valid(self):
        for name in TEMPLATES:
            n = Notification(template=name)
            assert isinstance(n.message, str)


class TestNotificationManager:
    def test_sends_to_all_providers(self):
        p1 = MockProvider()
        p2 = MockProvider()
        mgr = NotificationManager(providers=[p1, p2])
        result = mgr.notify(
            "session_started",
            {
                "session_id": "s1",
                "role_name": "coder",
                "goal": "test",
            },
        )
        assert result is True
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1

    def test_rate_limiting(self):
        p = MockProvider()
        mgr = NotificationManager(providers=[p], max_per_session=3)
        for _ in range(3):
            assert (
                mgr.notify(
                    "session_started",
                    {
                        "session_id": "s1",
                        "role_name": "r",
                        "goal": "g",
                    },
                )
                is True
            )
        # 4th should be blocked
        assert (
            mgr.notify(
                "session_started",
                {
                    "session_id": "s1",
                    "role_name": "r",
                    "goal": "g",
                },
            )
            is False
        )
        assert mgr.sent_count == 3
        assert mgr.remaining == 0

    def test_rejects_unknown_template(self):
        p = MockProvider()
        mgr = NotificationManager(providers=[p])
        result = mgr.notify("nonexistent_template")
        assert result is False
        assert len(p.calls) == 0

    def test_returns_false_if_all_providers_fail(self):
        p = MockProvider(succeed=False)
        mgr = NotificationManager(providers=[p])
        result = mgr.notify(
            "session_started",
            {
                "session_id": "s1",
                "role_name": "r",
                "goal": "g",
            },
        )
        assert result is False
        assert mgr.sent_count == 1  # Still counts toward limit

    def test_history_tracking(self):
        p = MockProvider()
        mgr = NotificationManager(providers=[p])
        mgr.notify(
            "session_started",
            {
                "session_id": "s1",
                "role_name": "r",
                "goal": "g",
            },
        )
        assert len(mgr.history) == 1
        assert mgr.history[0]["template"] == "session_started"
        assert mgr.history[0]["providers_succeeded"] == 1

    def test_reset(self):
        p = MockProvider()
        mgr = NotificationManager(providers=[p], max_per_session=2)
        mgr.notify(
            "session_started",
            {
                "session_id": "s1",
                "role_name": "r",
                "goal": "g",
            },
        )
        mgr.reset()
        assert mgr.sent_count == 0
        assert mgr.remaining == 2
        assert len(mgr.history) == 0

    def test_add_provider(self):
        mgr = NotificationManager()
        p = MockProvider()
        mgr.add_provider(p)
        mgr.notify(
            "session_started",
            {
                "session_id": "s1",
                "role_name": "r",
                "goal": "g",
            },
        )
        assert len(p.calls) == 1

    def test_no_providers_returns_false(self):
        mgr = NotificationManager(providers=[])
        result = mgr.notify(
            "session_started",
            {
                "session_id": "s1",
                "role_name": "r",
                "goal": "g",
            },
        )
        assert result is False


class TestProviderInstantiation:
    def test_email_provider_name(self):
        p = EmailProvider()
        assert p.provider_name == "email"

    def test_webhook_provider_name(self):
        p = WebhookProvider(url="http://example.com/hook")
        assert p.provider_name == "webhook"

    def test_desktop_provider_name(self):
        p = DesktopProvider()
        assert p.provider_name == "desktop"
