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
Orion Agent -- Learning Bridge (v7.8.0)

Closes the feedback loop between user ratings and the ExemplarBank.
When a user rates a response positively, the classified message
becomes a new "learned" exemplar, improving future classification.

Part of the Natural Language Architecture (NLA-002, Phase 3B).

Flow:
    User rates response (4-5) → LearningBridge → ExemplarBank.add(source="learned")
    User corrects intent      → LearningBridge → ExemplarBank.add(corrected_intent)
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orion.core.understanding.exemplar_bank import ExemplarBank
    from orion.core.understanding.intent_classifier import ClassificationResult

logger = logging.getLogger("orion.understanding.learning_bridge")

# Only ratings >= this threshold create learned exemplars
_MIN_RATING_FOR_LEARNING = 4

# Max message length stored as an exemplar
_MAX_EXEMPLAR_LENGTH = 500


class LearningBridge:
    """
    Bridges user feedback to the ExemplarBank.

    Positive feedback (rating 4-5) on a correctly classified message
    adds it as a "learned" exemplar. Corrections override the intent.
    """

    def __init__(self, exemplar_bank: "ExemplarBank | None" = None):
        self._bank = exemplar_bank

    def record_classification_feedback(
        self,
        user_message: str,
        classification: "ClassificationResult",
        rating: int,
    ) -> None:
        """
        Record user feedback on a classification.

        Args:
            user_message: The original user message.
            classification: How it was classified.
            rating: User satisfaction (1-5).
        """
        if not self._bank:
            return

        text = user_message.strip()
        if not text:
            return

        if rating < _MIN_RATING_FOR_LEARNING:
            return

        # Truncate long messages
        if len(text) > _MAX_EXEMPLAR_LENGTH:
            text = text[:_MAX_EXEMPLAR_LENGTH]

        self._bank.add(
            user_message=text,
            intent=classification.intent,
            sub_intent=classification.sub_intent,
            confidence=min(1.0, classification.confidence + 0.05),
            source="learned",
        )
        logger.info(
            "Learned exemplar from feedback: '%s' → %s/%s (rating=%d)",
            text[:50],
            classification.intent,
            classification.sub_intent,
            rating,
        )

    def record_correction(
        self,
        user_message: str,
        original: "ClassificationResult",
        corrected_intent: str,
        corrected_sub_intent: str = "",
    ) -> None:
        """
        Record a user correction of a misclassification.

        Args:
            user_message: The original user message.
            original: How it was originally classified.
            corrected_intent: The correct intent.
            corrected_sub_intent: The correct sub-intent.
        """
        if not self._bank:
            return

        text = user_message.strip()
        if not text:
            return

        if len(text) > _MAX_EXEMPLAR_LENGTH:
            text = text[:_MAX_EXEMPLAR_LENGTH]

        self._bank.add(
            user_message=text,
            intent=corrected_intent,
            sub_intent=corrected_sub_intent,
            confidence=1.0,
            source="learned",
        )
        logger.info(
            "Learned correction: '%s' → %s/%s (was %s/%s)",
            text[:50],
            corrected_intent,
            corrected_sub_intent,
            original.intent,
            original.sub_intent,
        )

    def get_learning_stats(self) -> dict[str, Any]:
        """Get statistics about learned exemplars."""
        if not self._bank:
            return {"total_learned": 0, "total_curated": 0}

        stats = self._bank.get_stats()
        return {
            "total_learned": stats.get("sources", {}).get("learned", 0),
            "total_curated": stats.get("sources", {}).get("curated", 0),
            "total": stats.get("total", 0),
            "intents": stats.get("intents", {}),
        }
