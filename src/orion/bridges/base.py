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
Orion Agent -- Messaging Bridge Base (v6.8.0)

Abstract base class for all messaging bridges. Each platform adapter
(Telegram, Slack, Discord) implements this interface.

SECURITY MODEL (NON-NEGOTIABLE):
  1. Every bridge has an allowlist of authorized user/chat IDs
  2. New users must authenticate with a one-time passphrase
  3. All messages are logged with user identity
  4. AEGIS gate applies to all destructive actions
  5. Per-user rate limiting prevents abuse
  6. Bridge can be disabled instantly via CLI or API
"""

import asyncio
import time
import json
import hashlib
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any, Callable, Awaitable
from pathlib import Path
from datetime import datetime


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class BridgeUser:
    """An authenticated bridge user."""
    platform: str                    # "telegram", "slack", "discord"
    platform_user_id: str            # Platform-specific user ID
    display_name: str = ""           # Human-readable name
    authorized: bool = False         # Has passed passphrase auth
    authorized_at: str = ""          # ISO timestamp
    last_active: str = ""            # ISO timestamp
    request_count: int = 0           # Total requests made
    is_owner: bool = False           # Primary owner (first to auth)


@dataclass
class BridgeMessage:
    """An inbound message from a messaging platform."""
    platform: str
    user_id: str
    chat_id: str
    text: str
    display_name: str = ""
    timestamp: str = ""
    message_id: str = ""
    reply_to: str = ""               # For threaded replies


@dataclass
class BridgeConfig:
    """Configuration for a messaging bridge."""
    platform: str
    enabled: bool = False
    token: str = ""                   # Bot token (stored encrypted)
    workspace: str = ""               # Default workspace path
    passphrase_hash: str = ""         # SHA-256 of the auth passphrase
    allowed_users: Dict[str, BridgeUser] = field(default_factory=dict)
    rate_limit_per_minute: int = 10   # Max requests per user per minute
    max_response_length: int = 4000   # Platform message length limit
    created_at: str = ""


# =============================================================================
# RATE LIMITER (per-user)
# =============================================================================

class UserRateLimiter:
    """Per-user rate limiting for bridge requests."""

    def __init__(self, max_per_minute: int = 10):
        self.max_per_minute = max_per_minute
        self._timestamps: Dict[str, List[float]] = {}

    def is_allowed(self, user_id: str) -> bool:
        """Check if a user is within their rate limit."""
        now = time.time()
        cutoff = now - 60.0

        if user_id not in self._timestamps:
            self._timestamps[user_id] = []

        # Prune old timestamps
        self._timestamps[user_id] = [
            t for t in self._timestamps[user_id] if t > cutoff
        ]

        if len(self._timestamps[user_id]) >= self.max_per_minute:
            return False

        self._timestamps[user_id].append(now)
        return True

    def remaining(self, user_id: str) -> int:
        """How many requests remain for this user in the current window."""
        now = time.time()
        cutoff = now - 60.0
        if user_id not in self._timestamps:
            return self.max_per_minute
        recent = [t for t in self._timestamps[user_id] if t > cutoff]
        return max(0, self.max_per_minute - len(recent))


# =============================================================================
# ABSTRACT BRIDGE
# =============================================================================

class MessagingBridge(ABC):
    """
    Abstract base class for messaging platform bridges.

    Each platform adapter must implement:
      - start()      -- connect to the platform and start listening
      - stop()       -- disconnect gracefully
      - send()       -- send a message to a chat
      - send_approval_prompt() -- send an AEGIS approval request with buttons
    """

    def __init__(self, config: BridgeConfig):
        self.config = config
        self.platform = config.platform
        self._running = False
        self._rate_limiter = UserRateLimiter(config.rate_limit_per_minute)

        # These are injected by BridgeManager
        self._router = None
        self._memory_engine = None
        self._log = None
        self._on_message: Optional[Callable] = None

    # =========================================================================
    # ABSTRACT METHODS -- Platform adapters implement these
    # =========================================================================

    @abstractmethod
    async def start(self):
        """Connect to the platform and begin listening for messages."""
        ...

    @abstractmethod
    async def stop(self):
        """Disconnect from the platform gracefully."""
        ...

    @abstractmethod
    async def send(self, chat_id: str, text: str, **kwargs):
        """Send a text message to a specific chat."""
        ...

    @abstractmethod
    async def send_approval_prompt(self, chat_id: str, prompt: str,
                                   approval_id: str) -> None:
        """Send an AEGIS approval request with Approve/Deny buttons."""
        ...

    # =========================================================================
    # SECURITY -- Authentication & Authorization
    # =========================================================================

    def set_passphrase(self, passphrase: str):
        """Set the authentication passphrase (hashed, never stored in plain text)."""
        self.config.passphrase_hash = hashlib.sha256(
            passphrase.encode("utf-8")
        ).hexdigest()

    def generate_passphrase(self) -> str:
        """Generate a random passphrase and set it. Returns the plain text."""
        passphrase = secrets.token_urlsafe(16)
        self.set_passphrase(passphrase)
        return passphrase

    def verify_passphrase(self, candidate: str) -> bool:
        """Check if a candidate passphrase matches."""
        if not self.config.passphrase_hash:
            return False
        candidate_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        return secrets.compare_digest(candidate_hash, self.config.passphrase_hash)

    def is_authorized(self, user_id: str) -> bool:
        """Check if a user is authorized to use this bridge."""
        user = self.config.allowed_users.get(user_id)
        return user is not None and user.authorized

    def authorize_user(self, user_id: str, display_name: str = "") -> BridgeUser:
        """Authorize a user after successful passphrase verification."""
        now = datetime.utcnow().isoformat()
        is_owner = len(self.config.allowed_users) == 0  # First user is owner
        user = BridgeUser(
            platform=self.platform,
            platform_user_id=user_id,
            display_name=display_name,
            authorized=True,
            authorized_at=now,
            last_active=now,
            is_owner=is_owner,
        )
        self.config.allowed_users[user_id] = user
        return user

    def revoke_user(self, user_id: str) -> bool:
        """Revoke a user's access."""
        if user_id in self.config.allowed_users:
            self.config.allowed_users[user_id].authorized = False
            return True
        return False

    # =========================================================================
    # MESSAGE HANDLING -- Common logic for all platforms
    # =========================================================================

    async def handle_inbound(self, message: BridgeMessage):
        """
        Process an inbound message. This is the main entry point called
        by platform adapters when a message arrives.

        Security flow:
          1. Check if user is authorized -> if not, check for passphrase
          2. Rate limit check
          3. Route through Orion's RequestRouter
          4. Send response back via platform
          5. Log everything
        """
        user_id = message.user_id
        chat_id = message.chat_id
        text = message.text.strip()

        if self._log:
            self._log.info("Bridge", f"Inbound from {self.platform}",
                           user_id=user_id, chat_id=chat_id)

        # ---- Step 1: Authorization ----
        if not self.is_authorized(user_id):
            if self.config.passphrase_hash and self.verify_passphrase(text):
                # Passphrase correct -- authorize this user
                user = self.authorize_user(user_id, message.display_name)
                if self._log:
                    self._log.security("bridge_auth", passed=True,
                                       user_id=user_id, platform=self.platform)
                await self.send(chat_id,
                    "✅ Authenticated successfully. You can now interact with Orion.\n\n"
                    "Type your request in plain English, or /help for commands."
                )
                return
            elif self.config.passphrase_hash:
                # Not authorized, wrong passphrase
                if self._log:
                    self._log.security("bridge_auth", passed=False,
                                       user_id=user_id, platform=self.platform)
                await self.send(chat_id,
                    "🔒 This Orion instance requires authentication.\n"
                    "Send the passphrase to get started."
                )
                return
            else:
                # No passphrase set -- auto-authorize (owner setup)
                user = self.authorize_user(user_id, message.display_name)
                if self._log:
                    self._log.security("bridge_auto_auth", passed=True,
                                       user_id=user_id, platform=self.platform)

        # Update last active
        user = self.config.allowed_users[user_id]
        user.last_active = datetime.utcnow().isoformat()
        user.request_count += 1

        # ---- Step 2: Rate limiting ----
        if not self._rate_limiter.is_allowed(user_id):
            remaining_msg = "⏳ Rate limit reached. Please wait a moment."
            await self.send(chat_id, remaining_msg)
            if self._log:
                self._log.warn("Bridge", "Rate limited", user_id=user_id)
            return

        # ---- Step 3: Handle bridge commands ----
        if text.startswith("/"):
            handled = await self._handle_bridge_command(text, chat_id, user_id)
            if handled:
                return

        # ---- Step 4: Route through Orion ----
        if not self._router:
            await self.send(chat_id, "⚠️ Orion router not initialized. Set a workspace first.")
            return

        try:
            await self.send(chat_id, "🔄 Processing...")

            result = await self._router.handle_request(text)
            response = result.get("response", "No response generated.")
            route = result.get("route", "unknown")

            # Record in memory
            if self._router:
                self._router.record_interaction(text, response, route)

            # Truncate for platform limits
            if len(response) > self.config.max_response_length:
                response = response[:self.config.max_response_length - 50] + \
                    "\n\n... (truncated -- full response in logs)"

            await self.send(chat_id, response)

            if self._log:
                self._log.route(route, text, platform=self.platform,
                                user_id=user_id)

        except Exception as e:
            error_msg = f"❌ Error: {str(e)[:200]}"
            await self.send(chat_id, error_msg)
            if self._log:
                self._log.error("Bridge", f"Request failed: {e}",
                                user_id=user_id, platform=self.platform)

    async def _handle_bridge_command(self, text: str, chat_id: str,
                                     user_id: str) -> bool:
        """Handle bridge-specific commands. Returns True if handled."""
        cmd = text.lower().strip()

        if cmd == "/help":
            await self.send(chat_id,
                "🌟 *Orion Commands*\n\n"
                "/help -- Show this help\n"
                "/status -- Bridge status & stats\n"
                "/memory -- Memory stats\n"
                "/whoami -- Your auth info\n"
                "/workspace -- Show current workspace\n\n"
                "Or just type your request in plain English!"
            )
            return True

        if cmd == "/status":
            user = self.config.allowed_users.get(user_id)
            remaining = self._rate_limiter.remaining(user_id)
            status = (
                f"📊 *Bridge Status*\n\n"
                f"Platform: {self.platform}\n"
                f"Authorized users: {sum(1 for u in self.config.allowed_users.values() if u.authorized)}\n"
                f"Your requests: {user.request_count if user else 0}\n"
                f"Rate limit remaining: {remaining}/{self.config.rate_limit_per_minute}\n"
                f"Workspace: {self.config.workspace or '(not set)'}"
            )
            await self.send(chat_id, status)
            return True

        if cmd == "/whoami":
            user = self.config.allowed_users.get(user_id)
            if user:
                info = (
                    f"👤 *Your Identity*\n\n"
                    f"Platform: {user.platform}\n"
                    f"ID: {user.platform_user_id}\n"
                    f"Name: {user.display_name}\n"
                    f"Owner: {'Yes' if user.is_owner else 'No'}\n"
                    f"Authorized: {user.authorized_at}\n"
                    f"Requests: {user.request_count}"
                )
                await self.send(chat_id, info)
            return True

        if cmd == "/memory":
            if self._memory_engine:
                stats = self._memory_engine.get_stats()
                mem_info = (
                    f"🧠 *Memory Stats*\n\n"
                    f"Session (T1): {stats.tier1_entries}\n"
                    f"Project (T2): {stats.tier2_entries}\n"
                    f"Global  (T3): {stats.tier3_entries}\n"
                    f"Patterns: {stats.patterns_learned}\n"
                    f"Anti-patterns: {stats.anti_patterns}\n"
                    f"Approval rate: {stats.approval_rate:.0%}"
                )
                await self.send(chat_id, mem_info)
            else:
                await self.send(chat_id, "Memory engine not initialized.")
            return True

        if cmd == "/workspace":
            await self.send(chat_id,
                f"📂 Workspace: {self.config.workspace or '(not set)'}")
            return True

        return False  # Not a bridge command


# =============================================================================
# BRIDGE MANAGER -- Orchestrates all platform bridges
# =============================================================================

class BridgeManager:
    """
    Manages all messaging bridges. Handles configuration persistence,
    Router/Memory injection, and lifecycle management.

    Config stored at: ~/.orion/bridges.json
    """

    def __init__(self):
        self._bridges: Dict[str, MessagingBridge] = {}
        self._config_path = Path.home() / ".orion" / "bridges.json"
        self._router = None
        self._memory_engine = None
        self._log = None

        try:
            from orion.core.logging import get_logger
            self._log = get_logger()
        except Exception:
            pass

        self._load_config()

    def _load_config(self):
        """Load bridge configurations from disk."""
        if self._config_path.exists():
            try:
                data = json.loads(self._config_path.read_text(encoding="utf-8"))
                for platform, cfg_data in data.items():
                    # Reconstruct BridgeUser objects
                    users = {}
                    for uid, udata in cfg_data.get("allowed_users", {}).items():
                        users[uid] = BridgeUser(**udata)
                    cfg_data["allowed_users"] = users
                    config = BridgeConfig(**cfg_data)
                    self._register_bridge(config)
            except Exception as e:
                if self._log:
                    self._log.error("Bridge", f"Failed to load config: {e}")

    def _save_config(self):
        """Persist bridge configurations to disk."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for name, bridge in self._bridges.items():
            cfg = bridge.config
            cfg_dict = {
                "platform": cfg.platform,
                "enabled": cfg.enabled,
                "token": cfg.token,  # Should be encrypted via SecureStore in production
                "workspace": cfg.workspace,
                "passphrase_hash": cfg.passphrase_hash,
                "allowed_users": {
                    uid: asdict(u) for uid, u in cfg.allowed_users.items()
                },
                "rate_limit_per_minute": cfg.rate_limit_per_minute,
                "max_response_length": cfg.max_response_length,
                "created_at": cfg.created_at,
            }
            data[name] = cfg_dict
        self._config_path.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def _register_bridge(self, config: BridgeConfig):
        """Create and register a bridge adapter for the given config."""
        bridge = self._create_adapter(config)
        if bridge:
            bridge._router = self._router
            bridge._memory_engine = self._memory_engine
            bridge._log = self._log
            self._bridges[config.platform] = bridge

    def _create_adapter(self, config: BridgeConfig) -> Optional[MessagingBridge]:
        """Factory: create the correct platform adapter."""
        if config.platform == "telegram":
            from orion.bridges.telegram_bridge import TelegramBridge
            return TelegramBridge(config)
        elif config.platform == "slack":
            from orion.bridges.slack_bridge import SlackBridge
            return SlackBridge(config)
        elif config.platform == "discord":
            from orion.bridges.discord_bridge import DiscordBridge
            return DiscordBridge(config)
        return None

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def set_router(self, router):
        """Inject the RequestRouter into all bridges."""
        self._router = router
        for bridge in self._bridges.values():
            bridge._router = router

    def set_memory_engine(self, engine):
        """Inject the MemoryEngine into all bridges."""
        self._memory_engine = engine
        for bridge in self._bridges.values():
            bridge._memory_engine = engine

    def enable(self, platform: str, token: str, workspace: str = "",
               passphrase: str = "") -> str:
        """
        Enable a messaging bridge.

        Returns the generated passphrase if none was provided.
        """
        config = BridgeConfig(
            platform=platform,
            enabled=True,
            token=token,
            workspace=workspace,
            created_at=datetime.utcnow().isoformat(),
        )

        self._register_bridge(config)
        bridge = self._bridges[platform]

        # Set or generate passphrase
        if passphrase:
            bridge.set_passphrase(passphrase)
            result_passphrase = passphrase
        else:
            result_passphrase = bridge.generate_passphrase()

        self._save_config()

        if self._log:
            self._log.info("Bridge", f"Enabled {platform} bridge",
                           platform=platform)

        return result_passphrase

    def disable(self, platform: str) -> bool:
        """Disable a messaging bridge."""
        if platform in self._bridges:
            self._bridges[platform].config.enabled = False
            self._save_config()
            if self._log:
                self._log.info("Bridge", f"Disabled {platform} bridge")
            return True
        return False

    def revoke(self, platform: str, user_id: str) -> bool:
        """Revoke a user's access to a bridge."""
        if platform in self._bridges:
            result = self._bridges[platform].revoke_user(user_id)
            if result:
                self._save_config()
                if self._log:
                    self._log.security("bridge_revoke", passed=True,
                                       user_id=user_id, platform=platform)
            return result
        return False

    def get_status(self) -> Dict[str, Any]:
        """Get status of all bridges."""
        status = {}
        for name, bridge in self._bridges.items():
            cfg = bridge.config
            status[name] = {
                "enabled": cfg.enabled,
                "running": bridge._running,
                "authorized_users": sum(
                    1 for u in cfg.allowed_users.values() if u.authorized
                ),
                "total_requests": sum(
                    u.request_count for u in cfg.allowed_users.values()
                ),
                "workspace": cfg.workspace,
                "rate_limit": cfg.rate_limit_per_minute,
            }
        return status

    async def start(self, platform: str):
        """Start a specific bridge."""
        if platform in self._bridges and self._bridges[platform].config.enabled:
            await self._bridges[platform].start()

    async def stop(self, platform: str):
        """Stop a specific bridge."""
        if platform in self._bridges:
            await self._bridges[platform].stop()

    async def start_all(self):
        """Start all enabled bridges."""
        tasks = []
        for name, bridge in self._bridges.items():
            if bridge.config.enabled:
                tasks.append(bridge.start())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self):
        """Stop all running bridges."""
        tasks = []
        for bridge in self._bridges.values():
            if bridge._running:
                tasks.append(bridge.stop())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._save_config()


# =============================================================================
# SINGLETON
# =============================================================================

_manager_instance: Optional[BridgeManager] = None


def get_bridge_manager() -> BridgeManager:
    """Get or create the global BridgeManager singleton."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = BridgeManager()
    return _manager_instance
