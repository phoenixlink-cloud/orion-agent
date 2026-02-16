# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Teaching Engine — Q&A-based institutional learning.

Implements a school-style teach-student cycle:
1. Load curriculum (subjects → lessons → questions)
2. Present questions to Orion (via LLM)
3. Grade answers against expected concepts
4. Reinforce patterns (pass) or store corrections (fail)
5. Track progress in a grade book

Usage:
    engine = TeachingEngine(provider="ollama", model="qwen2.5:14b")
    results = await engine.run_lesson("fo-101")
    engine.print_report(results)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.memory.teaching")

CURRICULUM_PATH = Path(__file__).resolve().parents[4] / "data" / "seed" / "curriculum.json"
GRADEBOOK_PATH = Path.home() / ".orion" / "gradebook.json"


# ─── Data structures ─────────────────────────────────────────────────────

@dataclass
class QuestionResult:
    """Result of a single Q&A exchange."""
    question_id: str
    question: str
    orion_answer: str
    expected_concepts: list[str]
    concepts_found: list[str]
    concepts_missed: list[str]
    score: float  # 0.0 to 1.0
    passed: bool
    correction: str | None = None


@dataclass
class LessonResult:
    """Result of running a complete lesson."""
    lesson_id: str
    lesson_title: str
    subject: str
    grade: int
    questions: list[QuestionResult] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    overall_score: float = 0.0
    passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "lesson_id": self.lesson_id,
            "lesson_title": self.lesson_title,
            "subject": self.subject,
            "grade": self.grade,
            "overall_score": self.overall_score,
            "passed": self.passed,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "questions": [
                {
                    "id": q.question_id,
                    "score": q.score,
                    "passed": q.passed,
                    "concepts_found": q.concepts_found,
                    "concepts_missed": q.concepts_missed,
                }
                for q in self.questions
            ],
        }


# ─── Curriculum loader ───────────────────────────────────────────────────

def load_curriculum(path: Path | None = None) -> dict[str, Any]:
    """Load the curriculum JSON file."""
    p = path or CURRICULUM_PATH
    if not p.exists():
        raise FileNotFoundError(f"Curriculum not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def find_lesson(curriculum: dict, lesson_id: str) -> tuple[dict, dict] | None:
    """Find a lesson by ID. Returns (subject, lesson) or None."""
    for subject in curriculum.get("subjects", []):
        for lesson in subject.get("lessons", []):
            if lesson["id"] == lesson_id:
                return subject, lesson
    return None


def list_lessons(curriculum: dict) -> list[dict[str, str]]:
    """List all available lessons with their status."""
    lessons = []
    for subject in curriculum.get("subjects", []):
        for lesson in subject.get("lessons", []):
            lessons.append({
                "id": lesson["id"],
                "title": lesson["title"],
                "subject": subject["name"],
                "grade": lesson["grade"],
                "questions": len(lesson.get("questions", [])),
                "prerequisite": lesson.get("prerequisite"),
            })
    return lessons


# ─── Grading ─────────────────────────────────────────────────────────────

def _phrase_in_text(phrase: str, text: str) -> bool:
    """Check if a concept phrase appears in text (fuzzy for multi-word)."""
    words = phrase.split()
    if len(words) == 1:
        # Single word — check as substring
        return words[0] in text
    else:
        # Multi-word — at least 60% of words must be present
        matches = sum(1 for w in words if w in text)
        return matches >= len(words) * 0.6


def grade_answer(
    orion_answer: str,
    expected_concepts: list[str],
    passing_threshold: float = 0.6,
) -> tuple[list[str], list[str], float, bool]:
    """Grade Orion's answer against expected concepts.

    Each concept can contain '|'-delimited synonyms/alternatives:
        "regression guard|reject edit|revert|keep original"
    A concept is matched if ANY of its alternatives appear in the answer.

    Returns (concepts_found, concepts_missed, score, passed).
    """
    answer_lower = orion_answer.lower()
    found = []
    missed = []

    for concept_entry in expected_concepts:
        # Split on | for synonym alternatives
        alternatives = [alt.strip().lower() for alt in concept_entry.split("|")]
        # Concept is found if ANY alternative matches
        if any(_phrase_in_text(alt, answer_lower) for alt in alternatives):
            found.append(concept_entry.split("|")[0])  # Report primary name
        else:
            missed.append(concept_entry.split("|")[0])

    score = len(found) / len(expected_concepts) if expected_concepts else 1.0
    passed = score >= passing_threshold
    return found, missed, score, passed


# ─── Teaching Engine ─────────────────────────────────────────────────────

class TeachingEngine:
    """Runs Q&A lessons against Orion's LLM and grades the responses.

    This is the core of the teach-student cycle:
    - Presents questions to Orion (via LLM call)
    - Grades answers against expected concepts
    - Reinforces patterns in institutional memory (pass → confidence up)
    - Stores corrections for missed concepts (fail → new learning)
    """

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "qwen2.5:14b",
        curriculum_path: Path | None = None,
        institutional_memory: Any | None = None,
    ):
        self.provider = provider
        self.model = model
        self.curriculum = load_curriculum(curriculum_path)
        self._institutional = institutional_memory
        self._gradebook = self._load_gradebook()

    # ── Run a lesson ──────────────────────────────────────────────────

    async def run_lesson(self, lesson_id: str) -> LessonResult:
        """Run a complete lesson — present all questions, grade, and learn."""
        result_pair = find_lesson(self.curriculum, lesson_id)
        if not result_pair:
            raise ValueError(f"Lesson '{lesson_id}' not found in curriculum")

        subject, lesson = result_pair
        logger.info("Starting lesson: %s — %s", lesson_id, lesson["title"])

        result = LessonResult(
            lesson_id=lesson_id,
            lesson_title=lesson["title"],
            subject=subject["name"],
            grade=lesson["grade"],
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        for q in lesson.get("questions", []):
            qr = await self._ask_question(q)
            result.questions.append(qr)

            # Teach-student cycle: reinforce or correct
            self._process_outcome(q, qr)

            logger.info(
                "  Q: %s — score: %.0f%% %s",
                q["id"], qr.score * 100, "✓" if qr.passed else "✗",
            )

        result.completed_at = datetime.now(timezone.utc).isoformat()
        total = len(result.questions)
        if total > 0:
            result.overall_score = sum(q.score for q in result.questions) / total
        result.passed = result.overall_score >= 0.6

        # Save to gradebook
        self._save_lesson_result(result)

        logger.info(
            "Lesson %s complete: %.0f%% — %s",
            lesson_id, result.overall_score * 100,
            "PASSED" if result.passed else "NEEDS REVIEW",
        )
        return result

    async def run_subject(self, subject_id: str) -> list[LessonResult]:
        """Run all lessons in a subject sequentially."""
        results = []
        for subject in self.curriculum.get("subjects", []):
            if subject["id"] == subject_id:
                for lesson in subject.get("lessons", []):
                    result = await self.run_lesson(lesson["id"])
                    results.append(result)
        return results

    async def run_all(self) -> list[LessonResult]:
        """Run the entire curriculum."""
        results = []
        for subject in self.curriculum.get("subjects", []):
            for lesson in subject.get("lessons", []):
                result = await self.run_lesson(lesson["id"])
                results.append(result)
        return results

    # ── Ask a single question ─────────────────────────────────────────

    async def _ask_question(self, q: dict) -> QuestionResult:
        """Present a question to Orion and grade the answer."""
        # Include institutional wisdom if available (student uses what they know)
        context = ""
        if self._institutional:
            try:
                from orion.core.learning.patterns import get_learnings_for_prompt
                context = get_learnings_for_prompt(
                    self._institutional, q["question"], max_items=8
                )
            except Exception:
                pass

        system_prompt = (
            "You are Orion, an autonomous AI coding agent being tested on your knowledge. "
            "You have accumulated knowledge from previous lessons and real debugging experience. "
            "IMPORTANT: When answering, USE the corrections and patterns provided in your "
            "accumulated knowledge section below. These contain the exact principles you've "
            "learned from past mistakes. Reference them directly in your answers.\n"
            "Answer thoroughly — cover all aspects of the question including specific "
            "mechanisms, safeguards, and terminology from your training."
        )

        user_prompt = q["question"]
        if context:
            user_prompt += f"\n\nYour accumulated knowledge:\n{context}"

        # Call LLM
        try:
            from orion.core.llm.providers import call_provider
            from orion.core.llm.config import RoleConfig

            rc = RoleConfig(provider=self.provider, model=self.model)
            answer = await call_provider(
                role_config=rc,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                component="teaching_engine",
                temperature=0.3,
            )
        except Exception as e:
            logger.error("LLM call failed for question %s: %s", q["id"], e)
            answer = f"[LLM call failed: {e}]"

        # Grade
        found, missed, score, passed = grade_answer(
            answer, q["expected_concepts"]
        )

        correction = None
        if not passed:
            correction = q.get("correct_answer", "")

        return QuestionResult(
            question_id=q["id"],
            question=q["question"],
            orion_answer=answer,
            expected_concepts=q["expected_concepts"],
            concepts_found=found,
            concepts_missed=missed,
            score=score,
            passed=passed,
            correction=correction,
        )

    # ── Learn from outcomes ───────────────────────────────────────────

    def _process_outcome(self, q: dict, result: QuestionResult) -> None:
        """Reinforce patterns (pass) or store corrections (fail)."""
        if not self._institutional:
            return

        pattern_id = q.get("pattern_id")
        try:
            if result.passed:
                # Reinforce the pattern — Orion got it right
                self._institutional.learn_from_outcome(
                    action_type="teaching_qa",
                    context=f"[LESSON] {q['id']}: {q['question'][:100]}",
                    outcome=f"PASSED ({result.score:.0%}): {', '.join(result.concepts_found)}",
                    quality_score=result.score,
                    domain="institutional_learning",
                )
            else:
                # Store correction — Orion needs to learn this
                self._institutional.learn_from_outcome(
                    action_type="teaching_qa",
                    context=f"[LESSON] {q['id']}: {q['question'][:100]}",
                    outcome=f"FAILED ({result.score:.0%}): missed {', '.join(result.concepts_missed)}",
                    quality_score=result.score,
                    domain="institutional_learning",
                )
                # Store the correction as a confirmed feedback principle
                if result.correction:
                    self._institutional.store_confirmed_feedback(
                        principle=result.correction[:500],
                        original_feedback=f"Teaching Q&A correction for: {q['id']}",
                        rating=5,
                        task_description=q["question"][:500],
                        scope_domain="institutional_learning",
                    )
        except Exception as e:
            logger.debug("Could not update institutional memory: %s", e)

    # ── Grade book ────────────────────────────────────────────────────

    def _load_gradebook(self) -> dict[str, Any]:
        """Load existing grade book from disk."""
        if GRADEBOOK_PATH.exists():
            try:
                return json.loads(GRADEBOOK_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"sessions": [], "lesson_scores": {}}

    def _save_lesson_result(self, result: LessonResult) -> None:
        """Save lesson result to the grade book."""
        entry = result.to_dict()
        self._gradebook["sessions"].append(entry)
        # Track best score per lesson
        lid = result.lesson_id
        prev = self._gradebook["lesson_scores"].get(lid, 0)
        if result.overall_score > prev:
            self._gradebook["lesson_scores"][lid] = result.overall_score

        GRADEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
        GRADEBOOK_PATH.write_text(
            json.dumps(self._gradebook, indent=2), encoding="utf-8"
        )

    def get_progress(self) -> dict[str, Any]:
        """Get overall learning progress."""
        all_lessons = list_lessons(self.curriculum)
        total = len(all_lessons)
        scores = self._gradebook.get("lesson_scores", {})
        completed = sum(1 for lid, s in scores.items() if s >= 0.6)
        return {
            "total_lessons": total,
            "completed": completed,
            "remaining": total - completed,
            "completion_pct": (completed / total * 100) if total > 0 else 0,
            "lesson_scores": scores,
            "sessions_run": len(self._gradebook.get("sessions", [])),
        }

    # ── Reporting ─────────────────────────────────────────────────────

    @staticmethod
    def format_report(result: LessonResult) -> str:
        """Format a lesson result as a readable report."""
        lines = [
            f"╔══ Lesson: {result.lesson_title} ({result.lesson_id}) ══╗",
            f"  Subject: {result.subject} | Grade: {result.grade}",
            f"  Score: {result.overall_score:.0%} — {'PASSED ✓' if result.passed else 'NEEDS REVIEW ✗'}",
            "",
        ]
        for i, q in enumerate(result.questions, 1):
            status = "✓" if q.passed else "✗"
            lines.append(f"  Q{i} [{status}] {q.score:.0%} — {q.question[:60]}...")
            if q.concepts_found:
                lines.append(f"     Found: {', '.join(q.concepts_found)}")
            if q.concepts_missed:
                lines.append(f"     Missed: {', '.join(q.concepts_missed)}")
            if q.correction:
                lines.append(f"     Correction: {q.correction[:100]}...")
            lines.append("")

        lines.append(f"╚══ {len(result.questions)} questions, "
                      f"{sum(1 for q in result.questions if q.passed)} passed ══╝")
        return "\n".join(lines)

    @staticmethod
    def format_progress(progress: dict[str, Any]) -> str:
        """Format overall progress as a readable report."""
        lines = [
            "╔══ Orion Learning Progress ══╗",
            f"  Lessons: {progress['completed']}/{progress['total_lessons']} "
            f"({progress['completion_pct']:.0f}%)",
            f"  Sessions run: {progress['sessions_run']}",
            "",
        ]
        for lid, score in progress.get("lesson_scores", {}).items():
            status = "✓" if score >= 0.6 else "✗"
            lines.append(f"  [{status}] {lid}: {score:.0%}")
        lines.append("╚════════════════════════════╝")
        return "\n".join(lines)
