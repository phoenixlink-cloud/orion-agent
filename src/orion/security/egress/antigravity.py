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
"""Antigravity headless integration for Phase 2.

Antigravity is a VS Code fork that brokers LLM access through a Google
subscription. Orion interacts with it via headless browser automation
(Playwright/Puppeteer) inside the Docker sandbox.

Architecture (from Milestone Document):
  Orion --> Playwright --> Antigravity (headless) --> Google LLM API
                                                  --> Gemini 3 Pro
                                                  --> Claude Sonnet
                                                  --> GPT (via Google)

The Antigravity instance:
  - Runs inside the Docker sandbox (same container or sidecar)
  - Authenticates with the dedicated Google account (read-only creds)
  - Provides a web UI that Orion automates headlessly
  - All traffic goes through the egress proxy

This module provides:
  1. AntigravityConfig: Configuration for the Antigravity instance
  2. AntigravitySession: Manages a headless browser session
  3. AntigravityBridge: High-level API for sending LLM requests
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("orion.security.egress.antigravity")


class AntigravityProvider(str, Enum):
    """LLM providers accessible through Antigravity's Google subscription."""

    GEMINI_PRO = "gemini-pro"
    CLAUDE_SONNET = "claude-sonnet"
    GPT = "gpt"


class SessionState(str, Enum):
    """State of the Antigravity browser session."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class AntigravityConfig:
    """Configuration for the Antigravity headless instance."""

    # Antigravity server URL (inside Docker or sidecar)
    server_url: str = "http://localhost:3100"

    # Browser automation settings
    headless: bool = True
    browser_timeout_ms: int = 30000
    navigation_timeout_ms: int = 15000

    # Google credentials file (read-only mount from host)
    credentials_path: str = "/home/orion/.orion/google_credentials.json"

    # Retry settings
    max_retries: int = 3
    retry_delay_s: float = 2.0

    # Session management
    session_timeout_s: float = 3600.0  # 1 hour
    idle_timeout_s: float = 300.0  # 5 minutes

    # Available providers (from Google subscription)
    available_providers: list[str] = field(
        default_factory=lambda: [
            AntigravityProvider.GEMINI_PRO.value,
            AntigravityProvider.CLAUDE_SONNET.value,
            AntigravityProvider.GPT.value,
        ]
    )

    def to_dict(self) -> dict:
        return {
            "server_url": self.server_url,
            "headless": self.headless,
            "browser_timeout_ms": self.browser_timeout_ms,
            "credentials_path": self.credentials_path,
            "max_retries": self.max_retries,
            "session_timeout_s": self.session_timeout_s,
            "available_providers": self.available_providers,
        }


@dataclass
class LLMRequest:
    """A request to send to an LLM through Antigravity."""

    provider: str
    model: str
    messages: list[dict[str, str]]
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    system_prompt: str = ""

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "messages": self.messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
            "system_prompt": self.system_prompt,
        }


@dataclass
class LLMResponse:
    """Response from an LLM through Antigravity."""

    content: str = ""
    provider: str = ""
    model: str = ""
    finish_reason: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str = ""

    @property
    def success(self) -> bool:
        return bool(self.content) and not self.error

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "provider": self.provider,
            "model": self.model,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "success": self.success,
        }


class AntigravitySession:
    """Manages a headless browser session with Antigravity.

    This class handles the browser lifecycle: launch, authentication,
    navigation, and cleanup. It uses Playwright for browser automation.

    The session runs inside the Docker sandbox and communicates with
    the Antigravity server through the internal Docker network.
    """

    def __init__(self, config: AntigravityConfig | None = None) -> None:
        self._config = config or AntigravityConfig()
        self._state = SessionState.DISCONNECTED
        self._browser = None  # Playwright browser instance
        self._context = None  # Browser context
        self._page = None  # Active page
        self._created_at = 0.0
        self._last_activity = 0.0
        self._request_count = 0

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def is_ready(self) -> bool:
        return self._state == SessionState.READY

    @property
    def request_count(self) -> int:
        return self._request_count

    async def connect(self) -> bool:
        """Launch the headless browser and connect to Antigravity.

        Returns:
            True if connected and authenticated successfully.
        """
        if self._state in (SessionState.READY, SessionState.BUSY):
            return True

        self._state = SessionState.CONNECTING
        self._created_at = time.time()

        try:
            # Import Playwright (only available inside Docker with deps)
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                logger.error(
                    "Playwright not available. Install with: pip install playwright && playwright install chromium"
                )
                self._state = SessionState.ERROR
                return False

            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch(
                headless=self._config.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
            )
            self._page = await self._context.new_page()
            self._page.set_default_timeout(self._config.browser_timeout_ms)

            # Navigate to Antigravity
            logger.info("Connecting to Antigravity at %s", self._config.server_url)
            await self._page.goto(
                self._config.server_url,
                timeout=self._config.navigation_timeout_ms,
            )

            # Authenticate with Google credentials
            self._state = SessionState.AUTHENTICATING
            authenticated = await self._authenticate()
            if not authenticated:
                self._state = SessionState.ERROR
                return False

            self._state = SessionState.READY
            self._last_activity = time.time()
            logger.info("Antigravity session ready")
            return True

        except Exception as exc:
            logger.error("Failed to connect to Antigravity: %s", exc)
            self._state = SessionState.ERROR
            return False

    async def disconnect(self) -> None:
        """Close the browser session."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
        except Exception as exc:
            logger.debug("Error during disconnect: %s", exc)
        finally:
            self._browser = None
            self._context = None
            self._page = None
            self._state = SessionState.DISCONNECTED
            logger.info("Antigravity session disconnected (requests: %d)", self._request_count)

    async def send_request(self, request: LLMRequest) -> LLMResponse:
        """Send an LLM request through Antigravity.

        This automates the Antigravity UI to submit a prompt and
        capture the response.

        Args:
            request: The LLM request to send.

        Returns:
            LLMResponse with the result or error.
        """
        if self._state != SessionState.READY:
            return LLMResponse(error=f"Session not ready (state: {self._state.value})")

        self._state = SessionState.BUSY
        start_time = time.time()

        try:
            # Select the provider/model in the Antigravity UI
            await self._select_provider(request.provider, request.model)

            # Enter the prompt
            prompt_text = self._format_prompt(request)
            await self._enter_prompt(prompt_text)

            # Wait for and capture the response
            response_text = await self._capture_response()

            duration_ms = (time.time() - start_time) * 1000
            self._request_count += 1
            self._last_activity = time.time()
            self._state = SessionState.READY

            return LLMResponse(
                content=response_text,
                provider=request.provider,
                model=request.model,
                finish_reason="stop",
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("Antigravity request failed: %s", exc)
            self._state = SessionState.READY  # Recover to ready state
            return LLMResponse(
                error=str(exc),
                provider=request.provider,
                model=request.model,
                duration_ms=duration_ms,
            )

    async def _authenticate(self) -> bool:
        """Authenticate with the Google account in Antigravity.

        Reads credentials from the mounted file and fills in the
        Google sign-in form.

        Returns:
            True if authentication succeeded.
        """
        try:
            import json as _json
            from pathlib import Path

            creds_path = Path(self._config.credentials_path)
            if not creds_path.exists():
                logger.error("Google credentials file not found: %s", creds_path)
                return False

            creds = _json.loads(creds_path.read_text(encoding="utf-8"))
            access_token = creds.get("access_token", "")
            if not access_token:
                logger.error("No access token in credentials file")
                return False

            # Wait for Antigravity to be ready and inject the token
            # The exact automation depends on Antigravity's UI structure.
            # This is a placeholder that will be refined when Antigravity
            # is available for integration testing.
            await self._page.wait_for_load_state("networkidle")

            # Try to find and click a sign-in button
            sign_in = self._page.locator('[data-testid="sign-in"], button:has-text("Sign in")')
            if await sign_in.count() > 0:
                await sign_in.first.click()
                await self._page.wait_for_load_state("networkidle")

            logger.info("Authentication flow completed")
            return True

        except Exception as exc:
            logger.error("Authentication failed: %s", exc)
            return False

    async def _select_provider(self, provider: str, model: str) -> None:
        """Select the LLM provider and model in the Antigravity UI."""
        # This interacts with Antigravity's model selector
        # The exact selectors depend on Antigravity's UI structure
        selector = self._page.locator('[data-testid="model-selector"], select.model-select')
        if await selector.count() > 0:
            await selector.first.select_option(label=model)
            await self._page.wait_for_timeout(500)

    async def _enter_prompt(self, prompt: str) -> None:
        """Enter a prompt into the Antigravity chat input."""
        # Find the chat input field
        input_field = self._page.locator(
            '[data-testid="chat-input"], textarea.chat-input, [contenteditable="true"]'
        )
        if await input_field.count() > 0:
            await input_field.first.fill(prompt)
            # Submit the prompt
            await self._page.keyboard.press("Enter")
        else:
            raise RuntimeError("Could not find chat input field in Antigravity UI")

    async def _capture_response(self) -> str:
        """Wait for and capture the LLM response from Antigravity."""
        # Wait for the response to appear
        # The response element depends on Antigravity's UI structure
        response_selector = '[data-testid="response"], .assistant-message, .chat-response'

        try:
            await self._page.wait_for_selector(
                response_selector,
                timeout=self._config.browser_timeout_ms,
                state="visible",
            )

            # Wait for the response to finish generating
            # (look for a "done" indicator or wait for text to stabilize)
            await self._page.wait_for_timeout(1000)

            # Get all response elements and return the last one
            responses = self._page.locator(response_selector)
            count = await responses.count()
            if count > 0:
                return await responses.nth(count - 1).inner_text()

            return ""

        except Exception as exc:
            logger.warning("Response capture failed: %s", exc)
            raise RuntimeError(f"Failed to capture response: {exc}")

    def _format_prompt(self, request: LLMRequest) -> str:
        """Format an LLM request into a prompt string for the UI."""
        parts = []
        if request.system_prompt:
            parts.append(f"[System: {request.system_prompt}]")
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System: {content}]")
            elif role == "user":
                parts.append(content)
            elif role == "assistant":
                parts.append(f"[Previous response: {content}]")
        return "\n".join(parts)

    def get_status(self) -> dict:
        """Get session status for dashboard display."""
        return {
            "state": self._state.value,
            "server_url": self._config.server_url,
            "headless": self._config.headless,
            "created_at": self._created_at,
            "last_activity": self._last_activity,
            "request_count": self._request_count,
            "available_providers": self._config.available_providers,
            "session_age_s": time.time() - self._created_at if self._created_at else 0,
            "idle_s": time.time() - self._last_activity if self._last_activity else 0,
        }


class AntigravityBridge:
    """High-level bridge between Orion's LLM provider system and Antigravity.

    This class provides an interface compatible with Orion's existing
    `call_provider()` pattern, translating standard LLM requests into
    Antigravity headless browser interactions.

    Usage:
        bridge = AntigravityBridge()
        await bridge.initialize()

        response = await bridge.chat(
            provider="gemini-pro",
            model="gemini-3-pro",
            messages=[{"role": "user", "content": "Hello!"}],
        )

        await bridge.shutdown()
    """

    def __init__(self, config: AntigravityConfig | None = None) -> None:
        self._config = config or AntigravityConfig()
        self._session: AntigravitySession | None = None
        self._initialized = False
        self._total_requests = 0
        self._total_errors = 0

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_ready(self) -> bool:
        return self._initialized and self._session is not None and self._session.is_ready

    async def initialize(self) -> bool:
        """Initialize the Antigravity bridge.

        Creates a session and connects to the Antigravity instance.

        Returns:
            True if initialization succeeded.
        """
        if self._initialized:
            return True

        self._session = AntigravitySession(self._config)
        success = await self._session.connect()
        self._initialized = success
        return success

    async def shutdown(self) -> None:
        """Shutdown the Antigravity bridge."""
        if self._session:
            await self._session.disconnect()
        self._session = None
        self._initialized = False
        logger.info(
            "Antigravity bridge shutdown (requests: %d, errors: %d)",
            self._total_requests,
            self._total_errors,
        )

    async def chat(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str = "",
    ) -> LLMResponse:
        """Send a chat request through Antigravity.

        This is the main entry point, compatible with Orion's
        provider pattern.

        Args:
            provider: The LLM provider (gemini-pro, claude-sonnet, gpt).
            model: The specific model name.
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature.
            max_tokens: Maximum response tokens.
            system_prompt: Optional system prompt.

        Returns:
            LLMResponse with the result.
        """
        if not self.is_ready:
            # Try to initialize if not ready
            if not await self.initialize():
                return LLMResponse(error="Antigravity bridge not ready")

        request = LLMRequest(
            provider=provider,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )

        self._total_requests += 1

        # Retry logic
        last_error = ""
        for attempt in range(self._config.max_retries):
            response = await self._session.send_request(request)
            if response.success:
                return response

            last_error = response.error
            logger.warning(
                "Antigravity request attempt %d/%d failed: %s",
                attempt + 1,
                self._config.max_retries,
                last_error,
            )

            if attempt < self._config.max_retries - 1:
                await asyncio.sleep(self._config.retry_delay_s)

        self._total_errors += 1
        return LLMResponse(
            error=f"All {self._config.max_retries} attempts failed: {last_error}",
            provider=provider,
            model=model,
        )

    def get_available_providers(self) -> list[dict]:
        """Get the list of available LLM providers through Antigravity."""
        return [
            {
                "id": AntigravityProvider.GEMINI_PRO.value,
                "name": "Gemini 3 Pro",
                "description": "Google's frontier model via subscription",
                "models": ["gemini-3-pro", "gemini-3-flash"],
            },
            {
                "id": AntigravityProvider.CLAUDE_SONNET.value,
                "name": "Claude Sonnet",
                "description": "Anthropic's Claude via Google subscription",
                "models": ["claude-sonnet-4", "claude-sonnet-3.5"],
            },
            {
                "id": AntigravityProvider.GPT.value,
                "name": "GPT",
                "description": "OpenAI's GPT via Google subscription",
                "models": ["gpt-4o", "gpt-4o-mini"],
            },
        ]

    def get_status(self) -> dict:
        """Get bridge status for dashboard display."""
        session_status = self._session.get_status() if self._session else {}
        return {
            "initialized": self._initialized,
            "ready": self.is_ready,
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": (
                self._total_errors / self._total_requests if self._total_requests > 0 else 0
            ),
            "session": session_status,
            "config": self._config.to_dict(),
        }
