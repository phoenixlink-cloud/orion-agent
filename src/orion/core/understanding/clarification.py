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
Orion Agent -- Clarification Detector (v7.7.0)

Decides when Orion should ask the user for more information
instead of guessing. Generates targeted clarifying questions
based on what's missing from the request.

Part of the Natural Language Architecture (NLA-002, Phase 2A).

Decision factors:
    - Intent confidence (low → clarify)
    - Ambiguous intent classification
    - Missing context for coding tasks (no file, no target)
    - Vague/short messages with action intent
"""

import logging
import re
from dataclasses import dataclass, field

from orion.core.understanding.intent_classifier import ClassificationResult

logger = logging.getLogger("orion.understanding.clarification")

# Confidence below which we always ask for clarification
_LOW_CONFIDENCE_THRESHOLD = 0.5

# Minimum word count for coding tasks to be considered "specific enough"
_MIN_WORDS_FOR_CODING = 4

# File extension pattern -- if present, the user likely specified a target
_FILE_PATTERN = re.compile(
    r"\b[\w/\\-]+\.(py|js|ts|jsx|tsx|json|yaml|yml|html|css|sql|go|rs|java|cs|cpp|c|h|md|txt|toml|cfg|ini|sh|bat)\b"
)

# Line number / function / class reference pattern
_SPECIFIC_REF_PATTERN = re.compile(
    r"\b(line\s+\d+|function\s+\w+|class\s+\w+|method\s+\w+|def\s+\w+)\b", re.IGNORECASE
)


@dataclass
class ClarificationResult:
    """Result of clarification check."""

    needs_clarification: bool
    questions: list[str] = field(default_factory=list)
    reason: str = ""


class ClarificationDetector:
    """
    Decides whether Orion should ask for clarification before acting.

    Uses the ClassificationResult from IntentClassifier plus heuristics
    about missing context to make the decision.
    """

    def check(self, message: str, classification: ClassificationResult) -> ClarificationResult:
        """
        Check if a message needs clarification.

        Args:
            message: The user's raw message.
            classification: The result from IntentClassifier.

        Returns:
            ClarificationResult with decision and questions.
        """
        text = message.strip()

        # Empty / whitespace input
        if not text:
            return ClarificationResult(
                needs_clarification=True,
                questions=["What would you like me to help you with?"],
                reason="empty_input",
            )

        # Conversational intents never need clarification
        if (
            classification.intent == "conversational"
            and classification.confidence >= _LOW_CONFIDENCE_THRESHOLD
        ):
            return ClarificationResult(needs_clarification=False, reason="conversational")

        # Ambiguous intent → always clarify
        if classification.intent == "ambiguous":
            questions = self._generate_ambiguous_questions(text)
            return ClarificationResult(
                needs_clarification=True,
                questions=questions,
                reason="ambiguous_intent",
            )

        # Low confidence → clarify
        if classification.confidence < _LOW_CONFIDENCE_THRESHOLD:
            questions = self._generate_low_confidence_questions(text, classification)
            return ClarificationResult(
                needs_clarification=True,
                questions=questions,
                reason="low_confidence",
            )

        # Coding tasks: check for missing context
        if classification.intent == "coding":
            missing = self._check_coding_context(text, classification)
            if missing:
                return ClarificationResult(
                    needs_clarification=True,
                    questions=missing,
                    reason="missing_context",
                )

        # Compound intent: check if the task portion is specific enough
        if classification.intent == "compound":
            return self._check_compound(text, classification)

        # Question intent with high confidence → no clarification needed
        if (
            classification.intent == "question"
            and classification.confidence >= _LOW_CONFIDENCE_THRESHOLD
        ):
            return ClarificationResult(needs_clarification=False, reason="clear_question")

        return ClarificationResult(needs_clarification=False, reason="sufficient_context")

    # =========================================================================
    # QUESTION GENERATORS
    # =========================================================================

    def _generate_ambiguous_questions(self, text: str) -> list[str]:
        """Generate clarifying questions for ambiguous messages."""
        lower = text.lower().strip()
        questions: list[str] = []

        # "Fix this" / "it doesn't work" / "it's broken" → ask what & where
        if re.search(r"\b(fix|broken|doesn'?t\s+work|not\s+working)\b", lower):
            questions.append("Which file or component are you referring to?")
            questions.append("What error or unexpected behavior are you seeing?")

        # "Make it better" / "improve" → ask what aspect
        elif re.search(r"\b(better|improve|enhance|optimize)\b", lower):
            questions.append("What specifically would you like improved?")
            questions.append("Which file or function should I focus on?")

        # "Help" / "stuck" → open-ended
        elif re.search(r"\b(help|stuck|assist)\b", lower):
            questions.append("What are you trying to accomplish?")
            questions.append("What have you tried so far?")

        # "Look at this" / "check this" → ask what to look for
        elif re.search(r"\b(look|check|see)\b", lower):
            questions.append("What should I be looking for specifically?")
            questions.append("Which file or section are you referring to?")

        # Generic fallback
        else:
            questions.append("Could you be more specific about what you need?")
            questions.append("Which file or component does this relate to?")

        return questions[:3]

    def _generate_low_confidence_questions(
        self, text: str, classification: ClassificationResult
    ) -> list[str]:
        """Generate questions when we're unsure about the intent."""
        questions: list[str] = []

        if classification.intent == "coding":
            questions.append("It sounds like you'd like me to make a code change — is that right?")
            questions.append("Which file or module should I work on?")
        elif classification.intent == "question":
            questions.append("Would you like an explanation, or should I make changes?")
        else:
            questions.append("Could you tell me more about what you're looking for?")

        return questions[:3]

    def _check_coding_context(self, text: str, classification: ClassificationResult) -> list[str]:
        """
        Check if a coding request has enough context to act on.

        Returns a list of clarifying questions (empty if context is sufficient).
        """
        lower = text.lower()
        words = text.split()
        missing: list[str] = []

        # Very short coding requests are likely too vague
        if len(words) < _MIN_WORDS_FOR_CODING:
            missing.append("Could you provide more detail about what you'd like me to do?")
            return missing[:3]

        has_file_ref = bool(_FILE_PATTERN.search(text))
        has_specific_ref = bool(_SPECIFIC_REF_PATTERN.search(text))

        # fix_bug without a file or specific reference
        if classification.sub_intent == "fix_bug":
            if not has_file_ref and not has_specific_ref:
                if not re.search(r"\b(error|exception|traceback|stack\s*trace)\b", lower):
                    missing.append("Which file or function has the bug?")
                    if not re.search(r"\b(error|wrong|incorrect|unexpected)\b", lower):
                        missing.append("What error or unexpected behavior are you seeing?")

        # create_file without a filename
        elif classification.sub_intent == "create_file":
            if not has_file_ref and not re.search(r"\bcalled\s+\w+", lower):
                missing.append("What should the new file be named?")

        # refactor without a target
        elif classification.sub_intent == "refactor":
            if not has_file_ref and not has_specific_ref:
                missing.append("Which file or function should I refactor?")

        return missing[:3]

    def _check_compound(
        self, text: str, classification: ClassificationResult
    ) -> ClarificationResult:
        """Check compound intents (greeting + task) for sufficient task context."""
        # Strip the greeting portion and check what's left
        lower = text.lower()

        # Remove common greeting prefixes
        task_text = re.sub(
            r"^\s*(hi|hello|hey|good\s+(morning|afternoon|evening)|howdy)\s*[,!.]?\s*",
            "",
            lower,
            flags=re.IGNORECASE,
        ).strip()

        # If the remaining task is too short or vague → clarify
        if len(task_text.split()) < 3:
            return ClarificationResult(
                needs_clarification=True,
                questions=["What specifically would you like me to help with?"],
                reason="compound_vague_task",
            )

        # Check if the task part has enough specificity
        has_file = bool(_FILE_PATTERN.search(task_text))
        has_ref = bool(_SPECIFIC_REF_PATTERN.search(task_text))
        has_verb = bool(
            re.search(
                r"\b(fix|create|add|update|write|refactor|explain|debug|implement)\b",
                task_text,
            )
        )

        if has_verb and (has_file or has_ref or len(task_text.split()) >= 5):
            return ClarificationResult(needs_clarification=False, reason="compound_clear_task")

        # Vague help request after greeting
        if re.search(r"\b(help|stuck|assist)\b", task_text) and len(task_text.split()) < 5:
            return ClarificationResult(
                needs_clarification=True,
                questions=["What specifically would you like me to help with?"],
                reason="compound_vague_help",
            )

        return ClarificationResult(needs_clarification=False, reason="compound_sufficient")
