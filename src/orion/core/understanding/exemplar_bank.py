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
Orion Agent -- Intent Exemplar Bank (v7.6.0)

Stores labeled intent exemplars that the IntentClassifier compares
against via embedding similarity. Replaces regex-based intent
classification with semantic matching.

Part of the Natural Language Architecture (NLA-002, Phase 1B).

Tables:
    intent_exemplars -- user_message → intent mapping with embeddings

Growth model:
    - Ships with ~200 curated exemplars (data/seed/intent_exemplars.json)
    - Grows via feedback: correct classifications become new exemplars
    - Curated exemplars refreshed on upgrade; learned exemplars preserved
"""

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.understanding.exemplar_bank")


@dataclass
class IntentExemplar:
    """A single labeled intent exemplar."""

    id: str
    user_message: str
    intent: str  # conversational, question, coding, compound, ambiguous
    sub_intent: str  # greeting, fix_bug, code_explanation, etc.
    confidence: float  # how clearly this maps to the intent
    source: str  # "curated" or "learned"
    created_at: str


class ExemplarBank:
    """
    Storage and query layer for intent exemplars.

    Provides CRUD operations and seed data loading.
    The IntentClassifier (Phase 1C) will use this bank
    to classify user messages via embedding similarity.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(Path.home() / ".orion" / "exemplar_bank.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create the intent_exemplars table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS intent_exemplars (
                id TEXT PRIMARY KEY,
                user_message TEXT NOT NULL,
                intent TEXT NOT NULL,
                sub_intent TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'curated',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exemplar_intent
            ON intent_exemplars (intent)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exemplar_source
            ON intent_exemplars (source)
        """)
        conn.commit()
        conn.close()

    # =========================================================================
    # ADD
    # =========================================================================

    def add(
        self,
        user_message: str,
        intent: str,
        sub_intent: str = "",
        confidence: float = 1.0,
        source: str = "curated",
    ) -> IntentExemplar:
        """
        Add an intent exemplar. If the exact message already exists, update it.

        Args:
            user_message: The example user message.
            intent: Primary intent category.
            sub_intent: More specific classification.
            confidence: How clearly this maps (0.0–1.0).
            source: "curated" (ships with Orion) or "learned" (from feedback).

        Returns:
            The created or updated IntentExemplar.
        """
        exemplar_id = self._make_id(user_message)
        now = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO intent_exemplars "
            "(id, user_message, intent, sub_intent, confidence, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (exemplar_id, user_message, intent, sub_intent, confidence, source, now),
        )
        conn.commit()
        conn.close()

        return IntentExemplar(
            id=exemplar_id,
            user_message=user_message,
            intent=intent,
            sub_intent=sub_intent,
            confidence=confidence,
            source=source,
            created_at=now,
        )

    # =========================================================================
    # QUERY
    # =========================================================================

    def get_by_intent(self, intent: str, sub_intent: str | None = None) -> list[IntentExemplar]:
        """Get all exemplars matching an intent (and optionally sub-intent)."""
        conn = sqlite3.connect(self.db_path)
        if sub_intent is not None:
            rows = conn.execute(
                "SELECT id, user_message, intent, sub_intent, confidence, source, created_at "
                "FROM intent_exemplars WHERE intent = ? AND sub_intent = ?",
                (intent, sub_intent),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, user_message, intent, sub_intent, confidence, source, created_at "
                "FROM intent_exemplars WHERE intent = ?",
                (intent,),
            ).fetchall()
        conn.close()
        return [self._row_to_exemplar(r) for r in rows]

    def get_all(self) -> list[IntentExemplar]:
        """Get all exemplars."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT id, user_message, intent, sub_intent, confidence, source, created_at "
            "FROM intent_exemplars ORDER BY intent, sub_intent"
        ).fetchall()
        conn.close()
        return [self._row_to_exemplar(r) for r in rows]

    def get_intents(self) -> list[str]:
        """Get all distinct intent categories."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT DISTINCT intent FROM intent_exemplars ORDER BY intent"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def get_sub_intents(self, intent: str) -> list[str]:
        """Get all distinct sub-intents for a given intent."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT DISTINCT sub_intent FROM intent_exemplars "
            "WHERE intent = ? AND sub_intent != '' ORDER BY sub_intent",
            (intent,),
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def count(self) -> int:
        """Total number of exemplars."""
        conn = sqlite3.connect(self.db_path)
        result = conn.execute("SELECT COUNT(*) FROM intent_exemplars").fetchone()[0]
        conn.close()
        return result

    # =========================================================================
    # DELETE
    # =========================================================================

    def delete(self, exemplar_id: str) -> None:
        """Delete a single exemplar by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM intent_exemplars WHERE id = ?", (exemplar_id,))
        conn.commit()
        conn.close()

    def delete_by_source(self, source: str) -> None:
        """Delete all exemplars from a given source (e.g. 'curated' for refresh)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM intent_exemplars WHERE source = ?", (source,))
        conn.commit()
        conn.close()

    # =========================================================================
    # SEED DATA
    # =========================================================================

    def load_seed_data(self, seed_file_path: str) -> int:
        """
        Load exemplars from a JSON seed file.

        Replaces all 'curated' exemplars with the seed data.
        Preserves 'learned' exemplars (user feedback).

        Args:
            seed_file_path: Path to JSON file with exemplar array.

        Returns:
            Number of exemplars loaded.
        """
        try:
            data = json.loads(Path(seed_file_path).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load seed data from %s: %s", seed_file_path, e)
            return 0

        if not isinstance(data, list):
            logger.warning("Seed data must be a JSON array")
            return 0

        # Remove old curated exemplars (preserve learned)
        self.delete_by_source("curated")

        loaded = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            msg = item.get("user_message", "")
            intent = item.get("intent", "")
            if not msg or not intent:
                continue
            self.add(
                user_message=msg,
                intent=intent,
                sub_intent=item.get("sub_intent", ""),
                confidence=item.get("confidence", 1.0),
                source="curated",
            )
            loaded += 1

        logger.info("Loaded %d curated exemplars from %s", loaded, seed_file_path)
        return loaded

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get bank statistics: total, by intent, by source."""
        conn = sqlite3.connect(self.db_path)

        total = conn.execute("SELECT COUNT(*) FROM intent_exemplars").fetchone()[0]

        intent_rows = conn.execute(
            "SELECT intent, COUNT(*) FROM intent_exemplars GROUP BY intent"
        ).fetchall()
        intents = {r[0]: r[1] for r in intent_rows}

        source_rows = conn.execute(
            "SELECT source, COUNT(*) FROM intent_exemplars GROUP BY source"
        ).fetchall()
        sources = {r[0]: r[1] for r in source_rows}

        conn.close()
        return {"total": total, "intents": intents, "sources": sources}

    # =========================================================================
    # INTERNAL
    # =========================================================================

    @staticmethod
    def _make_id(user_message: str) -> str:
        """Deterministic ID from message content (dedup key)."""
        return hashlib.md5(user_message.strip().lower().encode()).hexdigest()[:12]

    @staticmethod
    def _row_to_exemplar(row: tuple) -> IntentExemplar:
        """Convert a database row to an IntentExemplar."""
        return IntentExemplar(
            id=row[0],
            user_message=row[1],
            intent=row[2],
            sub_intent=row[3],
            confidence=row[4],
            source=row[5],
            created_at=row[6],
        )
