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
Orion Agent -- Reviewer (v6.4.0)

Reviews Builder proposals for correctness, safety, and quality.
Migrated from Orion_MVP/core/llm_calls.py (call_claude_reviewer).

Decisions:
  - APPROVE: Proposal is acceptable as-is
  - REVISE_AND_APPROVE: Fixable issues corrected, then approved
  - BLOCK: Safety/constraint violation (hard stop)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

logger = logging.getLogger("orion.reviewer")


@dataclass
class ReviewerResult:
    """Result from Reviewer evaluation."""
    decision: str         # "APPROVE", "REVISE_AND_APPROVE", "BLOCK"
    assessment: str       # Brief overall assessment
    revised_output: Optional[Dict[str, Any]] = None  # Corrected proposal if REVISE_AND_APPROVE
    revision_notes: List[str] = field(default_factory=list)
    block_reason: str = ""
    raw: str = ""
    provider: str = ""
    model: str = ""


def _get_reviewer_persona() -> str:
    """Load the Orion persona for the Reviewer."""
    try:
        from orion.core.persona import get_reviewer_persona
        return get_reviewer_persona()
    except Exception:
        return "You are a quality-control reviewer in a governed AI system."


_REVIEWER_SYSTEM_PROMPT = """{persona}

Current mode: {mode}

## YOUR THREE DECISIONS

1. **APPROVE** - Proposal is acceptable as-is
2. **REVISE_AND_APPROVE** - Proposal has FIXABLE issues; you correct them and approve
3. **BLOCK** - Proposal violates safety, workspace confinement, or user constraints (HARD STOP)

## WHEN TO REVISE_AND_APPROVE (preferred over blocking)

Use REVISE_AND_APPROVE for fixable issues:
- **STUBS/TODOs**: REPLACE them with REAL, WORKING implementations
- Incorrect file paths (fix them)
- Framework drift (correct the framework)
- Structural issues (reorganize)
- Minor errors in code (fix them)
- Incomplete implementations (COMPLETE them with real code)

CRITICAL: If Builder provides stubs or TODOs:
1. You MUST replace them with complete, functional implementations
2. Do NOT block for stubs - REVISE them into real implementations

## WHEN TO BLOCK (use sparingly)

ONLY block for:
- Safety violations (malicious code, system access)
- Workspace escape attempts (paths outside workspace)
- User constraint violations (explicit "do not" instructions)

DO NOT BLOCK FOR:
- Stubs or TODOs (REVISE them instead)
- Incomplete implementations (COMPLETE them)
- Scaffolding quality (REVISE instead)

## RESPONSE FORMAT

Respond with JSON:
{{
    "decision": "APPROVE" | "REVISE_AND_APPROVE" | "BLOCK",
    "revised_output": {{...}},
    "revision_notes": ["what was changed", "and why"],
    "block_reason": "why this must be blocked",
    "assessment": "brief overall assessment"
}}

IMPORTANT: Prefer REVISE_AND_APPROVE over BLOCK. Enable progress, don't stall it."""


async def run_reviewer(
    user_input: str,
    builder_output: str,
    evidence_context: str,
    mode: str = "safe",
    session_header: str = "",
) -> ReviewerResult:
    """
    Run the Reviewer agent.

    Args:
        user_input: Original user request
        builder_output: Raw Builder response (JSON string or text)
        evidence_context: Formatted evidence from workspace
        mode: Current AEGIS mode
        session_header: Session state header

    Returns:
        ReviewerResult with decision and optional revisions
    """
    from orion.core.llm.config import get_model_config
    from orion.core.agents.builder import _call_provider, extract_json

    model_cfg = get_model_config()
    reviewer = model_cfg.get_reviewer()

    system_prompt = _REVIEWER_SYSTEM_PROMPT.format(
        persona=_get_reviewer_persona(),
        mode=mode.upper(),
    )

    user_prompt = f"""## ORIGINAL USER REQUEST
{user_input}

{session_header}## BUILDER'S PROPOSAL
{builder_output}

## EVIDENCE
{evidence_context}

Review the Builder's proposal. Decide: APPROVE, REVISE_AND_APPROVE, or BLOCK."""

    logger.info(f"Reviewer calling {reviewer.provider}/{reviewer.model}")

    try:
        raw = await _call_provider(
            provider=reviewer.provider,
            model=reviewer.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=8000,
            temperature=0.3,
        )
    except Exception as e:
        logger.error(f"Reviewer call failed: {e}")
        return ReviewerResult(
            decision="APPROVE",
            assessment=f"Reviewer unavailable ({e}), defaulting to approve.",
            raw=str(e),
            provider=reviewer.provider,
            model=reviewer.model,
        )

    # Parse response
    parsed = extract_json(raw)
    if parsed:
        decision = parsed.get("decision", "APPROVE").upper()
        # Backward compat: old "approved" field
        if "approved" in parsed and "decision" not in parsed:
            decision = "APPROVE" if parsed.get("approved", True) else "BLOCK"

        return ReviewerResult(
            decision=decision,
            assessment=parsed.get("assessment", ""),
            revised_output=parsed.get("revised_output"),
            revision_notes=parsed.get("revision_notes", []),
            block_reason=parsed.get("block_reason", ""),
            raw=raw,
            provider=reviewer.provider,
            model=reviewer.model,
        )

    # Couldn't parse -- default to approve
    return ReviewerResult(
        decision="APPROVE",
        assessment="Could not parse reviewer response, defaulting to approve.",
        raw=raw,
        provider=reviewer.provider,
        model=reviewer.model,
    )
