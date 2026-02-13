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
Orion Agent -- Intent Classifier (v7.6.0)

Classifies user messages into intents by comparing against the
ExemplarBank via embedding similarity or keyword fallback.

Replaces regex-based _classify_intent() in fast_path.py and
keyword patterns in scout.py.

Part of the Natural Language Architecture (NLA-002, Phase 1C).

Classification flow:
    1. Try embedding similarity against exemplar bank (fast, accurate)
    2. Fall back to keyword matching if embeddings unavailable
    3. Return ClassificationResult with intent, sub_intent, confidence, method
"""

import logging
import re
from dataclasses import dataclass

from orion.core.understanding.exemplar_bank import ExemplarBank

logger = logging.getLogger("orion.understanding.intent_classifier")

# =============================================================================
# KEYWORD PATTERNS (fallback when embeddings unavailable)
# =============================================================================

_GREETING_PATTERNS = [
    r"^\s*(hi|hello|hey|howdy|greetings|good\s+(morning|afternoon|evening|day)|yo|sup)\b",
    r"^\s*how\s+are\s+you",
    r"^\s*what'?s\s+up\s*\??$",
    r"^\s*are\s+you\s+(there|ready|ok|okay)",
]

_FAREWELL_PATTERNS = [
    r"^\s*(bye|goodbye|see\s+you|good\s*night|talk\s+to\s+you\s+later)\b",
    r"^\s*(i'?m\s+done|that'?s\s+all|signing\s+off|gotta\s+go)\b",
]

_GRATITUDE_PATTERNS = [
    r"^\s*thanks?\s*(you)?[!.]*$",
    r"^\s*thank\s+you",
    r"^\s*(great|awesome|excellent|perfect|nice|well\s+done|good\s+job)[!.]*$",
]

_IDENTITY_PATTERNS = [
    r"\bwho\s+are\s+you\b",
    r"\btell\s+me\s+about\s+(yourself|you)\b",
    r"\bwhat\s+can\s+you\s+do\b",
    r"\bwhat\s+are\s+your\s+capabilities\b",
    r"\bare\s+you\s+an?\s+ai\b",
    r"\bwho\s+(built|made|created)\s+you\b",
]

_CODING_PATTERNS = [
    r"\b(create|write|build|implement|add|fix|debug|refactor|update|modify|delete|remove)\b",
    r"\b(file|function|class|method|module|api|endpoint|route|component|test)\b",
    r"\b(install|deploy|run|execute|compile|lint|format)\b",
    r"\b(error|bug|exception|traceback|stack\s*trace|crash|fail)\b",
    r"\.(py|js|ts|jsx|tsx|json|yaml|yml|html|css|sql|go|rs|java|cs|cpp|c|h)\b",
    r"```",
    r"\b(import|from|def |class |function |const |let |var )\b",
]

_QUESTION_PATTERNS = [
    r"^\s*(what|how|why|when|where|which|can\s+you\s+explain|explain)\b",
    r"\?\s*$",
    r"\b(difference\s+between|pros?\s+and\s+cons?|best\s+way|should\s+i)\b",
]

_AMBIGUOUS_PATTERNS = [
    r"^\s*(i'?m\s+stuck|help|make\s+it\s+(better|work)|fix\s+(this|it)|it\s+doesn'?t\s+work)\s*[.!?]*$",
    r"^\s*(something\s+is\s+wrong|look\s+at\s+this|check\s+this|can\s+you\s+(help|change\s+this))\s*[.!?]*$",
    r"^\s*(do\s+the\s+thing|improve\s+(this|it))\s*[.!?]*$",
]


@dataclass
class ClassificationResult:
    """Result of intent classification."""

    intent: str  # conversational, question, coding, compound, ambiguous
    sub_intent: str  # greeting, fix_bug, etc.
    confidence: float  # 0.0–1.0
    method: str  # "embedding" or "keyword"


class IntentClassifier:
    """
    Classifies user messages into intents.

    Uses embedding similarity against ExemplarBank when available,
    falls back to keyword pattern matching otherwise.
    """

    # Confidence thresholds for embedding classification
    HIGH_CONFIDENCE = 0.85
    MEDIUM_CONFIDENCE = 0.60

    def __init__(self, exemplar_bank: ExemplarBank | None = None):
        self._bank = exemplar_bank
        self._embedding_store = None
        self._embeddings_available = False
        self._exemplar_embeddings: list[tuple[str, str, str, object]] | None = None

        # English Foundation pre-processor (NLA Phase 3A)
        self._english = None
        try:
            from orion.core.understanding.english_foundation import EnglishFoundation

            self._english = EnglishFoundation()
        except Exception:
            pass

        self._try_init_embeddings()

    def _try_init_embeddings(self) -> None:
        """Try to initialise the embedding model for semantic classification."""
        try:
            from orion.core.memory.embeddings import EmbeddingStore

            store = EmbeddingStore()
            if store.available:
                self._embedding_store = store
                self._embeddings_available = True
                logger.info("IntentClassifier: embedding mode available")
            else:
                logger.info("IntentClassifier: embeddings not available, using keyword fallback")
        except Exception:
            logger.info("IntentClassifier: embeddings not available, using keyword fallback")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def classify(self, message: str) -> ClassificationResult:
        """
        Classify a user message into an intent.

        Tries embedding similarity first, falls back to keywords.
        """
        text = message.strip()
        if not text:
            return ClassificationResult(
                intent="conversational", sub_intent="", confidence=0.1, method="keyword"
            )

        # Pre-process via English Foundation
        if self._english:
            text = self._english.pre_process(text)

        # Try embedding-based classification
        if self._embeddings_available and self._bank:
            result = self._classify_embedding(text)
            if result is not None:
                return result

        # Fallback to keyword classification
        return self.classify_keyword(text)

    def classify_keyword(self, message: str) -> ClassificationResult:
        """
        Classify using keyword pattern matching only.

        This is the fallback path and also the baseline for benchmarks.
        """
        text = message.strip()
        if not text:
            return ClassificationResult(
                intent="conversational", sub_intent="", confidence=0.1, method="keyword"
            )

        lower = text.lower()

        # Check for compound intent (greeting + task)
        has_greeting = any(re.search(p, lower) for p in _GREETING_PATTERNS)
        has_coding = any(re.search(p, lower) for p in _CODING_PATTERNS)
        if has_greeting and has_coding:
            return ClassificationResult(
                intent="compound",
                sub_intent="greeting_plus_task",
                confidence=0.75,
                method="keyword",
            )

        # Check ambiguous patterns (short vague messages)
        for pattern in _AMBIGUOUS_PATTERNS:
            if re.search(pattern, lower):
                return ClassificationResult(
                    intent="ambiguous",
                    sub_intent="needs_clarification",
                    confidence=0.7,
                    method="keyword",
                )

        # Conversational: greetings
        for pattern in _GREETING_PATTERNS:
            if re.search(pattern, lower):
                return ClassificationResult(
                    intent="conversational",
                    sub_intent="greeting",
                    confidence=0.9,
                    method="keyword",
                )

        # Conversational: farewells
        for pattern in _FAREWELL_PATTERNS:
            if re.search(pattern, lower):
                return ClassificationResult(
                    intent="conversational",
                    sub_intent="farewell",
                    confidence=0.9,
                    method="keyword",
                )

        # Conversational: gratitude
        for pattern in _GRATITUDE_PATTERNS:
            if re.search(pattern, lower):
                return ClassificationResult(
                    intent="conversational",
                    sub_intent="gratitude",
                    confidence=0.9,
                    method="keyword",
                )

        # Conversational: identity questions
        for pattern in _IDENTITY_PATTERNS:
            if re.search(pattern, lower):
                return ClassificationResult(
                    intent="conversational",
                    sub_intent="identity",
                    confidence=0.85,
                    method="keyword",
                )

        # Coding signals
        coding_hits = sum(1 for p in _CODING_PATTERNS if re.search(p, lower))
        question_hits = sum(1 for p in _QUESTION_PATTERNS if re.search(p, lower))

        if coding_hits >= 2:
            sub = self._detect_coding_sub_intent(lower)
            return ClassificationResult(
                intent="coding",
                sub_intent=sub,
                confidence=min(0.95, 0.6 + coding_hits * 0.1),
                method="keyword",
            )

        # Question signals
        if question_hits >= 1:
            sub = self._detect_question_sub_intent(lower)
            conf = 0.7 if coding_hits == 0 else 0.5
            return ClassificationResult(
                intent="question", sub_intent=sub, confidence=conf, method="keyword"
            )

        # Single coding signal (weaker)
        if coding_hits == 1:
            sub = self._detect_coding_sub_intent(lower)
            return ClassificationResult(
                intent="coding", sub_intent=sub, confidence=0.55, method="keyword"
            )

        # Default: question
        return ClassificationResult(
            intent="question", sub_intent="general", confidence=0.4, method="keyword"
        )

    def classify_batch(self, messages: list[str]) -> list[ClassificationResult]:
        """Classify multiple messages."""
        return [self.classify(m) for m in messages]

    # =========================================================================
    # EMBEDDING-BASED CLASSIFICATION
    # =========================================================================

    def _classify_embedding(self, text: str) -> ClassificationResult | None:
        """
        Classify by embedding similarity against exemplar bank.

        Returns None if classification fails (caller should fall back to keywords).
        """
        if not self._embedding_store or not self._bank:
            return None

        try:
            # Embed the user message
            query_emb = self._embedding_store.embed_text(text)
            if query_emb is None:
                return None

            # Build exemplar embeddings cache on first use
            if self._exemplar_embeddings is None:
                self._build_exemplar_cache()

            if not self._exemplar_embeddings:
                return None

            # Compute similarities
            import numpy as np

            best_score = -1.0
            best_intent = "question"
            best_sub = ""

            # Score against each exemplar
            scores_by_intent: dict[str, list[float]] = {}

            for intent, sub_intent, _msg, emb in self._exemplar_embeddings:
                sim = float(
                    np.dot(query_emb, emb)
                    / (np.linalg.norm(query_emb) * np.linalg.norm(emb) + 1e-10)
                )
                scores_by_intent.setdefault(intent, []).append(sim)
                if sim > best_score:
                    best_score = sim
                    best_intent = intent
                    best_sub = sub_intent

            # Confidence from similarity score
            confidence = max(0.0, min(1.0, best_score))

            return ClassificationResult(
                intent=best_intent,
                sub_intent=best_sub,
                confidence=confidence,
                method="embedding",
            )

        except Exception as e:
            logger.debug("Embedding classification failed: %s", e)
            return None

    def _build_exemplar_cache(self) -> None:
        """Pre-compute embeddings for all exemplars in the bank."""
        if not self._bank or not self._embedding_store:
            self._exemplar_embeddings = []
            return

        exemplars = self._bank.get_all()
        cache = []
        for ex in exemplars:
            emb = self._embedding_store.embed_text(ex.user_message)
            if emb is not None:
                cache.append((ex.intent, ex.sub_intent, ex.user_message, emb))

        self._exemplar_embeddings = cache
        logger.info("Cached %d exemplar embeddings for classification", len(cache))

    # =========================================================================
    # SUB-INTENT DETECTION (keyword helpers)
    # =========================================================================

    @staticmethod
    def _detect_coding_sub_intent(lower: str) -> str:
        """Detect specific coding sub-intent from keywords."""
        if re.search(r"\b(fix|bug|error|broken|crash|fail|wrong)\b", lower):
            return "fix_bug"
        if re.search(r"\b(create|new|scaffold|set\s*up|write\s+a)\b", lower):
            return "create_file"
        if re.search(r"\b(refactor|clean|simplify|extract|reorganize)\b", lower):
            return "refactor"
        if re.search(r"\b(test|spec|coverage|assert)\b", lower):
            return "write_tests"
        if re.search(r"\b(add|update|change|modify|implement)\b", lower):
            return "modify_file"
        return "general"

    @staticmethod
    def _detect_question_sub_intent(lower: str) -> str:
        """Detect specific question sub-intent from keywords."""
        if re.search(r"\b(error|fail|crash|bug|broken|wrong|exception)\b", lower):
            return "debugging"
        if re.search(r"\b(explain|what\s+does|how\s+does|walk\s+me|describe)\b", lower):
            return "code_explanation"
        if re.search(r"\b(architect|design|structure|organize|approach|tradeoff)\b", lower):
            return "architecture"
        return "general_knowledge"
