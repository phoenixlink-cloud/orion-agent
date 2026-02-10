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
Orion Agent -- LLM Provider Integrations (v6.4.0)

Re-exports from core/llm/providers.py for convenience.
All LLM provider logic lives in core/llm/providers.py (unified async call_provider).

Usage:
    from orion.integrations.llm import call_provider, is_ollama_available
"""

from orion.core.llm.providers import (
    call_provider,
    is_ollama_available,
    retry_api_call,
    OLLAMA_BASE_URL,
    OLLAMA_TIMEOUT,
    API_MAX_RETRIES,
)

__all__ = [
    "call_provider",
    "is_ollama_available",
    "retry_api_call",
    "OLLAMA_BASE_URL",
    "OLLAMA_TIMEOUT",
    "API_MAX_RETRIES",
]
