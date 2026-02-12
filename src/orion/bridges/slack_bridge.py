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
Orion Agent -- Slack Bridge (v6.8.0)

Bidirectional Slack bot bridge. Users interact with Orion by messaging
the bot in a DM or mentioning it in a channel.

Requirements:
    pip install slack-bolt>=1.18

Setup:
    1. Create a Slack app at api.slack.com/apps
    2. Enable Socket Mode (no public URL needed)
    3. Add Bot Token Scopes: chat:write, app_mentions:read, im:history, im:read
    4. Install to workspace -> copy Bot Token + App Token
    5. In Orion CLI: /bridge enable slack <bot_token> --app-token <app_token>
    6. Message the bot on Slack with the passphrase
"""

import contextlib

from orion.bridges.base import BridgeConfig, BridgeMessage, MessagingBridge


class SlackBridge(MessagingBridge):
    """Slack bot bridge using slack-bolt (Socket Mode -- no public URL needed)."""

    def __init__(self, config: BridgeConfig):
        super().__init__(config)
        self._bolt_app = None
        self._handler = None

    async def start(self):
        """Start the Slack bot with Socket Mode."""
        try:
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
            from slack_bolt.async_app import AsyncApp
        except ImportError:
            if self._log:
                self._log.error("Bridge", "slack-bolt not installed. Run: pip install slack-bolt")
            return

        if not self.config.token:
            if self._log:
                self._log.error("Bridge", "No Slack bot token configured")
            return

        # Extract app token from metadata if stored
        app_token = self.config.__dict__.get("app_token", "")
        if not app_token:
            # Try environment
            import os

            app_token = os.environ.get("SLACK_APP_TOKEN", "")

        self._bolt_app = AsyncApp(token=self.config.token)

        bridge_ref = self

        @self._bolt_app.message("")
        async def on_message(message, say):
            text = message.get("text", "")
            user_id = message.get("user", "")
            channel = message.get("channel", "")

            if not text or not user_id:
                return

            msg = BridgeMessage(
                platform="slack",
                user_id=user_id,
                chat_id=channel,
                text=text,
                message_id=message.get("ts", ""),
            )
            await bridge_ref.handle_inbound(msg)

        @self._bolt_app.event("app_mention")
        async def on_mention(event, say):
            text = event.get("text", "")
            user_id = event.get("user", "")
            channel = event.get("channel", "")

            # Strip the bot mention from text
            import re

            text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

            if not text:
                return

            msg = BridgeMessage(
                platform="slack",
                user_id=user_id,
                chat_id=channel,
                text=text,
                message_id=event.get("ts", ""),
            )
            await bridge_ref.handle_inbound(msg)

        self._running = True
        if self._log:
            self._log.info("Bridge", "Slack bridge started (Socket Mode)")

        if app_token:
            self._handler = AsyncSocketModeHandler(self._bolt_app, app_token)
            await self._handler.start_async()
        else:
            if self._log:
                self._log.warn(
                    "Bridge",
                    "No SLACK_APP_TOKEN -- Socket Mode unavailable. "
                    "Set SLACK_APP_TOKEN env var for real-time messaging.",
                )

    async def stop(self):
        """Stop the Slack bot."""
        if self._handler:
            with contextlib.suppress(Exception):
                await self._handler.close_async()
        self._running = False
        if self._log:
            self._log.info("Bridge", "Slack bridge stopped")

    async def send(self, chat_id: str, text: str, **kwargs):
        """Send a message to a Slack channel/DM."""
        if not self._bolt_app:
            return

        try:
            from slack_sdk.web.async_client import AsyncWebClient

            client = AsyncWebClient(token=self.config.token)
            await client.chat_postMessage(channel=chat_id, text=text)
        except Exception as e:
            if self._log:
                self._log.error("Bridge", f"Slack send failed: {e}")

    async def send_approval_prompt(self, chat_id: str, prompt: str, approval_id: str) -> None:
        """Send an AEGIS approval request with Slack action buttons."""
        if not self._bolt_app:
            return

        try:
            from slack_sdk.web.async_client import AsyncWebClient

            client = AsyncWebClient(token=self.config.token)

            blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"⚠️ *AEGIS APPROVAL REQUIRED*\n\n{prompt}"},
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "✅ Approve"},
                            "style": "primary",
                            "action_id": f"aegis_approve_{approval_id}",
                            "value": approval_id,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "❌ Deny"},
                            "style": "danger",
                            "action_id": f"aegis_deny_{approval_id}",
                            "value": approval_id,
                        },
                    ],
                },
            ]

            await client.chat_postMessage(
                channel=chat_id,
                text=f"AEGIS Approval Required: {prompt}",
                blocks=blocks,
            )
        except Exception:
            await self.send(chat_id, f"⚠️ AEGIS APPROVAL REQUIRED\n\n{prompt}")
