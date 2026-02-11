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
Orion Agent -- Training CLI Commands (v7.1.0)

CLI commands for the knowledge distillation training workflow.
Handles: /train load, /train run, /train auto, /train status,
         /train export, /train import, /train packs

USAGE (from REPL):
    /train load legal_sa curriculum_legal.json
    /train run legal_sa
    /train auto legal_sa --max-cycles 3
    /train status
    /train export legal_sa 1.0.0
    /train import legal_sa_1.0.0.orionpack
    /train packs
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger("orion.cli.commands_training")


async def handle_train_command(
    command: str,
    router,
    memory_engine,
    console,
):
    """
    Dispatch /train subcommands.

    Args:
        command: The full command string (e.g., "/train load legal_sa file.json").
        router: The Router instance (for workspace_path access).
        memory_engine: The MemoryEngine instance.
        console: Console for output.
    """
    parts = command.strip().split()
    if len(parts) < 2:
        _print_train_help(console)
        return

    subcommand = parts[1].lower()
    args = parts[2:]

    workspace = getattr(router, "workspace_path", None) or ""

    if subcommand == "load":
        await _handle_load(args, workspace, memory_engine, console)
    elif subcommand == "run":
        await _handle_run(args, workspace, memory_engine, console)
    elif subcommand == "auto":
        await _handle_auto(args, workspace, memory_engine, console)
    elif subcommand == "status":
        await _handle_status(args, workspace, memory_engine, console)
    elif subcommand == "export":
        await _handle_export(args, workspace, memory_engine, console)
    elif subcommand == "import":
        await _handle_import(args, memory_engine, console)
    elif subcommand == "packs":
        await _handle_packs(memory_engine, console)
    else:
        _print_train_help(console)


def _print_train_help(console):
    """Print training command help."""
    console.print(
        "[bold]Training Commands:[/bold]\n"
        "  /train load <domain> <file>        -- Load a curriculum from JSON\n"
        "  /train run <domain> [prompt_id]    -- Run a single training cycle\n"
        "  /train auto <domain> [--max-cycles N] -- Auto-train to graduation\n"
        "  /train status [domain]             -- Show training status\n"
        "  /train export <domain> <version>   -- Export as knowledge pack\n"
        "  /train import <file> [--strategy skip_existing|overwrite|merge]\n"
        "  /train packs                       -- List knowledge packs"
    )


async def _handle_load(args, workspace, memory_engine, console):
    """Handle /train load <domain> <curriculum_file>."""
    if len(args) < 2:
        console.print("[red]Usage: /train load <domain> <curriculum_file>[/red]")
        return

    domain = args[0]
    curriculum_file = args[1]

    try:
        from orion.core.learning.benchmark import BenchmarkEngine
        from orion.core.learning.curriculum import CurriculumEngine

        benchmark = BenchmarkEngine()
        engine = CurriculumEngine(
            memory_engine=memory_engine,
            benchmark_engine=benchmark,
            workspace_path=workspace,
        )
        state = engine.load_curriculum(domain, curriculum_file)

        # Count difficulties
        curriculum = engine._curricula.get(domain, {})
        prompts = curriculum.get("prompts", [])
        diff_counts = {}
        for p in prompts:
            d = p.difficulty
            diff_counts[d] = diff_counts.get(d, 0) + 1

        diff_str = ", ".join(f"{v} {k}" for k, v in diff_counts.items())
        source_files = curriculum.get("source_files", [])
        source_str = ", ".join(source_files) if source_files else "none"

        console.print(
            f"[green]✅ Loaded curriculum: {curriculum.get('description', domain)}[/green]\n"
            f"   Domain: {domain}\n"
            f"   Prompts: {state.total_prompts}\n"
            f"   Difficulty: {diff_str}\n"
            f"   Source files: {source_str}"
        )

    except FileNotFoundError as e:
        console.print(f"[red]❌ {e}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Failed to load curriculum: {e}[/red]")


async def _handle_run(args, workspace, memory_engine, console):
    """Handle /train run <domain> [prompt_id]."""
    if len(args) < 1:
        console.print("[red]Usage: /train run <domain> [prompt_id][/red]")
        return

    domain = args[0]
    prompt_id = args[1] if len(args) > 1 else None

    try:
        from orion.core.learning.benchmark import BenchmarkEngine
        from orion.core.learning.curriculum import CurriculumEngine

        benchmark = BenchmarkEngine()
        engine = CurriculumEngine(
            memory_engine=memory_engine,
            benchmark_engine=benchmark,
            workspace_path=workspace,
        )

        # Try to reload curriculum from saved state
        state_dir = engine._training_dir / domain / "curriculum.json"
        if state_dir.exists():
            engine.load_curriculum(domain, str(state_dir))
        else:
            console.print(f"[red]❌ Domain '{domain}' not loaded. Use /train load first.[/red]")
            return

        start = time.time()
        console.print(f"[bold]🎓 Training cycle: {domain}[/bold]")

        result = await engine.run_training_cycle(domain, prompt_id)
        elapsed = time.time() - start

        state = engine.get_domain_status(domain)
        avg_pct = (state.current_avg_score * 100) if state else 0

        console.print(
            f"   ├── Prompt: {result.prompt_id} (cycle {result.cycle_number})\n"
            f"   ├── Quality score: {result.quality_score}/5\n"
            f"   ├── Similarity: {result.similarity_score:.2f}\n"
            f"   ├── Missing: {result.missing_concepts if result.missing_concepts else 'none'}\n"
            f"   ├── Patterns created: {len(result.patterns_created)}\n"
            f"   ├── Time: {elapsed:.1f}s\n"
            f"   └── Domain score: {avg_pct:.0f}% "
            f"(graduation at {state.graduation_threshold * 100:.0f}%)"
        )

    except Exception as e:
        console.print(f"[red]❌ Training failed: {e}[/red]")


async def _handle_auto(args, workspace, memory_engine, console):
    """Handle /train auto <domain> [--max-cycles N]."""
    if len(args) < 1:
        console.print("[red]Usage: /train auto <domain> [--max-cycles N][/red]")
        return

    domain = args[0]
    max_cycles = 3

    # Parse --max-cycles
    for i, a in enumerate(args):
        if a == "--max-cycles" and i + 1 < len(args):
            try:
                max_cycles = int(args[i + 1])
            except ValueError:
                pass

    try:
        from orion.core.learning.benchmark import BenchmarkEngine
        from orion.core.learning.curriculum import CurriculumEngine

        benchmark = BenchmarkEngine()
        engine = CurriculumEngine(
            memory_engine=memory_engine,
            benchmark_engine=benchmark,
            workspace_path=workspace,
        )

        # Reload curriculum
        state_dir = engine._training_dir / domain / "curriculum.json"
        if state_dir.exists():
            engine.load_curriculum(domain, str(state_dir))
        else:
            console.print(f"[red]❌ Domain '{domain}' not loaded. Use /train load first.[/red]")
            return

        start = time.time()
        console.print(f"[bold]🎓 Auto-training: {domain}[/bold]")

        results = await engine.run_full_curriculum(domain, max_cycles=max_cycles)
        elapsed = time.time() - start

        state = engine.get_domain_status(domain)
        total_patterns = sum(len(r.patterns_created) for r in results)

        status_emoji = "✅" if state and state.status == "graduated" else "🔄"
        status_text = state.status if state else "unknown"
        avg_pct = (state.current_avg_score * 100) if state else 0

        console.print(
            f"\n   {status_emoji} Status: {status_text}\n"
            f"   Average: {avg_pct:.0f}%\n"
            f"   Cycles completed: {len(results)}\n"
            f"   Patterns created: {total_patterns}\n"
            f"   Total time: {elapsed / 60:.1f} minutes"
        )

    except Exception as e:
        console.print(f"[red]❌ Auto-training failed: {e}[/red]")


async def _handle_status(args, workspace, memory_engine, console):
    """Handle /train status [domain]."""
    try:
        from orion.core.learning.curriculum import CurriculumEngine
        from orion.core.learning.benchmark import BenchmarkEngine

        benchmark = BenchmarkEngine()
        engine = CurriculumEngine(
            memory_engine=memory_engine,
            benchmark_engine=benchmark,
            workspace_path=workspace,
        )

        if args:
            domain = args[0]
            state = engine.get_domain_status(domain)
            if state:
                console.print(
                    f"[bold]🎓 Training Status: {domain}[/bold]\n"
                    f"   Status: {state.status}\n"
                    f"   Prompts: {state.total_prompts}\n"
                    f"   Cycles: {state.completed_cycles}\n"
                    f"   Average: {state.current_avg_score * 100:.0f}%\n"
                    f"   Best: {state.best_score * 100:.0f}%\n"
                    f"   Worst: {state.worst_score * 100:.0f}%\n"
                    f"   Threshold: {state.graduation_threshold * 100:.0f}%"
                )
            else:
                console.print(f"[yellow]No training data for domain: {domain}[/yellow]")
        else:
            states = engine.list_domains()
            if not states:
                console.print("[yellow]No training domains found. Use /train load to start.[/yellow]")
                return

            console.print("[bold]🎓 Training Status[/bold]")
            for s in states:
                status = s.status.upper() if isinstance(s.status, str) else s.status
                avg = f"{s.current_avg_score * 100:.0f}%" if s.current_avg_score else "--"
                console.print(
                    f"   {s.domain:<20} {status:<14} {avg:<8} {s.completed_cycles} cycles"
                )

    except Exception as e:
        console.print(f"[red]❌ Status check failed: {e}[/red]")


async def _handle_export(args, workspace, memory_engine, console):
    """Handle /train export <domain> <version>."""
    if len(args) < 2:
        console.print("[red]Usage: /train export <domain> <version>[/red]")
        return

    domain = args[0]
    version = args[1]

    try:
        from orion.core.learning.knowledge_pack import KnowledgePackManager
        from orion.core.learning.curriculum import CurriculumEngine
        from orion.core.learning.benchmark import BenchmarkEngine

        mgr = KnowledgePackManager(memory_engine)

        # Get training state for metadata
        benchmark = BenchmarkEngine()
        engine = CurriculumEngine(
            memory_engine=memory_engine,
            benchmark_engine=benchmark,
            workspace_path=workspace,
        )
        state = engine.get_domain_status(domain)

        pack = mgr.export_pack(
            domain=domain,
            name=f"Orion {domain.replace('_', ' ').title()}",
            version=version,
            description=f"Knowledge pack for {domain}",
            training_cycles=state.completed_cycles if state else 0,
            graduation_score=state.current_avg_score if state else 0.0,
        )

        pack_file = mgr.packs_dir / f"{domain}_{version}.orionpack"
        size_kb = pack_file.stat().st_size / 1024 if pack_file.exists() else 0

        console.print(
            f"[green]📦 Exported: {pack.name} v{version}[/green]\n"
            f"   File: {pack_file}\n"
            f"   Patterns: {pack.pattern_count} success + {pack.anti_pattern_count} anti-patterns\n"
            f"   Checksum: {pack.checksum[:40]}...\n"
            f"   Size: {size_kb:.0f} KB"
        )

    except Exception as e:
        console.print(f"[red]❌ Export failed: {e}[/red]")


async def _handle_import(args, memory_engine, console):
    """Handle /train import <pack_file> [--strategy ...]."""
    if len(args) < 1:
        console.print("[red]Usage: /train import <pack_file> [--strategy skip_existing|overwrite|merge][/red]")
        return

    pack_file = args[0]
    strategy = "skip_existing"

    for i, a in enumerate(args):
        if a == "--strategy" and i + 1 < len(args):
            strategy = args[i + 1]

    try:
        from orion.core.learning.knowledge_pack import KnowledgePackManager

        mgr = KnowledgePackManager(memory_engine)

        # Verify first
        if not mgr.verify_pack(pack_file):
            console.print("[red]❌ Pack checksum verification failed -- file may be corrupted[/red]")
            return

        result = mgr.import_pack(pack_file, merge_strategy=strategy)

        console.print(
            f"[green]📦 Imported: {result.domain} v{result.version}[/green]\n"
            f"   Patterns imported: {result.patterns_imported}\n"
            f"   Patterns skipped: {result.patterns_skipped}\n"
            f"   Patterns conflicted: {result.patterns_conflicted}\n"
            f"   Domain: {result.domain} -- ready to use"
        )

    except Exception as e:
        console.print(f"[red]❌ Import failed: {e}[/red]")


async def _handle_packs(memory_engine, console):
    """Handle /train packs."""
    try:
        from orion.core.learning.knowledge_pack import KnowledgePackManager

        mgr = KnowledgePackManager(memory_engine)

        installed = mgr.list_installed_packs()
        available = mgr.list_packs()

        console.print("[bold]📦 Knowledge Packs[/bold]")

        if installed:
            console.print("   [bold]Installed:[/bold]")
            for p in installed:
                console.print(
                    f"   ├── {p['domain']} v{p.get('pack_version', '?')} "
                    f"({p['pattern_count']} patterns)"
                )
        else:
            console.print("   [dim]No packs installed[/dim]")

        if available:
            console.print("   [bold]Available (local):[/bold]")
            for p in available:
                is_installed = any(
                    i["pack_id"] == p["pack_id"] for i in installed
                )
                status = "installed" if is_installed else "not installed"
                console.print(
                    f"   ├── {p['name']} v{p['version']} "
                    f"({p['pattern_count']} patterns) -- {status}"
                )
        else:
            console.print("   [dim]No packs available locally[/dim]")

    except Exception as e:
        console.print(f"[red]❌ Failed to list packs: {e}[/red]")
