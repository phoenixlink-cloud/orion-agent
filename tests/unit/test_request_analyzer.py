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
"""Tests for RequestAnalyzer -- the NLA orchestrator."""

import pytest

from orion.core.understanding.brief_builder import TaskBrief
from orion.core.understanding.exemplar_bank import ExemplarBank
from orion.core.understanding.request_analyzer import AnalysisResult, RequestAnalyzer

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def bank(tmp_path):
    """Provide a minimal ExemplarBank."""
    b = ExemplarBank(db_path=str(tmp_path / "test.db"))
    for msg in ["Hi", "Hello", "Hey there", "Good morning"]:
        b.add(msg, "conversational", "greeting")
    for msg in ["Bye", "Goodbye"]:
        b.add(msg, "conversational", "farewell")
    for msg in ["Thanks!", "Thank you"]:
        b.add(msg, "conversational", "gratitude")
    for msg in ["Fix the bug in auth.py", "Create a test file", "Add error handling"]:
        b.add(msg, "coding", "fix_bug")
    for msg in ["What does this function do?", "Explain the router"]:
        b.add(msg, "question", "code_explanation")
    for msg in ["I'm stuck", "Fix this", "Make it better"]:
        b.add(msg, "ambiguous", "needs_clarification")
    return b


@pytest.fixture
def analyzer(bank):
    """Provide a RequestAnalyzer."""
    return RequestAnalyzer(exemplar_bank=bank)


@pytest.fixture
def analyzer_no_bank():
    """Provide a RequestAnalyzer without an exemplar bank."""
    return RequestAnalyzer()


# =============================================================================
# ANALYSIS RESULT STRUCTURE
# =============================================================================


class TestAnalysisResultStructure:
    """Test that AnalysisResult has the correct shape."""

    def test_returns_analysis_result(self, analyzer):
        result = analyzer.analyze("Hello!")
        assert isinstance(result, AnalysisResult)

    def test_has_brief(self, analyzer):
        result = analyzer.analyze("Hello!")
        assert isinstance(result.brief, TaskBrief)

    def test_has_intent(self, analyzer):
        result = analyzer.analyze("Hello!")
        assert isinstance(result.intent, str)

    def test_has_needs_clarification(self, analyzer):
        result = analyzer.analyze("Hello!")
        assert isinstance(result.needs_clarification, bool)

    def test_has_questions(self, analyzer):
        result = analyzer.analyze("Fix this")
        assert isinstance(result.questions, list)

    def test_has_confidence(self, analyzer):
        result = analyzer.analyze("Hello!")
        assert isinstance(result.confidence, float)

    def test_has_fast_path_intent(self, analyzer):
        result = analyzer.analyze("Hello!")
        assert result.fast_path_intent in ("conversational", "question", "coding_task")


# =============================================================================
# END-TO-END: GREETING
# =============================================================================


class TestGreeting:
    """Test full pipeline for greetings."""

    def test_greeting_classified(self, analyzer):
        result = analyzer.analyze("Hello!")
        assert result.intent == "conversational"

    def test_greeting_no_clarification(self, analyzer):
        result = analyzer.analyze("Hi there!")
        assert result.needs_clarification is False

    def test_greeting_high_confidence(self, analyzer):
        result = analyzer.analyze("Good morning")
        assert result.confidence >= 0.7

    def test_greeting_maps_to_conversational(self, analyzer):
        result = analyzer.analyze("Hey!")
        assert result.fast_path_intent == "conversational"


# =============================================================================
# END-TO-END: CODING TASK
# =============================================================================


class TestCodingTask:
    """Test full pipeline for coding tasks."""

    def test_specific_coding_classified(self, analyzer):
        result = analyzer.analyze("Fix the TypeError in auth.py on line 42")
        assert result.intent == "coding"

    def test_specific_coding_no_clarification(self, analyzer):
        result = analyzer.analyze("Fix the TypeError in auth.py on line 42")
        assert result.needs_clarification is False

    def test_coding_maps_to_coding_task(self, analyzer):
        result = analyzer.analyze("Fix the bug in auth.py")
        assert result.fast_path_intent == "coding_task"

    def test_coding_extracts_files(self, analyzer):
        result = analyzer.analyze("Fix the bug in auth.py")
        assert "auth.py" in result.brief.file_references

    def test_vague_coding_needs_clarification(self, analyzer):
        result = analyzer.analyze("Fix the bug")
        assert result.needs_clarification is True
        assert len(result.questions) >= 1


# =============================================================================
# END-TO-END: QUESTION
# =============================================================================


class TestQuestion:
    """Test full pipeline for questions."""

    def test_question_classified(self, analyzer):
        result = analyzer.analyze("What does the authenticate function do?")
        assert result.intent == "question"

    def test_question_no_clarification(self, analyzer):
        result = analyzer.analyze("What does this function do?")
        assert result.needs_clarification is False

    def test_question_maps_to_question(self, analyzer):
        result = analyzer.analyze("What is dependency injection?")
        assert result.fast_path_intent == "question"


# =============================================================================
# END-TO-END: AMBIGUOUS
# =============================================================================


class TestAmbiguous:
    """Test full pipeline for ambiguous input."""

    def test_ambiguous_detected(self, analyzer):
        result = analyzer.analyze("Make it better")
        assert result.needs_clarification is True

    def test_ambiguous_has_questions(self, analyzer):
        result = analyzer.analyze("I'm stuck")
        assert len(result.questions) >= 1

    def test_fix_this_ambiguous(self, analyzer):
        result = analyzer.analyze("Fix this")
        assert result.needs_clarification is True


# =============================================================================
# WITHOUT EXEMPLAR BANK
# =============================================================================


class TestWithoutBank:
    """Test that analyzer works without an exemplar bank (keyword only)."""

    def test_greeting_still_works(self, analyzer_no_bank):
        result = analyzer_no_bank.analyze("Hello!")
        assert result.intent == "conversational"

    def test_coding_still_works(self, analyzer_no_bank):
        result = analyzer_no_bank.analyze("Fix the bug in auth.py")
        assert result.intent == "coding"

    def test_question_still_works(self, analyzer_no_bank):
        result = analyzer_no_bank.analyze("What is the difference between REST and GraphQL?")
        assert result.intent == "question"


# =============================================================================
# CONVERSATION CONTEXT
# =============================================================================


class TestConversationContext:
    """Test that conversation buffer context influences analysis."""

    def test_analyze_with_no_conversation(self, analyzer):
        result = analyzer.analyze("Hello!")
        assert result is not None

    def test_analyze_with_conversation_buffer(self, analyzer):
        from orion.core.memory.conversation import ConversationBuffer

        conv = ConversationBuffer()
        conv.add("user", "Fix the bug in auth.py")
        conv.add("orion", "I fixed the TypeError on line 42.")

        result = analyzer.analyze("What about the tests?", conversation=conv)
        # Follow-up should still be classified (not crash)
        assert result is not None
        assert isinstance(result.intent, str)


# =============================================================================
# FORMAT FOR PROMPT
# =============================================================================


class TestFormatForPrompt:
    """Test prompt formatting from analysis result."""

    def test_format_returns_string(self, analyzer):
        result = analyzer.analyze("Fix auth.py")
        prompt = result.format_for_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_format_includes_intent(self, analyzer):
        result = analyzer.analyze("Fix auth.py")
        prompt = result.format_for_prompt()
        assert "coding" in prompt.lower()

    def test_clarification_format(self, analyzer):
        result = analyzer.analyze("Fix this")
        if result.needs_clarification:
            prompt = result.format_for_prompt()
            assert "clarif" in prompt.lower() or "question" in prompt.lower()
