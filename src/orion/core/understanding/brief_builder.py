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
Orion Agent -- Brief Builder (v7.7.0)

Converts a classified + clarification-checked user message into a
structured TaskBrief that Builder/Reviewer/FastPath can consume.

Replaces passing raw user text straight to the LLM prompt.

Part of the Natural Language Architecture (NLA-002, Phase 2B).
"""

import logging
import re
from dataclasses import dataclass, field

from orion.core.understanding.clarification import ClarificationResult
from orion.core.understanding.intent_classifier import ClassificationResult

logger = logging.getLogger("orion.understanding.brief_builder")

# File reference pattern
_FILE_PATTERN = re.compile(
    r"\b([\w./\\-]+\.(?:py|js|ts|jsx|tsx|json|yaml|yml|html|css|sql|go|rs|java|cs|cpp|c|h|md|txt|toml|cfg|ini|sh|bat))\b"
)

# Action verbs in priority order
_ACTION_VERBS = [
    "fix",
    "create",
    "refactor",
    "add",
    "update",
    "modify",
    "delete",
    "remove",
    "write",
    "implement",
    "build",
    "debug",
    "explain",
    "describe",
    "deploy",
    "install",
    "test",
    "run",
    "check",
    "review",
    "rename",
    "move",
    "clean",
    "simplify",
    "extract",
    "scaffold",
    "set up",
    "configure",
]

_MAX_SUMMARY_LEN = 200


@dataclass
class TaskBrief:
    """Structured brief for downstream agents (Builder, Reviewer, FastPath)."""

    original_message: str
    intent: str
    sub_intent: str
    confidence: float
    summary: str
    action_verb: str
    file_references: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_questions: list[str] = field(default_factory=list)

    def format_for_prompt(self) -> str:
        """Format this brief for injection into an LLM system/user prompt."""
        parts: list[str] = []

        parts.append(f"[Intent: {self.intent}]")
        if self.sub_intent:
            parts.append(f"[Sub-intent: {self.sub_intent}]")

        if self.needs_clarification:
            parts.append("[Status: needs clarification]")
            if self.clarification_questions:
                parts.append("Questions to ask:")
                for q in self.clarification_questions:
                    parts.append(f"  - {q}")
        else:
            parts.append(f"[Task: {self.summary}]")

        if self.file_references:
            parts.append(f"[Files: {', '.join(self.file_references)}]")

        if self.action_verb:
            parts.append(f"[Action: {self.action_verb}]")

        return "\n".join(parts)


class BriefBuilder:
    """
    Builds a structured TaskBrief from classified user input.

    Extracts:
        - File references from the message
        - Action verb (fix, create, refactor, etc.)
        - Concise summary
        - Clarification state
    """

    def build(
        self,
        message: str,
        classification: ClassificationResult,
        clarification: ClarificationResult,
    ) -> TaskBrief:
        """
        Build a TaskBrief from a user message and its analysis.

        Args:
            message: Raw user message.
            classification: Result from IntentClassifier.
            clarification: Result from ClarificationDetector.

        Returns:
            Structured TaskBrief.
        """
        text = message.strip()
        file_refs = self._extract_files(text)
        action = self._extract_action_verb(text)
        summary = self._generate_summary(text, classification, action, file_refs)

        return TaskBrief(
            original_message=text,
            intent=classification.intent,
            sub_intent=classification.sub_intent,
            confidence=classification.confidence,
            summary=summary,
            action_verb=action,
            file_references=file_refs,
            needs_clarification=clarification.needs_clarification,
            clarification_questions=list(clarification.questions),
        )

    # =========================================================================
    # EXTRACTORS
    # =========================================================================

    @staticmethod
    def _extract_files(text: str) -> list[str]:
        """Extract file references from the message."""
        matches = _FILE_PATTERN.findall(text)
        # Deduplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for m in matches:
            if m not in seen:
                seen.add(m)
                result.append(m)
        return result

    @staticmethod
    def _extract_action_verb(text: str) -> str:
        """Extract the primary action verb from the message."""
        lower = text.lower()
        for verb in _ACTION_VERBS:
            if re.search(rf"\b{re.escape(verb)}\b", lower):
                return verb
        return ""

    @staticmethod
    def _generate_summary(
        text: str,
        classification: ClassificationResult,
        action: str,
        files: list[str],
    ) -> str:
        """Generate a concise summary of the task."""
        if not text:
            return ""

        # For conversational intent, the summary is simple
        if classification.intent == "conversational":
            label = classification.sub_intent or "message"
            return f"User {label}"

        # For questions
        if classification.intent == "question":
            truncated = text[:_MAX_SUMMARY_LEN]
            if len(text) > _MAX_SUMMARY_LEN:
                truncated = truncated.rsplit(" ", 1)[0] + "..."
            return truncated

        # For coding / compound / ambiguous: build structured summary
        parts: list[str] = []
        if action:
            parts.append(action.capitalize())
        if files:
            parts.append("in " + ", ".join(files))

        # Add context from the message (strip code blocks for brevity)
        clean = re.sub(r"```[\s\S]*?```", "[code]", text)
        clean = re.sub(r"`[^`]+`", "[ref]", clean)
        # Remove greeting prefix for compound
        clean = re.sub(
            r"^\s*(hi|hello|hey|good\s+(morning|afternoon|evening))\s*[,!.]?\s*",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()

        if not parts:
            # No action or files — use truncated message
            truncated = clean[:_MAX_SUMMARY_LEN]
            if len(clean) > _MAX_SUMMARY_LEN:
                truncated = truncated.rsplit(" ", 1)[0] + "..."
            return truncated

        # Add a brief description from the message if action alone is too terse
        if len(" ".join(parts)) < 30 and clean:
            desc = clean[: _MAX_SUMMARY_LEN - len(" ".join(parts)) - 3]
            if len(clean) > len(desc):
                desc = desc.rsplit(" ", 1)[0] + "..." if " " in desc else desc
            combined = " ".join(parts) + " — " + desc
            return combined[:_MAX_SUMMARY_LEN]

        return " ".join(parts)[:_MAX_SUMMARY_LEN]
