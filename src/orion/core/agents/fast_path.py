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
Orion Agent -- Fast Path Execution (v7.4.0)

Direct execution for simple requests without Council deliberation.
Single LLM call with tool access -> Execute -> Done

This handles:
- File reads
- Simple explanations
- Single-file edits
- Quick searches

Target: <3 seconds for simple requests

Architecture:
  - Uses httpx (async) for non-blocking HTTP -- never blocks the event loop
  - True token-by-token streaming via SSE for both Ollama and OpenAI
  - Centralized model config from orion.core.llm.config
  - Secure API key retrieval via orion.security.store
"""

import json
import logging
import os
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("orion.agents.fast_path")

# ---------------------------------------------------------------------------
# INTENT CLASSIFICATION
# ---------------------------------------------------------------------------


class _Intent:
    CONVERSATIONAL = "conversational"
    QUESTION = "question"
    CODING_TASK = "coding_task"


# Patterns that indicate casual / conversational messages
_CONVERSATIONAL_PATTERNS = [
    r"^\s*(hi|hello|hey|howdy|greetings|good\s+(morning|afternoon|evening|day)|yo|sup)\b",
    r"^\s*how\s+are\s+you",
    r"^\s*what'?s\s+up",
    r"^\s*thanks?\s*(you)?[!.]*$",
    r"^\s*thank\s+you",
    r"^\s*bye|goodbye|see\s+you|good\s*night",
    r"^\s*nice|cool|awesome|great|perfect[!.]*$",
    r"^\s*who\s+are\s+you",
    r"^\s*tell\s+me\s+about\s+(yourself|you)",
    r"^\s*what\s+can\s+you\s+do\s*\??",
    r"^\s*are\s+you\s+(there|ready|ok|okay)",
]

# Patterns that indicate a coding/technical task
_CODING_PATTERNS = [
    r"\b(create|write|build|implement|add|fix|debug|refactor|update|modify|delete|remove)\b",
    r"\b(file|function|class|method|module|api|endpoint|route|component|test)\b",
    r"\b(install|deploy|run|execute|compile|build|lint|format)\b",
    r"\b(error|bug|exception|traceback|stack\s*trace|crash|fail)\b",
    r"\.(py|js|ts|jsx|tsx|json|yaml|yml|html|css|sql|go|rs|java|cs|cpp|c|h)\b",
    r"```",
    r"\b(import|from|def |class |function |const |let |var )\b",
]


def _classify_intent(request: str) -> str:
    """Classify user request intent for context injection decisions."""
    text = request.strip()
    lower = text.lower()

    # Short messages that are just greetings
    for pattern in _CONVERSATIONAL_PATTERNS:
        if re.search(pattern, lower):
            # But if the message also contains coding signals, it's a coding task
            for cp in _CODING_PATTERNS:
                if re.search(cp, lower):
                    return _Intent.CODING_TASK
            return _Intent.CONVERSATIONAL

    # Check for coding task signals
    for pattern in _CODING_PATTERNS:
        if re.search(pattern, lower):
            return _Intent.CODING_TASK

    # Default: treat as a general question
    return _Intent.QUESTION


@dataclass
class FastPathResult:
    """Result of fast path execution."""

    success: bool
    response: str
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0


class FastPath:
    """
    Execute simple requests directly without Council deliberation.

    Single LLM call with tool access -> Execute -> Done.
    Tries Ollama (local) first, then cloud providers via centralized config.

    Uses httpx for fully async HTTP -- never blocks the event loop.
    """

    SYSTEM_PROMPT = (
        "You are Orion, a governed AI coding assistant by Phoenix Link. "
        "Be honest, concise, and match the user's tone. "
        "Never fabricate facts. When unsure, say so."
    )

    @staticmethod
    def _get_persona_for_intent(intent: str) -> str:
        """Load a slim persona card matching the request intent."""
        try:
            from orion.core.persona import get_fastpath_persona

            return get_fastpath_persona(intent)
        except Exception:
            return FastPath.SYSTEM_PROMPT

    @staticmethod
    def _get_platform_context() -> str:
        """Get a summary of connected platforms for the system prompt."""
        try:
            from orion.integrations.platform_service import get_platform_service

            service = get_platform_service()
            return service.describe_capabilities()
        except Exception:
            return ""

    # Timeout config: connect 5s, read 120s (LLM generation can be slow)
    _TIMEOUT = httpx.Timeout(5.0, read=120.0)

    def __init__(self, workspace_path: str, model: str = "gpt-4o"):
        self.workspace = str(Path(workspace_path).resolve())
        self.model = model

        # NLA Phase 2C: RequestAnalyzer replaces regex _classify_intent
        self._request_analyzer = None
        try:
            from orion.core.understanding.request_analyzer import RequestAnalyzer

            self._request_analyzer = RequestAnalyzer()
        except Exception:
            logger.debug("RequestAnalyzer not available, using regex fallback")

        # Evolution guidance is loaded once (appended to coding prompts)
        self._evolution_guidance = self._load_evolution_guidance()

    def _nla_classify(self, request: str) -> str:
        """Classify intent via NLA RequestAnalyzer, falling back to regex."""
        if self._request_analyzer:
            try:
                result = self._request_analyzer.analyze(request)
                return result.fast_path_intent
            except Exception:
                logger.debug("NLA classification failed, using regex fallback")
        return _classify_intent(request)

    def _build_system_prompt(self, intent: str) -> str:
        """Build a slim system prompt matching the request intent.

        Conversational: ~50 tokens (just persona)
        Question:        ~70 tokens (persona + grounding)
        Coding:          ~120 tokens (persona + grounding + quality + evolution)
        """
        persona = self._get_persona_for_intent(intent)

        if intent == _Intent.CONVERSATIONAL:
            return persona

        prompt = persona
        if self._evolution_guidance:
            prompt += f"\n\n{self._evolution_guidance}"
        return prompt

    @staticmethod
    def _load_evolution_guidance() -> str:
        """Load improvement guidance from the evolution engine."""
        try:
            from orion.core.learning.evolution import get_evolution_engine

            engine = get_evolution_engine()
            guidance = engine.get_improvement_guidance()
            if guidance:
                return f"SELF-IMPROVEMENT NOTES:\n{guidance}"
        except Exception as e:
            logger.debug("Could not load evolution guidance: %s", e)
        return ""

    def _build_prompt(self, request: str, scout_report=None, intent: str = None) -> str:
        """Build the user prompt with context appropriate to the request intent.

        Classifies the request intent and only injects context that is
        relevant -- casual messages get no technical context dump.
        """
        if intent is None:
            intent = _classify_intent(request)
        user_prompt = f"Request: {request}"

        # Memory context is always relevant (contains learned preferences)
        memory_ctx = getattr(self, "_memory_context", "")
        if memory_ctx:
            user_prompt += f"\n\n{memory_ctx}"

        # For conversational messages, skip all technical context
        if intent == _Intent.CONVERSATIONAL:
            return user_prompt

        # For questions, include repo map but skip platforms unless asked
        if intent == _Intent.QUESTION:
            repo_context = self._try_get_repo_map()
            if repo_context:
                user_prompt += f"\n\nRepository Map:\n{repo_context}"
            return user_prompt

        # For coding tasks, include full context
        file_contents = self._get_relevant_files(scout_report)
        repo_context = self._try_get_repo_map()
        platform_ctx = self._get_platform_context()

        if platform_ctx:
            user_prompt += f"\n\n{platform_ctx}"
        if repo_context:
            user_prompt += f"\n\nRepository Map:\n{repo_context}"
        if file_contents:
            user_prompt += f"\n\nRelevant Files:\n{chr(10).join(file_contents)}"

        return user_prompt

    def _try_get_repo_map(self) -> str:
        """Get repository map, returning empty string on failure."""
        try:
            from orion.core.context.repo_map import generate_repo_map

            return generate_repo_map(self.workspace, max_tokens=1024)
        except Exception as e:
            logger.debug("Could not load repo map: %s", e)
            return ""

    def _get_relevant_files(self, scout_report) -> list[str]:
        """Read relevant files from scout report."""
        file_contents = []
        if scout_report and hasattr(scout_report, "relevant_files"):
            for fpath in scout_report.relevant_files[:3]:
                try:
                    full_path = Path(self.workspace) / fpath
                    if full_path.exists() and full_path.is_file():
                        content = full_path.read_text(encoding="utf-8", errors="ignore")
                        if len(content) > 5000:
                            content = content[:5000] + "\n... (truncated)"
                        file_contents.append(f"=== {fpath} ===\n{content}")
                except Exception as e:
                    logger.debug("Could not read file %s: %s", fpath, e)
        return file_contents

    async def execute(self, request: str, scout_report=None) -> FastPathResult:
        """
        Execute a simple request directly.

        Uses the centralized call_provider from providers.py which handles
        all providers, model config, key retrieval, and retry logic.
        """
        intent = self._nla_classify(request)
        system_prompt = self._build_system_prompt(intent)
        user_prompt = self._build_prompt(request, scout_report, intent)

        try:
            from orion.core.llm.config import get_model_config
            from orion.core.llm.providers import call_provider

            cfg = get_model_config()
            builder_rc = cfg.builder
            response = await call_provider(
                role_config=builder_rc,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=4000,
                component="fast_path",
            )

            # call_provider returns error JSON on failure
            if response and not response.startswith('{"outcome": "ANSWER", "response": "API error'):
                return FastPathResult(success=True, response=response)

            # Extract error message from JSON
            try:
                import json as _json

                err = _json.loads(response)
                err_msg = err.get("response", response)
            except Exception:
                err_msg = response or "Unknown error"

            return FastPathResult(success=False, response=err_msg)

        except Exception as e:
            return FastPathResult(
                success=False,
                response=(
                    f"LLM call failed: {e}\n\n"
                    "No LLM available. Either:\n"
                    "  1. Start Ollama: ollama serve\n"
                    "  2. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable\n"
                    "  3. Add an API key in Settings -> API Keys\n"
                    "  4. Run /doctor to check your configuration"
                ),
            )

    async def execute_streaming(self, request: str, scout_report=None) -> AsyncGenerator[str, None]:
        """
        Execute with true token-by-token streaming.

        Yields tokens as they arrive from the LLM provider.
        Uses SSE (Server-Sent Events) for both Ollama and OpenAI-compatible APIs.
        Falls back to non-streaming execute() if streaming isn't available.
        """
        intent = self._nla_classify(request)
        self._current_system_prompt = self._build_system_prompt(intent)
        user_prompt = self._build_prompt(request, scout_report, intent)

        # Get provider config from centralized source
        try:
            from orion.core.llm.config import get_model_config

            cfg = get_model_config()
            provider = cfg.builder.provider
            model = cfg.builder.model
        except Exception:
            provider = "ollama"
            model = os.environ.get("OLLAMA_BUILDER_MODEL", "qwen2.5-coder:14b")

        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

        # Stream from the configured provider
        if provider == "ollama":
            try:
                async for token in self._stream_ollama(user_prompt, ollama_url, model):
                    yield token
                return
            except Exception:
                pass
        elif provider in ("openai", "groq"):
            try:
                from orion.core.llm.providers import _get_key

                api_key = _get_key(provider)
                if api_key:
                    async for token in self._stream_openai(user_prompt, api_key, model):
                        yield token
                    return
            except Exception:
                pass
            # Fallback: try Ollama streaming (local, free)
            try:
                fallback_model = os.environ.get("OLLAMA_BUILDER_MODEL", "qwen2.5-coder:14b")
                async for token in self._stream_ollama(user_prompt, ollama_url, fallback_model):
                    yield token
                return
            except Exception:
                pass

        # No streaming available -- fall back to non-streaming
        result = await self.execute(request, scout_report)
        yield result.response

    # =========================================================================
    # Streaming providers (unique to FastPath -- providers.py has no streaming)
    # =========================================================================

    async def _stream_ollama(
        self, prompt: str, ollama_url: str, model: str
    ) -> AsyncGenerator[str, None]:
        """True token-by-token streaming from Ollama via NDJSON."""

        async with (
            httpx.AsyncClient(timeout=self._TIMEOUT) as client,
            client.stream(
                "POST",
                f"{ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": f"{getattr(self, '_current_system_prompt', self.SYSTEM_PROMPT)}\n\n{prompt}",
                    "stream": True,
                },
            ) as response,
        ):
            if response.status_code != 200:
                raise RuntimeError(f"Ollama streaming failed: {response.status_code}")
            async for line in response.aiter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            yield token
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        pass

    async def _stream_openai(
        self, prompt: str, api_key: str, model: str
    ) -> AsyncGenerator[str, None]:
        """True token-by-token streaming from OpenAI-compatible APIs via SSE."""
        async with (
            httpx.AsyncClient(timeout=self._TIMEOUT) as client,
            client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": getattr(self, "_current_system_prompt", self.SYSTEM_PROMPT),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "stream": True,
                },
            ) as response,
        ):
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI streaming failed: {response.status_code}")
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                        delta = data["choices"][0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass


def get_fast_path(workspace_path: str, model: str = "gpt-4o") -> FastPath:
    """Factory function to get a FastPath instance."""
    return FastPath(workspace_path, model)
