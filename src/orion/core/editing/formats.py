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
Orion Agent -- Edit Format Selector (v7.4.0)

Selects the optimal edit format for each LLM model and generates
model-specific system prompt instructions.

Architecture:
    1. MODEL PROFILES:  Known capabilities per model family
    2. FORMAT SCORING:  Score each format for the current model + edit size
    3. PROMPT INJECTION: Generate format-specific instructions for the LLM
    4. RESPONSE PARSING: Route to correct parser based on selected format
"""

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# EDIT FORMATS
# ---------------------------------------------------------------------------


class EditFormat(Enum):
    """Available edit output formats."""

    WHOLE_FILE = "whole_file"
    SEARCH_REPLACE = "search_replace"
    UNIFIED_DIFF = "unified_diff"
    ARCHITECT = "architect"


# ---------------------------------------------------------------------------
# MODEL PROFILES
# ---------------------------------------------------------------------------


@dataclass
class ModelProfile:
    """Capabilities of a model family for edit format selection."""

    name: str
    preferred_format: EditFormat
    supports_diff: bool
    supports_search_replace: bool
    supports_whole_file: bool
    supports_architect: bool
    max_reliable_output: int
    diff_accuracy: float
    search_replace_accuracy: float
    whole_file_accuracy: float


MODEL_PROFILES: dict[str, ModelProfile] = {
    # OpenAI GPT-5 Series
    "gpt-5.2": ModelProfile(
        "gpt-5.2", EditFormat.ARCHITECT, True, True, True, True, 16384, 0.97, 0.98, 0.97
    ),
    "gpt-5.1": ModelProfile(
        "gpt-5.1", EditFormat.ARCHITECT, True, True, True, True, 16384, 0.96, 0.97, 0.96
    ),
    "gpt-5": ModelProfile(
        "gpt-5", EditFormat.ARCHITECT, True, True, True, True, 16384, 0.95, 0.97, 0.96
    ),
    "gpt-5-mini": ModelProfile(
        "gpt-5-mini", EditFormat.SEARCH_REPLACE, True, True, True, False, 8192, 0.80, 0.92, 0.90
    ),
    "gpt-5-nano": ModelProfile(
        "gpt-5-nano", EditFormat.SEARCH_REPLACE, False, True, True, False, 4096, 0.60, 0.88, 0.85
    ),
    # OpenAI GPT-4.1 Series
    "gpt-4.1": ModelProfile(
        "gpt-4.1", EditFormat.SEARCH_REPLACE, True, True, True, True, 8192, 0.90, 0.96, 0.93
    ),
    "gpt-4.1-mini": ModelProfile(
        "gpt-4.1-mini", EditFormat.SEARCH_REPLACE, True, True, True, False, 4096, 0.70, 0.90, 0.87
    ),
    "gpt-4.1-nano": ModelProfile(
        "gpt-4.1-nano", EditFormat.SEARCH_REPLACE, False, True, True, False, 2048, 0.50, 0.85, 0.82
    ),
    # OpenAI o-Series (Reasoning)
    "o3": ModelProfile("o3", EditFormat.ARCHITECT, True, True, True, True, 16384, 0.95, 0.97, 0.96),
    "o3-pro": ModelProfile(
        "o3-pro", EditFormat.ARCHITECT, True, True, True, True, 16384, 0.96, 0.98, 0.97
    ),
    "o4-mini": ModelProfile(
        "o4-mini", EditFormat.SEARCH_REPLACE, True, True, True, True, 8192, 0.88, 0.94, 0.92
    ),
    "o3-mini": ModelProfile(
        "o3-mini", EditFormat.SEARCH_REPLACE, True, True, True, True, 4096, 0.82, 0.92, 0.88
    ),
    "o1": ModelProfile("o1", EditFormat.ARCHITECT, True, True, True, True, 8192, 0.90, 0.95, 0.95),
    # OpenAI GPT-4o Series (Legacy)
    "gpt-4o": ModelProfile(
        "gpt-4o", EditFormat.SEARCH_REPLACE, True, True, True, True, 4096, 0.85, 0.95, 0.90
    ),
    "gpt-4o-mini": ModelProfile(
        "gpt-4o-mini", EditFormat.SEARCH_REPLACE, False, True, True, False, 2048, 0.50, 0.85, 0.80
    ),
    "gpt-4-turbo": ModelProfile(
        "gpt-4-turbo", EditFormat.SEARCH_REPLACE, True, True, True, True, 4096, 0.80, 0.92, 0.88
    ),
    # Anthropic Claude 4.5 Series
    "claude-opus-4-5": ModelProfile(
        "claude-opus-4-5", EditFormat.ARCHITECT, True, True, True, True, 16384, 0.96, 0.97, 0.98
    ),
    "claude-sonnet-4-5": ModelProfile(
        "claude-sonnet-4-5", EditFormat.WHOLE_FILE, True, True, True, True, 16384, 0.94, 0.96, 0.97
    ),
    "claude-haiku-4-5": ModelProfile(
        "claude-haiku-4-5",
        EditFormat.SEARCH_REPLACE,
        True,
        True,
        True,
        False,
        4096,
        0.70,
        0.88,
        0.90,
    ),
    # Anthropic Claude 4 Series
    "claude-opus-4": ModelProfile(
        "claude-opus-4", EditFormat.WHOLE_FILE, True, True, True, True, 8192, 0.92, 0.95, 0.97
    ),
    "claude-sonnet-4": ModelProfile(
        "claude-sonnet-4", EditFormat.WHOLE_FILE, True, True, True, True, 8192, 0.88, 0.93, 0.96
    ),
    # Anthropic Claude 3.x Legacy
    "claude-3-7-sonnet": ModelProfile(
        "claude-3-7-sonnet", EditFormat.WHOLE_FILE, True, True, True, True, 4096, 0.85, 0.90, 0.95
    ),
    "claude-3-5-sonnet": ModelProfile(
        "claude-3-5-sonnet", EditFormat.WHOLE_FILE, True, True, True, True, 4096, 0.80, 0.88, 0.95
    ),
    "claude-3-5-haiku": ModelProfile(
        "claude-3-5-haiku",
        EditFormat.SEARCH_REPLACE,
        False,
        True,
        True,
        False,
        2048,
        0.45,
        0.82,
        0.85,
    ),
    "claude-3-opus": ModelProfile(
        "claude-3-opus", EditFormat.WHOLE_FILE, True, True, True, True, 4096, 0.82, 0.90, 0.95
    ),
    # Google Gemini 3
    "gemini-3-pro": ModelProfile(
        "gemini-3-pro", EditFormat.ARCHITECT, True, True, True, True, 8192, 0.90, 0.95, 0.93
    ),
    "gemini-3-flash": ModelProfile(
        "gemini-3-flash", EditFormat.SEARCH_REPLACE, True, True, True, False, 4096, 0.75, 0.90, 0.88
    ),
    # Google Gemini 2.5
    "gemini-2.5-pro": ModelProfile(
        "gemini-2.5-pro", EditFormat.SEARCH_REPLACE, True, True, True, True, 4096, 0.85, 0.92, 0.90
    ),
    "gemini-2.5-flash": ModelProfile(
        "gemini-2.5-flash",
        EditFormat.SEARCH_REPLACE,
        True,
        True,
        True,
        False,
        2048,
        0.65,
        0.88,
        0.85,
    ),
    # Google Legacy
    "gemini-pro": ModelProfile(
        "gemini-pro", EditFormat.SEARCH_REPLACE, False, True, True, False, 2048, 0.40, 0.80, 0.82
    ),
    "gemini-2.0-flash": ModelProfile(
        "gemini-2.0-flash",
        EditFormat.SEARCH_REPLACE,
        False,
        True,
        True,
        False,
        2048,
        0.45,
        0.82,
        0.80,
    ),
    # Cohere Command
    "command-a": ModelProfile(
        "command-a", EditFormat.SEARCH_REPLACE, True, True, True, True, 8192, 0.85, 0.92, 0.90
    ),
    "command-r-plus": ModelProfile(
        "command-r-plus", EditFormat.SEARCH_REPLACE, True, True, True, True, 4096, 0.78, 0.88, 0.85
    ),
    "command-r": ModelProfile(
        "command-r", EditFormat.SEARCH_REPLACE, False, True, True, False, 2048, 0.55, 0.80, 0.78
    ),
    "command-r7b": ModelProfile(
        "command-r7b", EditFormat.WHOLE_FILE, False, True, True, False, 1024, 0.40, 0.72, 0.70
    ),
    # AWS Bedrock Nova
    "nova-pro": ModelProfile(
        "nova-pro", EditFormat.SEARCH_REPLACE, True, True, True, True, 4096, 0.80, 0.88, 0.85
    ),
    "nova-lite": ModelProfile(
        "nova-lite", EditFormat.SEARCH_REPLACE, False, True, True, False, 2048, 0.50, 0.78, 0.75
    ),
    "nova-micro": ModelProfile(
        "nova-micro", EditFormat.WHOLE_FILE, False, True, True, False, 1024, 0.35, 0.70, 0.68
    ),
    # Mistral AI
    "mistral-large": ModelProfile(
        "mistral-large", EditFormat.SEARCH_REPLACE, True, True, True, True, 8192, 0.88, 0.93, 0.90
    ),
    "mistral-medium": ModelProfile(
        "mistral-medium", EditFormat.SEARCH_REPLACE, True, True, True, True, 4096, 0.82, 0.90, 0.88
    ),
    "mistral-small": ModelProfile(
        "mistral-small", EditFormat.SEARCH_REPLACE, False, True, True, False, 2048, 0.55, 0.82, 0.80
    ),
    "codestral": ModelProfile(
        "codestral", EditFormat.SEARCH_REPLACE, True, True, True, True, 8192, 0.90, 0.95, 0.92
    ),
    "devstral": ModelProfile(
        "devstral", EditFormat.SEARCH_REPLACE, True, True, True, True, 8192, 0.88, 0.93, 0.90
    ),
    "magistral-medium": ModelProfile(
        "magistral-medium", EditFormat.ARCHITECT, True, True, True, True, 8192, 0.90, 0.94, 0.92
    ),
    "magistral-small": ModelProfile(
        "magistral-small", EditFormat.SEARCH_REPLACE, True, True, True, True, 4096, 0.78, 0.88, 0.85
    ),
    # Groq
    "gpt-oss-120b": ModelProfile(
        "gpt-oss-120b", EditFormat.SEARCH_REPLACE, True, True, True, True, 8192, 0.88, 0.94, 0.92
    ),
    "gpt-oss-20b": ModelProfile(
        "gpt-oss-20b", EditFormat.SEARCH_REPLACE, False, True, True, False, 4096, 0.60, 0.85, 0.82
    ),
    "llama-3.3-70b": ModelProfile(
        "llama-3.3-70b", EditFormat.SEARCH_REPLACE, True, True, True, True, 4096, 0.82, 0.90, 0.88
    ),
    "llama-3.1-8b": ModelProfile(
        "llama-3.1-8b", EditFormat.SEARCH_REPLACE, False, True, True, False, 2048, 0.45, 0.78, 0.75
    ),
    "llama-4-maverick": ModelProfile(
        "llama-4-maverick",
        EditFormat.SEARCH_REPLACE,
        True,
        True,
        True,
        True,
        4096,
        0.80,
        0.88,
        0.86,
    ),
    "llama-4-scout": ModelProfile(
        "llama-4-scout", EditFormat.SEARCH_REPLACE, False, True, True, False, 2048, 0.55, 0.82, 0.80
    ),
    # Local models (Ollama)
    "ollama_default": ModelProfile(
        "ollama_default", EditFormat.WHOLE_FILE, False, True, True, False, 1024, 0.25, 0.65, 0.70
    ),
    "codellama": ModelProfile(
        "codellama", EditFormat.WHOLE_FILE, False, True, True, False, 1024, 0.30, 0.70, 0.75
    ),
    "deepseek-coder": ModelProfile(
        "deepseek-coder", EditFormat.SEARCH_REPLACE, True, True, True, False, 2048, 0.65, 0.85, 0.80
    ),
    "qwen2.5-coder": ModelProfile(
        "qwen2.5-coder", EditFormat.SEARCH_REPLACE, True, True, True, False, 2048, 0.60, 0.82, 0.78
    ),
}

DEFAULT_PROFILE = ModelProfile(
    name="unknown",
    preferred_format=EditFormat.SEARCH_REPLACE,
    supports_diff=False,
    supports_search_replace=True,
    supports_whole_file=True,
    supports_architect=False,
    max_reliable_output=2048,
    diff_accuracy=0.40,
    search_replace_accuracy=0.70,
    whole_file_accuracy=0.70,
)


# ---------------------------------------------------------------------------
# FORMAT SELECTION
# ---------------------------------------------------------------------------


def get_model_profile(model_name: str) -> ModelProfile:
    """
    Get the profile for a model.

    Matching priority:
      1. Exact match on full model ID
      2. Model name starts with a known profile key (longest match wins)
      3. Profile key is a substring of model name (longest match wins)
      4. Provider-based fallback (ollama)
      5. DEFAULT_PROFILE
    """
    if not model_name:
        return DEFAULT_PROFILE

    model_lower = model_name.lower()

    # 1. Exact match
    if model_lower in MODEL_PROFILES:
        return MODEL_PROFILES[model_lower]

    # 2. Longest prefix match
    best_key, best_profile = "", None
    for key, profile in MODEL_PROFILES.items():
        if model_lower.startswith(key) and len(key) > len(best_key):
            best_key, best_profile = key, profile
    if best_profile:
        return best_profile

    # 3. Longest substring match
    best_key, best_profile = "", None
    for key, profile in MODEL_PROFILES.items():
        if key in model_lower and len(key) > len(best_key):
            best_key, best_profile = key, profile
    if best_profile:
        return best_profile

    # 4. Provider-based fallback for local models
    if ":" in model_lower or "ollama" in model_lower:
        return MODEL_PROFILES.get("ollama_default", DEFAULT_PROFILE)

    return DEFAULT_PROFILE


@dataclass
class FormatDecision:
    """The selected format and reasoning."""

    format: EditFormat
    model_profile: ModelProfile
    reasoning: str
    confidence: float


def select_edit_format(
    model_name: str,
    file_size_lines: int = 0,
    change_size: str = "medium",
    file_extension: str = ".py",
) -> FormatDecision:
    """
    Select the optimal edit format based on model, file size, and change scope.
    """
    profile = get_model_profile(model_name)
    scores: dict[EditFormat, float] = {}

    # -- WHOLE FILE --
    if profile.supports_whole_file:
        score = profile.whole_file_accuracy * 100
        if file_size_lines > 500:
            score -= 30
        elif file_size_lines > 200:
            score -= 15
        if change_size == "rewrite":
            score += 25
        if file_size_lines == 0:
            score += 40
        scores[EditFormat.WHOLE_FILE] = score

    # -- SEARCH/REPLACE --
    if profile.supports_search_replace:
        score = profile.search_replace_accuracy * 100
        if change_size in ("tiny", "small"):
            score += 20
        elif change_size == "medium":
            score += 10
        if change_size == "rewrite":
            score -= 25
        if file_size_lines == 0:
            score -= 50
        scores[EditFormat.SEARCH_REPLACE] = score

    # -- UNIFIED DIFF --
    if profile.supports_diff:
        score = profile.diff_accuracy * 100
        if change_size in ("medium", "large"):
            score += 15
        if change_size == "tiny":
            score -= 10
        if change_size == "rewrite":
            score -= 20
        if file_size_lines == 0:
            score -= 40
        scores[EditFormat.UNIFIED_DIFF] = score

    # -- ARCHITECT --
    if profile.supports_architect:
        score = 70
        if change_size in ("large", "rewrite"):
            score += 20
        if change_size in ("tiny", "small"):
            score -= 20
        scores[EditFormat.ARCHITECT] = score

    if not scores:
        return FormatDecision(
            format=EditFormat.WHOLE_FILE,
            model_profile=profile,
            reasoning="Fallback: no formats scored",
            confidence=0.3,
        )

    best_format = max(scores, key=lambda f: scores[f])
    best_score = scores[best_format]
    confidence = min(best_score / 120, 1.0)

    reasons = [f"Model: {profile.name}"]
    if file_size_lines > 0:
        reasons.append(f"File: {file_size_lines} lines")
    reasons.append(f"Change: {change_size}")
    reasons.append(
        f"Format scores: {', '.join(f'{f.value}={s:.0f}' for f, s in sorted(scores.items(), key=lambda x: -x[1]))}"
    )

    return FormatDecision(
        format=best_format,
        model_profile=profile,
        reasoning="; ".join(reasons),
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# PROMPT INSTRUCTIONS PER FORMAT
# ---------------------------------------------------------------------------

WHOLE_FILE_INSTRUCTIONS = """
When editing a file, return the COMPLETE file content inside a code block:

```<language>
# entire file content here
```

Return the FULL file, not just the changed parts. This ensures nothing is lost.
Do NOT use placeholders like "... rest of file ..." -- include every line.
"""

SEARCH_REPLACE_INSTRUCTIONS = """
When editing a file, use SEARCH/REPLACE blocks to show only the changes:

<<<SEARCH
exact text to find (copy from the file verbatim, including whitespace)
===
replacement text
REPLACE>>>

Rules:
- The SEARCH text must EXACTLY match the original file content
- Include enough context lines to make the match unique
- Use multiple SEARCH/REPLACE blocks for multiple changes
- Order blocks from top to bottom of the file
- Do NOT include line numbers in the search/replace text
"""

UNIFIED_DIFF_INSTRUCTIONS = """
When editing a file, return changes as a unified diff:

```diff
--- a/filename.py
+++ b/filename.py
@@ -10,7 +10,8 @@
 context line (unchanged, starts with space)
-removed line (starts with minus)
+added line (starts with plus)
 context line (unchanged, starts with space)
```

Rules:
- Include 3 lines of context around each change
- Use correct @@ hunk headers with line numbers
- Prefix unchanged lines with a space (not blank)
- Use separate hunks for non-adjacent changes
"""

ARCHITECT_INSTRUCTIONS = """
When editing a file, describe the changes precisely in natural language.
Do NOT write code. Instead, specify:

1. WHAT to change (function name, class, line range)
2. HOW to change it (add, remove, modify, replace)
3. The exact new content for each change

Be specific enough that another system can apply these changes mechanically.
"""

FORMAT_INSTRUCTIONS: dict[EditFormat, str] = {
    EditFormat.WHOLE_FILE: WHOLE_FILE_INSTRUCTIONS,
    EditFormat.SEARCH_REPLACE: SEARCH_REPLACE_INSTRUCTIONS,
    EditFormat.UNIFIED_DIFF: UNIFIED_DIFF_INSTRUCTIONS,
    EditFormat.ARCHITECT: ARCHITECT_INSTRUCTIONS,
}


def get_format_instructions(decision: FormatDecision) -> str:
    """Get the system prompt instructions for the selected edit format."""
    return FORMAT_INSTRUCTIONS.get(decision.format, SEARCH_REPLACE_INSTRUCTIONS)


def get_format_instructions_for_model(model_name: str, **kwargs) -> tuple[EditFormat, str]:
    """
    Convenience: select format and return instructions in one call.

    Returns:
        (format, instructions_string)
    """
    decision = select_edit_format(model_name, **kwargs)
    instructions = get_format_instructions(decision)
    return decision.format, instructions


# ---------------------------------------------------------------------------
# FORMAT OVERRIDE (user preference)
# ---------------------------------------------------------------------------

_user_override: EditFormat | None = None


def set_format_override(fmt: EditFormat | None):
    """Allow user to force a specific edit format."""
    global _user_override
    _user_override = fmt


def get_format_override() -> EditFormat | None:
    """Get the user's format override, if set."""
    return _user_override


def select_edit_format_with_override(model_name: str, **kwargs) -> FormatDecision:
    """Select format, respecting user override if set."""
    if _user_override is not None:
        profile = get_model_profile(model_name)
        return FormatDecision(
            format=_user_override,
            model_profile=profile,
            reasoning=f"User override: {_user_override.value}",
            confidence=1.0,
        )
    return select_edit_format(model_name, **kwargs)
