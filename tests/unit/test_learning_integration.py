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
"""Tests for NLA learning integration -- feedback loop into ExemplarBank."""

import pytest

from orion.core.understanding.exemplar_bank import ExemplarBank
from orion.core.understanding.intent_classifier import ClassificationResult
from orion.core.understanding.learning_bridge import LearningBridge

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def bank(tmp_path):
    """Provide a fresh ExemplarBank."""
    return ExemplarBank(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def bridge(bank):
    """Provide a LearningBridge connected to the test bank."""
    return LearningBridge(exemplar_bank=bank)


def _cr(intent: str, sub: str = "", conf: float = 0.9) -> ClassificationResult:
    return ClassificationResult(intent=intent, sub_intent=sub, confidence=conf, method="keyword")


# =============================================================================
# POSITIVE FEEDBACK → NEW EXEMPLAR
# =============================================================================


class TestPositiveFeedback:
    """Test that positive feedback creates learned exemplars."""

    def test_high_rating_creates_exemplar(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="Deploy the staging server",
            classification=_cr("coding", "modify_file", 0.8),
            rating=5,
        )
        assert bank.count() == 1
        ex = bank.get_all()[0]
        assert ex.user_message == "Deploy the staging server"
        assert ex.intent == "coding"
        assert ex.source == "learned"

    def test_rating_4_creates_exemplar(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="Explain the auth flow",
            classification=_cr("question", "code_explanation", 0.85),
            rating=4,
        )
        assert bank.count() == 1

    def test_rating_3_does_not_create(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="Maybe fix something",
            classification=_cr("ambiguous", "needs_clarification", 0.4),
            rating=3,
        )
        assert bank.count() == 0

    def test_low_rating_does_not_create(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="Wrong classification",
            classification=_cr("coding", "fix_bug", 0.9),
            rating=1,
        )
        assert bank.count() == 0

    def test_learned_exemplar_has_correct_metadata(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="Set up the CI pipeline",
            classification=_cr("coding", "create_file", 0.75),
            rating=5,
        )
        ex = bank.get_all()[0]
        assert ex.source == "learned"
        assert ex.confidence <= 1.0
        assert ex.intent == "coding"
        assert ex.sub_intent == "create_file"


# =============================================================================
# NEGATIVE FEEDBACK
# =============================================================================


class TestNegativeFeedback:
    """Test that negative feedback doesn't pollute the bank."""

    def test_rating_1_no_exemplar(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="This was wrong",
            classification=_cr("coding", "fix_bug"),
            rating=1,
        )
        assert bank.count() == 0

    def test_rating_2_no_exemplar(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="Not quite right",
            classification=_cr("question", "debugging"),
            rating=2,
        )
        assert bank.count() == 0


# =============================================================================
# CORRECTION FEEDBACK
# =============================================================================


class TestCorrectionFeedback:
    """Test recording corrected classifications."""

    def test_correction_creates_exemplar_with_corrected_intent(self, bridge, bank):
        bridge.record_correction(
            user_message="Check the logs",
            original=_cr("question", "code_explanation"),
            corrected_intent="coding",
            corrected_sub_intent="debugging",
        )
        assert bank.count() == 1
        ex = bank.get_all()[0]
        assert ex.intent == "coding"
        assert ex.sub_intent == "debugging"
        assert ex.source == "learned"

    def test_correction_overwrites_previous(self, bridge, bank):
        bridge.record_correction(
            user_message="Check the logs",
            original=_cr("question", "code_explanation"),
            corrected_intent="coding",
            corrected_sub_intent="fix_bug",
        )
        bridge.record_correction(
            user_message="Check the logs",
            original=_cr("question", "code_explanation"),
            corrected_intent="coding",
            corrected_sub_intent="debugging",
        )
        # Same message → should be 1 (upsert)
        assert bank.count() == 1
        ex = bank.get_all()[0]
        assert ex.sub_intent == "debugging"


# =============================================================================
# DUPLICATE PREVENTION
# =============================================================================


class TestDuplicatePrevention:
    """Test that the same message isn't added twice."""

    def test_same_message_not_duplicated(self, bridge, bank):
        for _ in range(5):
            bridge.record_classification_feedback(
                user_message="Deploy to production",
                classification=_cr("coding", "modify_file"),
                rating=5,
            )
        assert bank.count() == 1

    def test_different_messages_both_added(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="Deploy to staging",
            classification=_cr("coding", "modify_file"),
            rating=5,
        )
        bridge.record_classification_feedback(
            user_message="Deploy to production",
            classification=_cr("coding", "modify_file"),
            rating=5,
        )
        assert bank.count() == 2


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Edge cases for learning bridge."""

    def test_empty_message_ignored(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="",
            classification=_cr("coding", "fix_bug"),
            rating=5,
        )
        assert bank.count() == 0

    def test_whitespace_message_ignored(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="   ",
            classification=_cr("coding", "fix_bug"),
            rating=5,
        )
        assert bank.count() == 0

    def test_very_long_message_truncated(self, bridge, bank):
        long_msg = "Fix the bug " * 100
        bridge.record_classification_feedback(
            user_message=long_msg,
            classification=_cr("coding", "fix_bug"),
            rating=5,
        )
        assert bank.count() == 1
        ex = bank.get_all()[0]
        assert len(ex.user_message) <= 500

    def test_no_bank_doesnt_crash(self):
        bridge = LearningBridge(exemplar_bank=None)
        bridge.record_classification_feedback(
            user_message="Test",
            classification=_cr("coding", "fix_bug"),
            rating=5,
        )
        # Should not raise

    def test_get_stats(self, bridge, bank):
        bridge.record_classification_feedback(
            user_message="Fix auth.py",
            classification=_cr("coding", "fix_bug"),
            rating=5,
        )
        stats = bridge.get_learning_stats()
        assert stats["total_learned"] >= 0
        assert isinstance(stats, dict)
