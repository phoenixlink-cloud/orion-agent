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
#    See LICENSE-ENTERPRISE.md or contact licensing@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- Fast Path Execution (v6.4.0)

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

import os
import json
from typing import List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path

import httpx


@dataclass
class FastPathResult:
    """Result of fast path execution."""
    success: bool
    response: str
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0


class FastPath:
    """
    Execute simple requests directly without Council deliberation.

    Single LLM call with tool access -> Execute -> Done.
    Tries Ollama (local) first, then cloud providers via centralized config.

    Uses httpx for fully async HTTP -- never blocks the event loop.
    """

    @staticmethod
    def _get_persona() -> str:
        """Load the Orion persona for FastPath."""
        try:
            from orion.core.persona import get_builder_persona, AUTONOMY_TIERS
            return get_builder_persona() + "\n\n" + AUTONOMY_TIERS
        except Exception:
            return "You are Orion, a governed AI coding assistant."

    SYSTEM_PROMPT = """You are Orion, a governed AI coding assistant with AEGIS safety.

You have direct access to the user's codebase. Be concise and direct.

IMPORTANT RULES:
- Stay within the workspace directory
- For write operations, show a brief diff of changes
- Be concise and direct
- If you can't do something, explain why briefly
- When the user asks about connected services (GitHub, Slack, etc.), check platform capabilities
"""

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

        # Build persona-aware system prompt (instance-level overrides class-level)
        persona = self._get_persona()
        if persona and len(persona) > 50:
            self.SYSTEM_PROMPT = f"""{persona}

FAST PATH RULES:
- Stay within the workspace directory
- For write operations, show a brief diff of changes
- Be concise and direct
- If you can't do something, explain why briefly
- When the user asks about connected services (GitHub, Slack, etc.), check platform capabilities
"""

    def _build_prompt(self, request: str, scout_report=None) -> str:
        """Build the full prompt with file context and repo map."""
        file_contents = []
        if scout_report and hasattr(scout_report, 'relevant_files'):
            for fpath in scout_report.relevant_files[:3]:
                try:
                    full_path = Path(self.workspace) / fpath
                    if full_path.exists() and full_path.is_file():
                        content = full_path.read_text(encoding='utf-8', errors='ignore')
                        if len(content) > 5000:
                            content = content[:5000] + "\n... (truncated)"
                        file_contents.append(f"=== {fpath} ===\n{content}")
                except Exception:
                    pass

        repo_context = ""
        try:
            from orion.core.context.repo_map import generate_repo_map
            repo_context = generate_repo_map(self.workspace, max_tokens=1024)
        except Exception:
            pass

        user_prompt = f"Request: {request}"

        # Inject memory context (set by Router from MemoryEngine)
        memory_ctx = getattr(self, '_memory_context', '')
        if memory_ctx:
            user_prompt += f"\n\n{memory_ctx}"

        # Inject connected platform capabilities
        platform_ctx = self._get_platform_context()
        if platform_ctx:
            user_prompt += f"\n\n{platform_ctx}"

        if repo_context:
            user_prompt += f"\n\nRepository Map:\n{repo_context}"
        if file_contents:
            user_prompt += f"\n\nRelevant Files:\n{chr(10).join(file_contents)}"

        return user_prompt

    async def execute(self, request: str, scout_report=None) -> FastPathResult:
        """
        Execute a simple request directly.

        Uses the centralized call_provider from providers.py which handles
        all providers, model config, key retrieval, and retry logic.
        """
        user_prompt = self._build_prompt(request, scout_report)

        try:
            from orion.core.llm.providers import call_provider
            from orion.core.llm.config import get_model_config

            cfg = get_model_config()
            builder_rc = cfg.builder
            response = await call_provider(
                role_config=builder_rc,
                system_prompt=self.SYSTEM_PROMPT,
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

    async def execute_streaming(
        self,
        request: str,
        scout_report=None
    ) -> AsyncGenerator[str, None]:
        """
        Execute with true token-by-token streaming.

        Yields tokens as they arrive from the LLM provider.
        Uses SSE (Server-Sent Events) for both Ollama and OpenAI-compatible APIs.
        Falls back to non-streaming execute() if streaming isn't available.
        """
        user_prompt = self._build_prompt(request, scout_report)

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

        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": f"{self.SYSTEM_PROMPT}\n\n{prompt}",
                    "stream": True,
                },
            ) as response:
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
        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": True,
                },
            ) as response:
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
