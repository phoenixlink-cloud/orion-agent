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
Orion Agent -- Benchmark Engine (v7.1.0)

Compares Orion's output against a gold-standard teacher response.
Produces structured quality assessment using:
1. Concept coverage -- did the student hit all expected concepts?
2. Semantic similarity -- how close is the overall meaning?
3. LLM-as-judge -- ask a model to evaluate the quality gap

USAGE:
    from orion.core.learning.benchmark import BenchmarkEngine
    engine = BenchmarkEngine()
    result = await engine.compare(student_text, teacher_text, expected_concepts)
"""

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("orion.learning.benchmark")


@dataclass
class ComparisonResult:
    """Result of comparing student vs teacher response."""

    similarity_score: float  # 0.0-1.0 overall
    concept_coverage: float  # 0.0-1.0 what % of expected concepts were present
    concepts_present: list[str] = field(default_factory=list)
    concepts_missing: list[str] = field(default_factory=list)
    incorrect_claims: list[str] = field(default_factory=list)
    quality_score: int = 3  # 1-5 derived score
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    feedback_text: str = ""  # Human-readable gap analysis


class BenchmarkEngine:
    """
    Evaluates student (Orion) responses against teacher (gold standard) responses.
    Uses a combination of:
    1. Concept coverage -- did the student hit all expected concepts?
    2. Semantic similarity -- how close is the overall meaning?
    3. LLM-as-judge -- ask a model to evaluate the quality gap
    """

    def __init__(
        self,
        judge_provider: str = "anthropic",
        judge_model: str = "claude-opus-4-20250514",
    ):
        self.judge_provider = judge_provider
        self.judge_model = judge_model
        self._embedding_store = None

    def _get_embedding_store(self):
        """Lazy-load embedding store."""
        if self._embedding_store is None:
            from orion.core.memory.embeddings import EmbeddingStore

            self._embedding_store = EmbeddingStore()
        return self._embedding_store

    async def compare(
        self,
        student: str,
        teacher: str,
        expected_concepts: list[str],
        prompt: str = "",
    ) -> ComparisonResult:
        """
        Compare student response against teacher response.

        Args:
            student: The student (Orion) response text.
            teacher: The teacher (gold standard) response text.
            expected_concepts: List of concepts the response MUST cover.
            prompt: The original prompt/question (for LLM judge context).

        Returns:
            ComparisonResult with scores, concept analysis, and feedback.
        """
        # 1. Concept coverage check (embedding-based or keyword fallback)
        concepts_present, concepts_missing = self._check_concept_coverage(
            student, expected_concepts
        )
        concept_coverage = (
            len(concepts_present) / len(expected_concepts) if expected_concepts else 1.0
        )

        # 2. Semantic similarity
        similarity_score = self._compute_similarity(student, teacher)

        # 3. LLM-as-judge
        judge_result = await self._llm_judge(student, teacher, expected_concepts, prompt)

        # 4. Combine scores
        # Map concept_coverage to 1-5
        concept_score = self._coverage_to_score(concept_coverage)
        # Map similarity to 1-5
        similarity_mapped = self._similarity_to_score(similarity_score)
        # LLM judge score
        llm_score = judge_result.get("quality_score", 3)

        # Final quality score is the average, rounded to nearest int
        combined = (llm_score + concept_score + similarity_mapped) / 3.0
        quality_score = max(1, min(5, round(combined)))

        # Merge judge insights with our computed data
        return ComparisonResult(
            similarity_score=round(similarity_score, 3),
            concept_coverage=round(concept_coverage, 3),
            concepts_present=judge_result.get("concepts_present", concepts_present),
            concepts_missing=judge_result.get("concepts_missing", concepts_missing),
            incorrect_claims=judge_result.get("incorrect_claims", []),
            quality_score=quality_score,
            strengths=judge_result.get("strengths", []),
            weaknesses=judge_result.get("weaknesses", []),
            feedback_text=judge_result.get("feedback", ""),
        )

    def _check_concept_coverage(self, student: str, expected_concepts: list[str]) -> tuple:
        """
        Check which expected concepts are present in the student response.
        Uses embedding similarity if available, falls back to keyword matching.

        Returns:
            (concepts_present, concepts_missing) tuple of lists.
        """
        store = self._get_embedding_store()
        present = []
        missing = []

        for concept in expected_concepts:
            if store.available:
                # Embedding-based: check similarity of concept against student sentences
                sentences = [s.strip() for s in student.split(".") if s.strip()]
                max_sim = 0.0
                for sentence in sentences:
                    sim = store.similarity(concept, sentence)
                    max_sim = max(max_sim, sim)
                if max_sim > 0.7:
                    present.append(concept)
                else:
                    # Also try whole-text similarity as fallback
                    whole_sim = store.similarity(concept, student)
                    if whole_sim > 0.6:
                        present.append(concept)
                    else:
                        missing.append(concept)
            else:
                # Keyword fallback
                concept_words = set(concept.lower().split())
                student_lower = student.lower()
                matched = sum(1 for w in concept_words if w in student_lower)
                if matched >= len(concept_words) * 0.5:
                    present.append(concept)
                else:
                    missing.append(concept)

        return present, missing

    def _compute_similarity(self, student: str, teacher: str) -> float:
        """Compute semantic similarity between student and teacher responses."""
        store = self._get_embedding_store()
        if store.available:
            return store.similarity(student, teacher)
        else:
            # Keyword fallback: Jaccard similarity
            student_words = set(student.lower().split())
            teacher_words = set(teacher.lower().split())
            if not student_words or not teacher_words:
                return 0.0
            intersection = len(student_words & teacher_words)
            union = len(student_words | teacher_words)
            return intersection / union if union > 0 else 0.0

    async def _llm_judge(
        self,
        student: str,
        teacher: str,
        expected_concepts: list[str],
        prompt: str,
    ) -> dict:
        """
        Ask an LLM to evaluate the student response against the teacher response.
        Returns a dict with quality_score, concepts_present, concepts_missing, etc.
        """
        judge_prompt = (
            f'You are an expert evaluator. Compare these two responses to the question: "{prompt}"\n\n'
            f"STUDENT RESPONSE:\n{student[:3000]}\n\n"
            f"TEACHER RESPONSE (gold standard):\n{teacher[:3000]}\n\n"
            f"EXPECTED CONCEPTS: {json.dumps(expected_concepts)}\n\n"
            "Evaluate the student response and return ONLY valid JSON (no markdown, no explanation):\n"
            "{\n"
            '  "quality_score": <1-5>,\n'
            '  "concepts_present": [<list of expected concepts the student covered>],\n'
            '  "concepts_missing": [<list of expected concepts the student missed>],\n'
            '  "incorrect_claims": [<list of factual errors, empty if none>],\n'
            '  "strengths": [<2-3 specific things done well>],\n'
            '  "weaknesses": [<2-3 specific improvement areas>],\n'
            '  "feedback": "<2-3 sentence summary of the gap>"\n'
            "}"
        )

        try:
            from orion.core.llm.config import RoleConfig
            from orion.core.llm.providers import call_provider

            role = RoleConfig(provider=self.judge_provider, model=self.judge_model)
            response = await call_provider(
                role_config=role,
                system_prompt="You are a precise evaluation judge. Return only valid JSON.",
                user_prompt=judge_prompt,
                max_tokens=2000,
                component="benchmark_judge",
                temperature=0.1,
            )

            # Parse JSON from response
            result = self._parse_judge_response(response)
            return result

        except Exception as e:
            logger.warning("LLM judge failed: %s -- using fallback scoring", e)
            return self._fallback_judge(student, teacher, expected_concepts)

    def _parse_judge_response(self, response: str) -> dict:
        """Parse the LLM judge response, extracting JSON."""
        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        if "```" in response:
            parts = response.split("```")
            for part in parts:
                cleaned = part.strip()
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    continue

        # Try to find JSON object in the response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end])
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse judge response as JSON")
        return {"quality_score": 3, "feedback": "Could not parse judge evaluation"}

    def _fallback_judge(self, student: str, teacher: str, expected_concepts: list[str]) -> dict:
        """Fallback scoring when LLM judge is unavailable."""
        present, missing = self._check_concept_coverage(student, expected_concepts)
        coverage = len(present) / len(expected_concepts) if expected_concepts else 1.0
        score = self._coverage_to_score(coverage)
        return {
            "quality_score": score,
            "concepts_present": present,
            "concepts_missing": missing,
            "incorrect_claims": [],
            "strengths": ["Response provided"] if len(student) > 50 else [],
            "weaknesses": [f"Missing {len(missing)} concepts"] if missing else [],
            "feedback": f"Covered {len(present)}/{len(expected_concepts)} concepts. "
            f"Missing: {', '.join(missing[:3])}"
            if missing
            else "All concepts covered.",
        }

    @staticmethod
    def _coverage_to_score(coverage: float) -> int:
        """Map concept coverage (0.0-1.0) to score (1-5)."""
        if coverage >= 0.8:
            return 5
        elif coverage >= 0.6:
            return 4
        elif coverage >= 0.4:
            return 3
        elif coverage >= 0.2:
            return 2
        else:
            return 1

    @staticmethod
    def _similarity_to_score(similarity: float) -> int:
        """Map semantic similarity (0.0-1.0) to score (1-5)."""
        if similarity >= 0.8:
            return 5
        elif similarity >= 0.6:
            return 4
        elif similarity >= 0.4:
            return 3
        elif similarity >= 0.2:
            return 2
        else:
            return 1
