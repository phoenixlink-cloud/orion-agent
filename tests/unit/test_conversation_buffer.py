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
"""Tests for ConversationBuffer -- Orion's session-level conversation memory."""

import pytest

from orion.core.memory.conversation import ConversationBuffer, ConversationTurn


# =============================================================================
# BASIC OPERATIONS
# =============================================================================


class TestConversationBufferBasic:
    """Test basic add/retrieve operations."""

    def test_empty_buffer(self):
        buf = ConversationBuffer()
        assert buf.turn_count == 0
        assert buf.get_context_window() == []

    def test_add_user_turn(self):
        buf = ConversationBuffer()
        buf.add("user", "Hello Orion")
        assert buf.turn_count == 1
        turns = buf.get_context_window()
        assert len(turns) == 1
        assert turns[0].role == "user"
        assert turns[0].content == "Hello Orion"

    def test_add_orion_turn(self):
        buf = ConversationBuffer()
        buf.add("orion", "Hello! How can I help?")
        assert buf.turn_count == 1
        assert buf.get_context_window()[0].role == "orion"

    def test_multi_turn_conversation(self):
        buf = ConversationBuffer()
        buf.add("user", "Hi")
        buf.add("orion", "Hey! What's up?")
        buf.add("user", "Can you fix the auth bug?")
        buf.add("orion", "Sure, let me look at it.")
        assert buf.turn_count == 4
        turns = buf.get_context_window(n=4)
        assert turns[0].role == "user"
        assert turns[0].content == "Hi"
        assert turns[3].role == "orion"

    def test_turn_has_timestamp(self):
        buf = ConversationBuffer()
        buf.add("user", "test")
        turn = buf.get_context_window()[0]
        assert turn.timestamp is not None
        assert len(turn.timestamp) > 0

    def test_turn_stores_intent(self):
        buf = ConversationBuffer()
        buf.add("user", "Hi", intent="conversational")
        turn = buf.get_context_window()[0]
        assert turn.intent == "conversational"

    def test_turn_stores_clarification_flag(self):
        buf = ConversationBuffer()
        buf.add("user", "What do you mean?", clarification=True)
        turn = buf.get_context_window()[0]
        assert turn.clarification is True

    def test_default_intent_is_empty(self):
        buf = ConversationBuffer()
        buf.add("user", "hello")
        assert buf.get_context_window()[0].intent == ""

    def test_default_clarification_is_false(self):
        buf = ConversationBuffer()
        buf.add("user", "hello")
        assert buf.get_context_window()[0].clarification is False


# =============================================================================
# CONTEXT WINDOW
# =============================================================================


class TestContextWindow:
    """Test sliding window retrieval."""

    def test_window_returns_last_n(self):
        buf = ConversationBuffer()
        for i in range(10):
            buf.add("user", f"message {i}")
        window = buf.get_context_window(n=3)
        assert len(window) == 3
        assert window[0].content == "message 7"
        assert window[2].content == "message 9"

    def test_window_returns_all_if_fewer_than_n(self):
        buf = ConversationBuffer()
        buf.add("user", "only one")
        window = buf.get_context_window(n=5)
        assert len(window) == 1

    def test_default_window_size(self):
        buf = ConversationBuffer()
        for i in range(20):
            buf.add("user", f"msg {i}")
        window = buf.get_context_window()
        # Default should return a reasonable number (5)
        assert len(window) == 5

    def test_window_preserves_order(self):
        buf = ConversationBuffer()
        buf.add("user", "first")
        buf.add("orion", "second")
        buf.add("user", "third")
        window = buf.get_context_window(n=3)
        assert window[0].content == "first"
        assert window[1].content == "second"
        assert window[2].content == "third"


# =============================================================================
# MAX TURNS (SLIDING WINDOW EVICTION)
# =============================================================================


class TestMaxTurns:
    """Test that buffer enforces max turn limit."""

    def test_max_turns_enforced(self):
        buf = ConversationBuffer(max_turns=5)
        for i in range(10):
            buf.add("user", f"msg {i}")
        assert buf.turn_count == 5

    def test_oldest_evicted(self):
        buf = ConversationBuffer(max_turns=3)
        buf.add("user", "first")
        buf.add("user", "second")
        buf.add("user", "third")
        buf.add("user", "fourth")
        turns = buf.get_context_window(n=10)
        assert len(turns) == 3
        assert turns[0].content == "second"
        assert turns[2].content == "fourth"

    def test_default_max_turns(self):
        buf = ConversationBuffer()
        # Default max should be 20
        for i in range(25):
            buf.add("user", f"msg {i}")
        assert buf.turn_count == 20


# =============================================================================
# LAST USER INTENT
# =============================================================================


class TestLastUserIntent:
    """Test retrieving the last classified user intent."""

    def test_no_turns_returns_none(self):
        buf = ConversationBuffer()
        assert buf.get_last_user_intent() is None

    def test_returns_last_user_intent(self):
        buf = ConversationBuffer()
        buf.add("user", "Hi", intent="conversational")
        buf.add("orion", "Hello!")
        buf.add("user", "Fix the bug in auth.py", intent="coding")
        assert buf.get_last_user_intent() == "coding"

    def test_skips_orion_turns(self):
        buf = ConversationBuffer()
        buf.add("user", "Hi", intent="conversational")
        buf.add("orion", "Hello!")
        assert buf.get_last_user_intent() == "conversational"

    def test_no_intent_set_returns_empty(self):
        buf = ConversationBuffer()
        buf.add("user", "something")
        assert buf.get_last_user_intent() == ""


# =============================================================================
# FOLLOW-UP DETECTION
# =============================================================================


class TestFollowUpDetection:
    """Test detection of follow-up messages."""

    def test_no_history_not_followup(self):
        buf = ConversationBuffer()
        assert buf.is_follow_up("what about the tests?") is False

    def test_pronoun_reference_is_followup(self):
        buf = ConversationBuffer()
        buf.add("user", "Fix the bug in auth.py", intent="coding")
        buf.add("orion", "Done, fixed the null check.")
        assert buf.is_follow_up("and what about the tests?") is True

    def test_continuation_words_are_followup(self):
        buf = ConversationBuffer()
        buf.add("user", "Show me the config file")
        buf.add("orion", "Here it is: ...")
        assert buf.is_follow_up("also show me the routes") is True

    def test_new_topic_not_followup(self):
        buf = ConversationBuffer()
        buf.add("user", "Fix the bug in auth.py")
        buf.add("orion", "Done.")
        # Completely new topic with no references
        assert buf.is_follow_up("Hello, how are you?") is False

    def test_it_this_that_are_followup(self):
        buf = ConversationBuffer()
        buf.add("user", "Create a login page")
        buf.add("orion", "Here's the implementation...")
        assert buf.is_follow_up("make it responsive") is True

    def test_empty_history_with_pronoun_not_followup(self):
        buf = ConversationBuffer()
        # "it" without prior context isn't a follow-up
        assert buf.is_follow_up("what is it?") is False


# =============================================================================
# PROMPT FORMATTING
# =============================================================================


class TestPromptFormatting:
    """Test formatting conversation history for LLM prompt injection."""

    def test_format_empty(self):
        buf = ConversationBuffer()
        assert buf.format_for_prompt() == ""

    def test_format_single_turn(self):
        buf = ConversationBuffer()
        buf.add("user", "Hi Orion")
        formatted = buf.format_for_prompt()
        assert "User: Hi Orion" in formatted

    def test_format_multi_turn(self):
        buf = ConversationBuffer()
        buf.add("user", "Hi")
        buf.add("orion", "Hello!")
        buf.add("user", "Fix auth.py")
        formatted = buf.format_for_prompt(n=3)
        assert "User: Hi" in formatted
        assert "Orion: Hello!" in formatted
        assert "User: Fix auth.py" in formatted

    def test_format_respects_n(self):
        buf = ConversationBuffer()
        for i in range(10):
            buf.add("user", f"msg {i}")
        formatted = buf.format_for_prompt(n=2)
        assert "msg 8" in formatted
        assert "msg 9" in formatted
        assert "msg 7" not in formatted

    def test_format_includes_header(self):
        buf = ConversationBuffer()
        buf.add("user", "test")
        formatted = buf.format_for_prompt()
        assert "CONVERSATION HISTORY" in formatted


# =============================================================================
# CLEAR / RESET
# =============================================================================


class TestClearReset:
    """Test clearing conversation state."""

    def test_clear(self):
        buf = ConversationBuffer()
        buf.add("user", "message 1")
        buf.add("user", "message 2")
        buf.clear()
        assert buf.turn_count == 0
        assert buf.get_context_window() == []

    def test_clear_preserves_max_turns(self):
        buf = ConversationBuffer(max_turns=10)
        buf.add("user", "test")
        buf.clear()
        # Should still enforce max_turns after clear
        for i in range(15):
            buf.add("user", f"msg {i}")
        assert buf.turn_count == 10
