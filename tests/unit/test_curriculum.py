"""
Tests for Orion's Curriculum Engine (v7.1.0)

Tests curriculum loading, training cycle execution, graduation logic,
state persistence, error handling, and multi-cycle improvement.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion.core.learning.benchmark import BenchmarkEngine, ComparisonResult
from orion.core.learning.curriculum import (
    CurriculumEngine,
    TrainingResult,
    TrainingStatus,
)
from orion.core.memory.engine import MemoryEngine


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace with a curriculum file."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return workspace


@pytest.fixture
def curriculum_file(tmp_workspace):
    """Create a sample curriculum JSON file."""
    curriculum = {
        "domain": "demo_python",
        "description": "Python Best Practices -- Demo",
        "source_files": [],
        "graduation_threshold": 0.75,
        "prompts": [
            {
                "id": "demo_001",
                "prompt": "What are the key principles of writing clean Python code?",
                "source_context": "",
                "difficulty": "basic",
                "expected_concepts": [
                    "PEP 8 style guide",
                    "meaningful variable names",
                    "DRY principle",
                ],
            },
            {
                "id": "demo_002",
                "prompt": "Explain Python's error handling best practices",
                "source_context": "",
                "difficulty": "basic",
                "expected_concepts": [
                    "specific exception types",
                    "try-except-finally",
                    "avoid bare except",
                ],
            },
        ],
    }
    path = tmp_workspace / "curriculum_demo.json"
    path.write_text(json.dumps(curriculum, indent=2), encoding="utf-8")
    return str(path)


@pytest.fixture
def memory_engine(tmp_path, monkeypatch):
    """Create a MemoryEngine with temporary paths."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return MemoryEngine(workspace_path=str(workspace))


@pytest.fixture
def benchmark_engine():
    """Create a BenchmarkEngine."""
    return BenchmarkEngine()


@pytest.fixture
def curriculum_engine(memory_engine, benchmark_engine, tmp_workspace, tmp_path, monkeypatch):
    """Create a CurriculumEngine with temporary paths."""
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return CurriculumEngine(
        memory_engine=memory_engine,
        benchmark_engine=benchmark_engine,
        workspace_path=str(tmp_workspace),
    )


class TestLoadCurriculum:
    """Test curriculum loading."""

    def test_load_curriculum(self, curriculum_engine, curriculum_file):
        """Load a curriculum JSON, verify prompts parsed correctly."""
        state = curriculum_engine.load_curriculum("demo_python", curriculum_file)

        assert state.domain == "demo_python"
        assert state.total_prompts == 2
        assert state.status == TrainingStatus.NOT_STARTED.value
        assert state.graduation_threshold == 0.75
        assert state.completed_cycles == 0

        # Verify prompts are loaded
        curriculum = curriculum_engine._curricula.get("demo_python")
        assert curriculum is not None
        prompts = curriculum["prompts"]
        assert len(prompts) == 2
        assert prompts[0].id == "demo_001"
        assert len(prompts[0].expected_concepts) == 3

    def test_curriculum_not_found(self, curriculum_engine):
        """Graceful error on missing file."""
        with pytest.raises(FileNotFoundError):
            curriculum_engine.load_curriculum("missing", "nonexistent.json")

    def test_state_persistence(self, curriculum_engine, curriculum_file, tmp_path, monkeypatch):
        """Load curriculum, verify state saved to disk."""
        fake_home = tmp_path / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        curriculum_engine.load_curriculum("demo_python", curriculum_file)

        # Verify state file exists
        state_file = fake_home / ".orion" / "training" / "demo_python" / "state.json"
        assert state_file.exists()

        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["domain"] == "demo_python"
        assert data["total_prompts"] == 2

    def test_resume_existing_state(self, curriculum_engine, curriculum_file, tmp_path, monkeypatch):
        """Load curriculum twice, verify state is resumed (not reset)."""
        fake_home = tmp_path / "home"
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        state1 = curriculum_engine.load_curriculum("demo_python", curriculum_file)
        # Manually update state
        state1.completed_cycles = 5
        state1.current_avg_score = 0.7
        curriculum_engine._save_state(state1)

        # Reload
        state2 = curriculum_engine.load_curriculum("demo_python", curriculum_file)
        assert state2.completed_cycles == 5
        assert state2.current_avg_score == 0.7


class TestTrainingCycle:
    """Test training cycle execution with mocked LLM calls."""

    @pytest.mark.asyncio
    async def test_run_training_cycle(self, curriculum_engine, curriculum_file):
        """Mock LLM calls, verify patterns created from comparison."""
        curriculum_engine.load_curriculum("demo_python", curriculum_file)

        # Mock student and teacher generation
        with (
            patch.object(
                curriculum_engine, "_generate_student_response", new_callable=AsyncMock
            ) as mock_student,
            patch.object(
                curriculum_engine, "_generate_teacher_response", new_callable=AsyncMock
            ) as mock_teacher,
            patch.object(
                curriculum_engine.benchmark_engine, "compare", new_callable=AsyncMock
            ) as mock_compare,
            patch("orion.core.learning.evolution.get_evolution_engine") as mock_evo,
        ):
            mock_student.return_value = "PEP 8 is important. Use good names."
            mock_teacher.return_value = "PEP 8 style guide defines coding standards. Use meaningful variable names. Follow DRY principle."
            mock_compare.return_value = ComparisonResult(
                similarity_score=0.6,
                concept_coverage=0.67,
                concepts_present=["PEP 8 style guide", "meaningful variable names"],
                concepts_missing=["DRY principle"],
                incorrect_claims=[],
                quality_score=3,
                strengths=["Mentioned PEP 8"],
                weaknesses=["Missing DRY"],
                feedback_text="Partial coverage.",
            )
            mock_evo.return_value = MagicMock()

            result = await curriculum_engine.run_training_cycle("demo_python")

            assert isinstance(result, TrainingResult)
            assert result.domain == "demo_python"
            assert result.quality_score == 3
            assert result.similarity_score == 0.6
            assert "DRY principle" in result.missing_concepts

    @pytest.mark.asyncio
    async def test_domain_not_loaded(self, curriculum_engine):
        """Raise ValueError if domain not loaded."""
        with pytest.raises(ValueError, match="not loaded"):
            await curriculum_engine.run_training_cycle("nonexistent_domain")


class TestGraduation:
    """Test graduation logic."""

    def test_graduation_check_not_enough_cycles(self, curriculum_engine, curriculum_file):
        """Domain should not graduate with insufficient cycles."""
        curriculum_engine.load_curriculum("demo_python", curriculum_file)
        state = curriculum_engine._states["demo_python"]

        # Only 1 cycle per prompt (need 2 passes = 4 cycles)
        state.completed_cycles = 2
        state.current_avg_score = 0.9
        state.prompt_scores = {"demo_001": [0.9], "demo_002": [0.9]}

        assert curriculum_engine.check_graduation("demo_python") is False

    def test_graduation_check_low_avg(self, curriculum_engine, curriculum_file):
        """Domain should not graduate if avg below threshold."""
        curriculum_engine.load_curriculum("demo_python", curriculum_file)
        state = curriculum_engine._states["demo_python"]

        state.completed_cycles = 10
        state.current_avg_score = 0.5  # Below 0.75 threshold
        state.prompt_scores = {"demo_001": [0.5, 0.5], "demo_002": [0.5, 0.5]}

        assert curriculum_engine.check_graduation("demo_python") is False

    def test_graduation_check_low_individual_score(self, curriculum_engine, curriculum_file):
        """Domain should not graduate if any prompt scores below 0.6."""
        curriculum_engine.load_curriculum("demo_python", curriculum_file)
        state = curriculum_engine._states["demo_python"]

        state.completed_cycles = 10
        state.current_avg_score = 0.8
        state.prompt_scores = {
            "demo_001": [0.9, 0.9],
            "demo_002": [0.5, 0.5],  # Latest score below 0.6
        }

        assert curriculum_engine.check_graduation("demo_python") is False

    def test_graduation_check_success(self, curriculum_engine, curriculum_file):
        """Domain should graduate when all criteria met."""
        curriculum_engine.load_curriculum("demo_python", curriculum_file)
        state = curriculum_engine._states["demo_python"]

        state.completed_cycles = 10
        state.current_avg_score = 0.85
        state.prompt_scores = {
            "demo_001": [0.6, 0.8, 0.9],
            "demo_002": [0.7, 0.8, 0.85],
        }

        assert curriculum_engine.check_graduation("demo_python") is True

    def test_graduation_unloaded_domain(self, curriculum_engine):
        """Unloaded domain should return False."""
        assert curriculum_engine.check_graduation("nonexistent") is False


class TestMultipleCycles:
    """Test multi-cycle training improvement."""

    @pytest.mark.asyncio
    async def test_multiple_cycles_improve_recall(self, curriculum_engine, curriculum_file):
        """Run 3 cycles, verify state tracks scores."""
        curriculum_engine.load_curriculum("demo_python", curriculum_file)

        scores = [2, 3, 4]  # Improving scores

        for i, score in enumerate(scores):
            with (
                patch.object(
                    curriculum_engine, "_generate_student_response", new_callable=AsyncMock
                ) as mock_s,
                patch.object(
                    curriculum_engine, "_generate_teacher_response", new_callable=AsyncMock
                ) as mock_t,
                patch.object(
                    curriculum_engine.benchmark_engine, "compare", new_callable=AsyncMock
                ) as mock_c,
                patch("orion.core.learning.evolution.get_evolution_engine") as mock_evo,
            ):
                mock_s.return_value = f"Student response cycle {i}"
                mock_t.return_value = f"Teacher response cycle {i}"
                mock_c.return_value = ComparisonResult(
                    similarity_score=0.5 + i * 0.1,
                    concept_coverage=0.3 + i * 0.2,
                    concepts_present=["PEP 8"] if i > 0 else [],
                    concepts_missing=["DRY"] if i < 2 else [],
                    quality_score=score,
                    strengths=["improving"],
                    weaknesses=[],
                    feedback_text=f"Cycle {i}",
                )
                mock_evo.return_value = MagicMock()

                await curriculum_engine.run_training_cycle("demo_python", "demo_001")

        state = curriculum_engine.get_domain_status("demo_python")
        assert state is not None
        assert state.completed_cycles == 3
        assert len(state.score_history) == 3
        # Scores should be improving
        assert state.score_history[-1] > state.score_history[0]
