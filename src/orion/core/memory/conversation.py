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
Orion Agent -- Conversation Buffer (v7.6.0)

Session-level sliding window of conversation turns.
Gives Orion memory of what was said earlier in the current session,
enabling follow-up detection, context-aware responses, and
conversation history injection into prompts.

Part of the Natural Language Architecture (NLA-002).
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

# Patterns that indicate a follow-up to a previous message
_FOLLOW_UP_PATTERNS = [
    # Pronouns referencing prior context
    r"\b(it|this|that|these|those|the same)\b",
    # Continuation / additive words
    r"^(also|and|additionally|plus|too|as well|moreover)\b",
    # Comparative / sequential
    r"^(but|however|instead|rather|what about|how about)\b",
    # Elliptical references
    r"^(same|again|more|another|next|now)\b",
]

# Patterns that indicate a genuinely new topic (overrides follow-up signals)
_NEW_TOPIC_PATTERNS = [
    r"^\s*(hi|hello|hey|howdy|greetings|good\s+(morning|afternoon|evening))\b",
    r"^\s*(bye|goodbye|see\s+you|good\s*night)\b",
    r"^\s*(thanks?|thank\s+you)[!.]*$",
]


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""

    role: str  # "user" or "orion"
    content: str
    timestamp: str
    intent: str = ""  # classified intent for this turn
    clarification: bool = False  # was this a clarification exchange?


class ConversationBuffer:
    """
    Sliding window of recent conversation turns.

    Provides:
    - Session memory (what was said recently)
    - Follow-up detection (is this message referencing the previous one?)
    - Prompt formatting (inject conversation history into LLM prompts)
    - Last intent retrieval (what was the user's last classified intent?)
    """

    DEFAULT_MAX_TURNS = 20
    DEFAULT_WINDOW_SIZE = 5

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS):
        self._turns: list[ConversationTurn] = []
        self._max_turns = max_turns

    @property
    def turn_count(self) -> int:
        """Number of turns currently in the buffer."""
        return len(self._turns)

    def add(
        self,
        role: str,
        content: str,
        intent: str = "",
        clarification: bool = False,
    ) -> ConversationTurn:
        """
        Add a conversation turn to the buffer.

        Args:
            role: "user" or "orion"
            content: The message content
            intent: Classified intent (for user turns)
            clarification: Whether this is part of a clarification exchange

        Returns:
            The created ConversationTurn
        """
        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            intent=intent,
            clarification=clarification,
        )
        self._turns.append(turn)

        # Evict oldest turns if over limit
        if len(self._turns) > self._max_turns:
            self._turns = self._turns[-self._max_turns :]

        return turn

    def get_context_window(self, n: int = DEFAULT_WINDOW_SIZE) -> list[ConversationTurn]:
        """
        Get the last N turns as a context window.

        Args:
            n: Number of recent turns to return. Defaults to 5.

        Returns:
            List of ConversationTurn, oldest first.
        """
        if not self._turns:
            return []
        return self._turns[-n:]

    def get_last_user_intent(self) -> str | None:
        """
        Get the intent of the most recent user turn.

        Returns:
            Intent string, empty string if no intent was set,
            or None if there are no user turns.
        """
        for turn in reversed(self._turns):
            if turn.role == "user":
                return turn.intent
        return None

    def is_follow_up(self, current_message: str) -> bool:
        """
        Detect if the current message is a follow-up to the previous conversation.

        Uses heuristics:
        - Pronoun references ("it", "this", "that") with prior context
        - Continuation words ("also", "and", "but", "what about")
        - NOT a follow-up if it's a greeting or new-topic opener

        Args:
            current_message: The new user message to check.

        Returns:
            True if this appears to reference the prior conversation.
        """
        # No history → can't be a follow-up
        if not self._turns:
            return False

        lower = current_message.strip().lower()

        # Check if it's clearly a new topic
        for pattern in _NEW_TOPIC_PATTERNS:
            if re.search(pattern, lower):
                return False

        # Check for follow-up signals
        for pattern in _FOLLOW_UP_PATTERNS:
            if re.search(pattern, lower):
                return True

        return False

    def format_for_prompt(self, n: int = DEFAULT_WINDOW_SIZE) -> str:
        """
        Format recent conversation history for injection into an LLM prompt.

        Args:
            n: Number of recent turns to include.

        Returns:
            Formatted string, or empty string if no history.
        """
        window = self.get_context_window(n)
        if not window:
            return ""

        lines = ["## CONVERSATION HISTORY"]
        for turn in window:
            label = "User" if turn.role == "user" else "Orion"
            lines.append(f"{label}: {turn.content}")

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all conversation history. Preserves max_turns setting."""
        self._turns.clear()
