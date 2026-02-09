"""
Orion Agent — Discord Bridge (v6.8.0)

Bidirectional Discord bot bridge. Users interact with Orion by
messaging the bot in a DM or mentioning it in a server channel.

Requirements:
    pip install discord.py>=2.3

Setup:
    1. Create a Discord app at discord.com/developers/applications
    2. Bot → create bot → copy Token
    3. OAuth2 → URL Generator → scopes: bot → permissions: Send Messages, Read Message History
    4. Use the generated URL to invite the bot to your server
    5. In Orion CLI: /bridge enable discord <token>
    6. DM the bot on Discord with the passphrase
"""

import asyncio
from typing import Optional

from orion.bridges.base import MessagingBridge, BridgeConfig, BridgeMessage


class DiscordBridge(MessagingBridge):
    """Discord bot bridge using discord.py."""

    def __init__(self, config: BridgeConfig):
        super().__init__(config)
        self._client = None
        self._task = None

    async def start(self):
        """Start the Discord bot."""
        try:
            import discord
        except ImportError:
            if self._log:
                self._log.error("Bridge", "discord.py not installed. "
                                "Run: pip install discord.py")
            return

        if not self.config.token:
            if self._log:
                self._log.error("Bridge", "No Discord bot token configured")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True

        self._client = discord.Client(intents=intents)
        bridge_ref = self

        @self._client.event
        async def on_ready():
            if bridge_ref._log:
                bridge_ref._log.info("Bridge",
                    f"Discord bridge connected as {self._client.user}")
            bridge_ref._running = True

        @self._client.event
        async def on_message(message):
            # Ignore own messages
            if message.author == self._client.user:
                return

            # Only respond to DMs or mentions
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mention = self._client.user in message.mentions if message.mentions else False

            if not is_dm and not is_mention:
                return

            text = message.content
            # Strip mention from text
            if is_mention and self._client.user:
                text = text.replace(f"<@{self._client.user.id}>", "").strip()

            if not text:
                return

            msg = BridgeMessage(
                platform="discord",
                user_id=str(message.author.id),
                chat_id=str(message.channel.id),
                text=text,
                display_name=str(message.author),
                message_id=str(message.id),
            )
            await bridge_ref.handle_inbound(msg)

        if self._log:
            self._log.info("Bridge", "Discord bridge starting...")

        # Run in background task
        self._task = asyncio.create_task(
            self._client.start(self.config.token)
        )

    async def stop(self):
        """Stop the Discord bot."""
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
        self._running = False
        if self._log:
            self._log.info("Bridge", "Discord bridge stopped")

    async def send(self, chat_id: str, text: str, **kwargs):
        """Send a message to a Discord channel/DM."""
        if not self._client:
            return

        try:
            channel = self._client.get_channel(int(chat_id))
            if channel is None:
                channel = await self._client.fetch_channel(int(chat_id))

            # Discord max message length is 2000
            if len(text) > 2000:
                chunks = [text[i:i+1990] for i in range(0, len(text), 1990)]
                for chunk in chunks:
                    await channel.send(chunk)
            else:
                await channel.send(text)
        except Exception as e:
            if self._log:
                self._log.error("Bridge", f"Discord send failed: {e}")

    async def send_approval_prompt(self, chat_id: str, prompt: str,
                                   approval_id: str) -> None:
        """Send an AEGIS approval request with Discord buttons."""
        if not self._client:
            return

        try:
            import discord

            channel = self._client.get_channel(int(chat_id))
            if channel is None:
                channel = await self._client.fetch_channel(int(chat_id))

            view = discord.ui.View(timeout=120)

            approve_btn = discord.ui.Button(
                label="Approve",
                style=discord.ButtonStyle.green,
                custom_id=f"aegis_approve:{approval_id}",
            )
            deny_btn = discord.ui.Button(
                label="Deny",
                style=discord.ButtonStyle.red,
                custom_id=f"aegis_deny:{approval_id}",
            )

            async def approve_callback(interaction):
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"http://localhost:8000/api/aegis/respond/{approval_id}",
                            json={"approved": True}, timeout=10,
                        )
                except Exception:
                    pass
                await interaction.response.edit_message(
                    content=f"⚠️ AEGIS APPROVAL\n\n{prompt}\n\n✅ Approved by {interaction.user}",
                    view=None,
                )

            async def deny_callback(interaction):
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"http://localhost:8000/api/aegis/respond/{approval_id}",
                            json={"approved": False}, timeout=10,
                        )
                except Exception:
                    pass
                await interaction.response.edit_message(
                    content=f"⚠️ AEGIS APPROVAL\n\n{prompt}\n\n❌ Denied by {interaction.user}",
                    view=None,
                )

            approve_btn.callback = approve_callback
            deny_btn.callback = deny_callback
            view.add_item(approve_btn)
            view.add_item(deny_btn)

            await channel.send(
                f"⚠️ **AEGIS APPROVAL REQUIRED**\n\n{prompt}",
                view=view,
            )
        except Exception:
            await self.send(chat_id, f"⚠️ AEGIS APPROVAL REQUIRED\n\n{prompt}\n\n(Auto-denied — button support unavailable)")
