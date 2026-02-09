"""
Orion Agent — Feedback Processing (v6.4.0)

Extracts patterns from user approval/rejection/edits.
Stores learnings in institutional and project memory tiers.

Migrated from Orion_MVP/core/learning.py (LearningLoop).

Flow:
    1. User gives feedback (thumbs up/down, edit, comment)
    2. Extract pattern from feedback
    3. Store in appropriate memory layer
    4. Use in future similar requests
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from orion.core.learning.patterns import classify_request_type
from orion.core.memory.institutional import InstitutionalMemory
from orion.core.memory.project import ProjectMemory

logger = logging.getLogger("orion.learning.feedback")


class LearningLoop:
    """
    Extract patterns from feedback and store in memory.

    Processes positive, negative, and edit feedback to build
    institutional and project-level wisdom over time.
    """

    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace = workspace_path
        self.institutional = InstitutionalMemory()
        self.project: Optional[ProjectMemory] = None
        if workspace_path:
            try:
                self.project = ProjectMemory(workspace_path)
            except Exception:
                pass

    def process_feedback(
        self,
        original_request: str,
        original_response: str,
        feedback_type: str,
        feedback_content: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process user feedback and learn from it.

        Args:
            original_request: What the user asked
            original_response: What Orion produced
            feedback_type: 'positive', 'negative', or 'edit'
            feedback_content: User's correction or comment
            context: Additional context (files involved, etc.)

        Returns:
            Dict with learning results
        """
        context = context or {}

        if feedback_type == "positive":
            return self._learn_success(original_request, original_response, context)
        elif feedback_type == "negative":
            return self._learn_failure(original_request, original_response, feedback_content, context)
        elif feedback_type == "edit":
            return self._learn_from_edit(original_request, original_response, feedback_content, context)
        else:
            return {"success": False, "error": f"Unknown feedback type: {feedback_type}"}

    # ── Internal learning methods ────────────────────────────────────────

    def _learn_success(self, request: str, response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        request_type = classify_request_type(request)

        self.institutional.learn_from_outcome(
            action_type=request_type,
            context=request[:100],
            outcome="User approved response",
            quality_score=0.9,
        )

        if self.project:
            self.project.record_decision(
                action=f"[{request_type}] {request[:80]}",
                outcome="approved",
                quality=0.9,
                context=f"positive feedback at {datetime.now(timezone.utc).isoformat()}",
            )

        logger.info("Learned success pattern: type=%s", request_type)
        return {"success": True, "learned": "success_pattern", "request_type": request_type}

    def _learn_failure(self, request: str, response: str, feedback: str, context: Dict[str, Any]) -> Dict[str, Any]:
        request_type = classify_request_type(request)

        self.institutional.learn_from_outcome(
            action_type=request_type,
            context=request[:100],
            outcome=f"User rejected: {feedback[:100]}",
            quality_score=0.2,
            user_feedback=feedback[:200],
        )

        if self.project:
            self.project.record_decision(
                action=f"[{request_type}] {request[:80]}",
                outcome="rejected",
                quality=0.2,
                context=f"negative: {feedback[:100]}",
            )

        logger.info("Learned anti-pattern: type=%s feedback=%s", request_type, feedback[:60])
        return {"success": True, "learned": "anti_pattern", "request_type": request_type, "feedback": feedback}

    def _learn_from_edit(self, request: str, original: str, edited: str, context: Dict[str, Any]) -> Dict[str, Any]:
        request_type = classify_request_type(request)

        self.institutional.learn_from_outcome(
            action_type=request_type,
            context=request[:100],
            outcome=f"User edited response — prefers different style",
            quality_score=0.5,
        )

        if self.project:
            self.project.record_decision(
                action=f"[{request_type}] {request[:80]}",
                outcome="edited",
                quality=0.5,
                context="user edited response to preferred style",
            )

        logger.info("Learned edit preference: type=%s", request_type)
        return {"success": True, "learned": "style_preference", "request_type": request_type}

    # ── Stats ────────────────────────────────────────────────────────────

    def get_feedback_stats(self) -> Dict[str, Any]:
        """Get statistics about feedback and accumulated learnings."""
        inst_stats = self.institutional.get_statistics()
        proj_stats = self.project.get_statistics() if self.project else {}
        return {
            "institutional": inst_stats,
            "project": proj_stats,
        }


def get_learning_loop(workspace_path: Optional[str] = None) -> LearningLoop:
    """Factory function to get a LearningLoop instance."""
    return LearningLoop(workspace_path)
