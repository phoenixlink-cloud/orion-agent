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
Orion Agent -- Continuous Learning & Evolution Engine (v6.4.0)

Orion's self-improvement system. Tracks performance over time,
identifies strengths and weaknesses, and generates actionable
improvement recommendations.

WHAT THIS DOES:
    1. Tracks every interaction outcome (quality score, user rating, task type)
    2. Computes rolling performance metrics (approval rate, quality trends)
    3. Identifies areas where Orion is strong vs weak
    4. Generates self-improvement recommendations
    5. Provides an "evolution timeline" showing how Orion has grown
"""

import json
import time
import sqlite3
import statistics
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta, timezone


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PerformanceMetrics:
    """Rolling performance metrics for a time window."""
    window_start: str
    window_end: str
    total_tasks: int
    approved_count: int
    rejected_count: int
    neutral_count: int
    approval_rate: float
    avg_quality_score: float
    avg_rating: float
    task_type_breakdown: Dict[str, int] = field(default_factory=dict)
    quality_trend: str = "stable"  # improving, stable, declining


@dataclass
class StrengthWeakness:
    """An identified strength or weakness."""
    area: str
    score: float  # 0.0 to 1.0
    evidence_count: int
    description: str
    is_strength: bool
    recommendation: str = ""


@dataclass
class ImprovementRecommendation:
    """A self-generated improvement recommendation."""
    id: str
    priority: str  # critical, high, medium, low
    area: str
    title: str
    description: str
    evidence: str
    suggested_action: str
    created_at: str


@dataclass
class EvolutionMilestone:
    """A milestone in Orion's evolution."""
    timestamp: str
    milestone_type: str  # approval_rate, pattern_count, quality_score
    title: str
    description: str
    value: float
    previous_value: float


# =============================================================================
# EVOLUTION ENGINE
# =============================================================================

class EvolutionEngine:
    """
    Continuous Learning & Evolution Engine.

    Tracks Orion's performance over time and generates self-improvement
    recommendations. Integrates with the Three-Tier Memory Engine.

    Usage:
        engine = EvolutionEngine()
        engine.record_outcome(task_type="bug_fix", quality=0.85, rating=4)
        metrics = engine.get_metrics(days=30)
        recs = engine.get_recommendations()
        timeline = engine.get_timeline()
    """

    def __init__(self):
        self._db_path = Path.home() / ".orion" / "evolution_engine.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # =========================================================================
    # PUBLIC API: RECORD OUTCOMES
    # =========================================================================

    def record_outcome(
        self,
        task_type: str,
        quality_score: float,
        rating: int = 0,
        feedback: str = "",
        task_description: str = "",
        files_modified: List[str] = None,
        iteration_count: int = 1,
        model_used: str = "",
        workspace: str = "",
    ) -> Dict[str, Any]:
        """Record a task outcome for evolution tracking."""
        now = datetime.now(timezone.utc).isoformat()
        approved = rating >= 4 if rating > 0 else None

        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO outcomes 
            (timestamp, task_type, quality_score, rating, feedback, 
             task_description, files_modified, iteration_count, model_used,
             workspace, approved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now, task_type, quality_score, rating, feedback[:500],
            task_description[:500], json.dumps(files_modified or []),
            iteration_count, model_used, workspace,
            1 if approved is True else (0 if approved is False else -1),
        ))

        outcome_id = cursor.lastrowid
        conn.commit()

        milestones = self._check_milestones(conn)
        conn.close()

        return {
            "outcome_id": outcome_id,
            "milestones": [asdict(m) for m in milestones],
        }

    # =========================================================================
    # PUBLIC API: PERFORMANCE METRICS
    # =========================================================================

    def get_metrics(self, days: int = 30) -> PerformanceMetrics:
        """Get rolling performance metrics for the last N days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM outcomes WHERE timestamp >= ?", (cutoff,)
        )
        total = cursor.fetchone()[0]

        if total == 0:
            conn.close()
            return PerformanceMetrics(
                window_start=cutoff,
                window_end=datetime.now(timezone.utc).isoformat(),
                total_tasks=0, approved_count=0, rejected_count=0,
                neutral_count=0, approval_rate=0.0,
                avg_quality_score=0.0, avg_rating=0.0,
            )

        cursor.execute(
            "SELECT COUNT(*) FROM outcomes WHERE timestamp >= ? AND approved = 1", (cutoff,)
        )
        approved = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM outcomes WHERE timestamp >= ? AND approved = 0", (cutoff,)
        )
        rejected = cursor.fetchone()[0]

        neutral = total - approved - rejected

        cursor.execute(
            "SELECT AVG(quality_score) FROM outcomes WHERE timestamp >= ? AND quality_score > 0", (cutoff,)
        )
        avg_q = cursor.fetchone()[0] or 0.0

        cursor.execute(
            "SELECT AVG(rating) FROM outcomes WHERE timestamp >= ? AND rating > 0", (cutoff,)
        )
        avg_r = cursor.fetchone()[0] or 0.0

        cursor.execute(
            "SELECT task_type, COUNT(*) FROM outcomes WHERE timestamp >= ? GROUP BY task_type", (cutoff,)
        )
        breakdown = {row[0]: row[1] for row in cursor.fetchall()}

        trend = self._compute_trend(cursor, cutoff)
        rated_total = approved + rejected
        conn.close()

        return PerformanceMetrics(
            window_start=cutoff,
            window_end=datetime.now(timezone.utc).isoformat(),
            total_tasks=total,
            approved_count=approved,
            rejected_count=rejected,
            neutral_count=neutral,
            approval_rate=round(approved / rated_total if rated_total > 0 else 0.0, 3),
            avg_quality_score=round(avg_q, 3),
            avg_rating=round(avg_r, 2),
            task_type_breakdown=breakdown,
            quality_trend=trend,
        )

    def get_metrics_by_task_type(self, days: int = 30) -> Dict[str, PerformanceMetrics]:
        """Get performance metrics broken down by task type."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT DISTINCT task_type FROM outcomes WHERE timestamp >= ?", (cutoff,)
        )
        task_types = [row[0] for row in cursor.fetchall()]
        conn.close()

        results = {}
        for tt in task_types:
            results[tt] = self._get_metrics_for_type(tt, cutoff)
        return results

    # =========================================================================
    # PUBLIC API: STRENGTHS & WEAKNESSES
    # =========================================================================

    def analyze_strengths_weaknesses(self, days: int = 60) -> List[StrengthWeakness]:
        """Analyze recent performance to identify strengths and weaknesses."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        results = []

        cursor.execute("""
            SELECT task_type, 
                   COUNT(*) as cnt,
                   AVG(quality_score) as avg_q,
                   AVG(CASE WHEN rating > 0 THEN rating ELSE NULL END) as avg_r,
                   SUM(CASE WHEN approved = 1 THEN 1 ELSE 0 END) as approvals,
                   SUM(CASE WHEN approved = 0 THEN 1 ELSE 0 END) as rejections
            FROM outcomes 
            WHERE timestamp >= ?
            GROUP BY task_type
            HAVING cnt >= 3
        """, (cutoff,))

        for row in cursor.fetchall():
            task_type, cnt, avg_q, avg_r, approvals, rejections = row
            avg_q = avg_q or 0.0
            avg_r = avg_r or 0.0
            rated = approvals + rejections
            approval_rate = approvals / rated if rated > 0 else 0.5

            score = (avg_q * 0.4 + (avg_r / 5.0 if avg_r else 0.5) * 0.3 + approval_rate * 0.3)
            is_strength = score >= 0.7

            if is_strength:
                desc = f"Strong at {task_type} tasks: {approval_rate:.0%} approval rate, avg quality {avg_q:.2f}"
                rec = f"Continue current approach for {task_type} tasks"
            else:
                desc = f"Weak at {task_type} tasks: {approval_rate:.0%} approval rate, avg quality {avg_q:.2f}"
                rec = f"Focus on improving {task_type} tasks -- review anti-patterns and user feedback"

            results.append(StrengthWeakness(
                area=task_type, score=round(score, 3), evidence_count=cnt,
                description=desc, is_strength=is_strength, recommendation=rec,
            ))

        cursor.execute("""
            SELECT AVG(iteration_count) FROM outcomes WHERE timestamp >= ?
        """, (cutoff,))
        avg_iterations = cursor.fetchone()[0] or 1.0

        if avg_iterations <= 1.2:
            results.append(StrengthWeakness(
                area="efficiency", score=0.9, evidence_count=0,
                description=f"Highly efficient: avg {avg_iterations:.1f} iterations per task",
                is_strength=True, recommendation="Quality gates are well calibrated",
            ))
        elif avg_iterations >= 2.5:
            results.append(StrengthWeakness(
                area="efficiency", score=0.3, evidence_count=0,
                description=f"Inefficient: avg {avg_iterations:.1f} iterations per task",
                is_strength=False,
                recommendation="Quality threshold may be too high, or prompts need improvement",
            ))

        conn.close()
        results.sort(key=lambda x: (x.is_strength, x.score))
        return results

    # =========================================================================
    # PUBLIC API: IMPROVEMENT RECOMMENDATIONS
    # =========================================================================

    def get_recommendations(self, days: int = 30) -> List[ImprovementRecommendation]:
        """Generate self-improvement recommendations based on recent performance."""
        metrics = self.get_metrics(days)
        sw = self.analyze_strengths_weaknesses(days)
        recs: List[ImprovementRecommendation] = []
        now = datetime.now(timezone.utc).isoformat()

        if metrics.total_tasks >= 5 and metrics.approval_rate < 0.6:
            recs.append(ImprovementRecommendation(
                id="low_approval", priority="critical", area="approval_rate",
                title="Low Approval Rate",
                description=f"Only {metrics.approval_rate:.0%} of tasks approved in last {days} days",
                evidence=f"{metrics.approved_count} approved / {metrics.rejected_count} rejected",
                suggested_action="Review anti-patterns in memory. Focus on understanding user expectations better.",
                created_at=now,
            ))

        if metrics.quality_trend == "declining":
            recs.append(ImprovementRecommendation(
                id="quality_decline", priority="high", area="quality_score",
                title="Quality Score Declining",
                description="Quality scores are trending downward over the analysis window",
                evidence=f"Current avg quality: {metrics.avg_quality_score:.2f}",
                suggested_action="Check if recent model changes or prompt modifications are causing degradation.",
                created_at=now,
            ))

        for item in sw:
            if not item.is_strength and item.evidence_count >= 3:
                recs.append(ImprovementRecommendation(
                    id=f"weak_{item.area}",
                    priority="high" if item.score < 0.4 else "medium",
                    area=item.area, title=f"Weak Area: {item.area}",
                    description=item.description,
                    evidence=f"Score: {item.score:.2f} across {item.evidence_count} tasks",
                    suggested_action=item.recommendation, created_at=now,
                ))

        if metrics.total_tasks >= 10 and metrics.neutral_count > metrics.total_tasks * 0.7:
            recs.append(ImprovementRecommendation(
                id="low_feedback", priority="medium", area="feedback",
                title="Not Enough User Feedback",
                description=f"{metrics.neutral_count}/{metrics.total_tasks} tasks have no rating",
                evidence="Without feedback, Orion cannot learn effectively",
                suggested_action="Prompt users for ratings after task completion. More feedback = faster evolution.",
                created_at=now,
            ))

        strengths = [s for s in sw if s.is_strength and s.score >= 0.8]
        if strengths:
            areas = ", ".join(s.area for s in strengths[:3])
            recs.append(ImprovementRecommendation(
                id="celebrate_strengths", priority="low", area="strengths",
                title="Recognized Strengths",
                description=f"Orion excels at: {areas}",
                evidence="High approval rates and quality scores in these areas",
                suggested_action="Leverage these strengths. Consider applying similar approaches to weak areas.",
                created_at=now,
            ))

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        recs.sort(key=lambda r: priority_order.get(r.priority, 4))
        return recs

    # =========================================================================
    # PUBLIC API: EVOLUTION TIMELINE
    # =========================================================================

    def get_timeline(self, limit: int = 20) -> List[EvolutionMilestone]:
        """Get Orion's evolution milestones as a timeline."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM milestones ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        conn.close()

        milestones = []
        for row in rows:
            data = dict(zip(cols, row))
            milestones.append(EvolutionMilestone(
                timestamp=data["timestamp"], milestone_type=data["milestone_type"],
                title=data["title"], description=data["description"],
                value=data["value"], previous_value=data["previous_value"],
            ))
        return milestones

    def get_evolution_summary(self) -> Dict[str, Any]:
        """Get a comprehensive evolution summary for display."""
        metrics_7d = self.get_metrics(7)
        metrics_30d = self.get_metrics(30)
        sw = self.analyze_strengths_weaknesses(30)
        recs = self.get_recommendations(30)
        timeline = self.get_timeline(10)

        strengths = [s for s in sw if s.is_strength]
        weaknesses = [s for s in sw if not s.is_strength]

        return {
            "last_7_days": {
                "tasks": metrics_7d.total_tasks,
                "approval_rate": metrics_7d.approval_rate,
                "avg_quality": metrics_7d.avg_quality_score,
                "trend": metrics_7d.quality_trend,
            },
            "last_30_days": {
                "tasks": metrics_30d.total_tasks,
                "approval_rate": metrics_30d.approval_rate,
                "avg_quality": metrics_30d.avg_quality_score,
                "trend": metrics_30d.quality_trend,
                "breakdown": metrics_30d.task_type_breakdown,
            },
            "strengths": [
                {"area": s.area, "score": s.score, "description": s.description}
                for s in strengths[:5]
            ],
            "weaknesses": [
                {"area": w.area, "score": w.score, "description": w.description}
                for w in weaknesses[:5]
            ],
            "recommendations": [
                {"priority": r.priority, "title": r.title, "action": r.suggested_action}
                for r in recs[:5]
            ],
            "milestones": [
                {"title": m.title, "value": m.value, "timestamp": m.timestamp}
                for m in timeline[:5]
            ],
        }

    # =========================================================================
    # PUBLIC API: DOMAIN TRAINING TRACKING
    # =========================================================================

    def track_domain_training(self, domain: str, score: float, cycle: int):
        """Record a training cycle result for domain progression tracking."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        # Ensure domain_training table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS domain_training (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                score REAL NOT NULL,
                cycle INTEGER NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        cursor.execute(
            "INSERT INTO domain_training (domain, score, cycle, timestamp) VALUES (?, ?, ?, ?)",
            (domain, score, cycle, time.time()),
        )
        conn.commit()
        conn.close()

    def get_domain_progress(self, domain: str) -> Dict[str, Any]:
        """Get training progress for a domain."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        # Ensure table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS domain_training (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                score REAL NOT NULL,
                cycle INTEGER NOT NULL,
                timestamp REAL NOT NULL
            )
        """)

        rows = cursor.execute(
            "SELECT score FROM domain_training WHERE domain = ? ORDER BY timestamp",
            (domain,),
        ).fetchall()
        conn.close()

        if not rows:
            return {"status": "not_started", "scores": [], "average": 0.0}

        scores = [r[0] for r in rows]

        # Check if graduated
        graduated_row = None
        try:
            conn2 = sqlite3.connect(self._db_path)
            graduated_row = conn2.execute(
                "SELECT 1 FROM domain_graduations WHERE domain = ?", (domain,)
            ).fetchone()
            conn2.close()
        except Exception:
            pass

        status = "graduated" if graduated_row else "in_progress"

        return {
            "status": status,
            "scores": scores,
            "average": sum(scores) / len(scores) if scores else 0.0,
            "best": max(scores) if scores else 0.0,
            "worst": min(scores) if scores else 0.0,
            "total_cycles": len(scores),
            "trend": self._calculate_domain_trend(scores),
        }

    def _calculate_domain_trend(self, scores: List[float]) -> str:
        """Determine if scores are improving, declining, or plateaued."""
        if len(scores) < 3:
            return "insufficient_data"
        recent = scores[-3:]
        earlier = scores[-6:-3] if len(scores) >= 6 else scores[:3]
        recent_avg = sum(recent) / len(recent)
        earlier_avg = sum(earlier) / len(earlier)
        diff = recent_avg - earlier_avg
        if diff > 0.1:
            return "improving"
        elif diff < -0.1:
            return "declining"
        else:
            return "plateaued"

    def graduate_domain(self, domain: str):
        """Mark a domain as graduated."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS domain_graduations (
                domain TEXT PRIMARY KEY,
                graduated_at REAL NOT NULL
            )
        """)
        cursor.execute(
            "INSERT OR REPLACE INTO domain_graduations (domain, graduated_at) VALUES (?, ?)",
            (domain, time.time()),
        )
        conn.commit()
        conn.close()

    # =========================================================================
    # INTERNAL: DATABASE
    # =========================================================================

    def _init_db(self):
        """Initialize evolution database."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task_type TEXT DEFAULT 'general',
                quality_score REAL DEFAULT 0.0,
                rating INTEGER DEFAULT 0,
                feedback TEXT DEFAULT '',
                task_description TEXT DEFAULT '',
                files_modified TEXT DEFAULT '[]',
                iteration_count INTEGER DEFAULT 1,
                model_used TEXT DEFAULT '',
                workspace TEXT DEFAULT '',
                approved INTEGER DEFAULT -1
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                milestone_type TEXT,
                title TEXT,
                description TEXT,
                value REAL,
                previous_value REAL
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_timestamp ON outcomes(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_type ON outcomes(task_type)")

        conn.commit()
        conn.close()

    def _compute_trend(self, cursor, cutoff: str) -> str:
        """Compute quality trend by comparing first half to second half."""
        cursor.execute(
            "SELECT quality_score FROM outcomes WHERE timestamp >= ? AND quality_score > 0 ORDER BY timestamp",
            (cutoff,),
        )
        scores = [row[0] for row in cursor.fetchall()]

        if len(scores) < 4:
            return "stable"

        mid = len(scores) // 2
        first_half = statistics.mean(scores[:mid])
        second_half = statistics.mean(scores[mid:])

        diff = second_half - first_half
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "declining"
        return "stable"

    def _get_metrics_for_type(self, task_type: str, cutoff: str) -> PerformanceMetrics:
        """Get metrics for a specific task type."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM outcomes WHERE timestamp >= ? AND task_type = ?", (cutoff, task_type)
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM outcomes WHERE timestamp >= ? AND task_type = ? AND approved = 1", (cutoff, task_type)
        )
        approved = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM outcomes WHERE timestamp >= ? AND task_type = ? AND approved = 0", (cutoff, task_type)
        )
        rejected = cursor.fetchone()[0]

        cursor.execute(
            "SELECT AVG(quality_score) FROM outcomes WHERE timestamp >= ? AND task_type = ? AND quality_score > 0", (cutoff, task_type)
        )
        avg_q = cursor.fetchone()[0] or 0.0

        cursor.execute(
            "SELECT AVG(rating) FROM outcomes WHERE timestamp >= ? AND task_type = ? AND rating > 0", (cutoff, task_type)
        )
        avg_r = cursor.fetchone()[0] or 0.0

        conn.close()

        rated = approved + rejected
        return PerformanceMetrics(
            window_start=cutoff, window_end=datetime.now(timezone.utc).isoformat(),
            total_tasks=total, approved_count=approved, rejected_count=rejected,
            neutral_count=total - approved - rejected,
            approval_rate=round(approved / rated if rated > 0 else 0.0, 3),
            avg_quality_score=round(avg_q, 3), avg_rating=round(avg_r, 2),
            task_type_breakdown={task_type: total},
        )

    def _check_milestones(self, conn) -> List[EvolutionMilestone]:
        """Check if any new milestones have been reached."""
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        milestones = []

        cursor.execute("SELECT COUNT(*) FROM outcomes")
        total = cursor.fetchone()[0]

        task_thresholds = [10, 25, 50, 100, 250, 500, 1000]
        for threshold in task_thresholds:
            if total == threshold:
                m = EvolutionMilestone(
                    timestamp=now, milestone_type="task_count",
                    title=f"{threshold} Tasks Completed",
                    description=f"Orion has now processed {threshold} tasks",
                    value=float(threshold), previous_value=float(threshold - 1),
                )
                self._store_milestone(cursor, m)
                milestones.append(m)

        cursor.execute("SELECT COUNT(*) FROM outcomes WHERE approved = 1")
        approved = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM outcomes WHERE approved >= 0")
        rated = cursor.fetchone()[0]

        if rated >= 10:
            rate = approved / rated
            cursor.execute(
                "SELECT value FROM milestones WHERE milestone_type = 'approval_rate' ORDER BY timestamp DESC LIMIT 1"
            )
            last = cursor.fetchone()
            last_rate = last[0] if last else 0.0

            if rate >= 0.8 and last_rate < 0.8:
                m = EvolutionMilestone(
                    timestamp=now, milestone_type="approval_rate",
                    title="80% Approval Rate Reached!",
                    description=f"Approval rate has crossed 80% ({rate:.1%})",
                    value=round(rate, 3), previous_value=round(last_rate, 3),
                )
                self._store_milestone(cursor, m)
                milestones.append(m)

            if rate >= 0.9 and last_rate < 0.9:
                m = EvolutionMilestone(
                    timestamp=now, milestone_type="approval_rate",
                    title="90% Approval Rate Reached!",
                    description=f"Approval rate has crossed 90% ({rate:.1%})",
                    value=round(rate, 3), previous_value=round(last_rate, 3),
                )
                self._store_milestone(cursor, m)
                milestones.append(m)

        conn.commit()
        return milestones

    def _store_milestone(self, cursor, milestone: EvolutionMilestone):
        """Store a milestone in the database."""
        cursor.execute("""
            INSERT INTO milestones (timestamp, milestone_type, title, description, value, previous_value)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            milestone.timestamp, milestone.milestone_type, milestone.title,
            milestone.description, milestone.value, milestone.previous_value,
        ))

    def clear(self):
        """Clear all evolution data (use with extreme caution)."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM outcomes")
        cursor.execute("DELETE FROM milestones")
        conn.commit()
        conn.close()


# =============================================================================
# FACTORY
# =============================================================================

_evolution_instance: Optional[EvolutionEngine] = None


def get_evolution_engine() -> EvolutionEngine:
    """Get or create the global EvolutionEngine instance."""
    global _evolution_instance
    if _evolution_instance is None:
        _evolution_instance = EvolutionEngine()
    return _evolution_instance
