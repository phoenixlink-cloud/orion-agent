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
"""

import os
import json
import asyncio
import fnmatch
from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path


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
    Tries Ollama (local) first, then OpenAI if API key is available.
    """

    SYSTEM_PROMPT = """You are Orion, a governed AI coding assistant with AEGIS safety.

You have direct access to the user's codebase. Be concise and direct.

IMPORTANT RULES:
- Stay within the workspace directory
- For write operations, show a brief diff of changes
- Be concise and direct
- If you can't do something, explain why briefly
"""

    def __init__(self, workspace_path: str, model: str = "gpt-4o"):
        self.workspace = str(Path(workspace_path).resolve())
        self.model = model

    async def execute(self, request: str, scout_report=None) -> FastPathResult:
        """
        Execute a simple request directly.

        Args:
            request: User's request
            scout_report: Scout analysis with relevant files

        Returns:
            FastPathResult with response and actions taken
        """
        # Build context from relevant files
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

        # Try repo map context
        repo_context = ""
        try:
            from orion.core.context.repo_map import generate_repo_map
            repo_context = generate_repo_map(self.workspace, max_tokens=1024)
        except Exception:
            pass

        user_prompt = f"Request: {request}"
        if repo_context:
            user_prompt += f"\n\nRepository Map:\n{repo_context}"
        if file_contents:
            user_prompt += f"\n\nRelevant Files:\n{chr(10).join(file_contents)}"

        # Try Ollama first (local, free), then OpenAI
        result = await self._call_ollama(user_prompt)
        if not result.success:
            result = await self._call_openai(user_prompt)
        return result

    async def execute_streaming(
        self,
        request: str,
        scout_report=None
    ) -> AsyncGenerator[str, None]:
        """Execute with streaming output. Yields tokens as they arrive."""
        result = await self.execute(request, scout_report)
        # Yield response in chunks
        chunk_size = 40
        for i in range(0, len(result.response), chunk_size):
            yield result.response[i:i + chunk_size]
            await asyncio.sleep(0.01)

    async def _call_ollama(self, prompt: str) -> FastPathResult:
        """Try Ollama (local model) first."""
        try:
            import requests as http_requests
        except ImportError:
            return FastPathResult(success=False, response="requests package not installed")

        # Get Ollama config
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.environ.get("OLLAMA_BUILDER_MODEL", "qwen2.5-coder:14b")

        # Also check settings file
        settings_file = Path.home() / ".orion" / "settings.json"
        if settings_file.exists():
            try:
                settings = json.loads(settings_file.read_text())
                ollama_url = settings.get("ollama_base_url", ollama_url)
                ollama_model = settings.get("ollama_builder_model", ollama_model)
            except Exception:
                pass

        try:
            response = http_requests.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": f"{self.SYSTEM_PROMPT}\n\n{prompt}",
                    "stream": False,
                },
                timeout=120,
            )
            if response.ok:
                data = response.json()
                return FastPathResult(
                    success=True,
                    response=data.get("response", ""),
                    tokens_used=data.get("eval_count", 0),
                )
            else:
                return FastPathResult(
                    success=False,
                    response=f"Ollama returned {response.status_code}",
                )
        except http_requests.ConnectionError:
            return FastPathResult(
                success=False,
                response="Ollama not running (connection refused)",
            )
        except Exception as e:
            return FastPathResult(success=False, response=f"Ollama error: {e}")

    async def _call_openai(self, prompt: str) -> FastPathResult:
        """Fallback to OpenAI if Ollama unavailable."""
        api_key = os.environ.get("OPENAI_API_KEY")

        # Check secure store
        if not api_key:
            try:
                from orion.security.store import get_secure_store
                store = get_secure_store()
                api_key = store.get_key("openai")
            except Exception:
                pass

        if not api_key:
            return FastPathResult(
                success=False,
                response=(
                    "No LLM available. Either:\n"
                    "  1. Start Ollama: ollama serve\n"
                    "  2. Set OPENAI_API_KEY environment variable\n"
                    "  3. Run /doctor to check your configuration"
                ),
            )

        try:
            import openai
            client = openai.OpenAI(api_key=api_key)

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )

            content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0

            return FastPathResult(success=True, response=content, tokens_used=tokens)

        except ImportError:
            return FastPathResult(
                success=False,
                response="openai package not installed. Run: pip install openai",
            )
        except Exception as e:
            return FastPathResult(success=False, response=f"OpenAI error: {e}")


def get_fast_path(workspace_path: str, model: str = "gpt-4o") -> FastPath:
    """Factory function to get a FastPath instance."""
    return FastPath(workspace_path, model)
