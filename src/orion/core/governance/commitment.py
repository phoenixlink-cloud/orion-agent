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
Orion Agent -- Commitment & Execution Authority (v7.4.0)

Migrated from Orion_MVP/core/commitment.py.

COMMITMENT = explicit handoff from planning to execution.
Once committed, Orion generates filesystem actions instead of plans.

EXECUTION AUTHORITY = how much autonomy Orion has during execution.
- STEP_BY_STEP: approve each batch
- PLAN_BOUNDED: auto-approve actions derived from approved plan
- WORKSPACE_BOUNDED: auto-approve actions implied by workspace artifacts
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Set

logger = logging.getLogger("orion.governance.commitment")


class ExecutionAuthority(Enum):
    """Execution authority scope. Set ONCE at commitment time."""
    STEP_BY_STEP = "step_by_step"
    PLAN_BOUNDED = "plan_bounded"
    WORKSPACE_BOUNDED = "workspace_bounded"


@dataclass
class CommitmentState:
    """
    Tracks commitment and execution authority for a session.

    Once committed:
    - Orion must NOT return plans or approaches
    - Orion must move to ACTION GENERATION
    """
    committed: bool = False
    authority: ExecutionAuthority = ExecutionAuthority.STEP_BY_STEP
    plan_path: Optional[str] = None
    batch_count: int = 0
    executed_actions: Set[str] = field(default_factory=set)
    termination_reason: Optional[str] = None

    def commit(self, authority: ExecutionAuthority, plan_path: Optional[str] = None):
        """Enter committed state. ONE-TIME transition per session."""
        if self.committed:
            return
        self.committed = True
        self.authority = authority
        self.plan_path = plan_path
        self.batch_count = 0
        logger.info(f"Commitment reached -- authority={authority.value}, plan={plan_path}")

    def record_batch(self, action_count: int, action_hashes: list = None):
        """Record an executed batch."""
        self.batch_count += 1
        if action_hashes:
            self.executed_actions.update(action_hashes)
        logger.info(f"Batch {self.batch_count} executed ({action_count} actions)")

    def halt(self, reason: str):
        """Halt execution with a reason."""
        self.termination_reason = reason
        logger.warning(f"Execution halted: {reason} (batches completed: {self.batch_count})")

    def is_action_executed(self, action_hash: str) -> bool:
        """Check if an action has already been executed (prevent duplicates)."""
        return action_hash in self.executed_actions

    def requires_approval(self) -> bool:
        """Check if current authority requires per-batch approval."""
        if self.authority == ExecutionAuthority.STEP_BY_STEP:
            return True
        return self.batch_count == 0

    def reset(self):
        """Reset commitment state for a new session."""
        self.committed = False
        self.authority = ExecutionAuthority.STEP_BY_STEP
        self.plan_path = None
        self.batch_count = 0
        self.executed_actions.clear()
        self.termination_reason = None


def compute_action_hash(action: dict) -> str:
    """Compute a hash for an action to detect duplicates."""
    op = action.get("operation", "").upper()
    path = action.get("path", "")
    return f"{op}:{path}"


def filter_duplicate_actions(actions: list, commitment: CommitmentState) -> list:
    """Filter out actions that have already been executed."""
    return [a for a in actions if not commitment.is_action_executed(compute_action_hash(a))]
