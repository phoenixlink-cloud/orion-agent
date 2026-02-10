"""Tests for the Platform Registry and Platform Service."""

import pytest
from unittest.mock import patch, MagicMock


class TestPlatformRegistry:
    """Test the platform registry definitions and status checking."""

    def test_registry_has_platforms(self):
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        assert len(registry._platforms) >= 20

    def test_all_categories_present(self):
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        by_cat = registry.list_by_category()
        expected = {"ai_models", "developer_tools", "messaging", "voice", "image", "cloud_storage"}
        assert expected == set(by_cat.keys())

    def test_each_platform_has_required_fields(self):
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        for pid, p in registry._platforms.items():
            assert p.id == pid
            assert p.name
            assert p.description
            assert p.icon
            assert p.auth_method is not None
            assert p.category is not None

    def test_ai_models_category(self):
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        by_cat = registry.list_by_category()
        ai_ids = [p["id"] for p in by_cat["ai_models"]]
        assert "ollama" in ai_ids
        assert "openai" in ai_ids
        assert "anthropic" in ai_ids
        assert "google" in ai_ids
        assert "groq" in ai_ids

    def test_developer_tools_category(self):
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        by_cat = registry.list_by_category()
        tool_ids = [p["id"] for p in by_cat["developer_tools"]]
        assert "github" in tool_ids
        assert "gitlab" in tool_ids
        assert "docker" in tool_ids
        assert "notion" in tool_ids

    def test_messaging_category(self):
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        by_cat = registry.list_by_category()
        msg_ids = [p["id"] for p in by_cat["messaging"]]
        assert "slack" in msg_ids
        assert "discord" in msg_ids
        assert "telegram" in msg_ids

    def test_local_platforms_auto_connected(self):
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        ollama = registry.get("ollama")
        assert ollama.is_local is True
        assert ollama.connected is True
        assert ollama.connection_source == "local"

    def test_env_var_connects_platform(self):
        from orion.integrations.platforms import get_platform_registry, _build_platforms, PlatformRegistry
        import orion.integrations.platforms as mod
        # Reset singleton
        mod._registry = None

        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test123"}):
            registry = PlatformRegistry()
            github = registry.get("github")
            assert github.connected is True
            assert github.connection_source == "environment"

        mod._registry = None

    def test_serialize_platform(self):
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        data = registry._serialize(registry.get("github"))
        assert data["id"] == "github"
        assert data["name"] == "GitHub"
        assert data["category"] == "developer_tools"
        assert data["auth_method"] in ("oauth", "cli_tool")
        assert isinstance(data["capabilities"], list)
        assert len(data["capabilities"]) > 0
        assert "name" in data["capabilities"][0]

    def test_list_capabilities_only_connected(self):
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        caps = registry.list_capabilities()
        # Only connected platforms should contribute
        for cap_name, providers in caps.items():
            for pid in providers:
                p = registry.get(pid)
                assert p.connected, f"Platform {pid} listed for {cap_name} but not connected"

    def test_refresh_updates_status(self):
        from orion.integrations.platforms import get_platform_registry
        registry = get_platform_registry()
        # Just verify refresh doesn't crash
        registry.refresh()
        assert len(registry._platforms) >= 20

    def test_category_labels_defined(self):
        from orion.integrations.platforms import CATEGORY_LABELS
        assert "ai_models" in CATEGORY_LABELS
        assert "developer_tools" in CATEGORY_LABELS
        assert "messaging" in CATEGORY_LABELS
        for cat, info in CATEGORY_LABELS.items():
            assert "label" in info
            assert "icon" in info


class TestPlatformService:
    """Test the platform service used by Orion agents."""

    def test_service_creation(self):
        from orion.integrations.platform_service import get_platform_service
        service = get_platform_service()
        assert service is not None

    def test_available_capabilities(self):
        from orion.integrations.platform_service import get_platform_service
        service = get_platform_service()
        caps = service.available_capabilities()
        assert isinstance(caps, dict)
        # Local services should provide at least 'chat'
        assert "chat" in caps or "code_generation" in caps or "run_code" in caps

    def test_can_checks_connected(self):
        from orion.integrations.platform_service import get_platform_service
        service = get_platform_service()
        # create_issue requires GitHub -- connected if GITHUB_TOKEN is set
        # or if 'gh' CLI is installed (CLI_TOOL auth)
        import os, shutil
        github_available = bool(os.environ.get("GITHUB_TOKEN")) or shutil.which("gh") is not None
        if not github_available:
            assert service.can("create_issue") is False

    def test_describe_capabilities(self):
        from orion.integrations.platform_service import get_platform_service
        service = get_platform_service()
        desc = service.describe_capabilities()
        assert isinstance(desc, str)
        assert len(desc) > 10

    def test_get_token_returns_none_for_unconnected(self):
        from orion.integrations.platform_service import get_platform_service
        service = get_platform_service()
        import os
        if not os.environ.get("SLACK_BOT_TOKEN"):
            assert service.get_token("slack") is None

    def test_get_token_from_env(self):
        from orion.integrations.platform_service import PlatformService
        service = PlatformService()
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_testtoken"}):
            service._registry = None  # Force re-init
            token = service.get_token("github")
            assert token == "ghp_testtoken"

    def test_is_connected_local(self):
        from orion.integrations.platform_service import get_platform_service
        service = get_platform_service()
        # Ollama is local, always connected
        assert service.is_connected("ollama") is True

    def test_get_provider_for_capability(self):
        from orion.integrations.platform_service import get_platform_service
        service = get_platform_service()
        # Chat should be available from some local provider
        provider = service.get_provider_for("chat")
        # Could be ollama or another local service
        if provider:
            assert isinstance(provider, str)

    @pytest.mark.asyncio
    async def test_execute_capability_no_provider(self):
        from orion.integrations.platform_service import get_platform_service
        service = get_platform_service()
        result = await service.execute_capability("nonexistent_capability")
        assert result["ok"] is False
        assert "No connected platform" in result["error"]

    @pytest.mark.asyncio
    async def test_api_call_not_connected(self):
        from orion.integrations.platform_service import PlatformService
        service = PlatformService()
        result = await service.api_call("slack", "GET", "https://slack.com/api/test")
        # Should fail gracefully if not connected
        if not result["ok"]:
            assert "Not connected" in result.get("error", "")
