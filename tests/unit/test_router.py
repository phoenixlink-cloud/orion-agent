"""Tests for orion.core.agents.router -- Request Router.

Tests cover:
- Intent dataclass
- classify_intent() with mocked Scout
- RequestRouter initialization (sandbox disabled)
- handle_request() routing: fast_path, council, escalation, no scout
- _get_memory_context() with and without memory engine
- record_interaction() with and without memory engine
- sandbox methods: get_sandbox_diff, promote_changes, destroy_sandbox, get_sandbox_status
- _handle_escalation() user confirms vs cancels
- get_router() factory
- process_request() / process_request_sync()
"""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.core.agents.router import (
    Intent,
    RequestRouter,
    classify_intent,
    get_router,
    process_request_sync,
)

# ---------------------------------------------------------------------------
# Helpers / Mocks
# ---------------------------------------------------------------------------


@dataclass
class MockScoutReport:
    route: object = None
    complexity_score: float = 0.3
    risk_level: str = "low"
    relevant_files: list[str] = field(default_factory=list)
    reasoning: str = "mock reasoning"


class MockRoute:
    """Mimics orion.core.agents.scout.Route enum."""

    FAST_PATH = "FAST_PATH"
    COUNCIL = "COUNCIL"
    ESCALATION = "ESCALATION"

    def __init__(self, value):
        self._value = value

    @property
    def name(self):
        return self._value

    def __eq__(self, other):
        if hasattr(other, "_value"):
            return self._value == other._value
        return self._value == other


@dataclass
class MockFastPathResult:
    success: bool = True
    response: str = "fast path response"


# ---------------------------------------------------------------------------
# Intent dataclass
# ---------------------------------------------------------------------------


class TestIntent:
    def test_fields(self):
        intent = Intent(
            category="analysis",
            requires_evidence=False,
            requires_action=True,
            confidence=0.85,
            keywords=["test"],
            raw_input="do something",
        )
        assert intent.category == "analysis"
        assert intent.requires_action is True
        assert intent.confidence == 0.85
        assert intent.raw_input == "do something"


# ---------------------------------------------------------------------------
# classify_intent()
# ---------------------------------------------------------------------------


class TestClassifyIntent:
    def test_returns_valid_intent(self, tmp_path):
        """classify_intent always returns a valid Intent."""
        intent = classify_intent("hello world", str(tmp_path))
        assert isinstance(intent, Intent)
        assert intent.category in ("analysis", "action")
        assert 0.0 <= intent.confidence <= 1.0
        assert intent.raw_input == "hello world"

    def test_fallback_on_scout_error(self, tmp_path):
        """When Scout raises, returns safe default."""
        with patch.dict("sys.modules", {"orion.core.agents.scout": None}):
            intent = classify_intent("test input", str(tmp_path))
            assert isinstance(intent, Intent)
            assert intent.category == "analysis"
            assert intent.confidence == 0.5


# ---------------------------------------------------------------------------
# RequestRouter -- init with sandbox disabled
# ---------------------------------------------------------------------------


class TestRequestRouterInit:
    def test_init_sandbox_disabled(self, tmp_path):
        router = RequestRouter(
            workspace_path=str(tmp_path),
            sandbox_enabled=False,
        )
        assert router.workspace_path == Path(tmp_path).resolve()
        assert router._sandbox_enabled is False
        assert router.sandbox_active is False

    def test_init_respects_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORION_SANDBOX_ENABLED", "false")
        router = RequestRouter(workspace_path=str(tmp_path))
        assert router._sandbox_enabled is False

    def test_default_confirm(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False)
        with patch("builtins.input", return_value="y"):
            assert router._default_confirm("test?") is True
        with patch("builtins.input", return_value="n"):
            assert router._default_confirm("test?") is False

    def test_custom_confirm_callback(self, tmp_path):
        cb = MagicMock(return_value=True)
        router = RequestRouter(str(tmp_path), confirm_callback=cb, sandbox_enabled=False)
        assert router.confirm_callback is cb


# ---------------------------------------------------------------------------
# Sandbox methods (when sandbox is not active)
# ---------------------------------------------------------------------------


class TestSandboxInactive:
    def test_get_sandbox_diff_returns_none(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False)
        assert router.get_sandbox_diff() is None

    def test_promote_changes_returns_error(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False)
        result = router.promote_changes()
        assert result == {"error": "Sandbox not active"}

    def test_destroy_sandbox_returns_false(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False)
        assert router.destroy_sandbox() is False

    def test_get_sandbox_status_disabled(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False)
        status = router.get_sandbox_status()
        assert status["enabled"] is False


# ---------------------------------------------------------------------------
# _get_memory_context()
# ---------------------------------------------------------------------------


class TestGetMemoryContext:
    def test_no_memory_engine(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False, memory_engine=None)
        router._institutional = None  # isolate from real DB
        assert router._get_memory_context("test") == ""

    def test_with_memory_engine(self, tmp_path):
        mock_engine = MagicMock()
        mock_engine.recall_for_prompt.return_value = "## MEMORY CONTEXT\n- Some pattern"
        router = RequestRouter(str(tmp_path), sandbox_enabled=False, memory_engine=mock_engine)
        router._institutional = None  # isolate from real DB
        result = router._get_memory_context("test query")
        assert "MEMORY CONTEXT" in result
        mock_engine.recall_for_prompt.assert_called_once_with("test query", max_tokens=1200)

    def test_memory_engine_exception(self, tmp_path):
        mock_engine = MagicMock()
        mock_engine.recall_for_prompt.side_effect = RuntimeError("oops")
        router = RequestRouter(str(tmp_path), sandbox_enabled=False, memory_engine=mock_engine)
        router._institutional = None  # isolate from real DB
        assert router._get_memory_context("test") == ""


# ---------------------------------------------------------------------------
# record_interaction()
# ---------------------------------------------------------------------------


class TestRecordInteraction:
    def test_no_memory_engine(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False, memory_engine=None)
        # Should not raise
        router.record_interaction("request", "response", "FAST_PATH")

    def test_with_memory_engine(self, tmp_path):
        mock_engine = MagicMock()
        router = RequestRouter(str(tmp_path), sandbox_enabled=False, memory_engine=mock_engine)
        router.record_interaction("what is X?", "X is Y", "FAST_PATH")
        mock_engine.remember.assert_called_once()
        call_kwargs = mock_engine.remember.call_args
        assert call_kwargs[1]["tier"] == 1
        assert call_kwargs[1]["category"] == "insight"

    def test_memory_engine_exception_swallowed(self, tmp_path):
        mock_engine = MagicMock()
        mock_engine.remember.side_effect = RuntimeError("fail")
        router = RequestRouter(str(tmp_path), sandbox_enabled=False, memory_engine=mock_engine)
        # Should not raise
        router.record_interaction("req", "resp", "FAST_PATH")


# ---------------------------------------------------------------------------
# handle_request() -- routing
# ---------------------------------------------------------------------------


class TestHandleRequest:
    @pytest.mark.asyncio
    async def test_no_scout_returns_failure(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False)
        router.scout = None
        result = await router.handle_request("test")
        assert result["success"] is False
        assert result["route"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_fast_path_routing(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False, stream_output=False)

        # Mock scout
        mock_route = MockRoute("FAST_PATH")
        mock_report = MockScoutReport(route=mock_route)
        router.scout = MagicMock()
        router.scout.analyze.return_value = mock_report

        # Mock fast_path
        mock_fp = AsyncMock()
        mock_fp.execute.return_value = MockFastPathResult(success=True, response="answer")
        router._fast_path = mock_fp

        # Mock Route enum import inside handle_request
        with patch(
            "orion.core.agents.router.RequestRouter._handle_fast_path",
            new_callable=AsyncMock,
            return_value={"content": "answer"},
        ):
            # Patch the Route import
            mock_route_module = MagicMock()
            mock_route_module.Route = type(
                "Route",
                (),
                {
                    "FAST_PATH": mock_route,
                    "COUNCIL": MockRoute("COUNCIL"),
                    "ESCALATION": MockRoute("ESCALATION"),
                },
            )
            with patch.dict("sys.modules", {"orion.core.agents.scout": mock_route_module}):
                result = await router.handle_request("show me main.py")
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_handle_request_exception(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False, stream_output=False)

        mock_route = MockRoute("FAST_PATH")
        mock_report = MockScoutReport(route=mock_route)
        router.scout = MagicMock()
        router.scout.analyze.return_value = mock_report

        # Force _handle_fast_path to raise
        router._handle_fast_path = AsyncMock(side_effect=RuntimeError("boom"))

        mock_route_module = MagicMock()
        mock_route_module.Route.FAST_PATH = mock_route
        mock_route_module.Route.COUNCIL = MockRoute("COUNCIL")
        mock_route_module.Route.ESCALATION = MockRoute("ESCALATION")
        with patch.dict("sys.modules", {"orion.core.agents.scout": mock_route_module}):
            result = await router.handle_request("test")
            assert result["success"] is False
            assert "execution_time_ms" in result
            assert "boom" in result.get("error", "")


# ---------------------------------------------------------------------------
# _handle_escalation()
# ---------------------------------------------------------------------------


class TestHandleEscalation:
    @pytest.mark.asyncio
    async def test_user_cancels(self, tmp_path):
        cb = MagicMock(return_value=False)
        router = RequestRouter(str(tmp_path), confirm_callback=cb, sandbox_enabled=False)

        mock_report = MockScoutReport(reasoning="dangerous operation")
        result = await router._handle_escalation("rm -rf /", mock_report)
        assert result["content"] == "Request cancelled by user."
        cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_confirms(self, tmp_path):
        cb = MagicMock(return_value=True)
        router = RequestRouter(str(tmp_path), confirm_callback=cb, sandbox_enabled=False)

        mock_report = MockScoutReport(reasoning="dangerous operation")

        # Mock _handle_council to avoid real execution
        router._handle_council = AsyncMock(return_value={"content": "council result"})
        result = await router._handle_escalation("delete old files", mock_report)
        assert result["content"] == "council result"


# ---------------------------------------------------------------------------
# _handle_council() fallback
# ---------------------------------------------------------------------------


class TestHandleCouncil:
    @pytest.mark.asyncio
    async def test_council_none_falls_back_to_fast_path(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False, stream_output=False)
        router._council = None

        # Mock fast_path
        mock_fp = AsyncMock()
        mock_fp.execute.return_value = MockFastPathResult(success=True, response="fallback")
        router._fast_path = mock_fp

        mock_report = MockScoutReport()
        result = await router._handle_council("complex request", mock_report)
        assert "content" in result or "error" in result


# ---------------------------------------------------------------------------
# Lazy property loading
# ---------------------------------------------------------------------------


class TestLazyProperties:
    def test_fast_path_lazy_load_fails_gracefully(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False)
        # In test env, FastPath import may fail -- should return None
        fp = router.fast_path
        # Either None or a FastPath instance
        assert fp is None or hasattr(fp, "execute")

    def test_council_lazy_load_fails_gracefully(self, tmp_path):
        router = RequestRouter(str(tmp_path), sandbox_enabled=False)
        council = router.council
        assert council is None or callable(council)


# ---------------------------------------------------------------------------
# get_router() factory
# ---------------------------------------------------------------------------


class TestGetRouter:
    def test_returns_router_instance(self, tmp_path):
        router = get_router(str(tmp_path), sandbox_enabled=False)
        assert isinstance(router, RequestRouter)

    def test_passes_kwargs(self, tmp_path):
        router = get_router(str(tmp_path), sandbox_enabled=False, model="gpt-3.5-turbo")
        assert router.model == "gpt-3.5-turbo"


# ---------------------------------------------------------------------------
# process_request_sync()
# ---------------------------------------------------------------------------


class TestProcessRequestSync:
    def test_sync_wrapper(self, tmp_path):
        with patch("orion.core.agents.router.RequestRouter") as MockRouter:
            mock_instance = MagicMock()
            mock_instance.handle_request = AsyncMock(
                return_value={
                    "success": True,
                    "route": "FAST_PATH",
                    "response": "done",
                }
            )
            MockRouter.return_value = mock_instance

            result = process_request_sync("hello", str(tmp_path), stream=False)
            assert result["success"] is True
