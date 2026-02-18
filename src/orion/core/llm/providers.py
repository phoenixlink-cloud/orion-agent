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
Orion Agent -- LLM Provider Routing (v7.4.0)

Unified async call_provider() entry point.
Migrated from Orion_MVP/core/llm_calls.py, adapted to httpx async architecture.

Supports: OpenAI, Anthropic, Google, Ollama, Cohere, AWS Bedrock,
          Azure OpenAI, Groq, OpenRouter, Mistral, Together AI.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Callable

import httpx

from orion.core.llm.config import RoleConfig

logger = logging.getLogger("orion.llm.providers")

# ── Retry configuration ──────────────────────────────────────────────────

API_MAX_RETRIES = 3
API_RETRY_DELAY_SECONDS = 2

_RETRYABLE_KEYWORDS = [
    "timeout",
    "connection",
    "rate limit",
    "503",
    "502",
    "500",
    "temporarily unavailable",
    "overloaded",
    "retry",
]

# ── OpenAI-compatible providers ──────────────────────────────────────────

_OPENAI_COMPATIBLE = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_name": "groq",
        "display": "Groq",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_name": "openrouter",
        "display": "OpenRouter",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "key_name": "mistral",
        "display": "Mistral AI",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "key_name": "together",
        "display": "Together AI",
    },
}

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_TIMEOUT = 300


# ── Key retrieval helper ─────────────────────────────────────────────────


def _get_key(provider: str) -> str | None:
    """Retrieve credential: SecureStore API key -> env var."""
    # Try SecureStore first
    try:
        from orion.security.store import SecureStore

        store = SecureStore()
        key = store.get_key(provider)
        if key:
            return key
    except Exception:
        pass

    # Fallback: check standard environment variables
    import os

    env_key = os.environ.get(f"{provider.upper()}_API_KEY")
    if env_key:
        return env_key

    return None


def _error_json(message: str) -> str:
    return json.dumps({"outcome": "ANSWER", "response": message})


# ── Async retry wrapper ──────────────────────────────────────────────────


async def retry_api_call(
    func: Callable,
    max_retries: int = API_MAX_RETRIES,
    delay_seconds: float = API_RETRY_DELAY_SECONDS,
    component: str = "api",
) -> str:
    """Retry an async API call with exponential backoff."""
    last_error = None

    attempts_made = 0
    for attempt in range(max_retries):
        attempts_made = attempt + 1
        try:
            return await func()
        except httpx.HTTPStatusError as e:
            last_error = e
            status = e.response.status_code

            # Auth errors — never retry, give clear guidance
            if status in (401, 403):
                logger.error(
                    "[%s] Auth error %d (not retrying): %s", component, status, str(e)[:200]
                )
                return _error_json(
                    "API key is invalid or expired. Update your key via Settings → API Keys "
                    "in the dashboard, or run: /key set <provider> <new-key>"
                )

            # Model/resource not found — never retry
            if status == 404:
                logger.error("[%s] Resource not found: %s", component, str(e)[:200])
                url = str(e.request.url) if e.request else ""
                if "ollama" in url or "localhost:11434" in url:
                    return _error_json(
                        "Ollama model not found. Make sure you've pulled the model first with: "
                        "ollama pull <model-name>. Check available models in Settings → AI Model Setup."
                    )
                return _error_json(f"Resource not found (404): {str(e)[:150]}")

            # Server errors may be transient — retry
            if status in (500, 502, 503, 429):
                if attempt < max_retries - 1:
                    wait_time = delay_seconds * (2**attempt)
                    logger.warning(
                        "[%s] Retrying in %.1fs (HTTP %d, attempt %d/%d)",
                        component,
                        wait_time,
                        status,
                        attempts_made,
                        max_retries,
                    )
                    await asyncio.sleep(wait_time)
                    continue

            # Other HTTP errors — don't retry
            logger.error(
                "[%s] HTTP %d after %d attempt(s): %s",
                component,
                status,
                attempts_made,
                str(e)[:200],
            )
            break

        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            retryable = any(kw in error_str for kw in _RETRYABLE_KEYWORDS)

            if not retryable or attempt >= max_retries - 1:
                logger.error(
                    "[%s] API call failed after %d attempt(s): %s",
                    component,
                    attempts_made,
                    str(e)[:200],
                )
                break

            wait_time = delay_seconds * (2**attempt)
            logger.warning(
                "[%s] Retrying in %.1fs (attempt %d/%d): %s",
                component,
                wait_time,
                attempts_made,
                max_retries,
                str(e)[:100],
            )
            await asyncio.sleep(wait_time)

    return _error_json(f"API error after {attempts_made} attempt(s): {str(last_error)}")


# ── Provider-specific callers ────────────────────────────────────────────


async def _call_ollama(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4000,
    temperature: float = 0.7,
) -> str:
    """Call a local Ollama model (non-streaming)."""
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")


async def _call_ollama_streaming(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4000,
    temperature: float = 0.7,
) -> AsyncGenerator[str, None]:
    """Call a local Ollama model with streaming response."""
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        pass


async def _call_openai(
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    max_tokens: int = 8000,
    temperature: float = 0.3,
    base_url: str = "https://api.openai.com/v1",
) -> str:
    """Call OpenAI or any OpenAI-compatible provider."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_anthropic(
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    max_tokens: int = 8000,
) -> str:
    """Call Anthropic Claude API."""
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages", headers=headers, json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


async def _call_google(
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    max_tokens: int = 8000,
    temperature: float = 0.3,
) -> str:
    """Call Google Gemini API via REST (API key auth)."""
    base = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    url = f"{base}?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_cohere(
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    max_tokens: int = 8000,
) -> str:
    """Call Cohere Chat API."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post("https://api.cohere.com/v2/chat", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"][0]["text"]


async def _call_azure_openai(
    model: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    endpoint: str,
    api_version: str = "2024-12-01-preview",
    max_tokens: int = 8000,
    temperature: float = 0.3,
) -> str:
    """Call Azure OpenAI."""
    url = f"{endpoint}/openai/deployments/{model}/chat/completions?api-version={api_version}"
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_aws_bedrock(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 8000,
    temperature: float = 0.3,
) -> str:
    """Call AWS Bedrock (requires boto3 installed, uses sync in executor)."""
    import boto3

    access_key = _get_key("aws_access_key_id")
    secret_key = _get_key("aws_secret_access_key")
    region = _get_key("aws_bedrock_region") or "us-east-1"

    if not access_key or not secret_key:
        return _error_json(
            "AWS credentials not configured. Use /key set aws_access_key_id and aws_secret_access_key."
        )

    def _sync_call():
        bedrock = boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        response = bedrock.converse(
            modelId=model,
            messages=[{"role": "user", "content": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        return response["output"]["message"]["content"][0]["text"]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_call)


# ── Ollama availability check ────────────────────────────────────────────


async def is_ollama_available() -> bool:
    """Check if Ollama is running and available."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


# ── Unified call_provider ────────────────────────────────────────────────


async def call_provider(
    role_config: RoleConfig,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 8000,
    component: str = "provider",
    temperature: float = 0.3,
) -> str:
    """
    Async unified entry point for all LLM calls.

    Routes to the correct provider based on RoleConfig.
    Handles key retrieval, retry logic, and error formatting.

    Args:
        role_config: Provider and model to use
        system_prompt: System message
        user_prompt: User message
        max_tokens: Maximum tokens to generate
        component: Component name for logging
        temperature: Sampling temperature

    Returns:
        str: Model response text, or error JSON on failure
    """
    provider = role_config.provider
    model = role_config.model

    logger.info(
        "[%s] Calling %s/%s (prompt=%d chars)", component, provider, model, len(user_prompt)
    )

    # ── Ollama (local) ────────────────────────────────────────────────
    if provider == "ollama":

        async def _do():
            return await _call_ollama(model, system_prompt, user_prompt, max_tokens, temperature)

        return await retry_api_call(_do, component=component)

    # ── OpenAI ────────────────────────────────────────────────────────
    elif provider == "openai":
        api_key = _get_key("openai")
        if not api_key:
            return _error_json("OpenAI API key not configured. Use /key set openai <key>.")

        async def _do():
            return await _call_openai(
                model, system_prompt, user_prompt, api_key, max_tokens, temperature
            )

        return await retry_api_call(_do, component=component)

    # ── Anthropic ─────────────────────────────────────────────────────
    elif provider == "anthropic":
        api_key = _get_key("anthropic")
        if not api_key:
            return _error_json("Anthropic API key not configured. Use /key set anthropic <key>.")

        async def _do():
            return await _call_anthropic(model, system_prompt, user_prompt, api_key, max_tokens)

        return await retry_api_call(_do, component=component)

    # ── Google Gemini ─────────────────────────────────────────────────
    elif provider == "google":
        api_key = _get_key("google")
        if not api_key:
            return _error_json(
                "Google API key not configured. Get a free key at "
                "https://aistudio.google.com/apikey or use /key set google <key>."
            )

        async def _do():
            return await _call_google(
                model,
                system_prompt,
                user_prompt,
                api_key,
                max_tokens,
                temperature,
            )

        return await retry_api_call(_do, component=component)

    # ── Cohere ────────────────────────────────────────────────────────
    elif provider == "cohere":
        api_key = _get_key("cohere")
        if not api_key:
            return _error_json("Cohere API key not configured. Use /key set cohere <key>.")

        async def _do():
            return await _call_cohere(model, system_prompt, user_prompt, api_key, max_tokens)

        return await retry_api_call(_do, component=component)

    # ── AWS Bedrock ───────────────────────────────────────────────────
    elif provider == "aws_bedrock":

        async def _do():
            return await _call_aws_bedrock(
                model, system_prompt, user_prompt, max_tokens, temperature
            )

        return await retry_api_call(_do, component=component)

    # ── Azure OpenAI ──────────────────────────────────────────────────
    elif provider == "azure_openai":
        api_key = _get_key("azure_openai")
        endpoint = _get_key("azure_openai_endpoint") or ""
        api_version = _get_key("azure_openai_api_version") or "2024-12-01-preview"
        if not api_key or not endpoint:
            return _error_json(
                "Azure OpenAI not configured. Use /key set azure_openai, azure_openai_endpoint."
            )

        async def _do():
            return await _call_azure_openai(
                model,
                system_prompt,
                user_prompt,
                api_key,
                endpoint,
                api_version,
                max_tokens,
                temperature,
            )

        return await retry_api_call(_do, component=component)

    # ── OpenAI-compatible (Groq, OpenRouter, Mistral, Together) ───────
    elif provider in _OPENAI_COMPATIBLE:
        cfg = _OPENAI_COMPATIBLE[provider]
        api_key = _get_key(cfg["key_name"])
        if not api_key:
            return _error_json(
                f"{cfg['display']} API key not configured. Use /key set {cfg['key_name']} <key>."
            )

        async def _do():
            return await _call_openai(
                model, system_prompt, user_prompt, api_key, max_tokens, temperature, cfg["base_url"]
            )

        return await retry_api_call(_do, component=component)

    # ── Unknown ───────────────────────────────────────────────────────
    else:
        return _error_json(f"Unknown provider: {provider}")
