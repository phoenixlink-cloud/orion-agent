"""
Tests for Orion's Benchmark Engine (v7.1.0)

Tests concept coverage checking, similarity computation,
LLM-as-judge evaluation, score mapping, and fallback behavior.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.core.learning.benchmark import BenchmarkEngine


class TestConceptCoverage:
    """Test concept coverage checking."""

    def test_concept_coverage_all_present(self):
        """Student covers all concepts -> 1.0 coverage."""
        engine = BenchmarkEngine()
        # Use keyword fallback (no embeddings)
        with patch.object(engine, "_get_embedding_store") as mock_store:
            mock_store.return_value = MagicMock(available=False)
            present, missing = engine._check_concept_coverage(
                student="PEP 8 style guide recommends meaningful variable names. "
                "The DRY principle means don't repeat yourself. "
                "Single responsibility keeps functions focused. "
                "Type hints improve code quality.",
                expected_concepts=[
                    "PEP 8 style guide",
                    "meaningful variable names",
                    "DRY principle",
                    "single responsibility",
                    "type hints",
                ],
            )
            assert len(present) == 5
            assert len(missing) == 0

    def test_concept_coverage_partial(self):
        """Student covers 3/5 concepts -> 0.6 coverage."""
        engine = BenchmarkEngine()
        with patch.object(engine, "_get_embedding_store") as mock_store:
            mock_store.return_value = MagicMock(available=False)
            present, missing = engine._check_concept_coverage(
                student="PEP 8 style guide recommends meaningful variable names. "
                "Type hints help catch errors.",
                expected_concepts=[
                    "PEP 8 style guide",
                    "meaningful variable names",
                    "DRY principle",
                    "single responsibility",
                    "type hints",
                ],
            )
            assert len(present) == 3
            assert len(missing) == 2
            assert "DRY principle" in missing
            assert "single responsibility" in missing

    def test_concept_coverage_none(self):
        """Student covers 0/5 concepts -> 0.0 coverage."""
        engine = BenchmarkEngine()
        with patch.object(engine, "_get_embedding_store") as mock_store:
            mock_store.return_value = MagicMock(available=False)
            present, missing = engine._check_concept_coverage(
                student="The weather is nice today. I like chocolate cake.",
                expected_concepts=[
                    "PEP 8 style guide",
                    "meaningful variable names",
                    "DRY principle",
                    "single responsibility",
                    "type hints",
                ],
            )
            assert len(present) == 0
            assert len(missing) == 5


class TestSimilarity:
    """Test similarity computation."""

    def test_compute_similarity_keyword_fallback(self):
        """Keyword-based Jaccard similarity."""
        engine = BenchmarkEngine()
        with patch.object(engine, "_get_embedding_store") as mock_store:
            mock_store.return_value = MagicMock(available=False)
            # Identical texts -> 1.0
            sim = engine._compute_similarity("hello world", "hello world")
            assert sim == 1.0

    def test_compute_similarity_different_texts(self):
        """Different texts -> lower similarity."""
        engine = BenchmarkEngine()
        with patch.object(engine, "_get_embedding_store") as mock_store:
            mock_store.return_value = MagicMock(available=False)
            sim = engine._compute_similarity(
                "Python is a programming language",
                "Chocolate cake recipe with frosting",
            )
            assert sim < 0.3

    def test_compute_similarity_empty(self):
        """Empty texts -> 0.0."""
        engine = BenchmarkEngine()
        with patch.object(engine, "_get_embedding_store") as mock_store:
            mock_store.return_value = MagicMock(available=False)
            sim = engine._compute_similarity("", "")
            assert sim == 0.0


class TestScoreMapping:
    """Test score mapping functions."""

    def test_coverage_to_score(self):
        assert BenchmarkEngine._coverage_to_score(0.0) == 1
        assert BenchmarkEngine._coverage_to_score(0.15) == 1
        assert BenchmarkEngine._coverage_to_score(0.25) == 2
        assert BenchmarkEngine._coverage_to_score(0.45) == 3
        assert BenchmarkEngine._coverage_to_score(0.65) == 4
        assert BenchmarkEngine._coverage_to_score(0.85) == 5
        assert BenchmarkEngine._coverage_to_score(1.0) == 5

    def test_similarity_to_score(self):
        assert BenchmarkEngine._similarity_to_score(0.0) == 1
        assert BenchmarkEngine._similarity_to_score(0.15) == 1
        assert BenchmarkEngine._similarity_to_score(0.25) == 2
        assert BenchmarkEngine._similarity_to_score(0.45) == 3
        assert BenchmarkEngine._similarity_to_score(0.65) == 4
        assert BenchmarkEngine._similarity_to_score(0.85) == 5
        assert BenchmarkEngine._similarity_to_score(1.0) == 5


class TestJudgeParsing:
    """Test LLM judge response parsing."""

    def test_parse_valid_json(self):
        engine = BenchmarkEngine()
        response = json.dumps(
            {
                "quality_score": 4,
                "concepts_present": ["a", "b"],
                "concepts_missing": ["c"],
                "incorrect_claims": [],
                "strengths": ["good structure"],
                "weaknesses": ["missing detail"],
                "feedback": "Good overall.",
            }
        )
        result = engine._parse_judge_response(response)
        assert result["quality_score"] == 4
        assert len(result["concepts_present"]) == 2

    def test_parse_json_in_code_block(self):
        engine = BenchmarkEngine()
        response = '```json\n{"quality_score": 3, "feedback": "ok"}\n```'
        result = engine._parse_judge_response(response)
        assert result["quality_score"] == 3

    def test_parse_json_with_preamble(self):
        engine = BenchmarkEngine()
        response = 'Here is my evaluation:\n{"quality_score": 5, "feedback": "excellent"}'
        result = engine._parse_judge_response(response)
        assert result["quality_score"] == 5

    def test_parse_invalid_json_fallback(self):
        engine = BenchmarkEngine()
        result = engine._parse_judge_response("This is not JSON at all")
        assert "quality_score" in result
        assert result["quality_score"] == 3


class TestCompare:
    """Test the full compare pipeline with mocked LLM judge."""

    @pytest.mark.asyncio
    async def test_compare_identical_responses(self):
        """Same text should get high scores."""
        engine = BenchmarkEngine()
        text = "PEP 8 is the style guide. Use meaningful names. DRY principle. Single responsibility. Type hints."

        # Mock LLM judge
        with patch.object(engine, "_llm_judge", new_callable=AsyncMock) as mock_judge:
            mock_judge.return_value = {
                "quality_score": 5,
                "concepts_present": [
                    "PEP 8 style guide",
                    "meaningful variable names",
                    "DRY principle",
                    "single responsibility",
                    "type hints",
                ],
                "concepts_missing": [],
                "incorrect_claims": [],
                "strengths": ["Comprehensive coverage"],
                "weaknesses": [],
                "feedback": "Excellent match.",
            }
            with patch.object(engine, "_get_embedding_store") as mock_store:
                mock_store.return_value = MagicMock(available=False)

                result = await engine.compare(
                    student=text,
                    teacher=text,
                    expected_concepts=[
                        "PEP 8 style guide",
                        "meaningful variable names",
                        "DRY principle",
                        "single responsibility",
                        "type hints",
                    ],
                )
                assert result.quality_score >= 4
                assert result.similarity_score == 1.0

    @pytest.mark.asyncio
    async def test_compare_completely_different(self):
        """Unrelated texts should get low scores."""
        engine = BenchmarkEngine()

        with patch.object(engine, "_llm_judge", new_callable=AsyncMock) as mock_judge:
            mock_judge.return_value = {
                "quality_score": 1,
                "concepts_present": [],
                "concepts_missing": ["PEP 8", "type hints"],
                "incorrect_claims": ["student discussed cooking"],
                "strengths": [],
                "weaknesses": ["Completely off topic"],
                "feedback": "Student response is unrelated.",
            }
            with patch.object(engine, "_get_embedding_store") as mock_store:
                mock_store.return_value = MagicMock(available=False)

                result = await engine.compare(
                    student="I love chocolate cake and vanilla ice cream",
                    teacher="PEP 8 defines Python coding standards. Type hints help.",
                    expected_concepts=["PEP 8", "type hints"],
                )
                assert result.quality_score <= 2

    @pytest.mark.asyncio
    async def test_incorrect_claims_detected(self):
        """Mock judge identifies factual errors."""
        engine = BenchmarkEngine()

        with patch.object(engine, "_llm_judge", new_callable=AsyncMock) as mock_judge:
            mock_judge.return_value = {
                "quality_score": 2,
                "concepts_present": ["PEP 8"],
                "concepts_missing": ["type hints"],
                "incorrect_claims": ["PEP 8 was created in 2020"],
                "strengths": ["Mentioned PEP 8"],
                "weaknesses": ["Factual error about PEP 8 date"],
                "feedback": "Contains factual errors.",
            }
            with patch.object(engine, "_get_embedding_store") as mock_store:
                mock_store.return_value = MagicMock(available=False)

                result = await engine.compare(
                    student="PEP 8 was created in 2020 and defines style.",
                    teacher="PEP 8 was created in 2001 and defines Python coding standards.",
                    expected_concepts=["PEP 8", "type hints"],
                )
                assert len(result.incorrect_claims) > 0
                assert "PEP 8 was created in 2020" in result.incorrect_claims[0]
