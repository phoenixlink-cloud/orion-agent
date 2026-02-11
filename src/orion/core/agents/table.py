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
Orion Agent -- Table of Three (v7.4.0)

The deliberation micro-flow:
    Builder -> Reviewer -> Governor

Produces exactly ONE outcome:
    - ANSWER: Direct response to user
    - PLAN: Multi-step plan for user review
    - ACTION_INTENT: Proposed file operations

Migrated from Orion_MVP/core/table.py.

Architecture:
    - Fully async
    - Uses centralized model config for Builder/Reviewer roles
    - Governor is always deterministic (never an LLM call)
    - Supports single-shot and staged (chunked) evidence
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from orion.core.agents.builder import BuilderResult, run_builder
from orion.core.agents.reviewer import ReviewerResult, run_reviewer
from orion.core.agents.governor import GovernorResult, decide as governor_decide

logger = logging.getLogger("orion.table")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TableResult:
    """Result from Table of Three deliberation."""
    outcome: str          # "ANSWER", "PLAN", "ACTION_INTENT"
    response: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    explanation: str = ""
    reviewer_decision: str = ""
    revision_notes: List[str] = field(default_factory=list)
    proposal_source: str = "builder"
    builder_provider: str = ""
    reviewer_provider: str = ""
    session_id: str = ""


@dataclass
class TableSession:
    """Tracks state across multi-chunk deliberation."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    seen_files: List[str] = field(default_factory=list)
    evidence_chunks: int = 0

    def mark_seen(self, files: List[str]):
        for f in files:
            if f not in self.seen_files:
                self.seen_files.append(f)
        self.evidence_chunks += 1

    def get_summary(self) -> str:
        if not self.seen_files:
            return ""
        return (
            f"TABLE SESSION {self.session_id}\n"
            f"Files analyzed so far ({len(self.seen_files)}): "
            + ", ".join(self.seen_files[:20])
            + ("\n..." if len(self.seen_files) > 20 else "")
            + "\n\nNew evidence provided below.\n"
        )


# =============================================================================
# SINGLE ROUND
# =============================================================================

async def _run_single_round(
    user_input: str,
    evidence_context: str,
    mode: str,
    session_header: str = "",
    execution_mode: bool = False,
) -> TableResult:
    """
    Run one Builder -> Reviewer -> Governor round.

    Returns:
        TableResult with final outcome
    """
    # STEP 1: Builder proposes
    logger.info("Table: Step 1 -- Builder proposing")
    builder_result = await run_builder(
        user_input=user_input,
        evidence_context=evidence_context,
        mode=mode,
        session_header=session_header,
        execution_mode=execution_mode,
    )
    logger.info(f"Table: Builder returned outcome={builder_result.outcome} ({builder_result.provider}/{builder_result.model})")

    # STEP 2: Reviewer evaluates
    logger.info("Table: Step 2 -- Reviewer evaluating")
    reviewer_result = await run_reviewer(
        user_input=user_input,
        builder_output=builder_result.raw or builder_result.response,
        evidence_context=evidence_context,
        mode=mode,
        session_header=session_header,
    )
    logger.info(f"Table: Reviewer decided={reviewer_result.decision} ({reviewer_result.provider}/{reviewer_result.model})")

    # STEP 3: Governor decides (deterministic)
    logger.info("Table: Step 3 -- Governor deciding")
    gov_result = governor_decide(
        builder_result=builder_result,
        reviewer_result=reviewer_result,
        mode=mode,
    )
    logger.info(f"Table: Governor final outcome={gov_result.outcome}")

    return TableResult(
        outcome=gov_result.outcome,
        response=gov_result.response,
        actions=gov_result.actions,
        explanation=gov_result.explanation,
        reviewer_decision=gov_result.reviewer_decision,
        revision_notes=gov_result.revision_notes,
        proposal_source=gov_result.proposal_source,
        builder_provider=f"{builder_result.provider}/{builder_result.model}",
        reviewer_provider=f"{reviewer_result.provider}/{reviewer_result.model}",
    )


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def run_table_of_three(
    user_input: str,
    evidence_context: str = "",
    mode: str = "safe",
    workspace_path: Optional[str] = None,
    execution_mode: bool = False,
) -> Dict[str, Any]:
    """
    Run the Table of Three deliberation.

    Flow:
        1. Builder proposes (LLM call)
        2. Reviewer evaluates (LLM call)
        3. Governor decides (deterministic)

    Args:
        user_input: User's request
        evidence_context: Pre-built evidence string (if available)
        mode: Current AEGIS mode (safe/pro/project)
        workspace_path: Workspace path (for building evidence if not provided)
        execution_mode: If True, force ACTION_INTENT from Builder

    Returns:
        Dict with outcome, response, actions, explanation, and metadata
    """
    session = TableSession()

    # Build evidence if not provided
    if not evidence_context and workspace_path:
        try:
            from orion.core.context.repo_map import generate_repo_map
            evidence_context = generate_repo_map(workspace_path, max_tokens=4096)
        except Exception:
            evidence_context = "No evidence collected."

    if not evidence_context:
        evidence_context = "No evidence collected."

    # Run single round
    result = await _run_single_round(
        user_input=user_input,
        evidence_context=evidence_context,
        mode=mode,
        session_header=session.get_summary(),
        execution_mode=execution_mode,
    )

    result.session_id = session.session_id

    return {
        "outcome": result.outcome,
        "response": result.response,
        "actions": result.actions,
        "explanation": result.explanation,
        "reviewer_decision": result.reviewer_decision,
        "revision_notes": result.revision_notes,
        "proposal_source": result.proposal_source,
        "builder": result.builder_provider,
        "reviewer": result.reviewer_provider,
        "session_id": result.session_id,
    }
