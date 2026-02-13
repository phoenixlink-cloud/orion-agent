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
"""Tests for IntentClassifier -- embedding + keyword intent classification."""

import pytest

from orion.core.understanding.exemplar_bank import ExemplarBank
from orion.core.understanding.intent_classifier import (
    ClassificationResult,
    IntentClassifier,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def bank(tmp_path):
    """Provide an ExemplarBank seeded with test exemplars."""
    bank = ExemplarBank(db_path=str(tmp_path / "test.db"))
    # Seed minimal exemplars for testing
    for msg in ["Hi", "Hello", "Hey there", "Good morning", "How are you?"]:
        bank.add(msg, "conversational", "greeting", source="test")
    for msg in ["Bye", "Goodbye", "See you later"]:
        bank.add(msg, "conversational", "farewell", source="test")
    for msg in ["Thanks!", "Thank you", "Great job"]:
        bank.add(msg, "conversational", "gratitude", source="test")
    for msg in ["What does this function do?", "Explain this code", "How does the router work?"]:
        bank.add(msg, "question", "code_explanation", source="test")
    for msg in ["Why is this failing?", "What's causing this error?"]:
        bank.add(msg, "question", "debugging", source="test")
    for msg in [
        "Fix the bug in auth.py",
        "Create a new test file",
        "Add error handling",
        "Refactor the router",
        "Write unit tests for the API",
    ]:
        bank.add(msg, "coding", "fix_bug", source="test")
    for msg in ["I'm stuck", "Make it better", "Fix this", "It doesn't work"]:
        bank.add(msg, "ambiguous", "needs_clarification", source="test")
    for msg in ["Hi, can you fix the auth bug?", "Hey Orion, create a test file"]:
        bank.add(msg, "compound", "greeting_plus_task", source="test")
    return bank


@pytest.fixture
def classifier(bank):
    """Provide an IntentClassifier backed by the test bank."""
    return IntentClassifier(exemplar_bank=bank)


# =============================================================================
# BASIC CLASSIFICATION (KEYWORD FALLBACK)
# =============================================================================


class TestKeywordFallback:
    """Test keyword-based classification (always available, no embeddings needed)."""

    def test_returns_classification_result(self, classifier):
        result = classifier.classify("Hello!")
        assert isinstance(result, ClassificationResult)
        assert result.intent is not None
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0

    def test_greeting_detected(self, classifier):
        result = classifier.classify("Hi there!")
        assert result.intent == "conversational"

    def test_farewell_detected(self, classifier):
        result = classifier.classify("Goodbye!")
        assert result.intent == "conversational"

    def test_coding_task_detected(self, classifier):
        result = classifier.classify("Fix the bug in auth.py")
        assert result.intent == "coding"

    def test_question_detected(self, classifier):
        result = classifier.classify("What does this function do?")
        assert result.intent == "question"

    def test_ambiguous_detected(self, classifier):
        result = classifier.classify("Make it better")
        assert result.intent == "ambiguous"

    def test_compound_greeting_plus_task(self, classifier):
        result = classifier.classify("Hi, can you fix the login?")
        # Should detect as compound or coding (either is acceptable)
        assert result.intent in ("compound", "coding")

    def test_unknown_defaults_to_question(self, classifier):
        # Completely novel input with no strong signals
        result = classifier.classify("Tell me about the weather in Paris")
        assert result.intent in ("question", "conversational")

    def test_empty_input(self, classifier):
        result = classifier.classify("")
        assert result.intent is not None  # Should not crash

    def test_whitespace_input(self, classifier):
        result = classifier.classify("   ")
        assert result.intent is not None


# =============================================================================
# CONFIDENCE SCORING
# =============================================================================


class TestConfidenceScoring:
    """Test that confidence reflects classification certainty."""

    def test_exact_match_high_confidence(self, classifier):
        # Exact exemplar match should have high confidence
        result = classifier.classify("Hi")
        assert result.confidence >= 0.8

    def test_clear_coding_high_confidence(self, classifier):
        result = classifier.classify("Fix the bug in auth.py")
        assert result.confidence >= 0.7

    def test_vague_input_lower_confidence(self, classifier):
        result = classifier.classify("help")
        assert result.confidence < 0.9

    def test_confidence_is_float(self, classifier):
        result = classifier.classify("test")
        assert isinstance(result.confidence, float)


# =============================================================================
# SUB-INTENT
# =============================================================================


class TestSubIntent:
    """Test sub-intent classification."""

    def test_greeting_sub_intent(self, classifier):
        result = classifier.classify("Hello!")
        if result.intent == "conversational":
            assert result.sub_intent in ("greeting", "farewell", "gratitude", "identity", "")

    def test_coding_has_sub_intent(self, classifier):
        result = classifier.classify("Fix the bug in the router")
        if result.intent == "coding":
            assert result.sub_intent != ""

    def test_sub_intent_is_string(self, classifier):
        result = classifier.classify("test")
        assert isinstance(result.sub_intent, str)


# =============================================================================
# METHOD
# =============================================================================


class TestClassificationMethod:
    """Test that the classifier reports which method was used."""

    def test_method_is_reported(self, classifier):
        result = classifier.classify("Hi")
        assert result.method in ("embedding", "keyword")

    def test_keyword_fallback_used_without_embeddings(self, classifier):
        # Force keyword mode
        result = classifier.classify_keyword("Hello")
        assert result.method == "keyword"


# =============================================================================
# BATCH CLASSIFICATION
# =============================================================================


class TestBatchClassification:
    """Test classifying multiple messages at once."""

    def test_batch_returns_list(self, classifier):
        messages = ["Hi", "Fix the bug", "What does this do?"]
        results = classifier.classify_batch(messages)
        assert len(results) == 3
        assert all(isinstance(r, ClassificationResult) for r in results)

    def test_batch_empty(self, classifier):
        results = classifier.classify_batch([])
        assert results == []


# =============================================================================
# ACCURACY BENCHMARK
# =============================================================================


class TestAccuracyBenchmark:
    """
    Benchmark test: keyword fallback must achieve reasonable accuracy.
    Embedding-based classification will be tested when available.
    """

    BENCHMARK_CASES = [
        # (message, expected_intent)
        ("Hello", "conversational"),
        ("Hi Orion", "conversational"),
        ("Good morning", "conversational"),
        ("Goodbye", "conversational"),
        ("Thanks!", "conversational"),
        ("Fix the bug in auth.py", "coding"),
        ("Create a new test file", "coding"),
        ("Add error handling to the API", "coding"),
        ("Refactor the router module", "coding"),
        ("Write unit tests", "coding"),
        ("What does this function do?", "question"),
        ("How does the router work?", "question"),
        ("Why is this test failing?", "question"),
        ("What's causing this error?", "question"),
        ("Explain the authentication flow", "question"),
    ]

    def test_keyword_accuracy_above_70_percent(self, classifier):
        """Keyword fallback should get at least 70% of clear-intent messages right."""
        correct = 0
        for message, expected in self.BENCHMARK_CASES:
            result = classifier.classify_keyword(message)
            if result.intent == expected:
                correct += 1

        accuracy = correct / len(self.BENCHMARK_CASES)
        assert accuracy >= 0.70, (
            f"Keyword accuracy {accuracy:.0%} is below 70% threshold. "
            f"Got {correct}/{len(self.BENCHMARK_CASES)} correct."
        )
