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
Orion Agent -- Pattern Extraction (v7.4.0)

Identifies success patterns and anti-patterns from outcomes.
Extracts request type classification for categorizing learnings.

Migrated from Orion_MVP/core/learning.py (pattern logic).
"""

import logging
from typing import Any

from orion.core.memory.institutional import InstitutionalMemory

logger = logging.getLogger("orion.learning.patterns")


# ── Request type classification ──────────────────────────────────────────

_REQUEST_TYPE_KEYWORDS = {
    "bug_fix": ["fix", "bug", "error", "issue", "broken", "crash", "fail"],
    "feature_add": ["add", "create", "implement", "new", "build", "generate"],
    "refactor": ["refactor", "improve", "optimize", "clean", "restructure"],
    "explanation": ["explain", "what", "how", "why", "describe", "tell me"],
    "testing": ["test", "testing", "spec", "unittest", "pytest"],
    "documentation": ["document", "docs", "comment", "readme", "docstring"],
    "read_operation": ["read", "show", "display", "list", "print", "cat"],
}


def classify_request_type(request: str) -> str:
    """Classify a user request into a category for pattern matching."""
    lower = request.lower()
    for rtype, keywords in _REQUEST_TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return rtype
    return "general"


# ── Pattern extraction ───────────────────────────────────────────────────


def extract_success_pattern(
    request: str,
    response: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Extract a success pattern from a positive interaction.

    Returns a dict describing the pattern for storage.
    """
    request_type = classify_request_type(request)
    return {
        "type": "success",
        "request_type": request_type,
        "request_summary": request[:100],
        "response_summary": response[:200],
        "quality_score": 0.9,
        "context": context or {},
    }


def extract_failure_pattern(
    request: str,
    response: str,
    feedback: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Extract an anti-pattern from a failed interaction.

    Returns a dict describing the anti-pattern for storage.
    """
    request_type = classify_request_type(request)
    return {
        "type": "failure",
        "request_type": request_type,
        "request_summary": request[:100],
        "response_summary": response[:200],
        "user_feedback": feedback[:200],
        "quality_score": 0.2,
        "context": context or {},
    }


def extract_edit_pattern(
    request: str,
    original: str,
    edited: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Extract a preference pattern from user edits.

    User edits are gold -- they show exactly what was wanted.
    """
    request_type = classify_request_type(request)
    return {
        "type": "preference",
        "request_type": request_type,
        "request_summary": request[:100],
        "original_snippet": original[:200],
        "preferred_snippet": edited[:200],
        "quality_score": 0.85,
        "context": context or {},
    }


# ── Batch pattern analysis ───────────────────────────────────────────────


def analyze_patterns(
    institutional: InstitutionalMemory,
    min_confidence: float = 0.7,
    min_severity: float = 0.6,
) -> dict[str, Any]:
    """
    Analyze accumulated patterns and anti-patterns.

    Returns a summary of what Orion has learned over time,
    grouped by type and sorted by significance.
    """
    patterns = institutional.get_learned_patterns(min_confidence)
    anti_patterns = institutional.get_learned_anti_patterns(min_severity)

    # Group patterns by implicit request type
    by_type: dict[str, list[dict]] = {}
    for p in patterns:
        desc = p.description
        rtype = "general"
        for t in _REQUEST_TYPE_KEYWORDS:
            if t in desc.lower():
                rtype = t
                break
        by_type.setdefault(rtype, []).append(
            {
                "description": p.description,
                "confidence": p.confidence,
                "success_count": p.success_count,
            }
        )

    return {
        "total_patterns": len(patterns),
        "total_anti_patterns": len(anti_patterns),
        "patterns_by_type": by_type,
        "top_anti_patterns": [
            {
                "description": ap.description,
                "severity": ap.severity,
                "occurrences": ap.occurrence_count,
            }
            for ap in anti_patterns[:5]
        ],
    }


def get_learnings_for_prompt(
    institutional: InstitutionalMemory,
    request: str,
    max_items: int = 5,
) -> str:
    """
    Get relevant learnings formatted for LLM prompt injection.

    Returns a markdown string to include in the system/user prompt,
    or empty string if no relevant learnings exist.
    """
    wisdom = institutional.get_relevant_wisdom(request)

    lines: list[str] = []
    patterns = wisdom.get("learned_patterns", [])
    anti_patterns = wisdom.get("learned_anti_patterns", [])
    prefs = wisdom.get("user_preferences", {})

    if patterns:
        lines.append("## Learned Patterns")
        for p in patterns[:max_items]:
            lines.append(f"- {p['description'][:150]}")

    if anti_patterns:
        lines.append("\n## Known Anti-Patterns (Avoid)")
        for ap in anti_patterns[:max_items]:
            lines.append(f"- {ap['description'][:150]}: {ap['reason'][:100]}")

    if prefs:
        lines.append("\n## User Preferences")
        for k, v in list(prefs.items())[:max_items]:
            lines.append(f"- {k}: {v}")

    return "\n".join(lines) if lines else ""
