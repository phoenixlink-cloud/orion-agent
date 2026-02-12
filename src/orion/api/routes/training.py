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
"""Orion Agent -- Training, Evolution & Memory Routes."""

from fastapi import APIRouter, HTTPException

from orion.api._shared import _get_orion_log, _load_user_settings

router = APIRouter()


# =============================================================================
# EVOLUTION / LEARNING (Phase 1A -- closing CLI-only gap)
# =============================================================================


@router.get("/api/evolution/snapshot")
async def get_evolution_snapshot():
    """Get Orion's learning evolution snapshot."""
    try:
        from orion.core.learning.evolution import get_evolution_engine

        engine = get_evolution_engine()
        summary = engine.get_evolution_summary()
        return {
            "summary": summary if isinstance(summary, dict) else str(summary),
        }
    except Exception as e:
        return {"summary": f"Evolution engine not available: {e}"}


@router.get("/api/evolution/recommendations")
async def get_evolution_recommendations():
    """Get self-improvement recommendations."""
    try:
        from orion.core.learning.evolution import get_evolution_engine

        engine = get_evolution_engine()
        return {"recommendations": engine.get_recommendations()}
    except Exception as e:
        return {"recommendations": [], "error": str(e)}


# =============================================================================
# MEMORY ENGINE (Phase 1C -- closing BOTH-MISSING gap)
# =============================================================================


@router.get("/api/memory/stats")
async def get_memory_stats():
    """Get three-tier memory system statistics."""
    try:
        from dataclasses import asdict

        from orion.core.memory.engine import MemoryEngine

        settings = _load_user_settings()
        engine = MemoryEngine(workspace_path=settings.get("workspace"))
        stats = engine.get_stats()
        if hasattr(stats, "__dataclass_fields__"):
            return asdict(stats)
        return stats if isinstance(stats, dict) else {"raw": str(stats)}
    except Exception as e:
        return {"error": str(e), "tier1": 0, "tier2": 0, "tier3": 0}


@router.get("/api/memory/recall")
async def recall_memories(q: str, max_results: int = 10):
    """Recall relevant memories for a query."""
    try:
        from orion.core.memory.engine import MemoryEngine

        settings = _load_user_settings()
        engine = MemoryEngine(workspace_path=settings.get("workspace"))
        memories = engine.recall(q, max_results=max_results)
        return {
            "query": q,
            "count": len(memories),
            "memories": [
                {
                    "content": m.content,
                    "tier": m.tier,
                    "category": m.category,
                    "confidence": m.confidence,
                    "source": m.source,
                }
                for m in memories
            ],
        }
    except Exception as e:
        return {"query": q, "count": 0, "memories": [], "error": str(e)}


# =============================================================================
# TRAINING / KNOWLEDGE DISTILLATION
# =============================================================================


@router.post("/api/training/load")
async def load_curriculum(domain: str, curriculum_file: str):
    """Load a training curriculum."""
    try:
        from orion.core.learning.benchmark import BenchmarkEngine
        from orion.core.learning.curriculum import CurriculumEngine
        from orion.core.memory.engine import get_memory_engine

        settings = _load_user_settings()
        workspace = settings.get("workspace", "")
        me = get_memory_engine(workspace)
        benchmark = BenchmarkEngine()
        engine = CurriculumEngine(
            memory_engine=me, benchmark_engine=benchmark, workspace_path=workspace
        )
        state = engine.load_curriculum(domain, curriculum_file)
        log = _get_orion_log()
        if log:
            log.info("Training", f"Curriculum loaded: {domain}", prompts=state.total_prompts)
        return {
            "status": "success",
            "domain": domain,
            "prompts": state.total_prompts,
            "threshold": state.graduation_threshold,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/training/run/{domain}")
async def run_training_cycle(domain: str, prompt_id: str = None):
    """Run a single training cycle."""
    try:
        from orion.core.learning.benchmark import BenchmarkEngine
        from orion.core.learning.curriculum import CurriculumEngine
        from orion.core.memory.engine import get_memory_engine

        settings = _load_user_settings()
        workspace = settings.get("workspace", "")
        me = get_memory_engine(workspace)
        benchmark = BenchmarkEngine()
        engine = CurriculumEngine(
            memory_engine=me, benchmark_engine=benchmark, workspace_path=workspace
        )

        # Reload curriculum from saved state
        state_dir = engine._training_dir / domain / "curriculum.json"
        if state_dir.exists():
            engine.load_curriculum(domain, str(state_dir))
        else:
            raise HTTPException(status_code=404, detail=f"Domain '{domain}' not loaded")

        result = await engine.run_training_cycle(domain, prompt_id)
        log = _get_orion_log()
        if log:
            log.info(
                "Training",
                f"Cycle complete: {domain}/{result.prompt_id}",
                score=result.quality_score,
            )
        return {
            "prompt_id": result.prompt_id,
            "cycle": result.cycle_number,
            "quality_score": result.quality_score,
            "similarity": result.similarity_score,
            "missing_concepts": result.missing_concepts,
            "patterns_created": len(result.patterns_created),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/training/auto/{domain}")
async def run_auto_training(domain: str, max_cycles: int = 3):
    """Run full auto-training for a domain."""
    try:
        from orion.core.learning.benchmark import BenchmarkEngine
        from orion.core.learning.curriculum import CurriculumEngine
        from orion.core.memory.engine import get_memory_engine

        settings = _load_user_settings()
        workspace = settings.get("workspace", "")
        me = get_memory_engine(workspace)
        benchmark = BenchmarkEngine()
        engine = CurriculumEngine(
            memory_engine=me, benchmark_engine=benchmark, workspace_path=workspace
        )

        state_dir = engine._training_dir / domain / "curriculum.json"
        if state_dir.exists():
            engine.load_curriculum(domain, str(state_dir))
        else:
            raise HTTPException(status_code=404, detail=f"Domain '{domain}' not loaded")

        results = await engine.run_full_curriculum(domain, max_cycles=max_cycles)
        state = engine.get_domain_status(domain)
        return {
            "domain": domain,
            "status": state.status if state else "unknown",
            "cycles_completed": len(results),
            "avg_score": state.current_avg_score if state else 0,
            "graduated": state.status == "graduated" if state else False,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/training/status")
async def get_training_status(domain: str = None):
    """Get training status for all or specific domain."""
    try:
        from orion.core.learning.benchmark import BenchmarkEngine
        from orion.core.learning.curriculum import CurriculumEngine
        from orion.core.memory.engine import get_memory_engine

        settings = _load_user_settings()
        workspace = settings.get("workspace", "")
        me = get_memory_engine(workspace)
        benchmark = BenchmarkEngine()
        engine = CurriculumEngine(
            memory_engine=me, benchmark_engine=benchmark, workspace_path=workspace
        )

        if domain:
            state = engine.get_domain_status(domain)
            if not state:
                return {"domain": domain, "status": "not_found"}
            return {
                "domain": state.domain,
                "status": state.status,
                "prompts": state.total_prompts,
                "cycles": state.completed_cycles,
                "avg_score": state.current_avg_score,
                "threshold": state.graduation_threshold,
            }
        else:
            states = engine.list_domains()
            return {
                "domains": [
                    {
                        "domain": s.domain,
                        "status": s.status,
                        "avg_score": s.current_avg_score,
                        "cycles": s.completed_cycles,
                    }
                    for s in states
                ]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/training/export/{domain}")
async def export_knowledge_pack(domain: str, version: str, name: str = None):
    """Export a graduated domain as a knowledge pack."""
    try:
        from orion.core.learning.knowledge_pack import KnowledgePackManager
        from orion.core.memory.engine import get_memory_engine

        settings = _load_user_settings()
        workspace = settings.get("workspace", "")
        me = get_memory_engine(workspace)
        mgr = KnowledgePackManager(me)
        pack = mgr.export_pack(
            domain=domain,
            name=name or f"Orion {domain.replace('_', ' ').title()}",
            version=version,
            description=f"Knowledge pack for {domain}",
        )
        return {
            "pack_id": pack.pack_id,
            "name": pack.name,
            "version": pack.version,
            "patterns": pack.pattern_count,
            "anti_patterns": pack.anti_pattern_count,
            "checksum": pack.checksum,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/training/import")
async def import_knowledge_pack(pack_path: str, strategy: str = "skip_existing"):
    """Import a knowledge pack."""
    try:
        from orion.core.learning.knowledge_pack import KnowledgePackManager
        from orion.core.memory.engine import get_memory_engine

        settings = _load_user_settings()
        workspace = settings.get("workspace", "")
        me = get_memory_engine(workspace)
        mgr = KnowledgePackManager(me)
        result = mgr.import_pack(pack_path, merge_strategy=strategy)
        return {
            "imported": result.patterns_imported,
            "skipped": result.patterns_skipped,
            "conflicted": result.patterns_conflicted,
            "domain": result.domain,
            "version": result.version,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/training/packs")
async def list_knowledge_packs():
    """List available and installed knowledge packs."""
    try:
        from orion.core.learning.knowledge_pack import KnowledgePackManager
        from orion.core.memory.engine import get_memory_engine

        settings = _load_user_settings()
        workspace = settings.get("workspace", "")
        me = get_memory_engine(workspace)
        mgr = KnowledgePackManager(me)
        return {"available": mgr.list_packs(), "installed": mgr.list_installed_packs()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
