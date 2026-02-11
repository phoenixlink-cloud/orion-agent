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
Orion Agent -- Governor (v7.4.0)

Orion's own decision layer. Always Orion, never configurable.
Migrated from Orion_MVP/core/llm_calls.py (orion_governor_decision).

This is DETERMINISTIC LOGIC, not an LLM call.
It takes the Builder's proposal and Reviewer's decision,
then produces the final outcome.

Governor rules (from Orion Persona):
  - BLOCK -> stop, show block reason (Reviewer says HARD STOP)
  - REVISE_AND_APPROVE -> use reviewer's corrected proposal
  - APPROVE -> use builder's original proposal
  - SAFE mode -> suppress file actions, show as answer

Governance hierarchy (immutable):
  Human authority -> Governance framework -> AI autonomy
  Never the reverse.

Autonomy tiers:
  GREEN:  Proceed independently (low-risk, reversible)
  YELLOW: Proceed then report (medium-risk)
  RED:    Await approval (high-risk, irreversible)
  HARD:   Never -- human only (financial, legal, ethical)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from orion.core.agents.builder import BuilderResult, extract_json
from orion.core.agents.reviewer import ReviewerResult

logger = logging.getLogger("orion.governor")

# Hard boundary categories -- Governor NEVER allows these through autonomously.
# These are structural, not configurable.
HARD_BOUNDARIES = frozenset({
    "financial_transaction",
    "legal_commitment",
    "ethical_violation",
    "production_deploy",
    "security_credential_exposure",
    "user_data_deletion",
})


@dataclass
class GovernorResult:
    """Final outcome from Governor decision."""
    outcome: str          # "ANSWER", "PLAN", "ACTION_INTENT"
    response: str         # Human-readable response
    actions: List[Dict[str, Any]] = field(default_factory=list)
    explanation: str = ""
    reviewer_decision: str = ""
    revision_notes: List[str] = field(default_factory=list)
    proposal_source: str = "builder"  # "builder" or "reviewer_revised"


def decide(
    builder_result: BuilderResult,
    reviewer_result: ReviewerResult,
    mode: str = "safe",
) -> GovernorResult:
    """
    Governor makes the final deterministic decision.

    This is NOT an LLM call. Pure logic only.

    Args:
        builder_result: Output from Builder agent
        reviewer_result: Output from Reviewer agent
        mode: Current AEGIS mode (safe/pro/project)

    Returns:
        GovernorResult with final outcome
    """
    decision = reviewer_result.decision

    # =========================================================================
    # BLOCK -- hard stop
    # =========================================================================
    if decision == "BLOCK":
        logger.warning(f"Governor: Reviewer BLOCKED -- {reviewer_result.block_reason}")
        return GovernorResult(
            outcome="ANSWER",
            response=f"⛔ Reviewer BLOCKED this proposal.\n\nReason: {reviewer_result.block_reason}",
            explanation="Reviewer blocked execution due to safety or constraint violation.",
            reviewer_decision="BLOCK",
        )

    # =========================================================================
    # Determine which proposal to use
    # =========================================================================
    proposal_source = "builder"
    outcome = builder_result.outcome
    response = builder_result.response
    actions = builder_result.actions
    explanation = builder_result.explanation

    if decision == "REVISE_AND_APPROVE" and reviewer_result.revised_output:
        # Use the reviewer's corrected proposal
        revised = reviewer_result.revised_output
        if isinstance(revised, dict):
            outcome = revised.get("outcome", outcome)
            response = revised.get("response", revised.get("explanation", response))
            actions = revised.get("actions", actions)
            explanation = revised.get("explanation", explanation)
        proposal_source = "reviewer_revised"
        logger.info(f"Governor: Using reviewer-revised proposal ({len(reviewer_result.revision_notes)} corrections)")

    # Build revision suffix
    revision_suffix = ""
    if decision == "REVISE_AND_APPROVE" and reviewer_result.revision_notes:
        revision_suffix = f"\n\n📝 Reviewer corrections: {'; '.join(reviewer_result.revision_notes)}"

    # =========================================================================
    # ACTION_INTENT -- mode gating
    # =========================================================================
    if outcome == "ACTION_INTENT":
        if mode not in ("pro", "project"):
            # SAFE mode: suppress file actions, show as answer
            display = explanation or response or "I can help with that!"
            return GovernorResult(
                outcome="ANSWER",
                response=display + "\n\n💡 _File actions are available in PRO mode. Use `/mode pro` to enable edits._",
                explanation="Safe mode: response shown, file actions suppressed.",
                reviewer_decision=decision,
                revision_notes=reviewer_result.revision_notes if decision == "REVISE_AND_APPROVE" else [],
                proposal_source=proposal_source,
            )

        return GovernorResult(
            outcome="ACTION_INTENT",
            response=(response or explanation or "") + revision_suffix,
            actions=actions,
            explanation=f"Builder proposed {len(actions)} action(s). Reviewer {decision.lower().replace('_', ' ')}.",
            reviewer_decision=decision,
            revision_notes=reviewer_result.revision_notes if decision == "REVISE_AND_APPROVE" else [],
            proposal_source=proposal_source,
        )

    # =========================================================================
    # PLAN
    # =========================================================================
    if outcome == "PLAN":
        return GovernorResult(
            outcome="PLAN",
            response=(response or "") + revision_suffix,
            explanation=f"Builder provided a plan. Reviewer {decision.lower().replace('_', ' ')}.",
            reviewer_decision=decision,
            revision_notes=reviewer_result.revision_notes if decision == "REVISE_AND_APPROVE" else [],
            proposal_source=proposal_source,
        )

    # =========================================================================
    # ANSWER (default)
    # =========================================================================
    return GovernorResult(
        outcome="ANSWER",
        response=(response or "") + revision_suffix,
        explanation=f"Builder provided a direct answer. Reviewer {decision.lower().replace('_', ' ')}.",
        reviewer_decision=decision,
        revision_notes=reviewer_result.revision_notes if decision == "REVISE_AND_APPROVE" else [],
        proposal_source=proposal_source,
    )
