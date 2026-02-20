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
"""ARA Notifications — multi-channel notification providers.

Supports email (SMTP), webhook (HTTP POST), and desktop (toast) delivery.
AEGIS-enforced: rate-limited (5/session), template-only, single recipient.

See ARA-001 §12 / Appendix C.11 for full design.
"""

from __future__ import annotations

import json
import logging
import smtplib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger("orion.ara.notifications")

MAX_NOTIFICATIONS_PER_SESSION = 5

TEMPLATES: dict[str, str] = {
    "session_started": "🚀 Orion session '{session_id}' started. Role: {role_name}. Goal: {goal}",
    "session_completed": "✅ Session '{session_id}' completed. {tasks_completed}/{tasks_total} tasks done in {elapsed}.",
    "session_failed": "❌ Session '{session_id}' failed. Error: {error}",
    "session_paused": "⏸️ Session '{session_id}' paused at task {current_task}.",
    "checkpoint_created": "💾 Checkpoint #{checkpoint_number} created for session '{session_id}'.",
    "review_ready": "📋 Session '{session_id}' ready for review. Run `orion review` to inspect changes.",
    "cost_warning": "⚠️ Session '{session_id}' approaching cost limit: ${cost_usd:.4f} / ${max_cost:.4f}.",
}


@dataclass
class Notification:
    """A single notification to be delivered."""

    template: str
    params: dict[str, Any] = field(default_factory=dict)
    subject: str | None = None
    urgency: str = "normal"  # low, normal, high
    timestamp: float = field(default_factory=time.time)

    @property
    def message(self) -> str:
        """Render the notification message from template."""
        tmpl = TEMPLATES.get(self.template, self.template)
        try:
            return tmpl.format(**self.params)
        except (KeyError, IndexError):
            return tmpl

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template,
            "params": self.params,
            "subject": self.subject,
            "urgency": self.urgency,
            "message": self.message,
            "timestamp": self.timestamp,
        }


class NotificationProvider(ABC):
    """Abstract base class for notification delivery."""

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """Send a notification. Returns True on success."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""


class EmailProvider(NotificationProvider):
    """SMTP email notification provider.

    Send-only, single recipient, template-only, AEGIS-locked.
    """

    def __init__(
        self,
        smtp_host: str = "localhost",
        smtp_port: int = 587,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        from_address: str = "orion@localhost",
        to_address: str = "user@localhost",
        use_tls: bool = True,
    ):
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._from_address = from_address
        self._to_address = to_address
        self._use_tls = use_tls

    @property
    def provider_name(self) -> str:
        return "email"

    def send(self, notification: Notification) -> bool:
        try:
            msg = MIMEMultipart()
            msg["From"] = self._from_address
            msg["To"] = self._to_address
            msg["Subject"] = notification.subject or f"Orion: {notification.template}"
            msg.attach(MIMEText(notification.message, "plain"))

            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=10) as server:
                if self._use_tls:
                    server.starttls()
                if self._smtp_user and self._smtp_password:
                    server.login(self._smtp_user, self._smtp_password)
                server.send_message(msg)

            logger.info("Email sent to %s: %s", self._to_address, notification.template)
            return True
        except Exception as e:
            logger.error("Email send failed: %s", e)
            return False


class WebhookProvider(NotificationProvider):
    """HTTP webhook notification provider.

    POSTs JSON payload to a configured URL.
    """

    def __init__(self, url: str, headers: dict[str, str] | None = None, timeout: int = 10):
        self._url = url
        self._headers = headers or {"Content-Type": "application/json"}
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return "webhook"

    def send(self, notification: Notification) -> bool:
        try:
            payload = json.dumps(notification.to_dict()).encode("utf-8")
            req = Request(
                self._url,
                data=payload,
                headers=self._headers,
                method="POST",
            )
            with urlopen(req, timeout=self._timeout) as resp:
                success = 200 <= resp.status < 300
                if success:
                    logger.info("Webhook delivered to %s: %s", self._url, notification.template)
                else:
                    logger.warning("Webhook returned %d", resp.status)
                return success
        except Exception as e:
            logger.error("Webhook failed: %s", e)
            return False


class DesktopProvider(NotificationProvider):
    """Desktop toast notification provider.

    Uses platform-native notifications where available.
    Falls back to logging if no desktop notification system is found.
    """

    @property
    def provider_name(self) -> str:
        return "desktop"

    def send(self, notification: Notification) -> bool:
        try:
            title = notification.subject or f"Orion: {notification.template}"
            message = notification.message

            # Try platform-specific notification
            import platform

            if platform.system() == "Windows":
                return self._send_windows(title, message)
            elif platform.system() == "Darwin":
                return self._send_macos(title, message)
            else:
                return self._send_linux(title, message)
        except Exception as e:
            logger.warning("Desktop notification fallback: %s", e)
            logger.info("DESKTOP: %s — %s", notification.template, notification.message)
            return True

    def _send_windows(self, title: str, message: str) -> bool:
        """Windows toast notification via PowerShell."""
        import subprocess

        ps_cmd = (
            f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            f"ContentType = WindowsRuntime] > $null; "
            f"$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(0); "
            f'$text = $template.GetElementsByTagName("text"); '
            f'$text[0].AppendChild($template.CreateTextNode("{title}")) > $null; '
            f'$text[1].AppendChild($template.CreateTextNode("{message}")) > $null; '
            f'$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Orion"); '
            f"$notifier.Show([Windows.UI.Notifications.ToastNotification]::new($template))"
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0

    def _send_macos(self, title: str, message: str) -> bool:
        """macOS notification via osascript."""
        import subprocess

        result = subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0

    def _send_linux(self, title: str, message: str) -> bool:
        """Linux notification via notify-send."""
        import subprocess

        result = subprocess.run(
            ["notify-send", title, message],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0


class MessagingProvider(NotificationProvider):
    """Messaging platform notification provider (Phase 4E).

    Routes notifications to the originating messaging platform (Slack, Telegram,
    Discord, etc.) using the existing adapters in orion.integrations.messaging.
    """

    def __init__(
        self,
        platform: str = "",
        channel: str = "",
    ):
        self._platform = platform
        self._channel = channel  # user_id or channel_id on the platform

    @property
    def provider_name(self) -> str:
        return f"messaging:{self._platform}" if self._platform else "messaging"

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def channel(self) -> str:
        return self._channel

    def send(self, notification: Notification) -> bool:
        """Send notification via the messaging platform adapter."""
        if not self._platform or not self._channel:
            logger.warning("MessagingProvider not configured (platform=%s, channel=%s)",
                           self._platform, self._channel)
            return False

        try:
            from orion.integrations.messaging import get_messaging_provider

            provider = get_messaging_provider(self._platform)
            if provider is None:
                logger.warning("No messaging provider found for platform: %s", self._platform)
                return False

            # send_message is async but NotificationProvider.send is sync.
            # Use fire-and-forget scheduling via asyncio if an event loop is running,
            # otherwise log the message for later delivery.
            import asyncio

            text = notification.message
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(provider.send_message(self._channel, text))
                logger.info("Messaging notification queued for %s/%s", self._platform, self._channel)
                return True
            except RuntimeError:
                # No running event loop — attempt synchronous send
                asyncio.run(provider.send_message(self._channel, text))
                logger.info("Messaging notification sent (sync) to %s/%s", self._platform, self._channel)
                return True

        except Exception as e:
            logger.error("Messaging send failed (%s/%s): %s", self._platform, self._channel, e)
            return False


class NotificationManager:
    """Manages notification delivery across providers with AEGIS rate limiting.

    Enforces:
    - Max notifications per session (default: 5)
    - Template-only messages
    - Delivery tracking
    """

    def __init__(
        self,
        providers: list[NotificationProvider] | None = None,
        max_per_session: int = MAX_NOTIFICATIONS_PER_SESSION,
    ):
        self._providers = providers or []
        self._max_per_session = max_per_session
        self._sent_count = 0
        self._history: list[dict[str, Any]] = []

    @property
    def sent_count(self) -> int:
        return self._sent_count

    @property
    def remaining(self) -> int:
        return max(0, self._max_per_session - self._sent_count)

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def add_provider(self, provider: NotificationProvider) -> None:
        self._providers.append(provider)

    def notify(self, template: str, params: dict[str, Any] | None = None, **kwargs: Any) -> bool:
        """Send a notification to all configured providers.

        Returns True if at least one provider succeeded.
        """
        if self._sent_count >= self._max_per_session:
            logger.warning(
                "Notification rate limit reached (%d/%d)",
                self._sent_count,
                self._max_per_session,
            )
            return False

        if template not in TEMPLATES:
            logger.warning("Unknown notification template: %s", template)
            return False

        notification = Notification(
            template=template,
            params=params or {},
            **kwargs,
        )

        successes = 0
        for provider in self._providers:
            try:
                if provider.send(notification):
                    successes += 1
            except Exception as e:
                logger.error("Provider %s failed: %s", provider.provider_name, e)

        self._sent_count += 1
        self._history.append(
            {
                "template": template,
                "timestamp": notification.timestamp,
                "providers_attempted": len(self._providers),
                "providers_succeeded": successes,
            }
        )

        return successes > 0

    def enable_messaging(self, platform: str, channel: str) -> MessagingProvider:
        """Wire a messaging platform as an additional notification provider.

        Call this when a session originates from a messaging platform so that
        all subsequent ``notify()`` calls also reach the originating user.

        Returns the created MessagingProvider instance.
        """
        mp = MessagingProvider(platform=platform, channel=channel)
        self.add_provider(mp)
        logger.info("Messaging notifications enabled for %s/%s", platform, channel)
        return mp

    @property
    def messaging_provider(self) -> MessagingProvider | None:
        """Return the first MessagingProvider attached, or None."""
        for p in self._providers:
            if isinstance(p, MessagingProvider):
                return p
        return None

    def reset(self) -> None:
        """Reset notification counter (for new session)."""
        self._sent_count = 0
        self._history.clear()
