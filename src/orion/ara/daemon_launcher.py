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
"""ARA Daemon Launcher — spawns the background daemon for ARA sessions.

Reads pending.json, loads the role profile, decomposes the goal via
ARALLMProvider, and runs the ARADaemon execution loop.

Supports all 11 AI providers via the unified call_provider router.

Can be invoked as a subprocess from cmd_work or run directly:
    python -m orion.ara.daemon_launcher
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("orion.ara.daemon_launcher")

DAEMON_DIR = Path.home() / ".orion" / "daemon"
SESSIONS_DIR = Path.home() / ".orion" / "sessions"


async def launch_from_pending() -> None:
    """Read pending.json and launch the daemon for that session."""
    pending_path = DAEMON_DIR / "pending.json"
    if not pending_path.exists():
        logger.error("No pending.json found at %s", pending_path)
        return

    config = json.loads(pending_path.read_text(encoding="utf-8"))
    session_id = config["session_id"]
    role_name = config["role_name"]
    goal = config["goal"]
    workspace_path = config.get("workspace_path", ".")
    role_source = config.get("role_source")
    project_mode = config.get("project_mode", "new")

    logger.info("Launching daemon for session %s (role=%s)", session_id, role_name)

    # Load role profile
    from orion.ara.role_profile import load_role

    if role_source and Path(role_source).exists():
        role = load_role(Path(role_source))
    else:
        from orion.ara.cli_commands import _find_role

        role = _find_role(role_name)
        if role is None:
            logger.error("Role '%s' not found", role_name)
            return

    # Load session
    from orion.ara.session import SessionState

    try:
        session = SessionState.load(session_id, sessions_dir=SESSIONS_DIR)
    except FileNotFoundError:
        logger.error("Session %s not found", session_id)
        return

    # Resolve provider and model from user's model configuration
    from orion.core.llm.config import load_model_config

    model_cfg = load_model_config()
    builder_rc = model_cfg.get_builder()
    provider = builder_rc.provider
    model = builder_rc.model

    # Role model_override takes precedence if set
    if role.model_override:
        model = role.model_override

    # Create goal engine with provider-agnostic LLM provider
    from orion.ara.goal_engine import GoalEngine
    from orion.ara.ollama_provider import ARALLMProvider
    from orion.ara.task_executor import ARATaskExecutor

    llm_provider = ARALLMProvider(provider=provider, model=model)
    engine = GoalEngine(llm_provider)

    logger.info("Decomposing goal into tasks via %s/%s...", provider, model)
    dag = await engine.decompose(goal)
    logger.info("Goal decomposed into %d tasks", dag.total_tasks)

    # Update session progress
    session.progress.total_tasks = dag.total_tasks

    # Create sandbox directory for file output
    sandbox_dir = SESSIONS_DIR / session_id / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    # Seed sandbox from workspace if continuing an existing project
    if project_mode == "continue":
        import shutil

        ws = Path(workspace_path)
        skip = {".git", ".orion-archive", "__pycache__", "node_modules", ".venv", ".env"}
        seeded = 0
        if ws.exists():
            for f in ws.rglob("*"):
                if not f.is_file():
                    continue
                parts = f.relative_to(ws).parts
                if any(p.startswith(".") or p in skip for p in parts):
                    continue
                dst = sandbox_dir / f.relative_to(ws)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(f), str(dst))
                seeded += 1
            logger.info("Seeded sandbox with %d files from workspace (continue mode)", seeded)

    # Save DAG to session dir for inspection
    dag_path = SESSIONS_DIR / session_id / "plan.json"
    dag_path.write_text(json.dumps(dag.to_dict(), indent=2), encoding="utf-8")

    # Load institutional memory for teach-student cycle
    from orion.core.memory.institutional import InstitutionalMemory

    try:
        institutional = InstitutionalMemory()
        logger.info(
            "Institutional memory loaded (%d patterns)",
            institutional.get_statistics().get("learned_patterns", 0),
        )
    except Exception as e:
        logger.warning("Could not load institutional memory: %s", e)
        institutional = None

    # Create task executor (provider-agnostic, context-aware, learning-enabled)
    executor = ARATaskExecutor(
        provider=provider,
        model=model,
        sandbox_dir=sandbox_dir,
        goal=goal,
        institutional_memory=institutional,
    )

    # Create and run daemon
    from orion.ara.daemon import ARADaemon, DaemonControl

    control = DaemonControl()

    daemon = ARADaemon(
        session=session,
        role=role,
        dag=dag,
        control=control,
        task_executor=executor.execute,
        task_executor_ref=executor,
    )

    # Clean up pending.json — daemon is now running
    pending_path.unlink(missing_ok=True)

    logger.info("Daemon starting execution loop...")
    await daemon.run()

    # Save final session state
    session.save()

    # Save final DAG state
    dag_path.write_text(json.dumps(dag.to_dict(), indent=2), encoding="utf-8")

    logger.info(
        "Daemon finished. Session %s status: %s",
        session_id,
        session.status.value,
    )


def main() -> None:
    """Entry point for subprocess invocation."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                str(Path.home() / ".orion" / "logs" / "daemon.log"),
                encoding="utf-8",
            ),
        ],
    )
    # Ensure log dir exists
    (Path.home() / ".orion" / "logs").mkdir(parents=True, exist_ok=True)

    logger.info("ARA Daemon Launcher starting...")
    asyncio.run(launch_from_pending())
    logger.info("ARA Daemon Launcher finished.")


if __name__ == "__main__":
    main()
