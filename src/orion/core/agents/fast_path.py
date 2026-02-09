"""
Orion Agent — Fast Path Execution (v6.4.0)

Direct execution for simple requests without Council deliberation.
Single LLM call with tool access → Execute → Done

This handles:
- File reads
- Simple explanations
- Single-file edits
- Quick searches

Target: <3 seconds for simple requests

Architecture:
  - Uses httpx (async) for non-blocking HTTP — never blocks the event loop
  - True token-by-token streaming via SSE for both Ollama and OpenAI
  - Centralized model config from orion.core.llm.config
  - Secure API key retrieval via orion.security.store
"""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator
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

    Single LLM call with tool access → Execute → Done.
    Tries Ollama (local) first, then cloud providers via centralized config.

    Uses httpx for fully async HTTP — never blocks the event loop.
    """

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

    def _get_model_config(self) -> Dict[str, Any]:
        """
        Get model configuration from centralized config module.

        Falls back to environment variables and sensible defaults.
        """
        config = {
            "ollama_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            "ollama_model": os.environ.get("OLLAMA_BUILDER_MODEL", "qwen2.5-coder:14b"),
            "openai_model": self.model,
        }

        # Try centralized config first
        try:
            from orion.core.llm.config import get_model_config
            mc = get_model_config()
            if hasattr(mc, "builder"):
                b = mc.builder
                if hasattr(b, "provider") and b.provider == "ollama":
                    config["ollama_model"] = getattr(b, "model", config["ollama_model"])
                elif hasattr(b, "provider") and b.provider in ("openai", "anthropic", "google", "groq"):
                    config["openai_model"] = getattr(b, "model", config["openai_model"])
        except Exception:
            pass

        return config

    def _get_api_key(self, provider: str) -> Optional[str]:
        """
        Retrieve API key using enterprise credential chain:
          1. Environment variable
          2. SecureStore (keyring / encrypted file)
        """
        # Environment variable (standard names)
        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "groq": "GROQ_API_KEY",
        }
        env_key = os.environ.get(env_map.get(provider, ""), "")
        if env_key:
            return env_key

        # SecureStore
        try:
            from orion.security.store import get_secure_store
            store = get_secure_store()
            return store.get_key(provider)
        except Exception:
            return None

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

        Uses the centralized call_provider which handles all providers,
        model config, key retrieval, and retry logic correctly.
        Falls back to direct Ollama/OpenAI/Anthropic calls if needed.
        """
        user_prompt = self._build_prompt(request, scout_report)

        # Primary path: use centralized call_provider (handles all providers)
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

            # Check if the response is an error JSON from call_provider
            if response and not response.startswith('{"outcome": "ANSWER", "response": "API error'):
                return FastPathResult(success=True, response=response)

            # call_provider returned an error — fall through to direct calls
        except Exception:
            pass

        # Fallback: Try Ollama directly (local, free)
        result = await self._call_ollama(user_prompt)
        if result.success:
            return result

        # Fallback: Try OpenAI directly
        result = await self._call_openai(user_prompt)
        if result.success:
            return result

        # Fallback: Try Anthropic directly
        result = await self._call_anthropic(user_prompt)
        if result.success:
            return result

        # No LLM available
        return FastPathResult(
            success=False,
            response=(
                "No LLM available. Either:\n"
                "  1. Start Ollama: ollama serve\n"
                "  2. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable\n"
                "  3. Add an API key in Settings → API Keys\n"
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
        Uses SSE (Server-Sent Events) for both Ollama and OpenAI.
        """
        user_prompt = self._build_prompt(request, scout_report)
        config = self._get_model_config()

        # Try Ollama streaming first
        try:
            async for token in self._stream_ollama(user_prompt, config):
                yield token
            return
        except Exception:
            pass

        # Fallback to OpenAI streaming
        api_key = self._get_api_key("openai")
        if api_key:
            try:
                async for token in self._stream_openai(user_prompt, api_key, config):
                    yield token
                return
            except Exception:
                pass

        # No streaming available — fall back to non-streaming
        result = await self.execute(request, scout_report)
        yield result.response

    # =========================================================================
    # Ollama (async via httpx)
    # =========================================================================

    async def _call_ollama(self, prompt: str) -> FastPathResult:
        """Call Ollama using async httpx. Non-blocking."""
        config = self._get_model_config()
        ollama_url = config["ollama_url"]
        ollama_model = config["ollama_model"]

        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                response = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": f"{self.SYSTEM_PROMPT}\n\n{prompt}",
                        "stream": False,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    return FastPathResult(
                        success=True,
                        response=data.get("response", ""),
                        tokens_used=data.get("eval_count", 0),
                    )
                return FastPathResult(
                    success=False,
                    response=f"Ollama returned {response.status_code}",
                )
        except httpx.ConnectError:
            return FastPathResult(
                success=False,
                response="Ollama not running (connection refused)",
            )
        except Exception as e:
            return FastPathResult(success=False, response=f"Ollama error: {e}")

    async def _stream_ollama(
        self, prompt: str, config: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """True token-by-token streaming from Ollama via NDJSON."""
        ollama_url = config["ollama_url"]
        ollama_model = config["ollama_model"]

        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{ollama_url}/api/generate",
                json={
                    "model": ollama_model,
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

    # =========================================================================
    # OpenAI (async via httpx — avoids openai SDK sync overhead)
    # =========================================================================

    async def _call_openai(self, prompt: str) -> FastPathResult:
        """Call OpenAI using async httpx. Non-blocking."""
        api_key = self._get_api_key("openai")
        if not api_key:
            return FastPathResult(success=False, response="No OpenAI API key")

        config = self._get_model_config()

        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": config["openai_model"],
                        "messages": [
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    tokens = data.get("usage", {}).get("total_tokens", 0)
                    return FastPathResult(
                        success=True, response=content, tokens_used=tokens
                    )
                return FastPathResult(
                    success=False,
                    response=f"OpenAI returned {response.status_code}: {response.text[:200]}",
                )
        except Exception as e:
            return FastPathResult(success=False, response=f"OpenAI error: {e}")

    async def _stream_openai(
        self, prompt: str, api_key: str, config: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """True token-by-token streaming from OpenAI via SSE."""
        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config["openai_model"],
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

    # =========================================================================
    # Anthropic (async via httpx)
    # =========================================================================

    async def _call_anthropic(self, prompt: str) -> FastPathResult:
        """Call Anthropic Claude using async httpx. Non-blocking."""
        api_key = self._get_api_key("anthropic")
        if not api_key:
            return FastPathResult(success=False, response="No Anthropic API key")

        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 4096,
                        "system": self.SYSTEM_PROMPT,
                        "messages": [
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    content = data["content"][0]["text"]
                    input_tokens = data.get("usage", {}).get("input_tokens", 0)
                    output_tokens = data.get("usage", {}).get("output_tokens", 0)
                    return FastPathResult(
                        success=True,
                        response=content,
                        tokens_used=input_tokens + output_tokens,
                    )
                return FastPathResult(
                    success=False,
                    response=f"Anthropic returned {response.status_code}: {response.text[:200]}",
                )
        except Exception as e:
            return FastPathResult(success=False, response=f"Anthropic error: {e}")


def get_fast_path(workspace_path: str, model: str = "gpt-4o") -> FastPath:
    """Factory function to get a FastPath instance."""
    return FastPath(workspace_path, model)
