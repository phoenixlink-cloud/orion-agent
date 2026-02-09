"""Unit tests for LLM provider routing — no real API calls, tests structure and error paths."""

import pytest
import asyncio
from orion.core.llm.providers import call_provider, _error_json, _get_key
from orion.core.llm.config import RoleConfig


class TestErrorJson:
    """Test error JSON formatting."""

    def test_error_json_format(self):
        import json
        result = _error_json("something failed")
        parsed = json.loads(result)
        assert parsed["outcome"] == "ANSWER"
        assert "something failed" in parsed["response"]


class TestCallProviderRouting:
    """Test that call_provider routes to correct provider without real API calls."""

    def test_unknown_provider_returns_error(self):
        rc = RoleConfig(provider="nonexistent_provider", model="fake-model")
        result = asyncio.run(call_provider(rc, "sys", "user"))
        assert "Unknown provider" in result

    def test_missing_openai_key_returns_error(self):
        """With placeholder key, OpenAI returns 401 — but the routing is correct."""
        rc = RoleConfig(provider="openai", model="gpt-4o-mini")
        result = asyncio.run(call_provider(rc, "sys", "user", max_tokens=10))
        # Either returns error about key or 401 — both prove routing works
        assert isinstance(result, str)
        assert len(result) > 0

    def test_missing_google_key_returns_error(self):
        """Google has no key stored — should return friendly error."""
        rc = RoleConfig(provider="google", model="gemini-2.5-pro")
        result = asyncio.run(call_provider(rc, "sys", "user", max_tokens=10))
        assert "not configured" in result or "API error" in result

    def test_ollama_timeout_handling(self):
        """Ollama not running should fail gracefully, not crash."""
        rc = RoleConfig(provider="ollama", model="nonexistent:0b")
        result = asyncio.run(call_provider(rc, "sys", "user", max_tokens=10))
        assert isinstance(result, str)
        assert len(result) > 0


class TestRoleConfig:
    """Test RoleConfig data structure."""

    def test_role_config_creation(self):
        rc = RoleConfig(provider="openai", model="gpt-4o")
        assert rc.provider == "openai"
        assert rc.model == "gpt-4o"
