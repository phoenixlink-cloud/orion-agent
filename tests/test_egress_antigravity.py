# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Antigravity headless integration."""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.security.egress.antigravity import (
    AntigravityBridge,
    AntigravityConfig,
    AntigravityProvider,
    AntigravitySession,
    LLMRequest,
    LLMResponse,
    SessionState,
)


class TestAntigravityConfig:
    """Tests for AntigravityConfig."""

    def test_default_values(self):
        config = AntigravityConfig()
        assert config.server_url == "http://localhost:3100"
        assert config.headless is True
        assert config.max_retries == 3
        assert len(config.available_providers) == 3

    def test_custom_values(self):
        config = AntigravityConfig(
            server_url="http://antigravity:4000",
            headless=False,
            max_retries=5,
        )
        assert config.server_url == "http://antigravity:4000"
        assert config.headless is False
        assert config.max_retries == 5

    def test_to_dict(self):
        config = AntigravityConfig()
        d = config.to_dict()
        assert "server_url" in d
        assert "headless" in d
        assert "available_providers" in d


class TestAntigravityProvider:
    """Tests for the provider enum."""

    def test_all_providers(self):
        assert AntigravityProvider.GEMINI_PRO.value == "gemini-pro"
        assert AntigravityProvider.CLAUDE_SONNET.value == "claude-sonnet"
        assert AntigravityProvider.GPT.value == "gpt"

    def test_provider_count(self):
        assert len(AntigravityProvider) == 3


class TestSessionState:
    """Tests for session state enum."""

    def test_all_states(self):
        states = [s.value for s in SessionState]
        assert "disconnected" in states
        assert "connecting" in states
        assert "authenticating" in states
        assert "ready" in states
        assert "busy" in states
        assert "error" in states


class TestLLMRequest:
    """Tests for LLM request data structure."""

    def test_create_request(self):
        req = LLMRequest(
            provider="gemini-pro",
            model="gemini-3-pro",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert req.provider == "gemini-pro"
        assert req.temperature == 0.7
        assert req.max_tokens == 4096

    def test_to_dict(self):
        req = LLMRequest(
            provider="gpt",
            model="gpt-4o",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.5,
        )
        d = req.to_dict()
        assert d["provider"] == "gpt"
        assert d["temperature"] == 0.5
        assert len(d["messages"]) == 1


class TestLLMResponse:
    """Tests for LLM response data structure."""

    def test_success_response(self):
        resp = LLMResponse(
            content="Hello! How can I help?",
            provider="gemini-pro",
            model="gemini-3-pro",
            finish_reason="stop",
            duration_ms=150.0,
        )
        assert resp.success is True
        assert resp.content == "Hello! How can I help?"

    def test_error_response(self):
        resp = LLMResponse(error="Connection failed")
        assert resp.success is False
        assert resp.error == "Connection failed"

    def test_empty_response_not_success(self):
        resp = LLMResponse(content="")
        assert resp.success is False

    def test_to_dict(self):
        resp = LLMResponse(
            content="test",
            provider="gpt",
            duration_ms=100.0,
        )
        d = resp.to_dict()
        assert d["success"] is True
        assert d["content"] == "test"
        assert d["duration_ms"] == 100.0


class TestAntigravitySession:
    """Tests for the Antigravity browser session."""

    def test_initial_state(self):
        session = AntigravitySession()
        assert session.state == SessionState.DISCONNECTED
        assert session.is_ready is False
        assert session.request_count == 0

    def test_get_status_disconnected(self):
        session = AntigravitySession()
        status = session.get_status()
        assert status["state"] == "disconnected"
        assert status["request_count"] == 0

    def test_format_prompt_simple(self):
        session = AntigravitySession()
        request = LLMRequest(
            provider="gemini-pro",
            model="gemini-3-pro",
            messages=[{"role": "user", "content": "What is Python?"}],
        )
        prompt = session._format_prompt(request)
        assert "What is Python?" in prompt

    def test_format_prompt_with_system(self):
        session = AntigravitySession()
        request = LLMRequest(
            provider="gemini-pro",
            model="gemini-3-pro",
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="You are a helpful assistant.",
        )
        prompt = session._format_prompt(request)
        assert "You are a helpful assistant" in prompt
        assert "Hello" in prompt

    def test_format_prompt_multi_turn(self):
        session = AntigravitySession()
        request = LLMRequest(
            provider="gpt",
            model="gpt-4o",
            messages=[
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
                {"role": "user", "content": "How are you?"},
            ],
        )
        prompt = session._format_prompt(request)
        assert "Hi" in prompt
        assert "Hello!" in prompt
        assert "How are you?" in prompt

    @pytest.mark.asyncio
    async def test_send_request_not_ready(self):
        session = AntigravitySession()
        request = LLMRequest(
            provider="gemini-pro",
            model="gemini-3-pro",
            messages=[{"role": "user", "content": "test"}],
        )
        response = await session.send_request(request)
        assert response.success is False
        assert "not ready" in response.error


class TestAntigravityBridge:
    """Tests for the high-level Antigravity bridge."""

    def test_initial_state(self):
        bridge = AntigravityBridge()
        assert bridge.is_initialized is False
        assert bridge.is_ready is False

    def test_get_available_providers(self):
        bridge = AntigravityBridge()
        providers = bridge.get_available_providers()
        assert len(providers) == 3
        provider_ids = [p["id"] for p in providers]
        assert "gemini-pro" in provider_ids
        assert "claude-sonnet" in provider_ids
        assert "gpt" in provider_ids

    def test_get_status_not_initialized(self):
        bridge = AntigravityBridge()
        status = bridge.get_status()
        assert status["initialized"] is False
        assert status["ready"] is False
        assert status["total_requests"] == 0
        assert status["total_errors"] == 0

    def test_provider_models(self):
        bridge = AntigravityBridge()
        providers = bridge.get_available_providers()
        for provider in providers:
            assert "models" in provider
            assert len(provider["models"]) > 0

    @pytest.mark.asyncio
    async def test_chat_not_initialized(self):
        """Chat without Playwright should return error (no browser available)."""
        bridge = AntigravityBridge()
        # This will fail because Playwright isn't available in test env
        response = await bridge.chat(
            provider="gemini-pro",
            model="gemini-3-pro",
            messages=[{"role": "user", "content": "test"}],
        )
        assert response.success is False

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self):
        bridge = AntigravityBridge()
        await bridge.shutdown()
        assert bridge.is_initialized is False
        # Should not error on double shutdown
        await bridge.shutdown()

    def test_error_rate_zero_initially(self):
        bridge = AntigravityBridge()
        status = bridge.get_status()
        assert status["error_rate"] == 0
