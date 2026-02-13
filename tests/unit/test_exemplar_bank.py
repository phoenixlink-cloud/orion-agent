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
"""Tests for ExemplarBank -- Orion's intent exemplar storage and query layer."""

import json
import tempfile
from pathlib import Path

import pytest

from orion.core.understanding.exemplar_bank import ExemplarBank, IntentExemplar

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def db_path(tmp_path):
    """Provide a temporary SQLite DB path."""
    return str(tmp_path / "test_exemplars.db")


@pytest.fixture
def bank(db_path):
    """Provide a fresh ExemplarBank."""
    return ExemplarBank(db_path=db_path)


@pytest.fixture
def populated_bank(bank):
    """Provide an ExemplarBank with a handful of exemplars."""
    bank.add("Hi there!", "conversational", "greeting", source="test")
    bank.add("Hello Orion", "conversational", "greeting", source="test")
    bank.add("Goodbye", "conversational", "farewell", source="test")
    bank.add("Fix the bug in auth.py", "coding", "fix_bug", source="test")
    bank.add("Create a login page", "coding", "create_file", source="test")
    bank.add("What does this function do?", "question", "code_explanation", source="test")
    bank.add("How are you?", "conversational", "greeting", source="test")
    return bank


# =============================================================================
# SCHEMA & INITIALIZATION
# =============================================================================


class TestExemplarBankInit:
    """Test database initialization and schema creation."""

    def test_creates_db(self, db_path):
        bank = ExemplarBank(db_path=db_path)
        assert Path(db_path).exists()

    def test_empty_bank_count(self, bank):
        assert bank.count() == 0

    def test_table_created(self, bank):
        import sqlite3

        conn = sqlite3.connect(bank.db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='intent_exemplars'"
        ).fetchall()
        conn.close()
        assert len(tables) == 1


# =============================================================================
# ADD EXEMPLARS
# =============================================================================


class TestAddExemplars:
    """Test adding exemplars to the bank."""

    def test_add_single(self, bank):
        ex = bank.add("Hello!", "conversational", "greeting")
        assert ex.user_message == "Hello!"
        assert ex.intent == "conversational"
        assert ex.sub_intent == "greeting"
        assert ex.id is not None
        assert bank.count() == 1

    def test_add_multiple(self, bank):
        bank.add("Hi", "conversational", "greeting")
        bank.add("Fix bug", "coding", "fix_bug")
        bank.add("What is X?", "question", "general")
        assert bank.count() == 3

    def test_add_with_source(self, bank):
        ex = bank.add("test", "coding", "test", source="curated")
        assert ex.source == "curated"

    def test_add_with_confidence(self, bank):
        ex = bank.add("test", "coding", "test", confidence=0.95)
        assert ex.confidence == 0.95

    def test_default_confidence(self, bank):
        ex = bank.add("test", "coding", "test")
        assert ex.confidence == 1.0

    def test_default_source(self, bank):
        ex = bank.add("test", "coding", "test")
        assert ex.source == "curated"

    def test_duplicate_message_updates(self, bank):
        bank.add("Hello!", "conversational", "greeting")
        bank.add("Hello!", "conversational", "greeting")
        # Should not create duplicates
        assert bank.count() == 1


# =============================================================================
# QUERY EXEMPLARS
# =============================================================================


class TestQueryExemplars:
    """Test querying exemplars by intent."""

    def test_get_by_intent(self, populated_bank):
        results = populated_bank.get_by_intent("conversational")
        assert len(results) == 4  # Hi there, Hello Orion, Goodbye, How are you

    def test_get_by_intent_and_sub_intent(self, populated_bank):
        results = populated_bank.get_by_intent("conversational", sub_intent="farewell")
        assert len(results) == 1
        assert results[0].user_message == "Goodbye"

    def test_get_by_intent_empty(self, populated_bank):
        results = populated_bank.get_by_intent("nonexistent")
        assert results == []

    def test_get_all(self, populated_bank):
        results = populated_bank.get_all()
        assert len(results) == 7

    def test_get_all_empty_bank(self, bank):
        assert bank.get_all() == []

    def test_get_intents(self, populated_bank):
        intents = populated_bank.get_intents()
        assert set(intents) == {"conversational", "coding", "question"}

    def test_get_sub_intents(self, populated_bank):
        subs = populated_bank.get_sub_intents("conversational")
        assert set(subs) == {"greeting", "farewell"}


# =============================================================================
# DELETE EXEMPLARS
# =============================================================================


class TestDeleteExemplars:
    """Test removing exemplars."""

    def test_delete_by_id(self, populated_bank):
        exemplars = populated_bank.get_all()
        first_id = exemplars[0].id
        populated_bank.delete(first_id)
        assert populated_bank.count() == 6

    def test_delete_nonexistent(self, bank):
        # Should not raise
        bank.delete("nonexistent_id")

    def test_delete_by_source(self, bank):
        bank.add("a", "conversational", "greeting", source="curated")
        bank.add("b", "conversational", "greeting", source="learned")
        bank.add("c", "coding", "fix", source="curated")
        bank.delete_by_source("curated")
        assert bank.count() == 1
        remaining = bank.get_all()
        assert remaining[0].source == "learned"


# =============================================================================
# SEED DATA LOADING
# =============================================================================


class TestSeedLoading:
    """Test loading seed data from JSON."""

    def test_load_from_json(self, bank, tmp_path):
        seed_data = [
            {"user_message": "Hi!", "intent": "conversational", "sub_intent": "greeting"},
            {"user_message": "Fix bug", "intent": "coding", "sub_intent": "fix_bug"},
            {"user_message": "What is X?", "intent": "question", "sub_intent": "general"},
        ]
        seed_file = tmp_path / "seed.json"
        seed_file.write_text(json.dumps(seed_data))

        loaded = bank.load_seed_data(str(seed_file))
        assert loaded == 3
        assert bank.count() == 3

    def test_load_seed_preserves_learned(self, bank, tmp_path):
        # Add a learned exemplar
        bank.add("my custom phrase", "coding", "custom", source="learned")

        # Load seed data
        seed_data = [
            {"user_message": "Hi!", "intent": "conversational", "sub_intent": "greeting"},
        ]
        seed_file = tmp_path / "seed.json"
        seed_file.write_text(json.dumps(seed_data))

        bank.load_seed_data(str(seed_file))
        assert bank.count() == 2  # 1 learned + 1 curated

    def test_load_seed_refreshes_curated(self, bank, tmp_path):
        # Add curated data
        bank.add("Old greeting", "conversational", "greeting", source="curated")

        # Load new seed — should replace curated
        seed_data = [
            {"user_message": "New greeting", "intent": "conversational", "sub_intent": "greeting"},
        ]
        seed_file = tmp_path / "seed.json"
        seed_file.write_text(json.dumps(seed_data))

        bank.load_seed_data(str(seed_file))
        all_ex = bank.get_all()
        messages = [e.user_message for e in all_ex]
        assert "New greeting" in messages
        assert "Old greeting" not in messages

    def test_load_seed_invalid_file(self, bank):
        loaded = bank.load_seed_data("/nonexistent/path.json")
        assert loaded == 0

    def test_load_seed_invalid_json(self, bank, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json{{{")
        loaded = bank.load_seed_data(str(bad_file))
        assert loaded == 0


# =============================================================================
# STATISTICS
# =============================================================================


class TestStatistics:
    """Test exemplar bank statistics."""

    def test_stats_empty(self, bank):
        stats = bank.get_stats()
        assert stats["total"] == 0
        assert stats["intents"] == {}
        assert stats["sources"] == {}

    def test_stats_populated(self, populated_bank):
        stats = populated_bank.get_stats()
        assert stats["total"] == 7
        assert stats["intents"]["conversational"] == 4
        assert stats["intents"]["coding"] == 2
        assert stats["intents"]["question"] == 1
        assert stats["sources"]["test"] == 7
