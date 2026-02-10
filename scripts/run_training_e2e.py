"""
Orion Knowledge Distillation -- End-to-End Training Demo

Student: Ollama qwen2.5:14b (local, weaker)
Teacher: OpenAI gpt-4o (cloud, stronger)
Judge:   OpenAI gpt-4o

Runs 3 passes through the demo_python curriculum (3 prompts × 3 passes = 9 cycles).
Prints real-time progress, score evolution, and final summary.
"""

import asyncio
import json
import time
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def main():
    from orion.core.memory.engine import MemoryEngine
    from orion.core.learning.benchmark import BenchmarkEngine
    from orion.core.learning.curriculum import CurriculumEngine

    workspace = str(Path(__file__).parent.parent)
    curriculum_file = str(Path(__file__).parent.parent / "examples" / "curriculum_demo.json")

    print("=" * 70)
    print("  ORION KNOWLEDGE DISTILLATION -- END-TO-END TRAINING")
    print("=" * 70)
    print()
    print("  Student : ollama / qwen2.5:14b  (local)")
    print("  Teacher : openai / gpt-4o       (cloud)")
    print("  Judge   : openai / gpt-4o       (cloud)")
    print("  Passes  : 3 (9 total cycles)")
    print("  Threshold: 75% for graduation")
    print()

    # Initialize engines
    me = MemoryEngine(workspace_path=workspace)
    benchmark = BenchmarkEngine(
        judge_provider="openai",
        judge_model="gpt-4o",
    )
    engine = CurriculumEngine(
        memory_engine=me,
        benchmark_engine=benchmark,
        workspace_path=workspace,
        teacher_provider="openai",
        teacher_model="gpt-4o",
        student_provider="ollama",
        student_model="qwen2.5:14b",
    )

    # Load curriculum
    print("Loading curriculum...")
    state = engine.load_curriculum("demo_python", curriculum_file)
    curriculum = engine._curricula["demo_python"]
    prompts = curriculum["prompts"]

    print(f"  Domain: demo_python")
    print(f"  Prompts: {state.total_prompts}")
    print(f"  Graduation threshold: {state.graduation_threshold:.0%}")
    print()

    for p in prompts:
        print(f"  [{p.difficulty}] {p.id}: {p.prompt[:65]}...")
        print(f"         Expected: {', '.join(p.expected_concepts[:3])}...")
    print()

    # Run training
    all_results = []
    pass_summaries = []

    for pass_num in range(1, 4):
        print("-" * 70)
        print(f"  PASS {pass_num}/3")
        print("-" * 70)

        pass_scores = []

        for prompt in prompts:
            t0 = time.time()
            print(f"\n  ▸ {prompt.id} [{prompt.difficulty}]")
            print(f"    Q: {prompt.prompt[:60]}...")

            try:
                result = await engine.run_training_cycle("demo_python", prompt.id)
                elapsed = time.time() - t0

                all_results.append(result)
                pass_scores.append(result.quality_score / 5.0)

                # Print result
                score_bar = "█" * result.quality_score + "░" * (5 - result.quality_score)
                print(f"    Score: [{score_bar}] {result.quality_score}/5  ({result.similarity_score:.0%} sim)  ⏱ {elapsed:.1f}s")

                if result.missing_concepts:
                    print(f"    Missing: {', '.join(result.missing_concepts[:3])}")
                if result.patterns_created:
                    print(f"    Patterns recorded: {len(result.patterns_created)}")

                # Show a snippet of student vs teacher
                student_snip = result.orion_response[:120].replace('\n', ' ')
                teacher_snip = result.benchmark_response[:120].replace('\n', ' ')
                print(f"    Student: {student_snip}...")
                print(f"    Teacher: {teacher_snip}...")

            except Exception as e:
                print(f"    ❌ FAILED: {e}")
                pass_scores.append(0)

        # Pass summary
        avg = sum(pass_scores) / len(pass_scores) if pass_scores else 0
        pass_summaries.append(avg)
        state = engine.get_domain_status("demo_python")
        print(f"\n  Pass {pass_num} average: {avg:.0%}  |  Cumulative avg: {state.current_avg_score:.0%}")

        if state.status == "graduated":
            print(f"\n  🎓 DOMAIN GRADUATED after pass {pass_num}!")
            break

    # Final summary
    print()
    print("=" * 70)
    print("  TRAINING SUMMARY")
    print("=" * 70)

    state = engine.get_domain_status("demo_python")
    print(f"  Status:      {state.status}")
    print(f"  Cycles:      {state.completed_cycles}")
    print(f"  Avg score:   {state.current_avg_score:.0%}")
    print(f"  Best score:  {state.best_score:.0%}")
    print(f"  Worst score: {state.worst_score:.0%}")
    print()

    # Score evolution per pass
    print("  Score evolution by pass:")
    for i, avg in enumerate(pass_summaries, 1):
        bar = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
        print(f"    Pass {i}: [{bar}] {avg:.0%}")

    # Score evolution per prompt
    print()
    print("  Score evolution by prompt:")
    for prompt in prompts:
        scores = state.prompt_scores.get(prompt.id, [])
        scores_str = " -> ".join(f"{s:.0%}" for s in scores)
        trend = ""
        if len(scores) >= 2:
            if scores[-1] > scores[0]:
                trend = " ↑"
            elif scores[-1] < scores[0]:
                trend = " ↓"
            else:
                trend = " ->"
        print(f"    {prompt.id}: {scores_str}{trend}")

    # Show full score history
    print()
    print("  Full score timeline:")
    for i, score in enumerate(state.score_history, 1):
        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        print(f"    Cycle {i:2d}: [{bar}] {score:.0%}")

    # Compounding check
    print()
    if len(pass_summaries) >= 2:
        delta = pass_summaries[-1] - pass_summaries[0]
        if delta > 0:
            print(f"  ✅ COMPOUNDING CONFIRMED: +{delta:.0%} improvement from pass 1 -> pass {len(pass_summaries)}")
        elif delta == 0:
            print(f"  ➡️  PLATEAU: No change between pass 1 and pass {len(pass_summaries)}")
        else:
            print(f"  ⚠️  REGRESSION: {delta:.0%} decline from pass 1 -> pass {len(pass_summaries)}")

    # Count patterns in Tier 3
    try:
        stats = me.get_stats()
        print(f"\n  Tier 3 memories: {stats.get('tier3_count', 'N/A')}")
    except Exception:
        pass

    print()
    print("=" * 70)
    print("  END OF TRAINING RUN")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
