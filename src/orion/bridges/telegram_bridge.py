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
Orion Agent -- Telegram Bridge (v6.8.0)

Bidirectional Telegram bot bridge. Users interact with Orion by
messaging the bot. Security enforced via chat ID allowlist +
passphrase authentication.

Requirements:
    pip install python-telegram-bot>=20.0

Setup:
    1. Message @BotFather on Telegram -> /newbot -> get the token
    2. In Orion CLI: /bridge enable telegram <token>
    3. Copy the passphrase Orion generates
    4. Message your bot on Telegram with the passphrase
    5. You're connected -- start chatting with Orion
"""

import asyncio
from typing import Optional

from orion.bridges.base import MessagingBridge, BridgeConfig, BridgeMessage


class TelegramBridge(MessagingBridge):
    """Telegram bot bridge using python-telegram-bot (async)."""

    def __init__(self, config: BridgeConfig):
        super().__init__(config)
        self._app = None  # telegram.ext.Application

    async def start(self):
        """Start the Telegram bot with long polling."""
        try:
            from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
            from telegram.ext import (
                Application, MessageHandler, CallbackQueryHandler,
                filters, ContextTypes,
            )
        except ImportError:
            if self._log:
                self._log.error("Bridge", "python-telegram-bot not installed. "
                                "Run: pip install python-telegram-bot")
            return

        if not self.config.token:
            if self._log:
                self._log.error("Bridge", "No Telegram bot token configured")
            return

        # Build the application
        self._app = Application.builder().token(self.config.token).build()

        # Message handler
        async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return

            msg = BridgeMessage(
                platform="telegram",
                user_id=str(update.effective_user.id),
                chat_id=str(update.effective_chat.id),
                text=update.message.text,
                display_name=update.effective_user.full_name or "",
                message_id=str(update.message.message_id),
            )
            await self.handle_inbound(msg)

        # Callback query handler (for AEGIS inline buttons)
        async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()

            data = query.data or ""
            # Format: "aegis_approve:<id>" or "aegis_deny:<id>"
            if data.startswith("aegis_"):
                parts = data.split(":", 1)
                if len(parts) == 2:
                    action = parts[0]  # aegis_approve or aegis_deny
                    approval_id = parts[1]
                    approved = action == "aegis_approve"

                    try:
                        import httpx
                        async with httpx.AsyncClient() as client:
                            await client.post(
                                f"http://localhost:8001/api/aegis/respond/{approval_id}",
                                json={"approved": approved},
                                timeout=10,
                            )
                    except Exception:
                        pass

                    result = "✅ Approved" if approved else "❌ Denied"
                    await query.edit_message_text(
                        f"{query.message.text}\n\n{result} by {update.effective_user.full_name}"
                    )

        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
        self._app.add_handler(MessageHandler(filters.COMMAND, on_message))
        self._app.add_handler(CallbackQueryHandler(on_callback))

        self._running = True
        if self._log:
            self._log.info("Bridge", "Telegram bridge started (long polling)")

        # Run polling in background
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

    async def stop(self):
        """Stop the Telegram bot."""
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception:
                pass
        self._running = False
        if self._log:
            self._log.info("Bridge", "Telegram bridge stopped")

    async def send(self, chat_id: str, text: str, **kwargs):
        """Send a message to a Telegram chat."""
        if not self._app or not self._app.bot:
            return

        # Telegram max message length is 4096
        if len(text) > 4096:
            # Split into chunks
            chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for chunk in chunks:
                await self._app.bot.send_message(
                    chat_id=int(chat_id),
                    text=chunk,
                    parse_mode=kwargs.get("parse_mode", None),
                )
        else:
            await self._app.bot.send_message(
                chat_id=int(chat_id),
                text=text,
                parse_mode=kwargs.get("parse_mode", None),
            )

    async def send_approval_prompt(self, chat_id: str, prompt: str,
                                   approval_id: str) -> None:
        """Send an AEGIS approval request with inline keyboard buttons."""
        if not self._app or not self._app.bot:
            return

        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"aegis_approve:{approval_id}"),
                    InlineKeyboardButton("❌ Deny", callback_data=f"aegis_deny:{approval_id}"),
                ]
            ])

            await self._app.bot.send_message(
                chat_id=int(chat_id),
                text=f"⚠️ *AEGIS APPROVAL REQUIRED*\n\n{prompt}\n\nThis action requires your approval.",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        except Exception as e:
            # Fallback without buttons
            await self.send(chat_id, f"⚠️ AEGIS APPROVAL REQUIRED\n\n{prompt}\n\n(Auto-denied -- button support unavailable)")
