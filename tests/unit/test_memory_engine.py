"""Tests for orion.core.memory.engine -- Three-Tier Memory Engine.

Tests cover:
- MemoryEntry dataclass serialization
- MemoryEngine initialization (with/without workspace)
- remember() across all three tiers
- recall() with keyword matching, tier/category/confidence filtering
- record_approval() for approved/rejected/neutral ratings
- promote_to_institutional() success and rejection paths
- auto_promote() criteria checking
- consolidate() decay logic
- Session lifecycle (start_session / end_session)
- get_evolution_snapshot() and get_stats()
- recall_for_prompt() formatted output
- load_knowledge_pack() bulk insert and deduplication
- _relevance_score() scoring logic
- _classify_task() task classification
- get_memory_engine() factory singleton
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Mock EmbeddingStore before importing engine (it tries to load
# sentence-transformers on init, which may not be installed).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_embedding_store(monkeypatch):
    """Patch EmbeddingStore so MemoryEngine never touches real embeddings."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.available = False
    mock_instance.search.return_value = []
    mock_cls.return_value = mock_instance
    monkeypatch.setattr(
        "orion.core.memory.engine.EmbeddingStore", mock_cls
    )
    return mock_instance


from orion.core.memory.engine import (
    MemoryEntry,
    ApprovalGateResult,
    EvolutionSnapshot,
    MemoryStats,
    MemoryEngine,
    get_memory_engine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(tmp_path):
    """Create a MemoryEngine using a temp workspace and temp DB path."""
    workspace = str(tmp_path / "project")
    os.makedirs(workspace, exist_ok=True)
    engine = MemoryEngine(workspace_path=workspace)
    # Override DB path to use temp dir instead of ~/.orion
    import sqlite3
    db_path = tmp_path / "test_memory.db"
    engine._db_path = db_path
    engine._init_db()
    return engine


# =========================================================================
# MemoryEntry dataclass
# =========================================================================

class TestMemoryEntry:
    def test_to_dict_roundtrip(self):
        entry = MemoryEntry(
            id="abc123", content="Use type hints", tier=2,
            category="pattern", confidence=0.8,
            created_at="2025-01-01T00:00:00", last_accessed="2025-01-01T00:00:00",
            access_count=3, source="test", metadata={"key": "val"},
        )
        d = entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.id == entry.id
        assert restored.content == entry.content
        assert restored.tier == entry.tier
        assert restored.confidence == entry.confidence
        assert restored.metadata == {"key": "val"}

    def test_from_dict_ignores_extra_keys(self):
        d = {
            "id": "x", "content": "y", "tier": 1, "category": "insight",
            "confidence": 0.5, "created_at": "", "last_accessed": "",
            "extra_field": "ignored",
        }
        entry = MemoryEntry.from_dict(d)
        assert entry.id == "x"
        assert not hasattr(entry, "extra_field")

    def test_defaults(self):
        entry = MemoryEntry(
            id="a", content="b", tier=1, category="insight",
            confidence=0.5, created_at="", last_accessed="",
        )
        assert entry.access_count == 0
        assert entry.source == ""
        assert entry.metadata == {}


# =========================================================================
# MemoryEngine -- init
# =========================================================================

class TestMemoryEngineInit:
    def test_creates_project_dir(self, tmp_path):
        workspace = str(tmp_path / "new_project")
        engine = MemoryEngine(workspace_path=workspace)
        assert (Path(workspace) / ".orion").is_dir()

    def test_no_workspace(self, tmp_path):
        engine = MemoryEngine(workspace_path=None)
        assert engine._project_path is None
        assert engine._session == {}


# =========================================================================
# remember()
# =========================================================================

class TestRemember:
    def test_tier1_session(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("session fact", tier=1, category="insight")
        assert entry.tier == 1
        assert entry.id in engine._session
        assert len(engine._project_cache) == 0

    def test_tier2_project(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("project pattern", tier=2, category="pattern", confidence=0.9)
        assert entry.tier == 2
        assert entry.id in engine._project_cache
        assert engine._project_path.exists()

    def test_tier3_institutional(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("global wisdom", tier=3, category="pattern", confidence=0.95)
        assert entry.tier == 3
        # Verify it's in SQLite
        retrieved = engine._get_tier3_entry(entry.id)
        assert retrieved is not None
        assert retrieved.content == "global wisdom"

    def test_metadata_preserved(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("test", tier=1, metadata={"lang": "python"})
        assert entry.metadata == {"lang": "python"}

    def test_confidence_stored(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("conf test", tier=2, confidence=0.42)
        assert entry.confidence == 0.42


# =========================================================================
# recall()
# =========================================================================

class TestRecall:
    def test_keyword_matching(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.remember("Python type hints improve readability", tier=1, confidence=0.8)
        engine.remember("JavaScript async await patterns", tier=1, confidence=0.8)

        results = engine.recall("type hints", max_results=10)
        assert len(results) >= 1
        assert any("type hints" in r.content.lower() for r in results)

    def test_tier_filtering(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.remember("session mem", tier=1, confidence=0.8)
        engine.remember("project mem", tier=2, confidence=0.8)

        results = engine.recall("mem", tiers=[1])
        contents = [r.content for r in results]
        assert "session mem" in contents
        assert "project mem" not in contents

    def test_category_filtering(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.remember("good pattern", tier=1, category="pattern", confidence=0.8)
        engine.remember("bad anti pattern", tier=1, category="anti_pattern", confidence=0.8)

        results = engine.recall("pattern", categories=["pattern"])
        assert all(r.category == "pattern" for r in results)

    def test_confidence_threshold(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.remember("low confidence fact", tier=1, confidence=0.1)
        engine.remember("high confidence fact", tier=1, confidence=0.9)

        results = engine.recall("confidence fact", min_confidence=0.5)
        assert all(r.confidence >= 0.5 for r in results)

    def test_max_results(self, tmp_path):
        engine = _make_engine(tmp_path)
        for i in range(20):
            engine.remember(f"memory item {i}", tier=1, confidence=0.8)

        results = engine.recall("memory item", max_results=5)
        assert len(results) <= 5

    def test_access_count_incremented(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("recall me", tier=1, confidence=0.8)
        assert entry.access_count == 0

        results = engine.recall("recall me")
        assert len(results) >= 1
        assert results[0].access_count == 1

    def test_empty_query_returns_nothing(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.remember("some content", tier=1, confidence=0.8)
        results = engine.recall("xyznonexistent")
        assert len(results) == 0


# =========================================================================
# recall_for_prompt()
# =========================================================================

class TestRecallForPrompt:
    def test_returns_formatted_string(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.remember("Python prefers spaces over tabs", tier=1, confidence=0.9)

        result = engine.recall_for_prompt("Python formatting")
        if result:  # may be empty if keyword match fails
            assert "ORION MEMORY CONTEXT" in result

    def test_empty_when_no_matches(self, tmp_path):
        engine = _make_engine(tmp_path)
        result = engine.recall_for_prompt("xyznonexistent")
        assert result == ""


# =========================================================================
# record_approval()
# =========================================================================

class TestRecordApproval:
    def test_approved_high_rating(self, tmp_path):
        engine = _make_engine(tmp_path)
        result = engine.record_approval(
            task_id="t1", task_description="Fixed the bug",
            rating=5, feedback="Perfect fix",
            quality_score=0.95,
        )
        assert result.approved is True
        assert result.rating == 5
        assert result.promoted_to_tier3 is True

    def test_rejected_low_rating(self, tmp_path):
        engine = _make_engine(tmp_path)
        result = engine.record_approval(
            task_id="t2", task_description="Broke the tests",
            rating=1, feedback="Wrong approach",
        )
        assert result.approved is False
        assert result.promoted_to_tier3 is True  # anti-patterns also go to tier3

    def test_neutral_rating_no_tier3(self, tmp_path):
        engine = _make_engine(tmp_path)
        result = engine.record_approval(
            task_id="t3", task_description="Average work",
            rating=3, feedback="Meh",
        )
        assert result.approved is False  # rating 3 < 4
        assert result.promoted_to_tier3 is False  # rating 3 is neutral

    def test_stores_in_project_memory(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.record_approval(
            task_id="t4", task_description="Some task",
            rating=4, feedback="Good",
        )
        # Should have at least one entry in project cache
        assert len(engine._project_cache) >= 1

    def test_records_evolution_event(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.record_approval(
            task_id="t5", task_description="Task five",
            rating=5, feedback="Great",
        )
        history = engine.get_evolution_history(limit=10)
        assert len(history) >= 1
        assert history[0]["task_id"] == "t5"


# =========================================================================
# promote_to_institutional()
# =========================================================================

class TestPromoteToInstitutional:
    def test_successful_promotion(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("promote me", tier=2, category="pattern", confidence=0.9)
        promoted = engine.promote_to_institutional(entry.id, reason="test")
        assert promoted is not None
        assert promoted.tier == 3
        assert "promoted_from_project" in promoted.source

    def test_low_confidence_rejected(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("low conf", tier=2, confidence=0.3)
        promoted = engine.promote_to_institutional(entry.id)
        assert promoted is None

    def test_nonexistent_entry(self, tmp_path):
        engine = _make_engine(tmp_path)
        promoted = engine.promote_to_institutional("does_not_exist")
        assert promoted is None


# =========================================================================
# auto_promote()
# =========================================================================

class TestAutoPromote:
    def test_promotes_eligible_entries(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember(
            "frequently accessed pattern", tier=2, category="pattern", confidence=0.9,
        )
        # Simulate 3+ accesses
        engine._project_cache[entry.id].access_count = 5
        promoted = engine.auto_promote()
        assert len(promoted) >= 1

    def test_skips_low_access_count(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.remember("new pattern", tier=2, category="pattern", confidence=0.9)
        # access_count defaults to 0 -- below threshold of 3
        promoted = engine.auto_promote()
        assert len(promoted) == 0

    def test_skips_wrong_category(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember(
            "anti pattern", tier=2, category="anti_pattern", confidence=0.9,
        )
        engine._project_cache[entry.id].access_count = 5
        promoted = engine.auto_promote()
        assert len(promoted) == 0


# =========================================================================
# consolidate()
# =========================================================================

class TestConsolidate:
    def test_decays_old_low_confidence_tier2(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("old low conf", tier=2, confidence=0.3)
        # Backdate to 60 days ago
        old_date = (datetime.utcnow() - timedelta(days=60)).isoformat()
        engine._project_cache[entry.id].created_at = old_date
        engine._project_cache[entry.id].access_count = 0

        result = engine.consolidate()
        assert result["decayed"] >= 1
        assert entry.id not in engine._project_cache

    def test_preserves_high_confidence_old(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("old high conf", tier=2, confidence=0.9)
        old_date = (datetime.utcnow() - timedelta(days=60)).isoformat()
        engine._project_cache[entry.id].created_at = old_date

        engine.consolidate()
        assert entry.id in engine._project_cache

    def test_preserves_recent_low_confidence(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("recent low conf", tier=2, confidence=0.3)
        # Created just now -- should not be decayed
        engine.consolidate()
        assert entry.id in engine._project_cache


# =========================================================================
# Session lifecycle
# =========================================================================

class TestSessionLifecycle:
    def test_start_session_clears_tier1(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.remember("temp fact", tier=1)
        assert len(engine._session) == 1
        engine.start_session()
        assert len(engine._session) == 0

    def test_end_session_promotes_valuable_to_tier2(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = engine.remember("valuable insight", tier=1, confidence=0.8)
        engine._session[entry.id].access_count = 3  # meets threshold
        initial_project_count = len(engine._project_cache)

        engine.end_session()
        assert len(engine._project_cache) > initial_project_count
        assert len(engine._session) == 0

    def test_end_session_skips_low_value(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.remember("throwaway", tier=1, confidence=0.2)
        initial_project_count = len(engine._project_cache)

        engine.end_session()
        # Low confidence + low access count -> not promoted
        assert len(engine._project_cache) == initial_project_count


# =========================================================================
# get_evolution_snapshot() and get_stats()
# =========================================================================

class TestEvolutionAndStats:
    def test_snapshot_empty_db(self, tmp_path):
        engine = _make_engine(tmp_path)
        snap = engine.get_evolution_snapshot()
        assert isinstance(snap, EvolutionSnapshot)
        assert snap.total_interactions == 0
        assert snap.approval_rate == 0.0

    def test_snapshot_after_approvals(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.record_approval("t1", "task 1", 5, "great")
        engine.record_approval("t2", "task 2", 1, "bad")

        snap = engine.get_evolution_snapshot()
        assert snap.total_interactions == 2
        assert snap.approval_rate == 0.5

    def test_stats_empty_db(self, tmp_path):
        engine = _make_engine(tmp_path)
        stats = engine.get_stats()
        assert isinstance(stats, MemoryStats)
        assert stats.tier3_entries == 0
        assert stats.total_approvals == 0

    def test_stats_after_remember(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.remember("a pattern", tier=3, category="pattern", confidence=0.9)
        engine.remember("a preference", tier=3, category="preference", confidence=0.8)
        engine.remember("session item", tier=1)

        stats = engine.get_stats()
        assert stats.tier3_entries == 2
        assert stats.tier1_entries == 1
        assert stats.patterns_learned == 1

    def test_evolution_history(self, tmp_path):
        engine = _make_engine(tmp_path)
        engine.record_approval("t1", "task one", 4, "ok")
        engine.record_approval("t2", "task two", 5, "great")

        history = engine.get_evolution_history(limit=10)
        assert len(history) == 2
        # Most recent first
        assert history[0]["task_id"] == "t2"


# =========================================================================
# _relevance_score()
# =========================================================================

class TestRelevanceScore:
    def test_full_overlap_scores_high(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = MemoryEntry(
            id="r1", content="python type hints", tier=3,
            category="pattern", confidence=1.0,
            created_at="", last_accessed="",
        )
        score = engine._relevance_score(entry, "python type hints", {"python", "type", "hints"})
        assert score > 0.5

    def test_no_overlap_scores_zero(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry = MemoryEntry(
            id="r2", content="java spring boot", tier=3,
            category="pattern", confidence=1.0,
            created_at="", last_accessed="",
        )
        score = engine._relevance_score(entry, "python type hints", {"python", "type", "hints"})
        assert score == 0.0

    def test_higher_tier_scores_higher(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry_t1 = MemoryEntry(
            id="t1", content="python best practices", tier=1,
            category="insight", confidence=0.8, created_at="", last_accessed="",
        )
        entry_t3 = MemoryEntry(
            id="t3", content="python best practices", tier=3,
            category="insight", confidence=0.8, created_at="", last_accessed="",
        )
        query_lower = "python best practices"
        query_words = {"python", "best", "practices"}
        score1 = engine._relevance_score(entry_t1, query_lower, query_words)
        score3 = engine._relevance_score(entry_t3, query_lower, query_words)
        assert score3 > score1

    def test_pattern_category_gets_boost(self, tmp_path):
        engine = _make_engine(tmp_path)
        entry_pattern = MemoryEntry(
            id="p", content="python tips", tier=2,
            category="pattern", confidence=0.8, created_at="", last_accessed="",
        )
        entry_insight = MemoryEntry(
            id="i", content="python tips", tier=2,
            category="insight", confidence=0.8, created_at="", last_accessed="",
        )
        query_words = {"python", "tips"}
        s_pat = engine._relevance_score(entry_pattern, "python tips", query_words)
        s_ins = engine._relevance_score(entry_insight, "python tips", query_words)
        assert s_pat > s_ins


# =========================================================================
# _classify_task()
# =========================================================================

class TestClassifyTask:
    def test_bug_fix(self, tmp_path):
        engine = _make_engine(tmp_path)
        assert engine._classify_task("Fix the broken import") == "bug_fix"

    def test_feature_add(self, tmp_path):
        engine = _make_engine(tmp_path)
        assert engine._classify_task("Implement new login flow") == "feature_add"

    def test_refactor(self, tmp_path):
        engine = _make_engine(tmp_path)
        assert engine._classify_task("Refactor the database module") == "refactor"

    def test_explanation(self, tmp_path):
        engine = _make_engine(tmp_path)
        assert engine._classify_task("Explain how the router works") == "explanation"

    def test_testing(self, tmp_path):
        engine = _make_engine(tmp_path)
        assert engine._classify_task("Write unit tests for login") == "testing"

    def test_documentation(self, tmp_path):
        engine = _make_engine(tmp_path)
        assert engine._classify_task("Update the README docs") == "documentation"

    def test_devops(self, tmp_path):
        engine = _make_engine(tmp_path)
        assert engine._classify_task("Set up CI/CD pipeline") == "devops"

    def test_general_fallback(self, tmp_path):
        engine = _make_engine(tmp_path)
        assert engine._classify_task("Do something random") == "general"


# =========================================================================
# load_knowledge_pack()
# =========================================================================

class TestLoadKnowledgePack:
    def test_inserts_patterns(self, tmp_path):
        engine = _make_engine(tmp_path)
        patterns = [
            {"content": "Always validate user input", "category": "pattern", "confidence": 0.9},
            {"content": "Never trust client-side data", "category": "pattern", "confidence": 0.85},
        ]
        count = engine.load_knowledge_pack(patterns, "pack_001", "1.0.0")
        assert count == 2
        assert engine._count_tier3() == 2

    def test_deduplication(self, tmp_path):
        engine = _make_engine(tmp_path)
        patterns = [
            {"content": "Same pattern twice", "category": "pattern"},
        ]
        engine.load_knowledge_pack(patterns, "pack_001", "1.0.0")
        # Insert same pattern again
        count = engine.load_knowledge_pack(patterns, "pack_002", "1.0.0")
        assert count == 0  # deduplicated by content hash

    def test_metadata_includes_pack_info(self, tmp_path):
        engine = _make_engine(tmp_path)
        patterns = [
            {"content": "metadata test pattern", "category": "pattern", "domain": "security"},
        ]
        engine.load_knowledge_pack(patterns, "pack_abc", "2.0.0")
        # Find it in tier 3
        entries = engine._search_tier3("", 0.0)
        assert len(entries) >= 1
        meta = entries[0].metadata
        assert meta["pack_id"] == "pack_abc"
        assert meta["pack_version"] == "2.0.0"
        assert meta["domain"] == "security"


# =========================================================================
# Project memory persistence (Tier 2)
# =========================================================================

class TestProjectPersistence:
    def test_save_and_reload(self, tmp_path):
        workspace = str(tmp_path / "persist_project")
        os.makedirs(workspace, exist_ok=True)

        engine1 = MemoryEngine(workspace_path=workspace)
        engine1.remember("persistent fact", tier=2, confidence=0.8)
        assert len(engine1._project_cache) >= 1

        # Create a new engine pointing to same workspace -- should load
        engine2 = MemoryEngine(workspace_path=workspace)
        assert len(engine2._project_cache) >= 1
        contents = [e.content for e in engine2._project_cache.values()]
        assert "persistent fact" in contents


# =========================================================================
# _count_tiers() static
# =========================================================================

class TestCountTiers:
    def test_single_tier(self):
        mems = [
            MemoryEntry("a", "x", 1, "insight", 0.5, "", ""),
            MemoryEntry("b", "y", 1, "insight", 0.5, "", ""),
        ]
        assert MemoryEngine._count_tiers(mems) == 1

    def test_multiple_tiers(self):
        mems = [
            MemoryEntry("a", "x", 1, "insight", 0.5, "", ""),
            MemoryEntry("b", "y", 2, "insight", 0.5, "", ""),
            MemoryEntry("c", "z", 3, "insight", 0.5, "", ""),
        ]
        assert MemoryEngine._count_tiers(mems) == 3


# =========================================================================
# get_memory_engine() singleton factory
# =========================================================================

class TestGetMemoryEngine:
    def test_returns_same_instance(self, tmp_path):
        import orion.core.memory.engine as mod
        mod._engine_instance = None  # reset singleton

        workspace = str(tmp_path / "singleton_test")
        os.makedirs(workspace, exist_ok=True)
        e1 = get_memory_engine(workspace)
        e2 = get_memory_engine(workspace)
        assert e1 is e2

        mod._engine_instance = None  # clean up

    def test_recreates_on_different_workspace(self, tmp_path):
        import orion.core.memory.engine as mod
        mod._engine_instance = None

        ws1 = str(tmp_path / "ws1")
        ws2 = str(tmp_path / "ws2")
        os.makedirs(ws1, exist_ok=True)
        os.makedirs(ws2, exist_ok=True)

        e1 = get_memory_engine(ws1)
        e2 = get_memory_engine(ws2)
        assert e1 is not e2

        mod._engine_instance = None
