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
Orion Agent -- Request Analyzer (v7.7.0)

The NLA orchestrator. Runs the full understanding pipeline:

    User message
        → IntentClassifier  (what does the user want?)
        → ClarificationDetector  (do we have enough info?)
        → BriefBuilder  (structured spec for downstream agents)
        → AnalysisResult  (single object for Scout / FastPath / Builder)

Replaces the regex-based _classify_intent() in fast_path.py and
enriches Scout's routing with semantic understanding.

Part of the Natural Language Architecture (NLA-002, Phase 2C).
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from orion.core.understanding.brief_builder import BriefBuilder, TaskBrief
from orion.core.understanding.clarification import ClarificationDetector
from orion.core.understanding.intent_classifier import IntentClassifier

if TYPE_CHECKING:
    from orion.core.memory.conversation import ConversationBuffer
    from orion.core.understanding.exemplar_bank import ExemplarBank

logger = logging.getLogger("orion.understanding.request_analyzer")

# Map NLA intents to FastPath's existing _Intent constants
_INTENT_TO_FAST_PATH = {
    "conversational": "conversational",
    "question": "question",
    "coding": "coding_task",
    "compound": "coding_task",
    "ambiguous": "question",
}


@dataclass
class AnalysisResult:
    """Complete analysis of a user request."""

    brief: TaskBrief
    intent: str
    sub_intent: str
    confidence: float
    needs_clarification: bool
    questions: list[str] = field(default_factory=list)
    fast_path_intent: str = "question"
    is_follow_up: bool = False

    def format_for_prompt(self) -> str:
        """Format the analysis for LLM prompt injection."""
        return self.brief.format_for_prompt()


class RequestAnalyzer:
    """
    NLA orchestrator: classify → clarify → brief → result.

    Drop-in replacement for regex-based intent classification.
    Works with or without an ExemplarBank (falls back to keywords).
    """

    def __init__(self, exemplar_bank: "ExemplarBank | None" = None):
        self._classifier = IntentClassifier(exemplar_bank=exemplar_bank)
        self._clarifier = ClarificationDetector()
        self._brief_builder = BriefBuilder()

    def analyze(
        self,
        message: str,
        conversation: "ConversationBuffer | None" = None,
    ) -> AnalysisResult:
        """
        Run the full NLA pipeline on a user message.

        Args:
            message: Raw user message.
            conversation: Optional conversation buffer for follow-up detection.

        Returns:
            AnalysisResult with classification, clarification, and brief.
        """
        text = message.strip()

        # Detect follow-up from conversation context
        is_follow_up = False
        if conversation:
            is_follow_up = conversation.is_follow_up(text)

        # Step 1: Classify intent
        classification = self._classifier.classify(text)

        # Step 2: Check if clarification is needed
        clarification = self._clarifier.check(text, classification)

        # Step 3: Build structured brief
        brief = self._brief_builder.build(text, classification, clarification)

        # Map to FastPath intent
        fp_intent = _INTENT_TO_FAST_PATH.get(classification.intent, "question")

        return AnalysisResult(
            brief=brief,
            intent=classification.intent,
            sub_intent=classification.sub_intent,
            confidence=classification.confidence,
            needs_clarification=clarification.needs_clarification,
            questions=list(clarification.questions),
            fast_path_intent=fp_intent,
            is_follow_up=is_follow_up,
        )
