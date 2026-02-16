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
Orion Agent -- Tier 3: Institutional Memory (v7.4.0)

Long-term wisdom that persists across ALL projects, ALL time.
This is what makes Orion truly intelligent over years, not just days.

Migrated from Orion_MVP/memory/institutional_memory.py.

Location: ~/.orion/institutional_memory.db (GLOBAL, not project-specific)
Duration: Years -- lifetime
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class LearnedPattern:
    """A pattern learned from experience."""

    id: str
    description: str
    context: str
    example: str
    success_count: int
    last_used: str
    confidence: float


@dataclass
class LearnedAntiPattern:
    """An anti-pattern learned from failures."""

    id: str
    description: str
    context: str
    failure_reason: str
    occurrence_count: int
    last_seen: str
    severity: float


@dataclass
class UserPreference:
    """A learned user preference."""

    key: str
    value: str
    confidence: float
    last_updated: str


class InstitutionalMemory:
    """
    Layer 3: Institutional Memory (Years – Lifetime)

    Long-term memory that persists across ALL projects.
    Accumulated wisdom -- patterns, anti-patterns, user preferences,
    domain expertise -- stored globally at ~/.orion/institutional_memory.db.
    """

    def __init__(self):
        self.db_path = Path.home() / ".orion" / "institutional_memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._seed_if_empty()

    # ── Schema ───────────────────────────────────────────────────────────

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id TEXT PRIMARY KEY,
                description TEXT,
                context TEXT,
                example TEXT,
                success_count INTEGER DEFAULT 1,
                last_used TEXT,
                confidence REAL DEFAULT 0.6
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS learned_anti_patterns (
                id TEXT PRIMARY KEY,
                description TEXT,
                context TEXT,
                failure_reason TEXT,
                occurrence_count INTEGER DEFAULT 1,
                last_seen TEXT,
                severity REAL DEFAULT 0.5
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT,
                confidence REAL DEFAULT 0.5,
                last_updated TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS domain_expertise (
                domain TEXT PRIMARY KEY,
                project_count INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0.0,
                learned_patterns TEXT,
                last_project TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS execution_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                action_type TEXT,
                context TEXT,
                outcome TEXT,
                quality_score REAL,
                user_feedback TEXT,
                domain TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS confirmed_feedback (
                id TEXT PRIMARY KEY,
                principle TEXT,
                original_feedback TEXT,
                rating INTEGER,
                scope_file TEXT,
                scope_project TEXT,
                scope_domain TEXT,
                task_description TEXT,
                confirmed_at TEXT,
                times_applied INTEGER DEFAULT 0,
                is_positive INTEGER DEFAULT 1
            )
        """)

        conn.commit()
        conn.close()

    def _seed_if_empty(self):
        """Load foundational knowledge if seed patterns are missing.

        The seed function checks each pattern by ID before inserting,
        so it's safe to call on every init — only truly new seeds get added.
        """
        conn = sqlite3.connect(self.db_path)
        # Check if any seed pattern exists (they all start with 'p-')
        has_seeds = conn.execute(
            "SELECT COUNT(*) FROM learned_patterns WHERE id LIKE 'p-%'"
        ).fetchone()[0]
        conn.close()
        if has_seeds == 0:
            try:
                from orion.core.memory.seed_knowledge import seed_institutional_memory

                seed_institutional_memory(self)
            except Exception:
                pass  # Seed data is optional — don't break init if missing

    # ── Learning from outcomes ───────────────────────────────────────────

    def learn_from_outcome(
        self,
        action_type: str,
        context: str,
        outcome: str,
        quality_score: float,
        user_feedback: str | None = None,
        domain: str | None = None,
    ):
        """Learn from an execution outcome. High quality -> pattern, low -> anti-pattern."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        ts = datetime.now(timezone.utc).isoformat()

        c.execute(
            "INSERT INTO execution_history "
            "(timestamp, action_type, context, outcome, quality_score, user_feedback, domain) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, action_type, context[:1000], outcome[:1000], quality_score, user_feedback, domain),
        )

        if quality_score >= 0.9:
            self._reinforce_pattern(c, action_type, context, outcome, ts)
        if quality_score < 0.5:
            self._reinforce_anti_pattern(c, action_type, context, outcome, ts)
        if domain:
            self._update_domain(c, domain, quality_score, ts)

        conn.commit()
        conn.close()

    def _reinforce_pattern(self, c, action_type, context, outcome, ts):
        pid = hashlib.md5(f"{action_type}:{context[:100]}".encode()).hexdigest()[:12]
        row = c.execute(
            "SELECT success_count, confidence FROM learned_patterns WHERE id = ?", (pid,)
        ).fetchone()
        if row:
            c.execute(
                "UPDATE learned_patterns SET success_count = success_count + 1, last_used = ?, confidence = ? WHERE id = ?",
                (ts, min(1.0, row[1] + 0.05), pid),
            )
        else:
            c.execute(
                "INSERT INTO learned_patterns (id, description, context, example, success_count, last_used, confidence) "
                "VALUES (?, ?, ?, ?, 1, ?, 0.6)",
                (pid, f"Successful {action_type}", context[:500], outcome[:1000], ts),
            )

    def _reinforce_anti_pattern(self, c, action_type, context, outcome, ts):
        aid = hashlib.md5(f"anti:{action_type}:{context[:100]}".encode()).hexdigest()[:12]
        row = c.execute(
            "SELECT occurrence_count, severity FROM learned_anti_patterns WHERE id = ?", (aid,)
        ).fetchone()
        if row:
            c.execute(
                "UPDATE learned_anti_patterns SET occurrence_count = occurrence_count + 1, last_seen = ?, severity = ? WHERE id = ?",
                (ts, min(1.0, row[1] + 0.1), aid),
            )
        else:
            c.execute(
                "INSERT INTO learned_anti_patterns (id, description, context, failure_reason, occurrence_count, last_seen, severity) "
                "VALUES (?, ?, ?, ?, 1, ?, 0.5)",
                (aid, f"Failed {action_type}", context[:500], outcome[:1000], ts),
            )

    def _update_domain(self, c, domain, quality_score, ts):
        row = c.execute(
            "SELECT project_count, success_rate FROM domain_expertise WHERE domain = ?", (domain,)
        ).fetchone()
        if row:
            new_count = row[0] + 1
            new_rate = ((row[1] * row[0]) + quality_score) / new_count
            c.execute(
                "UPDATE domain_expertise SET project_count = ?, success_rate = ?, last_project = ? WHERE domain = ?",
                (new_count, new_rate, ts, domain),
            )
        else:
            c.execute(
                "INSERT INTO domain_expertise (domain, project_count, success_rate, learned_patterns, last_project) "
                "VALUES (?, 1, ?, '[]', ?)",
                (domain, quality_score, ts),
            )

    # ── User preferences ─────────────────────────────────────────────────

    def record_user_preference(self, key: str, value: str, confidence: float = 0.7):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO user_preferences (key, value, confidence, last_updated) VALUES (?, ?, ?, ?)",
            (key, value, confidence, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    def get_user_preferences(self) -> dict[str, str]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT key, value FROM user_preferences WHERE confidence >= 0.5"
        ).fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}

    # ── Query patterns ───────────────────────────────────────────────────

    def get_learned_patterns(self, min_confidence: float = 0.7) -> list[LearnedPattern]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT id, description, context, example, success_count, last_used, confidence "
            "FROM learned_patterns WHERE confidence >= ? ORDER BY success_count DESC LIMIT 20",
            (min_confidence,),
        ).fetchall()
        conn.close()
        return [LearnedPattern(*r) for r in rows]

    def get_learned_anti_patterns(self, min_severity: float = 0.6) -> list[LearnedAntiPattern]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT id, description, context, failure_reason, occurrence_count, last_seen, severity "
            "FROM learned_anti_patterns WHERE severity >= ? ORDER BY occurrence_count DESC LIMIT 20",
            (min_severity,),
        ).fetchall()
        conn.close()
        return [LearnedAntiPattern(*r) for r in rows]

    def get_domain_expertise(self, domain: str) -> dict[str, Any] | None:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM domain_expertise WHERE domain = ?", (domain,)).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "domain": row[0],
            "project_count": row[1],
            "success_rate": row[2],
            "learned_patterns": json.loads(row[3]) if row[3] else [],
            "last_project": row[4],
        }

    # ── Wisdom retrieval (main query interface) ──────────────────────────

    def get_relevant_wisdom(self, task: str, domain: str | None = None) -> dict[str, Any]:
        """Retrieve accumulated wisdom relevant to current task."""
        patterns = self.get_learned_patterns(min_confidence=0.7)
        anti_patterns = self.get_learned_anti_patterns(min_severity=0.6)
        return {
            "learned_patterns": [
                {"description": p.description, "context": p.context, "confidence": p.confidence}
                for p in patterns[:10]
            ],
            "learned_anti_patterns": [
                {
                    "description": ap.description,
                    "reason": ap.failure_reason,
                    "severity": ap.severity,
                }
                for ap in anti_patterns[:10]
            ],
            "user_preferences": self.get_user_preferences(),
            "domain_expertise": self.get_domain_expertise(domain) if domain else None,
        }

    # ── Confirmed feedback ───────────────────────────────────────────────

    def store_confirmed_feedback(
        self,
        principle: str,
        original_feedback: str,
        rating: int,
        task_description: str,
        scope_file: str | None = None,
        scope_project: str | None = None,
        scope_domain: str | None = None,
    ) -> str:
        """Store user-confirmed feedback with full scope context."""
        scope_key = f"{scope_file or ''}:{scope_project or ''}:{scope_domain or ''}"
        fid = hashlib.md5(f"{principle}:{scope_key}".encode()).hexdigest()[:12]
        is_positive = 1 if rating >= 4 else 0

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO confirmed_feedback "
            "(id, principle, original_feedback, rating, scope_file, scope_project, "
            "scope_domain, task_description, confirmed_at, is_positive) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fid,
                principle,
                original_feedback,
                rating,
                scope_file,
                scope_project,
                scope_domain,
                task_description[:500],
                datetime.now(timezone.utc).isoformat(),
                is_positive,
            ),
        )
        conn.commit()
        conn.close()
        return fid

    def get_relevant_feedback(
        self,
        file_path: str | None = None,
        project_path: str | None = None,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get confirmed feedback relevant to the current context, sorted by relevance."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT * FROM confirmed_feedback").fetchall()
        conn.close()

        results = []
        for row in rows:
            fb = {
                "id": row[0],
                "principle": row[1],
                "original_feedback": row[2],
                "rating": row[3],
                "scope_file": row[4],
                "scope_project": row[5],
                "scope_domain": row[6],
                "task_description": row[7],
                "is_positive": row[9] == 1,
                "relevance": 0.0,
            }
            if file_path and fb["scope_file"] and file_path.endswith(fb["scope_file"]):
                fb["relevance"] = 1.0
            elif project_path and fb["scope_project"] and project_path == fb["scope_project"]:
                fb["relevance"] = 0.7
            elif domain and fb["scope_domain"] and domain == fb["scope_domain"]:
                fb["relevance"] = 0.4
            if fb["relevance"] > 0:
                results.append(fb)

        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:10]

    # ── Statistics ────────────────────────────────────────────────────────

    def get_statistics(self) -> dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        pattern_count = c.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()[0]
        anti_count = c.execute("SELECT COUNT(*) FROM learned_anti_patterns").fetchone()[0]
        exec_count = c.execute("SELECT COUNT(*) FROM execution_history").fetchone()[0]
        avg_quality = (
            c.execute("SELECT AVG(quality_score) FROM execution_history").fetchone()[0] or 0.0
        )
        domain_count = c.execute("SELECT COUNT(*) FROM domain_expertise").fetchone()[0]
        pref_count = c.execute("SELECT COUNT(*) FROM user_preferences").fetchone()[0]
        conn.close()
        return {
            "learned_patterns": pattern_count,
            "learned_anti_patterns": anti_count,
            "total_executions": exec_count,
            "average_quality": round(avg_quality, 3),
            "domains_with_expertise": domain_count,
            "user_preferences": pref_count,
        }

    def clear(self):
        """Clear all institutional memory (use with caution)."""
        conn = sqlite3.connect(self.db_path)
        for table in (
            "learned_patterns",
            "learned_anti_patterns",
            "user_preferences",
            "domain_expertise",
            "execution_history",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()
