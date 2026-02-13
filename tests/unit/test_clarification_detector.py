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
"""Tests for ClarificationDetector -- decides when Orion should ask before acting."""

import pytest

from orion.core.understanding.clarification import (
    ClarificationDetector,
    ClarificationResult,
)
from orion.core.understanding.intent_classifier import ClassificationResult

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def detector():
    """Provide a ClarificationDetector."""
    return ClarificationDetector()


def _make_cr(intent: str, sub_intent: str = "", confidence: float = 0.9) -> ClassificationResult:
    """Helper to build a ClassificationResult."""
    return ClassificationResult(
        intent=intent, sub_intent=sub_intent, confidence=confidence, method="keyword"
    )


# =============================================================================
# BASIC RESULT STRUCTURE
# =============================================================================


class TestResultStructure:
    """Test that ClarificationResult has the correct shape."""

    def test_returns_clarification_result(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.7)
        result = detector.check("Fix this", cr)
        assert isinstance(result, ClarificationResult)

    def test_result_has_needs_clarification(self, detector):
        cr = _make_cr("coding", "fix_bug", 0.9)
        result = detector.check("Fix the bug in auth.py", cr)
        assert isinstance(result.needs_clarification, bool)

    def test_result_has_questions(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.7)
        result = detector.check("Fix this", cr)
        assert isinstance(result.questions, list)

    def test_result_has_reason(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.7)
        result = detector.check("Fix this", cr)
        assert isinstance(result.reason, str)


# =============================================================================
# AMBIGUOUS INTENT → NEEDS CLARIFICATION
# =============================================================================


class TestAmbiguousDetection:
    """Test that ambiguous intents trigger clarification."""

    def test_ambiguous_needs_clarification(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.7)
        result = detector.check("Fix this", cr)
        assert result.needs_clarification is True

    def test_ambiguous_generates_questions(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.7)
        result = detector.check("Fix this", cr)
        assert len(result.questions) >= 1

    def test_vague_request_fix_it(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.7)
        result = detector.check("Make it better", cr)
        assert result.needs_clarification is True

    def test_vague_request_stuck(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.7)
        result = detector.check("I'm stuck", cr)
        assert result.needs_clarification is True

    def test_vague_help(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.5)
        result = detector.check("Can you help me?", cr)
        assert result.needs_clarification is True

    def test_it_doesnt_work(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.7)
        result = detector.check("It doesn't work", cr)
        assert result.needs_clarification is True
        # Should ask what "it" refers to
        combined = " ".join(result.questions).lower()
        assert any(w in combined for w in ("which", "what", "where", "specific", "file", "error"))


# =============================================================================
# LOW CONFIDENCE → NEEDS CLARIFICATION
# =============================================================================


class TestLowConfidence:
    """Test that low-confidence classifications trigger clarification."""

    def test_very_low_confidence(self, detector):
        cr = _make_cr("coding", "fix_bug", 0.2)
        result = detector.check("do the thing with the stuff", cr)
        assert result.needs_clarification is True

    def test_low_confidence_threshold(self, detector):
        cr = _make_cr("coding", "fix_bug", 0.4)
        result = detector.check("handle the error case", cr)
        assert result.needs_clarification is True

    def test_high_confidence_no_clarification(self, detector):
        cr = _make_cr("coding", "fix_bug", 0.9)
        result = detector.check("Fix the bug in auth.py line 42", cr)
        assert result.needs_clarification is False


# =============================================================================
# CLEAR INTENT → NO CLARIFICATION
# =============================================================================


class TestClearIntent:
    """Test that clear, specific requests don't trigger clarification."""

    def test_specific_coding_task(self, detector):
        cr = _make_cr("coding", "fix_bug", 0.9)
        result = detector.check("Fix the TypeError in auth.py on line 42", cr)
        assert result.needs_clarification is False

    def test_specific_create_file(self, detector):
        cr = _make_cr("coding", "create_file", 0.9)
        result = detector.check("Create a new file called utils.py with a merge_dicts function", cr)
        assert result.needs_clarification is False

    def test_greeting(self, detector):
        cr = _make_cr("conversational", "greeting", 0.95)
        result = detector.check("Hello!", cr)
        assert result.needs_clarification is False

    def test_farewell(self, detector):
        cr = _make_cr("conversational", "farewell", 0.95)
        result = detector.check("Goodbye!", cr)
        assert result.needs_clarification is False

    def test_specific_question(self, detector):
        cr = _make_cr("question", "code_explanation", 0.85)
        result = detector.check("What does the authenticate() function in auth.py do?", cr)
        assert result.needs_clarification is False

    def test_gratitude(self, detector):
        cr = _make_cr("conversational", "gratitude", 0.9)
        result = detector.check("Thanks!", cr)
        assert result.needs_clarification is False


# =============================================================================
# MISSING CONTEXT DETECTION
# =============================================================================


class TestMissingContext:
    """Test detection of requests missing key context."""

    def test_fix_bug_no_file(self, detector):
        cr = _make_cr("coding", "fix_bug", 0.8)
        result = detector.check("Fix the bug", cr)
        assert result.needs_clarification is True
        combined = " ".join(result.questions).lower()
        assert any(w in combined for w in ("which", "file", "where", "what"))

    def test_create_file_no_name(self, detector):
        cr = _make_cr("coding", "create_file", 0.8)
        result = detector.check("Create a new file", cr)
        assert result.needs_clarification is True

    def test_refactor_no_target(self, detector):
        cr = _make_cr("coding", "refactor", 0.8)
        result = detector.check("Refactor the code", cr)
        assert result.needs_clarification is True


# =============================================================================
# QUESTION GENERATION QUALITY
# =============================================================================


class TestQuestionGeneration:
    """Test that generated questions are useful and relevant."""

    def test_questions_are_strings(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.5)
        result = detector.check("Help", cr)
        assert all(isinstance(q, str) for q in result.questions)

    def test_questions_end_with_question_mark(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.5)
        result = detector.check("Fix this", cr)
        for q in result.questions:
            assert q.strip().endswith("?"), f"Question missing '?': {q}"

    def test_max_questions_limit(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.3)
        result = detector.check("stuff", cr)
        assert len(result.questions) <= 3

    def test_questions_not_empty_strings(self, detector):
        cr = _make_cr("ambiguous", "needs_clarification", 0.5)
        result = detector.check("Make it better", cr)
        for q in result.questions:
            assert len(q.strip()) > 5


# =============================================================================
# COMPOUND INTENT
# =============================================================================


class TestCompoundIntent:
    """Test handling of compound intents (greeting + task)."""

    def test_compound_with_clear_task(self, detector):
        cr = _make_cr("compound", "greeting_plus_task", 0.8)
        result = detector.check("Hi, fix the TypeError in auth.py", cr)
        assert result.needs_clarification is False

    def test_compound_with_vague_task(self, detector):
        cr = _make_cr("compound", "greeting_plus_task", 0.6)
        result = detector.check("Hey, can you help me?", cr)
        assert result.needs_clarification is True


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_empty_message(self, detector):
        cr = _make_cr("conversational", "", 0.1)
        result = detector.check("", cr)
        # Empty input should request clarification
        assert result.needs_clarification is True

    def test_whitespace_only(self, detector):
        cr = _make_cr("conversational", "", 0.1)
        result = detector.check("   ", cr)
        assert result.needs_clarification is True

    def test_single_word_coding(self, detector):
        cr = _make_cr("coding", "fix_bug", 0.5)
        result = detector.check("fix", cr)
        assert result.needs_clarification is True

    def test_very_long_specific_message(self, detector):
        cr = _make_cr("coding", "modify_file", 0.95)
        msg = (
            "Add error handling to the authenticate() function in auth.py. "
            "Catch ValueError and return a 400 status code with a JSON error message."
        )
        result = detector.check(msg, cr)
        assert result.needs_clarification is False
