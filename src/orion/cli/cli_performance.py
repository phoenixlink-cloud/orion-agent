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
"""CLI Performance Dashboard — ``/performance`` command.

Renders execution performance metrics in the terminal using the
``PerformanceMetrics`` engine.  Supports sub-commands:

    /performance            — Overview snapshot
    /performance trends     — Show improvement/regression trends
    /performance hotspots   — Error category hotspots
    /performance stacks     — Per-stack comparison
    /performance detail     — Full detail dump

See Phase 4D.4 specification.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("orion.cli.cli_performance")


def handle_performance_command(parts: list[str], console: Any) -> dict:
    """Entry point called from ``commands.py`` for ``/performance``."""
    action = parts[1].lower() if len(parts) > 1 else "overview"

    try:
        pm = _get_performance_metrics()
        if pm is None:
            console.print_info(
                "Performance metrics not available — no execution lessons recorded yet."
            )
            return {}

        if action == "overview":
            _render_overview(pm, console)
        elif action == "trends":
            _render_trends(pm, console)
        elif action == "hotspots":
            _render_hotspots(pm, console)
        elif action == "stacks":
            _render_stacks(pm, console)
        elif action == "detail":
            _render_overview(pm, console)
            _render_trends(pm, console)
            _render_hotspots(pm, console)
            _render_stacks(pm, console)
        else:
            console.print_info(
                "Usage:\n"
                "  /performance            Overview snapshot\n"
                "  /performance trends     Improvement trends\n"
                "  /performance hotspots   Error hotspots\n"
                "  /performance stacks     Per-stack comparison\n"
                "  /performance detail     Full detail"
            )
    except Exception as e:
        console.print_error(f"Performance dashboard error: {e}")

    return {}


# ---------------------------------------------------------------------------
# Sub-command renderers
# ---------------------------------------------------------------------------


def _render_overview(pm, console: Any) -> None:
    """Render the main performance overview."""
    m = pm.compute_metrics()
    if m.total_executions == 0:
        console.print_info("No executions recorded yet.")
        return

    console.print_info("╔══════════════════════════════════════╗")
    console.print_info("║     EXECUTION PERFORMANCE DASHBOARD  ║")
    console.print_info("╚══════════════════════════════════════╝")

    console._print(f"  Total executions:       {m.total_executions}")
    console._print(f"  Successful:             {m.successful}")
    console._print(f"  First-attempt success:  {m.first_attempt_successes}")
    console._print(f"  Fixed failures:         {m.failures_fixed}")
    console._print(f"  Permanent failures:     {m.permanent_failures}")
    console._print("")
    console._print(f"  Success rate:           {m.success_rate:.1%}")
    console._print(f"  First-attempt rate:     {m.first_attempt_success_rate:.1%}")
    console._print(f"  Fix rate:               {m.fix_rate:.1%}")
    console._print("")
    console._print(f"  Mean duration:          {m.mean_duration_seconds:.1f}s")
    console._print(f"  Mean retries:           {m.mean_retries:.1f}")
    console._print(f"  Mean time to fix:       {m.mean_time_to_resolution:.1f}s")

    if m.top_fixes:
        console._print("")
        console._print("  Top fixes applied:")
        for f in m.top_fixes[:3]:
            console._print(f"    {f['count']}x  {f['fix']}")


def _render_trends(pm, console: Any) -> None:
    """Render improvement/regression trends."""
    trends = pm.compute_trends()
    if not trends:
        console.print_info("Not enough data for trend analysis (need ≥20 executions).")
        return

    console._print("")
    console.print_info("Performance Trends (last 10 vs previous 10):")

    symbols = {"improving": "↑", "regressing": "↓", "stable": "→"}
    colors = {"improving": "green", "regressing": "red", "stable": "yellow"}

    for t in trends:
        sym = symbols.get(t.direction, "?")
        label = t.metric_name.replace("_", " ").title()
        delta_str = f"{t.delta:+.2%}" if "rate" in t.metric_name else f"{t.delta:+.2f}"
        console._print(f"  {sym} {label:<30} {t.current_value:.2f} ({delta_str})")


def _render_hotspots(pm, console: Any) -> None:
    """Render error category hotspots."""
    hotspots = pm.get_error_hotspots()
    if not hotspots:
        console.print_info("No error hotspots — clean execution history!")
        return

    console._print("")
    console.print_info("Error Hotspots:")
    for h in hotspots:
        bar_len = int(h["percentage"] / 5)  # Scale to ~20 chars max
        bar = "█" * bar_len
        console._print(
            f"  {h['category']:<25} {h['count']:>3}  ({h['percentage']:>5.1f}%)  {bar}"
        )


def _render_stacks(pm, console: Any) -> None:
    """Render per-stack comparison."""
    comparison = pm.get_stack_comparison()
    if not comparison:
        console.print_info("No multi-stack data available.")
        return

    console._print("")
    console.print_info("Stack Comparison:")
    console._print(f"  {'Stack':<12} {'Total':>6} {'Success':>8} {'FASR':>8} {'Retries':>8}")
    console._print(f"  {'─' * 12} {'─' * 6} {'─' * 8} {'─' * 8} {'─' * 8}")
    for s in comparison:
        console._print(
            f"  {s['stack']:<12} {s['total']:>6} "
            f"{s['success_rate']:>7.0%} {s['first_attempt_success_rate']:>7.0%} "
            f"{s['mean_retries']:>7.1f}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_performance_metrics():
    """Try to instantiate PerformanceMetrics from global memory engine."""
    try:
        from orion.ara.execution_memory import ExecutionMemory
        from orion.ara.performance_metrics import PerformanceMetrics
        from orion.core.memory.engine import get_memory_engine

        engine = get_memory_engine()
        em = ExecutionMemory(memory_engine=engine)
        return PerformanceMetrics(execution_memory=em)
    except Exception:
        return None
