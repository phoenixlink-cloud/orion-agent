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
#    See LICENSE-ENTERPRISE.md or contact licensing@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- Three-Tier Memory Engine (v6.4.0)

Orion's competitive moat: a unified, persistent memory system that learns
and evolves with every interaction. No other AI coding tool has this.

THREE TIERS:
    Tier 1: SESSION MEMORY (Working Memory)
        - In-process RAM, not persisted
        - Current request context, deliberation history, quality feedback
        - Duration: seconds to minutes
        - Resets per request

    Tier 2: PROJECT MEMORY (Workspace Memory)
        - Persisted per-project at {workspace}/.orion/project_memory.json
        - File context, decisions, preferences, patterns for THIS project
        - Duration: days to weeks (project lifetime)
        - Promotes high-confidence insights to Tier 3

    Tier 3: INSTITUTIONAL MEMORY (Global Wisdom)
        - Persisted globally at ~/.orion/institutional_memory.db (SQLite)
        - Learned patterns, anti-patterns, user preferences, domain expertise
        - Duration: months to years (forever)
        - Confidence-weighted: only high-scoring outcomes become patterns

MEMORY LIFECYCLE:
    1. Every interaction starts in Tier 1 (session)
    2. Outcomes with user feedback get stored in Tier 2 (project)
    3. High-confidence project patterns get PROMOTED to Tier 3 (institutional)
    4. Tier 3 patterns inform ALL future projects (cross-project learning)

APPROVAL GATE:
    - User feedback (approve/reject/edit) directly scores outcomes
    - Only approved outcomes (rating >= 4/5) create positive patterns
    - Rejected outcomes create anti-patterns (what NOT to do)
    - This creates a human-in-the-loop learning system
"""

import json
import time
import hashlib
import sqlite3
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta, timezone

from orion.core.memory.embeddings import EmbeddingStore


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MemoryEntry:
    """A single memory entry that can exist in any tier."""
    id: str
    content: str
    tier: int  # 1=session, 2=project, 3=institutional
    category: str  # pattern, anti_pattern, preference, decision, insight
    confidence: float  # 0.0 to 1.0
    created_at: str
    last_accessed: str
    access_count: int = 0
    source: str = ""  # what created this memory
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ApprovalGateResult:
    """Result of a user approval gate interaction."""
    task_id: str
    task_description: str
    rating: int  # 1-5
    feedback: str
    approved: bool  # rating >= 4
    timestamp: str
    actions_taken: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    promoted_to_tier3: bool = False


@dataclass
class EvolutionSnapshot:
    """Point-in-time snapshot of Orion's learning state."""
    timestamp: str
    total_interactions: int
    approval_rate: float
    avg_quality_score: float
    patterns_learned: int
    anti_patterns_learned: int
    domains_mastered: int
    tier2_entries: int
    tier3_entries: int
    top_strengths: List[str] = field(default_factory=list)
    top_weaknesses: List[str] = field(default_factory=list)


@dataclass
class MemoryStats:
    """Statistics about the three-tier memory system."""
    tier1_entries: int
    tier2_entries: int
    tier3_entries: int
    total_approvals: int
    total_rejections: int
    approval_rate: float
    avg_quality: float
    patterns_learned: int
    anti_patterns_learned: int
    preferences_stored: int
    domains_with_expertise: int
    oldest_memory: str
    newest_memory: str
    promotions_count: int  # tier2 -> tier3


# =============================================================================
# THREE-TIER MEMORY ENGINE
# =============================================================================

class MemoryEngine:
    """
    Unified Three-Tier Memory Engine.

    This is the single entry point for ALL memory operations in Orion.
    It manages the lifecycle of memories across three tiers and handles
    promotion from session -> project -> institutional.

    Usage:
        engine = MemoryEngine(workspace_path="/path/to/project")

        # Store a memory
        engine.remember("User prefers tabs over spaces", tier=2, category="preference")

        # Recall relevant memories
        memories = engine.recall("format this Python file", max_results=5)

        # Record approval gate result
        engine.record_approval(task_id, rating=5, feedback="Perfect!")

        # Get evolution snapshot
        snapshot = engine.get_evolution_snapshot()
    """

    def __init__(self, workspace_path: str = None):
        self.workspace_path = workspace_path

        # Tier 1: Session memory (RAM)
        self._session: Dict[str, MemoryEntry] = {}
        self._session_start = datetime.now(timezone.utc).isoformat()

        # Tier 2: Project memory (JSON file per project)
        self._project_path = None
        if workspace_path:
            self._project_path = Path(workspace_path) / ".orion" / "memory_engine_project.json"
            self._project_path.parent.mkdir(parents=True, exist_ok=True)
        self._project_cache: Dict[str, MemoryEntry] = {}
        self._load_project_memory()

        # Tier 3: Institutional memory (global SQLite)
        self._db_path = Path.home() / ".orion" / "memory_engine.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        # Embedding store for semantic recall
        self._embedding_store = EmbeddingStore(db_path=str(self._db_path))

    # =========================================================================
    # PUBLIC API: REMEMBER
    # =========================================================================

    def remember(
        self,
        content: str,
        tier: int = 1,
        category: str = "insight",
        confidence: float = 0.6,
        source: str = "",
        metadata: Dict[str, Any] = None,
    ) -> MemoryEntry:
        """
        Store a memory in the specified tier.

        Args:
            content: The memory content
            tier: 1=session, 2=project, 3=institutional
            category: pattern, anti_pattern, preference, decision, insight
            confidence: 0.0 to 1.0
            source: What created this memory
            metadata: Additional context

        Returns:
            The created MemoryEntry
        """
        now = datetime.now(timezone.utc).isoformat()
        entry_id = hashlib.md5(f"{content}:{tier}:{now}".encode()).hexdigest()[:12]

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            tier=tier,
            category=category,
            confidence=confidence,
            created_at=now,
            last_accessed=now,
            access_count=0,
            source=source,
            metadata=metadata or {},
        )

        if tier == 1:
            self._session[entry_id] = entry
        elif tier == 2:
            self._project_cache[entry_id] = entry
            self._save_project_memory()
        elif tier == 3:
            self._store_tier3(entry)
            if self._embedding_store.available:
                self._embedding_store.index_memory(entry.id, entry.content)

        return entry

    # =========================================================================
    # PUBLIC API: RECALL
    # =========================================================================

    def recall(
        self,
        query: str,
        max_results: int = 10,
        min_confidence: float = 0.3,
        tiers: List[int] = None,
        categories: List[str] = None,
    ) -> List[MemoryEntry]:
        """
        Recall memories relevant to a query, searching across tiers.

        Searches all three tiers (or specified tiers) and returns
        results ranked by relevance and confidence.
        """
        tiers = tiers or [1, 2, 3]
        results: List[Tuple[float, MemoryEntry]] = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        # Search Tier 1 (session)
        if 1 in tiers:
            for entry in self._session.values():
                score = self._relevance_score(entry, query_lower, query_words)
                if score > 0 and entry.confidence >= min_confidence:
                    if not categories or entry.category in categories:
                        results.append((score, entry))

        # Search Tier 2 (project)
        if 2 in tiers:
            for entry in self._project_cache.values():
                score = self._relevance_score(entry, query_lower, query_words)
                if score > 0 and entry.confidence >= min_confidence:
                    if not categories or entry.category in categories:
                        results.append((score, entry))

        # Search Tier 3 (institutional)
        if 3 in tiers:
            tier3_entries = self._search_tier3(query_lower, min_confidence, categories)
            for entry in tier3_entries:
                score = self._relevance_score(entry, query_lower, query_words)
                if score > 0:
                    results.append((score, entry))

        # Sort by relevance score descending
        results.sort(key=lambda x: x[0], reverse=True)

        # Update access counts for returned results
        final = []
        for _, entry in results[:max_results]:
            entry.access_count += 1
            entry.last_accessed = datetime.now(timezone.utc).isoformat()
            final.append(entry)

        return final

    def recall_for_prompt(self, query: str, max_tokens: int = 2000, domain: str = None, top_k: int = 10) -> str:
        """
        Recall memories formatted for LLM prompt injection.
        Uses embedding-based semantic search if available, falls back to keyword matching.

        Returns a formatted string ready to include in the system prompt.
        """
        if self._embedding_store.available:
            # Embedding-based search for Tier 3
            results = self._embedding_store.search(query, top_k=top_k, domain=domain)
            tier3_entries = []
            for memory_id, score in results:
                if score > 0.5:
                    entry = self._get_tier3_entry(memory_id)
                    if entry:
                        tier3_entries.append(entry)
            # Also include session + project memories via keyword
            keyword_memories = self.recall(query, max_results=top_k, min_confidence=0.5, tiers=[1, 2])
            # Merge, dedup by id
            seen_ids = {e.id for e in tier3_entries}
            memories = tier3_entries[:]
            for m in keyword_memories:
                if m.id not in seen_ids:
                    memories.append(m)
                    seen_ids.add(m.id)
        else:
            # Fallback to existing keyword search
            memories = self.recall(query, max_results=top_k, min_confidence=0.5)

        # Sort by confidence * access_count (most reliable patterns first)
        memories.sort(key=lambda e: e.confidence * (1 + e.access_count * 0.1), reverse=True)
        memories = memories[:top_k]

        if not memories:
            return ""

        # Increment access counts
        for entry in memories:
            self._increment_access(entry.id)

        lines = [
            "## ORION MEMORY CONTEXT",
            f"(Retrieved {len(memories)} relevant memories from {self._count_tiers(memories)} tiers)\n",
        ]

        for mem in memories:
            tier_label = {1: "Session", 2: "Project", 3: "Global"}[mem.tier]
            conf_label = "HIGH" if mem.confidence >= 0.8 else "MED" if mem.confidence >= 0.5 else "LOW"
            lines.append(f"- [{tier_label}/{conf_label}] {mem.content[:200]}")

        return "\n".join(lines)

    # =========================================================================
    # PUBLIC API: APPROVAL GATE
    # =========================================================================

    def record_approval(
        self,
        task_id: str,
        task_description: str,
        rating: int,
        feedback: str = "",
        actions_taken: List[str] = None,
        files_modified: List[str] = None,
        quality_score: float = 0.0,
    ) -> ApprovalGateResult:
        """
        Record a user approval gate result.

        This is the core of Orion's learning system. Every time a user
        approves or rejects Orion's output, it feeds back into memory.

        Rating scale:
            5 = Excellent (strong positive pattern)
            4 = Good (mild positive pattern)
            3 = Neutral (no learning)
            2 = Poor (mild anti-pattern)
            1 = Bad (strong anti-pattern)
        """
        now = datetime.now(timezone.utc).isoformat()
        approved = rating >= 4

        result = ApprovalGateResult(
            task_id=task_id,
            task_description=task_description,
            rating=rating,
            feedback=feedback,
            approved=approved,
            timestamp=now,
            actions_taken=actions_taken or [],
            files_modified=files_modified or [],
            quality_score=quality_score,
        )

        # Store in Tier 2 (project memory) always
        self.remember(
            content=f"{'APPROVED' if approved else 'REJECTED'} (rating {rating}/5): {task_description[:200]}. {feedback[:200]}",
            tier=2,
            category="pattern" if approved else "anti_pattern",
            confidence=rating / 5.0,
            source="approval_gate",
            metadata={
                "task_id": task_id,
                "rating": rating,
                "feedback": feedback,
                "files": files_modified or [],
                "quality_score": quality_score,
            },
        )

        # Store in Tier 3 (institutional) for strong signals
        if rating >= 4:
            self.remember(
                content=f"SUCCESS PATTERN: {task_description[:150]}. User approved ({rating}/5): {feedback[:150]}",
                tier=3,
                category="pattern",
                confidence=min(1.0, (rating / 5.0) + 0.1),
                source="approval_gate_positive",
                metadata={
                    "task_type": self._classify_task(task_description),
                    "rating": rating,
                    "files": files_modified or [],
                },
            )
            result.promoted_to_tier3 = True

        elif rating <= 2:
            self.remember(
                content=f"ANTI-PATTERN: {task_description[:150]}. User rejected ({rating}/5): {feedback[:150]}",
                tier=3,
                category="anti_pattern",
                confidence=min(1.0, (1 - rating / 5.0) + 0.1),
                source="approval_gate_negative",
                metadata={
                    "task_type": self._classify_task(task_description),
                    "rating": rating,
                    "avoid_reason": feedback[:300],
                },
            )
            result.promoted_to_tier3 = True

        # Record in evolution log
        self._record_evolution_event(result)

        return result

    # =========================================================================
    # PUBLIC API: PROMOTE (Tier 2 -> Tier 3)
    # =========================================================================

    def promote_to_institutional(
        self, entry_id: str, reason: str = ""
    ) -> Optional[MemoryEntry]:
        """
        Promote a Tier 2 (project) memory to Tier 3 (institutional).

        Only memories with confidence >= 0.7 can be promoted.
        """
        if entry_id not in self._project_cache:
            return None

        entry = self._project_cache[entry_id]
        if entry.confidence < 0.7:
            return None

        promoted = self.remember(
            content=entry.content,
            tier=3,
            category=entry.category,
            confidence=entry.confidence,
            source=f"promoted_from_project:{reason}",
            metadata={**entry.metadata, "promoted_from": entry_id},
        )

        return promoted

    def auto_promote(self) -> List[MemoryEntry]:
        """
        Automatically promote high-confidence Tier 2 memories to Tier 3.

        Promotion criteria:
        - Confidence >= 0.8
        - Access count >= 3 (used multiple times)
        - Category is 'pattern' or 'preference'
        """
        promoted = []
        for entry_id, entry in list(self._project_cache.items()):
            if (
                entry.confidence >= 0.8
                and entry.access_count >= 3
                and entry.category in ("pattern", "preference")
            ):
                result = self.promote_to_institutional(entry_id, "auto_promote")
                if result:
                    promoted.append(result)
        return promoted

    # =========================================================================
    # PUBLIC API: EVOLUTION TRACKING
    # =========================================================================

    def get_evolution_snapshot(self) -> EvolutionSnapshot:
        """Get a point-in-time snapshot of Orion's learning state."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM evolution_log")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM evolution_log WHERE approved = 1")
        approvals = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM evolution_log WHERE approved = 0")
        rejections = cursor.fetchone()[0]
        total_rated = approvals + rejections
        approval_rate = approvals / total_rated if total_rated > 0 else 0.0

        cursor.execute("SELECT AVG(quality_score) FROM evolution_log WHERE quality_score > 0")
        avg_q = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'pattern'")
        patterns = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'anti_pattern'")
        anti_patterns = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT json_extract(metadata, '$.task_type')) FROM memories WHERE json_extract(metadata, '$.task_type') IS NOT NULL")
        try:
            domains = cursor.fetchone()[0]
        except Exception:
            domains = 0

        tier3_count = self._count_tier3()
        strengths, weaknesses = self._analyze_trends(cursor)

        conn.close()

        return EvolutionSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_interactions=total,
            approval_rate=round(approval_rate, 3),
            avg_quality_score=round(avg_q, 3),
            patterns_learned=patterns,
            anti_patterns_learned=anti_patterns,
            domains_mastered=domains,
            tier2_entries=len(self._project_cache),
            tier3_entries=tier3_count,
            top_strengths=strengths,
            top_weaknesses=weaknesses,
        )

    def get_evolution_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent evolution events (approval gate history)."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM evolution_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        conn.close()
        return [dict(zip(cols, row)) for row in rows]

    def get_stats(self) -> MemoryStats:
        """Get comprehensive memory statistics."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM memories")
        tier3_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM evolution_log WHERE approved = 1")
        approvals = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM evolution_log WHERE approved = 0")
        rejections = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(quality_score) FROM evolution_log WHERE quality_score > 0")
        avg_q = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'pattern'")
        patterns = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'anti_pattern'")
        anti_patterns = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'preference'")
        prefs = cursor.fetchone()[0]

        cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM memories")
        row = cursor.fetchone()
        oldest = row[0] or ""
        newest = row[1] or ""

        cursor.execute("SELECT COUNT(*) FROM memories WHERE source LIKE 'promoted%'")
        promotions = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT json_extract(metadata, '$.task_type')) FROM memories WHERE json_extract(metadata, '$.task_type') IS NOT NULL")
        try:
            domains = cursor.fetchone()[0]
        except Exception:
            domains = 0

        conn.close()

        total_rated = approvals + rejections
        return MemoryStats(
            tier1_entries=len(self._session),
            tier2_entries=len(self._project_cache),
            tier3_entries=tier3_count,
            total_approvals=approvals,
            total_rejections=rejections,
            approval_rate=approvals / total_rated if total_rated > 0 else 0.0,
            avg_quality=round(avg_q, 3),
            patterns_learned=patterns,
            anti_patterns_learned=anti_patterns,
            preferences_stored=prefs,
            domains_with_expertise=domains,
            oldest_memory=oldest,
            newest_memory=newest,
            promotions_count=promotions,
        )

    # =========================================================================
    # PUBLIC API: CONSOLIDATE
    # =========================================================================

    def consolidate(self) -> Dict[str, int]:
        """
        Consolidate memories: decay old low-confidence entries, merge duplicates.

        Should be run periodically (e.g., on session end).
        """
        decayed = 0
        merged = 0

        # Decay Tier 2 entries older than 30 days with low confidence
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        to_remove = []
        for eid, entry in self._project_cache.items():
            if entry.created_at < cutoff and entry.confidence < 0.5 and entry.access_count < 2:
                to_remove.append(eid)
        for eid in to_remove:
            del self._project_cache[eid]
            decayed += 1
        if to_remove:
            self._save_project_memory()

        # Decay Tier 3 low-confidence entries older than 90 days
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cutoff_90 = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        cursor.execute(
            "DELETE FROM memories WHERE confidence < 0.4 AND created_at < ? AND access_count < 2",
            (cutoff_90,),
        )
        decayed += cursor.rowcount
        conn.commit()
        conn.close()

        return {"decayed": decayed, "merged": merged}

    # =========================================================================
    # PUBLIC API: SESSION LIFECYCLE
    # =========================================================================

    def start_session(self):
        """Start a new session, clearing Tier 1."""
        self._session.clear()
        self._session_start = datetime.now(timezone.utc).isoformat()

    def end_session(self):
        """
        End session: auto-promote valuable session memories to Tier 2,
        run consolidation.
        """
        for entry in list(self._session.values()):
            if entry.confidence >= 0.7 and entry.access_count >= 2:
                self.remember(
                    content=entry.content,
                    tier=2,
                    category=entry.category,
                    confidence=entry.confidence,
                    source="session_promotion",
                    metadata=entry.metadata,
                )

        self.auto_promote()
        self.consolidate()
        self._session.clear()

    # =========================================================================
    # INTERNAL: DATABASE
    # =========================================================================

    def _init_db(self):
        """Initialize SQLite database for Tier 3."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        cursor.execute("""
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evolution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                task_description TEXT,
                rating INTEGER,
                feedback TEXT,
                approved INTEGER,
                timestamp TEXT,
                quality_score REAL,
                actions_taken TEXT DEFAULT '[]',
                files_modified TEXT DEFAULT '[]',
                promoted INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_confidence ON memories(confidence)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_evolution_timestamp ON evolution_log(timestamp)
        """)

        conn.commit()
        conn.close()

    def _store_tier3(self, entry: MemoryEntry):
        """Store a memory in Tier 3 (SQLite)."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO memories 
            (id, content, tier, category, confidence, created_at, last_accessed, access_count, source, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.id,
                entry.content,
                entry.tier,
                entry.category,
                entry.confidence,
                entry.created_at,
                entry.last_accessed,
                entry.access_count,
                entry.source,
                json.dumps(entry.metadata),
            ),
        )
        conn.commit()
        conn.close()

    def _search_tier3(
        self, query_lower: str, min_confidence: float, categories: List[str] = None
    ) -> List[MemoryEntry]:
        """Search Tier 3 memories by keyword matching."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        sql = "SELECT * FROM memories WHERE confidence >= ?"
        params: list = [min_confidence]

        if categories:
            placeholders = ",".join("?" for _ in categories)
            sql += f" AND category IN ({placeholders})"
            params.extend(categories)

        sql += " ORDER BY confidence DESC, access_count DESC LIMIT 50"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        conn.close()

        entries = []
        for row in rows:
            data = dict(zip(cols, row))
            data["metadata"] = json.loads(data.get("metadata", "{}"))
            entries.append(MemoryEntry.from_dict(data))
        return entries

    def _count_tier3(self) -> int:
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memories")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def _record_evolution_event(self, result: ApprovalGateResult):
        """Record an approval gate event in the evolution log."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO evolution_log 
            (task_id, task_description, rating, feedback, approved, timestamp, 
             quality_score, actions_taken, files_modified, promoted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.task_id,
                result.task_description[:500],
                result.rating,
                result.feedback[:500],
                1 if result.approved else 0,
                result.timestamp,
                result.quality_score,
                json.dumps(result.actions_taken[:20]),
                json.dumps(result.files_modified[:20]),
                1 if result.promoted_to_tier3 else 0,
            ),
        )
        conn.commit()
        conn.close()

    def _analyze_trends(self, cursor) -> Tuple[List[str], List[str]]:
        """Analyze recent approval trends for strengths and weaknesses."""
        strengths = []
        weaknesses = []

        try:
            cursor.execute(
                "SELECT task_description, rating FROM evolution_log WHERE rating >= 4 ORDER BY timestamp DESC LIMIT 10"
            )
            for row in cursor.fetchall():
                task_type = self._classify_task(row[0])
                if task_type not in strengths:
                    strengths.append(task_type)

            cursor.execute(
                "SELECT task_description, rating FROM evolution_log WHERE rating <= 2 ORDER BY timestamp DESC LIMIT 10"
            )
            for row in cursor.fetchall():
                task_type = self._classify_task(row[0])
                if task_type not in weaknesses:
                    weaknesses.append(task_type)
        except Exception:
            pass

        return strengths[:5], weaknesses[:5]

    # =========================================================================
    # INTERNAL: PROJECT MEMORY (Tier 2 persistence)
    # =========================================================================

    def _load_project_memory(self):
        """Load Tier 2 memories from disk."""
        if not self._project_path or not self._project_path.exists():
            return
        try:
            data = json.loads(self._project_path.read_text(encoding="utf-8"))
            for entry_data in data.get("memories", []):
                entry = MemoryEntry.from_dict(entry_data)
                self._project_cache[entry.id] = entry
        except Exception:
            pass

    def _save_project_memory(self):
        """Save Tier 2 memories to disk."""
        if not self._project_path:
            return
        data = {
            "version": "7.1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "memories": [e.to_dict() for e in self._project_cache.values()],
        }
        self._project_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # =========================================================================
    # INTERNAL: RELEVANCE SCORING
    # =========================================================================

    def _relevance_score(
        self, entry: MemoryEntry, query_lower: str, query_words: set
    ) -> float:
        """
        Score a memory's relevance to a query.

        Uses keyword overlap + confidence weighting + recency boost.
        """
        content_lower = entry.content.lower()
        content_words = set(content_lower.split())

        # Word overlap
        overlap = len(query_words & content_words)
        if overlap == 0:
            if any(w in content_lower for w in query_words if len(w) > 3):
                overlap = 1
            else:
                return 0.0

        word_score = overlap / max(len(query_words), 1)
        conf_weight = entry.confidence
        tier_weight = {1: 0.6, 2: 0.8, 3: 1.0}[entry.tier]
        cat_boost = 1.2 if entry.category in ("pattern", "preference") else 1.0

        return word_score * conf_weight * tier_weight * cat_boost

    # =========================================================================
    # INTERNAL: TASK CLASSIFICATION
    # =========================================================================

    def _classify_task(self, description: str) -> str:
        """Classify a task description into a category."""
        desc = description.lower()
        if any(w in desc for w in ["fix", "bug", "error", "issue", "broken"]):
            return "bug_fix"
        elif any(w in desc for w in ["add", "create", "implement", "new", "build"]):
            return "feature_add"
        elif any(w in desc for w in ["refactor", "improve", "optimize", "clean"]):
            return "refactor"
        elif any(w in desc for w in ["explain", "what", "how", "why"]):
            return "explanation"
        elif any(w in desc for w in ["test", "testing", "spec"]):
            return "testing"
        elif any(w in desc for w in ["document", "docs", "readme"]):
            return "documentation"
        elif any(w in desc for w in ["deploy", "release", "ci", "cd"]):
            return "devops"
        return "general"

    def _get_tier3_entry(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve a single Tier 3 entry by ID."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return None
            cols = [d[0] for d in cursor.description]
            conn.close()
            data = dict(zip(cols, row))
            data["metadata"] = json.loads(data.get("metadata", "{}"))
            return MemoryEntry.from_dict(data)
        except Exception:
            return None

    def _increment_access(self, memory_id: str):
        """Increment the access count for a memory entry."""
        # Tier 1/2
        if memory_id in self._session:
            self._session[memory_id].access_count += 1
            return
        if memory_id in self._project_cache:
            self._project_cache[memory_id].access_count += 1
            return
        # Tier 3
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), memory_id),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _content_hash_exists(self, content_hash: str) -> bool:
        """Check if a content hash already exists in Tier 3 metadata."""
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE metadata LIKE ?",
                (f'%"content_hash": "{content_hash}"%',),
            ).fetchone()
            conn.close()
            return row[0] > 0
        except Exception:
            return False

    def load_knowledge_pack(self, patterns: list, pack_id: str, pack_version: str) -> int:
        """
        Bulk-insert patterns from a knowledge pack into Tier 3.
        Returns count of patterns inserted.
        """
        inserted = 0
        for pattern in patterns:
            content_hash = hashlib.sha256(pattern["content"].encode()).hexdigest()[:16]
            if self._content_hash_exists(content_hash):
                continue

            now = datetime.now(timezone.utc).isoformat()
            entry = MemoryEntry(
                id=f"kp_{pack_id[:8]}_{inserted:04d}",
                content=pattern["content"],
                tier=3,
                category=pattern.get("category", "pattern"),
                confidence=pattern.get("confidence", 0.9),
                created_at=now,
                last_accessed=now,
                access_count=0,
                source="knowledge_pack",
                metadata={
                    "source": "knowledge_pack",
                    "pack_id": pack_id,
                    "pack_version": pack_version,
                    "domain": pattern.get("domain", "general"),
                    "content_hash": content_hash,
                    **(pattern.get("metadata", {}) if isinstance(pattern.get("metadata"), dict) else {}),
                },
            )
            self._store_tier3(entry)
            if self._embedding_store.available:
                self._embedding_store.index_memory(entry.id, entry.content)
            inserted += 1

        return inserted

    @staticmethod
    def _count_tiers(memories: List[MemoryEntry]) -> int:
        return len(set(m.tier for m in memories))


# =============================================================================
# FACTORY
# =============================================================================

_engine_instance: Optional[MemoryEngine] = None


def get_memory_engine(workspace_path: str = None) -> MemoryEngine:
    """Get or create the global MemoryEngine instance."""
    global _engine_instance
    if _engine_instance is None or (
        workspace_path and _engine_instance.workspace_path != workspace_path
    ):
        _engine_instance = MemoryEngine(workspace_path)
    return _engine_instance
