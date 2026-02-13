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
"""NLA Benchmark Suite -- validates accuracy, latency, and pipeline integrity."""

import json
import time
from pathlib import Path

import pytest

from orion.core.understanding.brief_builder import TaskBrief
from orion.core.understanding.exemplar_bank import ExemplarBank
from orion.core.understanding.intent_classifier import IntentClassifier
from orion.core.understanding.request_analyzer import AnalysisResult, RequestAnalyzer

# =============================================================================
# BENCHMARK DATA
# =============================================================================

BENCHMARK_CASES = [
    # Conversational: greetings
    ("Hello", "conversational"),
    ("Hi Orion", "conversational"),
    ("Good morning", "conversational"),
    ("Hey there!", "conversational"),
    ("How are you?", "conversational"),
    # Conversational: farewells
    ("Goodbye", "conversational"),
    ("See you later", "conversational"),
    ("Good night", "conversational"),
    # Conversational: gratitude
    ("Thanks!", "conversational"),
    ("Thank you", "conversational"),
    ("Great job!", "conversational"),
    # Coding: fix bug
    ("Fix the bug in auth.py", "coding"),
    ("There's a TypeError in router.py line 42", "coding"),
    ("The login function throws an exception", "coding"),
    ("Fix the off-by-one error in the loop", "coding"),
    # Coding: create file
    ("Create a new file called utils.py", "coding"),
    ("Write a Dockerfile for this project", "coding"),
    ("Set up a new FastAPI endpoint", "coding"),
    # Coding: modify
    ("Add error handling to the API endpoint", "coding"),
    ("Update the config to use environment variables", "coding"),
    ("Add type hints to this function", "coding"),
    ("Implement rate limiting on the API", "coding"),
    # Coding: refactor
    ("Refactor the router to use a strategy pattern", "coding"),
    ("Clean up the duplicate code", "coding"),
    ("Simplify this nested if-else chain", "coding"),
    # Coding: tests
    ("Write unit tests for the auth module", "coding"),
    ("Add test coverage for the edge cases", "coding"),
    # Question: code explanation
    ("What does this function do?", "question"),
    ("How does the router work?", "question"),
    ("Explain the authentication flow", "question"),
    # Question: architecture
    ("How should I structure this project?", "question"),
    ("What's the best way to organize these files?", "question"),
    # Question: debugging
    ("Why is this test failing?", "question"),
    ("What's causing this error?", "question"),
    # Question: general knowledge
    ("What is dependency injection?", "question"),
    ("What's the difference between REST and GraphQL?", "question"),
    # Ambiguous
    ("Fix this", "ambiguous"),
    ("Make it better", "ambiguous"),
    ("I'm stuck", "ambiguous"),
    ("It doesn't work", "ambiguous"),
]


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(scope="module")
def seeded_bank(tmp_path_factory):
    """Provide an ExemplarBank loaded with the shipped seed data."""
    tmp = tmp_path_factory.mktemp("bench")
    bank = ExemplarBank(db_path=str(tmp / "bench.db"))
    seed_path = Path(__file__).resolve().parents[2] / "data" / "seed" / "intent_exemplars.json"
    if seed_path.exists():
        bank.load_seed_data(str(seed_path))
    return bank


@pytest.fixture(scope="module")
def seeded_analyzer(seeded_bank):
    """Provide a RequestAnalyzer backed by seeded exemplars."""
    return RequestAnalyzer(exemplar_bank=seeded_bank)


@pytest.fixture(scope="module")
def bare_analyzer():
    """Provide a RequestAnalyzer with no exemplar bank (keyword only)."""
    return RequestAnalyzer()


# =============================================================================
# KEYWORD ACCURACY BENCHMARK
# =============================================================================


class TestKeywordAccuracy:
    """Keyword fallback must achieve >= 70% on the benchmark set."""

    def test_keyword_accuracy_above_70_percent(self):
        classifier = IntentClassifier()
        correct = 0
        failures = []
        for msg, expected in BENCHMARK_CASES:
            result = classifier.classify_keyword(msg)
            if result.intent == expected:
                correct += 1
            else:
                failures.append((msg, expected, result.intent))

        accuracy = correct / len(BENCHMARK_CASES)
        assert accuracy >= 0.70, (
            f"Keyword accuracy {accuracy:.0%} ({correct}/{len(BENCHMARK_CASES)}). "
            f"Failures: {failures[:5]}"
        )


# =============================================================================
# SEEDED ANALYZER ACCURACY
# =============================================================================


class TestSeededAccuracy:
    """Analyzer with seed data must achieve >= 70% on the benchmark set."""

    def test_seeded_accuracy_above_70_percent(self, seeded_analyzer):
        correct = 0
        failures = []
        for msg, expected in BENCHMARK_CASES:
            result = seeded_analyzer.analyze(msg)
            if result.intent == expected:
                correct += 1
            else:
                failures.append((msg, expected, result.intent))

        accuracy = correct / len(BENCHMARK_CASES)
        assert accuracy >= 0.70, (
            f"Seeded accuracy {accuracy:.0%} ({correct}/{len(BENCHMARK_CASES)}). "
            f"Failures: {failures[:5]}"
        )


# =============================================================================
# LATENCY
# =============================================================================


class TestLatency:
    """Classification must be fast enough for interactive use."""

    def test_keyword_latency_under_50ms(self):
        classifier = IntentClassifier()
        # Warm up
        classifier.classify_keyword("Hello")

        start = time.perf_counter()
        for msg, _ in BENCHMARK_CASES:
            classifier.classify_keyword(msg)
        elapsed = time.perf_counter() - start

        per_message = (elapsed / len(BENCHMARK_CASES)) * 1000
        assert per_message < 50, f"Keyword classification too slow: {per_message:.1f}ms/msg"

    def test_full_pipeline_latency_under_500ms(self, bare_analyzer):
        # Warm up
        bare_analyzer.analyze("Hello")

        start = time.perf_counter()
        for msg, _ in BENCHMARK_CASES[:10]:
            bare_analyzer.analyze(msg)
        elapsed = time.perf_counter() - start

        per_message = (elapsed / 10) * 1000
        assert per_message < 500, f"Full pipeline too slow: {per_message:.1f}ms/msg"


# =============================================================================
# PIPELINE INTEGRITY
# =============================================================================


class TestPipelineIntegrity:
    """Validate the full pipeline produces well-formed results."""

    def test_all_results_have_intent(self, seeded_analyzer):
        for msg, _ in BENCHMARK_CASES:
            result = seeded_analyzer.analyze(msg)
            assert result.intent in (
                "conversational",
                "question",
                "coding",
                "compound",
                "ambiguous",
            )

    def test_all_results_have_confidence(self, seeded_analyzer):
        for msg, _ in BENCHMARK_CASES:
            result = seeded_analyzer.analyze(msg)
            assert 0.0 <= result.confidence <= 1.0

    def test_all_results_have_brief(self, seeded_analyzer):
        for msg, _ in BENCHMARK_CASES:
            result = seeded_analyzer.analyze(msg)
            assert isinstance(result.brief, TaskBrief)
            assert len(result.brief.summary) > 0 or result.brief.needs_clarification

    def test_all_results_have_fast_path_intent(self, seeded_analyzer):
        for msg, _ in BENCHMARK_CASES:
            result = seeded_analyzer.analyze(msg)
            assert result.fast_path_intent in ("conversational", "question", "coding_task")

    def test_clarification_only_for_ambiguous_or_missing_context(self, seeded_analyzer):
        for msg, expected in BENCHMARK_CASES:
            result = seeded_analyzer.analyze(msg)
            if result.needs_clarification:
                # Clarification is valid for: ambiguous, low confidence, or missing context on coding tasks
                valid = (
                    result.intent == "ambiguous"
                    or result.confidence < 0.5
                    or expected == "ambiguous"
                    or result.brief.needs_clarification  # detector found missing context
                )
                assert valid, (
                    f"Unexpected clarification for '{msg}' (intent={result.intent}, conf={result.confidence})"
                )

    def test_format_for_prompt_never_empty(self, seeded_analyzer):
        for msg, _ in BENCHMARK_CASES:
            result = seeded_analyzer.analyze(msg)
            prompt = result.format_for_prompt()
            assert isinstance(prompt, str)
            assert len(prompt) > 0


# =============================================================================
# SEED DATA VALIDATION
# =============================================================================


class TestSeedData:
    """Validate the shipped seed data is well-formed."""

    def test_seed_file_exists(self):
        seed_path = Path(__file__).resolve().parents[2] / "data" / "seed" / "intent_exemplars.json"
        assert seed_path.exists(), f"Seed file missing: {seed_path}"

    def test_seed_is_valid_json(self):
        seed_path = Path(__file__).resolve().parents[2] / "data" / "seed" / "intent_exemplars.json"
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) >= 100, f"Seed data too small: {len(data)} exemplars"

    def test_seed_has_required_fields(self):
        seed_path = Path(__file__).resolve().parents[2] / "data" / "seed" / "intent_exemplars.json"
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        for item in data:
            assert "user_message" in item, f"Missing user_message: {item}"
            assert "intent" in item, f"Missing intent: {item}"
            assert "sub_intent" in item, f"Missing sub_intent: {item}"

    def test_seed_covers_all_intents(self):
        seed_path = Path(__file__).resolve().parents[2] / "data" / "seed" / "intent_exemplars.json"
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        intents = {item["intent"] for item in data}
        assert "conversational" in intents
        assert "question" in intents
        assert "coding" in intents
        assert "compound" in intents
        assert "ambiguous" in intents

    def test_seed_loads_into_bank(self, seeded_bank):
        assert seeded_bank.count() >= 100
