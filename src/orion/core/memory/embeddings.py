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
Orion Agent -- Embedding-Based Semantic Recall (v7.1.0)

Replaces keyword-based memory recall with embedding-based semantic search.
Critical for scaling beyond ~50 patterns in Tier 3.

Uses sentence-transformers for local embedding generation (no API calls).
Falls back gracefully to keyword matching if sentence-transformers is not installed.

USAGE:
    from orion.core.memory.embeddings import EmbeddingStore
    store = EmbeddingStore()
    store.index_memory("mem_001", "Python type hints improve code readability")
    results = store.search("how to type annotate functions", top_k=5)
"""

import json
import time
import sqlite3
import logging
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger("orion.memory.embeddings")


class EmbeddingStore:
    """
    Manages embeddings for Tier 3 memory entries.
    Uses sentence-transformers for local embedding generation.
    Stores embeddings alongside memory entries in SQLite.

    Falls back to keyword matching if sentence-transformers
    is not installed (graceful degradation).
    """

    # Use a small, fast model -- runs locally, no API calls
    DEFAULT_MODEL = "all-MiniLM-L6-v2"  # 80MB, very fast, good quality

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Path.home() / ".orion" / "memory_engine.db")
        self._model = None
        self._np = None
        self._available = self._check_availability()
        if self._available:
            self._ensure_embedding_table()

    @property
    def available(self) -> bool:
        """Whether embedding-based search is available."""
        return self._available

    def _check_availability(self) -> bool:
        """Check if sentence-transformers is installed."""
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401
            import numpy  # noqa: F401
            self._np = numpy
            return True
        except ImportError:
            logger.info("sentence-transformers not installed -- using keyword fallback")
            return False

    def _ensure_embedding_table(self):
        """Add embeddings table to the existing memory database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    memory_id TEXT PRIMARY KEY,
                    embedding BLOB,
                    model_name TEXT,
                    created_at REAL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to create embeddings table: %s", e)
            self._available = False

    def _load_model(self):
        """Lazy-load the sentence-transformers model on first use."""
        if self._model is None and self._available:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.DEFAULT_MODEL)
                logger.info("Loaded embedding model: %s", self.DEFAULT_MODEL)
            except Exception as e:
                logger.warning("Failed to load embedding model: %s", e)
                self._available = False

    def embed_text(self, text: str):
        """
        Generate an embedding vector for the given text.

        Returns:
            numpy.ndarray or None if not available.
        """
        if not self._available:
            return None
        self._load_model()
        if self._model is None:
            return None
        try:
            return self._model.encode(text, convert_to_numpy=True)
        except Exception as e:
            logger.warning("Failed to embed text: %s", e)
            return None

    def index_memory(self, memory_id: str, content: str):
        """
        Generate embedding for content and store in the embeddings table.
        Call this whenever a new Tier 3 entry is created.
        """
        if not self._available:
            return
        embedding = self.embed_text(content)
        if embedding is None:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO memory_embeddings (memory_id, embedding, model_name, created_at) "
                "VALUES (?, ?, ?, ?)",
                (memory_id, embedding.tobytes(), self.DEFAULT_MODEL, time.time()),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to index memory %s: %s", memory_id, e)

    def search(self, query: str, top_k: int = 10, domain: str = None) -> List[Tuple[str, float]]:
        """
        Search for the most semantically similar memory entries.

        Args:
            query: The search query text.
            top_k: Number of top results to return.
            domain: Optional domain filter (filters by metadata in memories table).

        Returns:
            List of (memory_id, similarity_score) tuples, sorted by similarity descending.
        """
        if not self._available:
            return []
        query_embedding = self.embed_text(query)
        if query_embedding is None:
            return []

        try:
            conn = sqlite3.connect(self.db_path)

            if domain:
                # Join with memories table to filter by domain in metadata
                rows = conn.execute(
                    "SELECT e.memory_id, e.embedding FROM memory_embeddings e "
                    "JOIN memories m ON e.memory_id = m.id "
                    "WHERE m.metadata LIKE ?",
                    (f'%"domain": "{domain}"%',),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT memory_id, embedding FROM memory_embeddings"
                ).fetchall()

            conn.close()

            if not rows:
                return []

            # Batch cosine similarity with numpy
            np = self._np
            ids = [r[0] for r in rows]
            embeddings = np.array([
                np.frombuffer(r[1], dtype=np.float32) for r in rows
            ])

            # Normalize for cosine similarity
            query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)
            emb_norms = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10)
            similarities = emb_norms @ query_norm

            # Get top_k indices
            if len(similarities) <= top_k:
                top_indices = np.argsort(similarities)[::-1]
            else:
                top_indices = np.argpartition(similarities, -top_k)[-top_k:]
                top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]

            results = [(ids[i], float(similarities[i])) for i in top_indices]
            return results

        except Exception as e:
            logger.warning("Embedding search failed: %s", e)
            return []

    def reindex_all(self) -> int:
        """
        Index all Tier 3 entries that don't have embeddings yet.
        Use this for initial setup or after importing a knowledge pack.

        Returns:
            Count of entries indexed.
        """
        if not self._available:
            return 0

        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                "SELECT m.id, m.content FROM memories m "
                "LEFT JOIN memory_embeddings e ON m.id = e.memory_id "
                "WHERE e.memory_id IS NULL"
            ).fetchall()
            conn.close()

            indexed = 0
            for memory_id, content in rows:
                self.index_memory(memory_id, content)
                indexed += 1

            logger.info("Reindexed %d memory entries", indexed)
            return indexed

        except Exception as e:
            logger.warning("Reindex failed: %s", e)
            return 0

    def similarity(self, text_a: str, text_b: str) -> float:
        """
        Compute cosine similarity between two texts.
        Used by BenchmarkEngine for concept coverage checking.

        Returns:
            Float between -1.0 and 1.0 (typically 0.0-1.0 for text).
            Returns 0.0 if embeddings are not available.
        """
        if not self._available:
            return 0.0
        emb_a = self.embed_text(text_a)
        emb_b = self.embed_text(text_b)
        if emb_a is None or emb_b is None:
            return 0.0

        np = self._np
        norm_a = np.linalg.norm(emb_a)
        norm_b = np.linalg.norm(emb_b)
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        return float(np.dot(emb_a, emb_b) / (norm_a * norm_b))

    def delete_embedding(self, memory_id: str):
        """Remove an embedding for a memory entry."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM memory_embeddings WHERE memory_id = ?", (memory_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to delete embedding %s: %s", memory_id, e)

    def count(self) -> int:
        """Return the number of indexed embeddings."""
        try:
            conn = sqlite3.connect(self.db_path)
            count = conn.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()[0]
            conn.close()
            return count
        except Exception:
            return 0
