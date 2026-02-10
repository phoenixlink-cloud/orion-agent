"""
Tests for Orion's Embedding Store (v7.1.0)

Tests embedding generation, indexing, search, similarity,
domain filtering, reindexing, and graceful fallback when
sentence-transformers is not installed.
"""

import sqlite3
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from orion.core.memory.embeddings import EmbeddingStore


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database for testing."""
    db_path = str(tmp_path / "test_memory.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            tier INTEGER DEFAULT 3,
            category TEXT DEFAULT 'insight',
            confidence REAL DEFAULT 0.6,
            created_at TEXT,
            last_accessed TEXT,
            access_count INTEGER DEFAULT 0,
            source TEXT DEFAULT '',
            metadata TEXT DEFAULT '{}'
        )
    """)
    conn.commit()
    conn.close()
    return db_path


class TestEmbeddingStoreAvailability:
    """Test graceful degradation when sentence-transformers is unavailable."""

    def test_fallback_without_sentence_transformers(self, tmp_db):
        """Mock import failure, verify keyword fallback."""
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            store = EmbeddingStore.__new__(EmbeddingStore)
            store.db_path = tmp_db
            store._model = None
            store._np = None
            store._available = False

            assert store.available is False
            assert store.embed_text("test") is None
            assert store.search("test") == []
            assert store.similarity("a", "b") == 0.0
            assert store.reindex_all() == 0

    def test_check_availability_true(self, tmp_db):
        """If sentence-transformers is installed, available should be True."""
        try:
            import sentence_transformers  # noqa: F401
            import numpy  # noqa: F401
            store = EmbeddingStore(db_path=tmp_db)
            assert store.available is True
        except ImportError:
            pytest.skip("sentence-transformers not installed")

    def test_check_availability_false(self, tmp_db):
        """If sentence-transformers import fails, available should be False."""
        with patch("orion.core.memory.embeddings.EmbeddingStore._check_availability", return_value=False):
            store = EmbeddingStore(db_path=tmp_db)
            assert store.available is False


class TestEmbeddingStoreWithModel:
    """Tests that require sentence-transformers to be installed."""

    @pytest.fixture(autouse=True)
    def check_st(self):
        try:
            import sentence_transformers  # noqa: F401
            import numpy  # noqa: F401
        except ImportError:
            pytest.skip("sentence-transformers not installed")

    def test_embed_text(self, tmp_db):
        """Generate embedding, verify shape and type."""
        import numpy as np
        store = EmbeddingStore(db_path=tmp_db)
        embedding = store.embed_text("Python type hints improve code quality")
        assert embedding is not None
        assert isinstance(embedding, np.ndarray)
        assert len(embedding.shape) == 1
        assert embedding.shape[0] > 0

    def test_index_and_search(self, tmp_db):
        """Index entries, search query, verify top result is most relevant."""
        store = EmbeddingStore(db_path=tmp_db)

        # Insert test memories into the memories table
        conn = sqlite3.connect(tmp_db)
        entries = [
            ("mem_001", "Python type hints improve code readability and catch bugs early", '{"domain": "python"}'),
            ("mem_002", "Docker containers provide isolated environments for applications", '{"domain": "devops"}'),
            ("mem_003", "SQL databases use indexes for fast lookups", '{"domain": "databases"}'),
            ("mem_004", "Machine learning models need training data", '{"domain": "ml"}'),
            ("mem_005", "Type annotations in Python help IDEs provide better autocomplete", '{"domain": "python"}'),
        ]
        for mid, content, meta in entries:
            conn.execute(
                "INSERT INTO memories (id, content, metadata) VALUES (?, ?, ?)",
                (mid, content, meta),
            )
        conn.commit()
        conn.close()

        # Index all
        for mid, content, _ in entries:
            store.index_memory(mid, content)

        # Search for type hints
        results = store.search("type annotations in Python", top_k=3)
        assert len(results) > 0
        # Top result should be python-related
        top_id = results[0][0]
        assert top_id in ("mem_001", "mem_005")

    def test_search_with_domain_filter(self, tmp_db):
        """Index mixed domains, verify filter works."""
        store = EmbeddingStore(db_path=tmp_db)

        conn = sqlite3.connect(tmp_db)
        entries = [
            ("mem_010", "Python decorators simplify code reuse", '{"domain": "python"}'),
            ("mem_011", "Kubernetes orchestrates container deployments", '{"domain": "devops"}'),
            ("mem_012", "Python generators are memory efficient", '{"domain": "python"}'),
        ]
        for mid, content, meta in entries:
            conn.execute(
                "INSERT INTO memories (id, content, metadata) VALUES (?, ?, ?)",
                (mid, content, meta),
            )
        conn.commit()
        conn.close()

        for mid, content, _ in entries:
            store.index_memory(mid, content)

        # Search with domain filter
        results = store.search("code patterns", top_k=5, domain="python")
        result_ids = [r[0] for r in results]
        # Should not include devops entry
        assert "mem_011" not in result_ids

    def test_similarity_identical(self, tmp_db):
        """Same text should have similarity ~1.0."""
        store = EmbeddingStore(db_path=tmp_db)
        text = "Python is a great programming language"
        sim = store.similarity(text, text)
        assert sim > 0.99

    def test_similarity_unrelated(self, tmp_db):
        """Unrelated texts should have low similarity."""
        store = EmbeddingStore(db_path=tmp_db)
        sim = store.similarity(
            "Python decorators for function wrapping",
            "Chocolate cake recipe with vanilla frosting",
        )
        assert sim < 0.3

    def test_reindex_all(self, tmp_db):
        """Add entries without embeddings, reindex, verify all indexed."""
        store = EmbeddingStore(db_path=tmp_db)

        conn = sqlite3.connect(tmp_db)
        for i in range(5):
            conn.execute(
                "INSERT INTO memories (id, content) VALUES (?, ?)",
                (f"reindex_{i}", f"Test memory entry number {i} about topic {i}"),
            )
        conn.commit()
        conn.close()

        # No embeddings yet
        assert store.count() == 0

        # Reindex
        indexed = store.reindex_all()
        assert indexed == 5
        assert store.count() == 5

    def test_delete_embedding(self, tmp_db):
        """Delete an embedding and verify it's gone."""
        store = EmbeddingStore(db_path=tmp_db)
        store.index_memory("del_001", "Test content for deletion")
        assert store.count() >= 1

        store.delete_embedding("del_001")
        # Verify it's deleted from the embeddings table
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings WHERE memory_id = ?",
            ("del_001",),
        ).fetchone()
        conn.close()
        assert row[0] == 0
