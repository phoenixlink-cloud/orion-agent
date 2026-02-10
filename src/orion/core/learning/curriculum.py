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
Orion Agent -- Curriculum Engine (v7.1.0)

Orchestrates deliberate training sessions where Orion processes source
materials, generates output, compares against a benchmark, and records
patterns from the gap analysis.

TRAINING LOOP:
    1. Load curriculum (JSON file of training prompts)
    2. For each prompt: student generates -> teacher generates -> compare
    3. Record patterns (success/anti-pattern) in Tier 3
    4. Track domain progress toward graduation
    5. Export graduated domain as knowledge pack

USAGE:
    engine = CurriculumEngine(memory_engine, benchmark_engine, workspace)
    state = engine.load_curriculum("legal_sa", "curriculum_legal.json")
    result = await engine.run_training_cycle("legal_sa")
    results = await engine.run_full_curriculum("legal_sa", max_cycles=3)
"""

import json
import time
import logging
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from enum import Enum
from pathlib import Path

logger = logging.getLogger("orion.learning.curriculum")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class TrainingStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    GRADUATED = "graduated"
    NEEDS_REVIEW = "needs_review"


@dataclass
class TrainingPrompt:
    """A single training exercise within a curriculum."""
    id: str
    domain: str
    prompt: str
    source_context: str
    difficulty: str
    expected_concepts: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class TrainingResult:
    """Result of a single training cycle."""
    prompt_id: str
    domain: str
    cycle_number: int
    orion_response: str
    benchmark_response: str
    similarity_score: float
    missing_concepts: List[str] = field(default_factory=list)
    incorrect_claims: List[str] = field(default_factory=list)
    quality_score: int = 3
    feedback_text: str = ""
    patterns_created: List[str] = field(default_factory=list)
    timestamp: float = 0.0


@dataclass
class CurriculumState:
    """Persistent state for a training curriculum."""
    domain: str
    status: str  # TrainingStatus value
    total_prompts: int
    completed_cycles: int
    current_avg_score: float
    graduation_threshold: float
    best_score: float
    worst_score: float
    score_history: List[float] = field(default_factory=list)
    prompt_scores: Dict[str, List[float]] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0


# =============================================================================
# CURRICULUM ENGINE
# =============================================================================

class CurriculumEngine:
    """
    Orchestrates deliberate training of Orion's Tier 3 memory
    against authoritative source materials.
    """

    def __init__(
        self,
        memory_engine,
        benchmark_engine,
        workspace_path: str,
        teacher_provider: str = "anthropic",
        teacher_model: str = "claude-opus-4-20250514",
        student_provider: str = None,
        student_model: str = None,
    ):
        self.memory_engine = memory_engine
        self.benchmark_engine = benchmark_engine
        self.workspace_path = workspace_path
        self.teacher_provider = teacher_provider
        self.teacher_model = teacher_model
        self.student_provider = student_provider
        self.student_model = student_model

        # Training data directory
        self._training_dir = Path.home() / ".orion" / "training"
        self._training_dir.mkdir(parents=True, exist_ok=True)

        # Cached curricula
        self._curricula: Dict[str, Dict] = {}
        self._states: Dict[str, CurriculumState] = {}

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def load_curriculum(self, domain: str, prompts_file: str) -> CurriculumState:
        """
        Load a curriculum from a JSON file in the workspace.

        Args:
            domain: Domain identifier (e.g., "legal_sa").
            prompts_file: Path to curriculum JSON file (relative to workspace or absolute).

        Returns:
            CurriculumState for this domain.
        """
        # Resolve file path
        path = Path(prompts_file)
        if not path.is_absolute():
            path = Path(self.workspace_path) / prompts_file
        if not path.exists():
            raise FileNotFoundError(f"Curriculum file not found: {path}")

        curriculum_data = json.loads(path.read_text(encoding="utf-8"))

        # Parse prompts
        prompts = []
        for p in curriculum_data.get("prompts", []):
            prompts.append(TrainingPrompt(
                id=p["id"],
                domain=domain,
                prompt=p["prompt"],
                source_context=p.get("source_context", ""),
                difficulty=p.get("difficulty", "basic"),
                expected_concepts=p.get("expected_concepts", []),
                metadata=p.get("metadata", {}),
            ))

        self._curricula[domain] = {
            "domain": domain,
            "description": curriculum_data.get("description", ""),
            "source_files": curriculum_data.get("source_files", []),
            "graduation_threshold": curriculum_data.get("graduation_threshold", 0.80),
            "prompts": prompts,
        }

        # Create domain directory
        domain_dir = self._training_dir / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        (domain_dir / "results").mkdir(exist_ok=True)

        # Save curriculum copy
        (domain_dir / "curriculum.json").write_text(
            json.dumps(curriculum_data, indent=2), encoding="utf-8"
        )

        # Load or create state
        state = self._load_state(domain)
        if state is None:
            state = CurriculumState(
                domain=domain,
                status=TrainingStatus.NOT_STARTED.value,
                total_prompts=len(prompts),
                completed_cycles=0,
                current_avg_score=0.0,
                graduation_threshold=curriculum_data.get("graduation_threshold", 0.80),
                best_score=0.0,
                worst_score=5.0,
                score_history=[],
                prompt_scores={},
                created_at=time.time(),
                updated_at=time.time(),
            )
        else:
            state.total_prompts = len(prompts)

        self._states[domain] = state
        self._save_state(state)

        # Update domains index
        self._update_domains_index(domain, curriculum_data.get("description", ""))

        logger.info(
            "Loaded curriculum: %s -- %d prompts, threshold %.0f%%",
            domain, len(prompts), state.graduation_threshold * 100,
        )
        return state

    async def run_training_cycle(
        self, domain: str, prompt_id: str = None
    ) -> TrainingResult:
        """
        Run a single training cycle for a domain.

        Args:
            domain: Domain identifier.
            prompt_id: Specific prompt to train on. If None, picks next untrained.

        Returns:
            TrainingResult with scores and patterns created.
        """
        if domain not in self._curricula:
            raise ValueError(f"Domain '{domain}' not loaded. Call load_curriculum first.")

        curriculum = self._curricula[domain]
        state = self._states.get(domain)
        if state is None:
            raise ValueError(f"No state for domain '{domain}'")

        prompts = curriculum["prompts"]

        # Pick prompt
        if prompt_id:
            prompt = next((p for p in prompts if p.id == prompt_id), None)
            if not prompt:
                raise ValueError(f"Prompt '{prompt_id}' not found in {domain}")
        else:
            prompt = self._pick_next_prompt(prompts, state)
            if not prompt:
                raise ValueError(f"All prompts completed for {domain}")

        # Determine cycle number for this prompt
        prompt_history = state.prompt_scores.get(prompt.id, [])
        cycle_number = len(prompt_history) + 1

        # Update status
        state.status = TrainingStatus.IN_PROGRESS.value
        state.updated_at = time.time()

        # Step 1: Build student context -- recall existing patterns
        memory_context = self.memory_engine.recall_for_prompt(
            prompt.prompt, domain=domain
        )

        # Step 1b: Build remediation context from previous failures
        remediation = self._build_remediation_context(prompt, state)

        # Step 2: Generate student response
        student_response = await self._generate_student_response(
            prompt, memory_context, remediation
        )

        # Step 3: Generate teacher response
        teacher_response = await self._generate_teacher_response(prompt)

        # Step 4: Compare responses
        comparison = await self.benchmark_engine.compare(
            student=student_response,
            teacher=teacher_response,
            expected_concepts=prompt.expected_concepts,
            prompt=prompt.prompt,
        )

        # Step 5: Record patterns based on quality score
        patterns_created = self._record_patterns(
            prompt, comparison, student_response, teacher_response
        )

        # Step 6: Update evolution tracking
        try:
            from orion.core.learning.evolution import get_evolution_engine
            evo = get_evolution_engine()
            evo.track_domain_training(domain, comparison.quality_score / 5.0, cycle_number)
        except Exception as e:
            logger.warning("Failed to update evolution tracking: %s", e)

        # Step 7: Update state
        score = comparison.quality_score / 5.0
        state.completed_cycles += 1
        state.score_history.append(score)
        if prompt.id not in state.prompt_scores:
            state.prompt_scores[prompt.id] = []
        state.prompt_scores[prompt.id].append(score)
        state.current_avg_score = sum(state.score_history) / len(state.score_history)
        state.best_score = max(state.best_score, score)
        state.worst_score = min(state.worst_score, score)
        state.updated_at = time.time()

        # Check graduation
        if self.check_graduation(domain):
            state.status = TrainingStatus.GRADUATED.value
            try:
                evo = get_evolution_engine()
                evo.graduate_domain(domain)
            except Exception:
                pass

        self._save_state(state)

        # Build result
        result = TrainingResult(
            prompt_id=prompt.id,
            domain=domain,
            cycle_number=cycle_number,
            orion_response=student_response,
            benchmark_response=teacher_response,
            similarity_score=comparison.similarity_score,
            missing_concepts=comparison.concepts_missing,
            incorrect_claims=comparison.incorrect_claims,
            quality_score=comparison.quality_score,
            feedback_text=comparison.feedback_text,
            patterns_created=patterns_created,
            timestamp=time.time(),
        )

        # Save result to disk
        self._save_result(result)

        logger.info(
            "Training cycle: %s/%s (cycle %d) -- score %d/5, %.0f%% avg",
            domain, prompt.id, cycle_number,
            comparison.quality_score, state.current_avg_score * 100,
        )

        return result

    async def run_full_curriculum(
        self, domain: str, max_cycles: int = 3
    ) -> List[TrainingResult]:
        """
        Run the full curriculum automatically.

        Iterates through all prompts up to max_cycles passes.
        Stops early if domain reaches graduation threshold.

        Args:
            domain: Domain identifier.
            max_cycles: Maximum number of passes through all prompts.

        Returns:
            List of all TrainingResults.
        """
        if domain not in self._curricula:
            raise ValueError(f"Domain '{domain}' not loaded")

        curriculum = self._curricula[domain]
        prompts = curriculum["prompts"]
        results = []

        for cycle in range(max_cycles):
            for prompt in prompts:
                try:
                    result = await self.run_training_cycle(domain, prompt.id)
                    results.append(result)
                except Exception as e:
                    logger.warning("Training cycle failed for %s/%s: %s", domain, prompt.id, e)

            # Check graduation after each pass
            if self.check_graduation(domain):
                logger.info("Domain '%s' graduated after %d passes!", domain, cycle + 1)
                break

        return results

    def get_domain_status(self, domain: str) -> Optional[CurriculumState]:
        """Get current state for a domain."""
        if domain in self._states:
            return self._states[domain]
        return self._load_state(domain)

    def list_domains(self) -> List[CurriculumState]:
        """List all trained domains and their status."""
        domains_file = self._training_dir / "domains.json"
        if not domains_file.exists():
            return []

        try:
            domains_data = json.loads(domains_file.read_text(encoding="utf-8"))
            states = []
            for domain_info in domains_data.get("domains", []):
                domain = domain_info.get("domain", "")
                state = self._load_state(domain)
                if state:
                    states.append(state)
            return states
        except Exception:
            return []

    def check_graduation(self, domain: str) -> bool:
        """
        Check if a domain has graduated.

        Graduation criteria:
        - Average score across all prompts >= graduation_threshold
        - No individual prompt's latest score below 3/5 (0.6)
        - At least 2 complete passes through all prompts
        """
        state = self._states.get(domain)
        if not state:
            return False

        curriculum = self._curricula.get(domain)
        if not curriculum:
            return False

        prompts = curriculum["prompts"]
        threshold = state.graduation_threshold

        # Need at least 2 complete passes
        if state.completed_cycles < len(prompts) * 2:
            return False

        # Check average score
        if state.current_avg_score < threshold:
            return False

        # Check no individual prompt scores below 3/5 (0.6)
        for prompt in prompts:
            scores = state.prompt_scores.get(prompt.id, [])
            if not scores:
                return False
            if scores[-1] < 0.6:  # Latest score for this prompt
                return False

        return True

    # =========================================================================
    # INTERNAL
    # =========================================================================

    def _pick_next_prompt(
        self, prompts: List[TrainingPrompt], state: CurriculumState
    ) -> Optional[TrainingPrompt]:
        """Pick the next untrained or lowest-scoring prompt."""
        # First pass: find prompts never trained
        for prompt in prompts:
            if prompt.id not in state.prompt_scores:
                return prompt

        # Second pass: find lowest-scoring prompt
        min_score = 999.0
        min_prompt = None
        for prompt in prompts:
            scores = state.prompt_scores.get(prompt.id, [])
            if scores and scores[-1] < min_score:
                min_score = scores[-1]
                min_prompt = prompt

        return min_prompt

    def _build_remediation_context(
        self, prompt: TrainingPrompt, state: CurriculumState
    ) -> str:
        """
        Build remediation context from previous training results for this prompt.
        Tells the student exactly which concepts it previously missed.
        """
        prompt_history = state.prompt_scores.get(prompt.id, [])
        if not prompt_history:
            return ""

        # Load the most recent result file for this prompt
        results_dir = self._training_dir / state.domain / "results"
        missing_concepts = set()
        incorrect_claims = []
        prev_feedback = ""

        # Scan result files for this prompt (newest first)
        try:
            result_files = sorted(
                results_dir.glob(f"*_{prompt.id}.json"), reverse=True
            )
            for rf in result_files[:3]:  # Look at last 3 attempts
                try:
                    data = json.loads(rf.read_text(encoding="utf-8"))
                    for c in data.get("missing_concepts", []):
                        missing_concepts.add(c)
                    for c in data.get("incorrect_claims", []):
                        if c not in incorrect_claims:
                            incorrect_claims.append(c)
                    if not prev_feedback and data.get("feedback_text"):
                        prev_feedback = data["feedback_text"]
                except Exception:
                    continue
        except Exception:
            pass

        if not missing_concepts and not incorrect_claims:
            return ""

        parts = ["TRAINING FEEDBACK FROM PREVIOUS ATTEMPTS:"]
        parts.append(f"You have attempted this question {len(prompt_history)} time(s) before.")
        parts.append(f"Your latest score was {prompt_history[-1]:.0%}.")

        if missing_concepts:
            concepts_list = ", ".join(sorted(missing_concepts))
            parts.append(
                f"\nCRITICAL -- You previously MISSED these concepts and MUST cover them: "
                f"{concepts_list}"
            )
            parts.append(
                "Make sure your response explicitly addresses EACH of these concepts by name."
            )

        if incorrect_claims:
            parts.append(f"\nAVOID these errors from previous attempts:")
            for claim in incorrect_claims[:5]:
                parts.append(f"  - {claim}")

        if prev_feedback:
            parts.append(f"\nPrevious evaluator feedback: {prev_feedback[:500]}")

        return "\n".join(parts)

    async def _generate_student_response(
        self, prompt: TrainingPrompt, memory_context: str, remediation: str = ""
    ) -> str:
        """Generate the student (Orion) response."""
        system_prompt = "You are Orion, an AI assistant being trained on domain-specific knowledge."
        if remediation:
            system_prompt += f"\n\n{remediation}"
        if memory_context:
            system_prompt += f"\n\n{memory_context}"
        if prompt.source_context:
            system_prompt += f"\n\nREFERENCE MATERIAL:\n{prompt.source_context[:3000]}"

        try:
            from orion.core.llm.config import RoleConfig, get_model_config
            from orion.core.llm.providers import call_provider

            if self.student_provider and self.student_model:
                role = RoleConfig(provider=self.student_provider, model=self.student_model)
            else:
                config = get_model_config()
                role = config.builder

            response = await call_provider(
                role_config=role,
                system_prompt=system_prompt,
                user_prompt=prompt.prompt,
                max_tokens=4000,
                component="curriculum_student",
                temperature=0.3,
            )
            return response

        except Exception as e:
            logger.error("Student generation failed: %s", e)
            return f"[Student generation failed: {e}]"

    async def _generate_teacher_response(self, prompt: TrainingPrompt) -> str:
        """Generate the teacher (gold standard) response."""
        system_prompt = (
            "You are an expert evaluator. Provide a comprehensive, authoritative answer. "
            "Be specific, cite relevant principles, and cover all important nuances."
        )
        if prompt.source_context:
            system_prompt += f"\n\nREFERENCE MATERIAL:\n{prompt.source_context[:3000]}"

        try:
            from orion.core.llm.config import RoleConfig
            from orion.core.llm.providers import call_provider

            role = RoleConfig(provider=self.teacher_provider, model=self.teacher_model)
            response = await call_provider(
                role_config=role,
                system_prompt=system_prompt,
                user_prompt=prompt.prompt,
                max_tokens=4000,
                component="curriculum_teacher",
                temperature=0.2,
            )
            return response

        except Exception as e:
            logger.error("Teacher generation failed: %s", e)
            return f"[Teacher generation failed: {e}]"

    def _record_patterns(
        self, prompt: TrainingPrompt, comparison, student: str, teacher: str
    ) -> List[str]:
        """Record patterns in Tier 3 based on comparison results."""
        from orion.core.learning.feedback import StructuredFeedback, LearningLoop

        interaction_id = f"train_{prompt.domain}_{prompt.id}_{uuid.uuid4().hex[:8]}"

        feedback = StructuredFeedback(
            rating=comparison.quality_score,
            text=comparison.feedback_text,
            domain=prompt.domain,
            missing_concepts=comparison.concepts_missing,
            incorrect_claims=comparison.incorrect_claims,
            strengths=comparison.strengths,
            source="curriculum",
        )

        loop = LearningLoop(self.workspace_path)
        created_ids = loop.record_structured_feedback(
            interaction_id=interaction_id,
            feedback=feedback,
            memory_engine=self.memory_engine,
        )

        return created_ids

    def _load_state(self, domain: str) -> Optional[CurriculumState]:
        """Load curriculum state from disk."""
        state_file = self._training_dir / domain / "state.json"
        if not state_file.exists():
            return None
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return CurriculumState(**{
                k: v for k, v in data.items()
                if k in CurriculumState.__dataclass_fields__
            })
        except Exception as e:
            logger.warning("Failed to load state for %s: %s", domain, e)
            return None

    def _save_state(self, state: CurriculumState):
        """Save curriculum state to disk."""
        domain_dir = self._training_dir / state.domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        state_file = domain_dir / "state.json"
        state_file.write_text(
            json.dumps(asdict(state), indent=2), encoding="utf-8"
        )

    def _save_result(self, result: TrainingResult):
        """Save a training result to disk."""
        domain_dir = self._training_dir / result.domain / "results"
        domain_dir.mkdir(parents=True, exist_ok=True)
        filename = f"cycle_{result.cycle_number:03d}_{result.prompt_id}.json"
        result_file = domain_dir / filename
        result_file.write_text(
            json.dumps(asdict(result), indent=2), encoding="utf-8"
        )

    def _update_domains_index(self, domain: str, description: str):
        """Update the domains.json index file."""
        domains_file = self._training_dir / "domains.json"
        try:
            if domains_file.exists():
                data = json.loads(domains_file.read_text(encoding="utf-8"))
            else:
                data = {"domains": []}

            # Update or add domain
            found = False
            for d in data["domains"]:
                if d["domain"] == domain:
                    d["description"] = description
                    d["updated_at"] = time.time()
                    found = True
                    break

            if not found:
                data["domains"].append({
                    "domain": domain,
                    "description": description,
                    "created_at": time.time(),
                    "updated_at": time.time(),
                })

            domains_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to update domains index: %s", e)
