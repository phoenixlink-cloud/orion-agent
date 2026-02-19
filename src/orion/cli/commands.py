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
Orion Agent -- CLI Slash Command Handler (v9.0.0)

Handles all /slash commands: /workspace, /add, /drop, /clear, /undo,
/diff, /commit, /map, /mode, /status, /help, /settings, /tasks, /task,
/work, /pause, /resume, /cancel, /review, /role, /sessions, /setup,
/dashboard, /rollback, /plan-review, /ara-settings, /auth-switch.
"""

import os


def handle_command(
    cmd: str,
    console,
    workspace_path: str,
    mode: str,
    context_files: list = None,
    change_history: list = None,
) -> dict:
    """Handle slash commands -- familiar CLI patterns users expect."""
    parts = cmd.split()
    command = parts[0].lower()

    if context_files is None:
        context_files = []
    if change_history is None:
        change_history = []

    if command in ["/quit", "/exit"]:
        return "QUIT"

    elif command == "/workspace":
        return _handle_workspace(parts, console, workspace_path)

    elif command == "/add":
        return _handle_add(parts, console, workspace_path, context_files)

    elif command == "/drop":
        return _handle_drop(parts, console, context_files)

    elif command == "/clear":
        context_files.clear()
        console.print_success("Context cleared")
        return {"context_files": context_files}

    elif command == "/undo":
        return _handle_undo(parts, console, workspace_path, change_history)

    elif command == "/diff":
        return _handle_diff(console, workspace_path)

    elif command == "/commit":
        return _handle_commit(parts, console, workspace_path)

    elif command == "/map":
        return _handle_map(console, workspace_path)

    elif command == "/mode":
        return _handle_mode(parts, console, mode)

    elif command == "/status":
        console.print_status(workspace_path, mode)
        if context_files:
            console.print_info(f"Context files: {', '.join(context_files)}")
        return {}

    elif command == "/help":
        console.print_help()
        return {}

    elif command == "/doctor":
        try:
            import asyncio

            from orion.cli.doctor import run_doctor

            try:
                loop = asyncio.get_running_loop()
                # Already in async context -- schedule as task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    loop.run_in_executor(
                        pool, lambda: asyncio.run(run_doctor(console, workspace_path))
                    )
            except RuntimeError:
                # No running loop -- safe to use asyncio.run
                asyncio.run(run_doctor(console, workspace_path))
        except Exception as e:
            console.print_error(f"Doctor failed: {e}")
        return {}

    elif command == "/settings":
        try:
            import asyncio

            from orion.cli.settings_manager import run_settings

            action = parts[1] if len(parts) > 1 else "view"
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    loop.run_in_executor(pool, lambda: asyncio.run(run_settings(console, action)))
            except RuntimeError:
                asyncio.run(run_settings(console, action))
        except Exception as e:
            console.print_error(f"Settings failed: {e}")
        return {}

    elif command == "/health":
        try:
            from orion.integrations.health import IntegrationHealthChecker

            checker = IntegrationHealthChecker()
            dashboard = checker.get_dashboard()
            console.print_info(f"Health: {dashboard.get('summary', 'unknown')}")
        except ImportError:
            console.print_error("Health module not available")
        return {}

    elif command == "/connect":
        return _handle_connect(parts, console)

    elif command == "/disconnect":
        return _handle_disconnect(parts, console)

    elif command == "/key":
        return _handle_key(parts, console)

    elif command == "/memory":
        return _handle_memory(parts, console)

    elif command == "/bridge":
        return _handle_bridge(parts, console)

    elif command == "/log":
        try:
            from orion.core.learning.evolution import get_evolution_engine

            engine = get_evolution_engine()
            summary = engine.get_evolution_summary()
            console.print_info(f"Evolution: {summary}")
        except Exception:
            console.print_info("Activity log not available")
        return {}

    # =====================================================================
    # ARA Commands (Autonomous Role Architecture)
    # =====================================================================

    elif command == "/work":
        return _handle_ara_work(parts, console, workspace_path)

    elif command in ("/pause", "/resume", "/cancel"):
        return _handle_ara_session_control(command, console)

    elif command == "/review":
        return _handle_ara_review(parts, console)

    elif command == "/promote":
        return _handle_ara_promote(parts, console)

    elif command == "/reject":
        return _handle_ara_reject(parts, console)

    elif command == "/feedback":
        return _handle_ara_feedback(parts, console)

    elif command == "/notifications":
        return _handle_ara_notifications(parts, console)

    elif command == "/skill":
        return _handle_ara_skill(parts, console)

    elif command == "/role":
        return _handle_ara_role(parts, console)

    elif command == "/sessions":
        return _handle_ara_sessions(parts, console)

    elif command == "/setup":
        return _handle_ara_setup(console)

    elif command == "/dashboard":
        return _handle_ara_dashboard(console, workspace_path)

    elif command == "/rollback":
        return _handle_ara_rollback(parts, console)

    elif command == "/plan-review":
        return _handle_ara_plan_review(parts, console)

    elif command == "/ara-settings":
        return _handle_ara_settings(parts, console)

    elif command == "/auth-switch":
        return _handle_ara_auth_switch(parts, console)

    # =====================================================================
    # Google Account Commands
    # =====================================================================

    elif command == "/google":
        return _handle_google(parts, console)

    # =====================================================================
    # Sandbox Commands (Phase 3 -- Docker Governed Sandbox)
    # =====================================================================

    elif command == "/sandbox":
        return _handle_sandbox(parts, console)

    else:
        console.print_error(f"Unknown command: {command}")
        return {}


# =============================================================================
# INDIVIDUAL COMMAND HANDLERS
# =============================================================================


def _handle_workspace(parts, console, workspace_path):
    """Handle /workspace command and subcommands."""
    if len(parts) < 2:
        if workspace_path:
            console.print_info(f"Current workspace: {workspace_path}")
        else:
            console.print_info("No workspace set. Use /workspace <path>")
        return {}

    subcommand = parts[1].lower()

    if subcommand == "list":
        console.print_info("Use /workspace <path> to set workspace")
        return {}

    # Direct: /workspace <path>
    path = " ".join(parts[1:]).strip('"').strip("'")
    if os.path.isdir(path):
        console.print_success(f"Workspace set to: {path}")
        return {"workspace": os.path.abspath(path)}
    else:
        console.print_error(f"Invalid directory: {path}")
        return {}


def _handle_add(parts, console, workspace_path, context_files):
    """Handle /add <file> -- Add file to context."""
    if len(parts) < 2:
        if context_files:
            console.print_info(f"Files in context: {', '.join(context_files)}")
        else:
            console.print_info("No files in context. Use /add <file> to add files.")
        return {}

    file_pattern = " ".join(parts[1:]).strip('"').strip("'")
    if workspace_path:
        import glob

        full_pattern = os.path.join(workspace_path, file_pattern)
        matches = glob.glob(full_pattern, recursive=True)
        if matches:
            added = []
            for match in matches:
                rel_path = os.path.relpath(match, workspace_path)
                if rel_path not in context_files:
                    context_files.append(rel_path)
                    added.append(rel_path)
            if added:
                console.print_success(f"Added to context: {', '.join(added)}")
            else:
                console.print_info("Files already in context")
            return {"context_files": context_files}
        else:
            console.print_error(f"No files match: {file_pattern}")
            return {}
    else:
        console.print_error("Set workspace first with /workspace <path>")
        return {}


def _handle_drop(parts, console, context_files):
    """Handle /drop <file> -- Remove file from context."""
    if len(parts) < 2:
        console.print_info("Usage: /drop <file> or /drop all")
        return {}

    target = parts[1]
    if target.lower() == "all":
        context_files.clear()
        console.print_success("Cleared all files from context")
    else:
        if target in context_files:
            context_files.remove(target)
            console.print_success(f"Dropped from context: {target}")
        else:
            console.print_error(f"File not in context: {target}")
    return {"context_files": context_files}


def _handle_undo(parts, console, workspace_path, change_history):
    """Handle /undo -- Revert last change using git safety net."""
    if not workspace_path:
        console.print_error("Set workspace first with /workspace <path>")
        return {}

    try:
        from orion.core.editing.safety import get_git_safety

        safety = get_git_safety(workspace_path)

        subcommand = parts[1].lower() if len(parts) > 1 else ""

        if subcommand == "all":
            result = safety.undo_all()
            if result.success:
                console.print_success(f"Undo all: {result.message}")
            else:
                console.print_error(result.message)
            return {"change_history": []}

        if subcommand == "stack":
            stack = safety.get_undo_stack()
            if stack:
                console.print_info("Undo stack:")
                for entry in stack:
                    console._print(
                        f"  [{entry['index']}] {entry['hash']} {entry['description']} ({entry['files']} files)"
                    )
            else:
                console.print_info("Undo stack is empty")
            return {}

        if subcommand == "history":
            history = safety.get_edit_history()
            if history:
                console.print_info("Edit history:")
                for entry in history[:15]:
                    icon = {"savepoint": "●", "edit": "✎", "user": "○"}.get(entry["type"], "?")
                    console._print(f"  {icon} {entry['hash']} {entry['message']}")
            else:
                console.print_info("No edit history")
            return {}

        # Default: undo last
        if safety.get_savepoint_count() > 0:
            result = safety.undo()
            if result.success:
                console.print_success(
                    f"Undo: {result.message} (restored {result.files_restored} files)"
                )
            else:
                console.print_error(result.message)
            return {"change_history": change_history}
    except Exception:
        pass

    console.print_info("No changes to undo. Use /undo stack to see available savepoints.")
    return {"change_history": change_history}


def _handle_diff(console, workspace_path):
    """Handle /diff -- Show pending changes."""
    if workspace_path:
        try:
            import subprocess

            result = subprocess.run(
                ["git", "diff", "--stat"], cwd=workspace_path, capture_output=True, text=True
            )
            if result.stdout.strip():
                console.print_info("Pending changes:")
                console._print(result.stdout)
            else:
                console.print_info("No pending changes")
        except Exception as e:
            console.print_error(f"Could not get diff: {e}")
    else:
        console.print_error("Set workspace first")
    return {}


def _handle_commit(parts, console, workspace_path):
    """Handle /commit [msg] -- Commit changes to git."""
    if not workspace_path:
        console.print_error("Set workspace first")
        return {}

    msg = " ".join(parts[1:]) if len(parts) > 1 else "orion: automated changes"
    try:
        import subprocess

        subprocess.run(["git", "add", "-A"], cwd=workspace_path, check=True)
        result = subprocess.run(
            ["git", "commit", "-m", msg], cwd=workspace_path, capture_output=True, text=True
        )
        if result.returncode == 0:
            console.print_success(f"Committed: {msg}")
        else:
            console.print_info("Nothing to commit")
    except Exception as e:
        console.print_error(f"Commit failed: {e}")
    return {}


def _handle_map(console, workspace_path):
    """Handle /map -- Show repository map."""
    if not workspace_path:
        console.print_error("Set workspace first")
        return {}

    console.print_info("Repository map:")
    try:
        from orion.core.context.repo_map import generate_repo_map

        repo_map = generate_repo_map(workspace_path)
        console._print(repo_map)
    except ImportError:
        for root, dirs, files in os.walk(workspace_path):
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in ["node_modules", "__pycache__", "venv", ".git"]
            ]
            level = root.replace(workspace_path, "").count(os.sep)
            indent = "  " * level
            folder = os.path.basename(root)
            if level < 3:
                console._print(f"{indent}{folder}/")
                for f in files[:10]:
                    console._print(f"{indent}  {f}")
                if len(files) > 10:
                    console._print(f"{indent}  ... and {len(files) - 10} more")
    return {}


def _handle_mode(parts, console, mode):
    """Handle /mode [new_mode] -- Show or change mode."""
    valid_modes = {"safe", "pro", "project"}

    if len(parts) < 2:
        console.print_info(f"Current mode: {mode.upper()}")
        return {}

    new_mode = parts[1].lower()
    if new_mode in valid_modes:
        mode_desc = {
            "safe": "SAFE (read-only)",
            "pro": "PRO (file operations with approval)",
            "project": "PROJECT (file + command execution with approval)",
        }
        console.print_success(f"Mode switched to: {mode_desc.get(new_mode, new_mode.upper())}")
        return {"mode": new_mode}
    else:
        console.print_error(f"Invalid mode. Use: {', '.join(sorted(valid_modes))}")
        return {}


def _handle_connect(parts, console):
    """Handle /connect <platform> [token] -- Connect a platform."""
    if len(parts) < 2:
        console.print_info("Usage: /connect <platform> [token]")
        console.print_info("  /connect github          -- auto-detect gh CLI")
        console.print_info("  /connect slack xoxb-...  -- store bot token")
        console.print_info("  /connect                 -- list all platforms")
        try:
            from orion.integrations.platforms import get_platform_registry

            registry = get_platform_registry()
            for p in registry.list_all():
                status = "✓" if p.connected else "·"
                console._print(f"  {status} {p.id:<15} {p.name} ({p.auth_method.value})")
        except Exception:
            pass
        return {}

    platform_id = parts[1].lower()
    token = parts[2] if len(parts) > 2 else None

    try:
        from orion.integrations.platforms import get_platform_registry

        registry = get_platform_registry()
        platform = registry.get(platform_id)
        if not platform:
            console.print_error(f"Unknown platform: {platform_id}")
            return {}

        if not token and platform.cli_tool:
            import shutil

            if shutil.which(platform.cli_tool):
                console.print_success(
                    f"{platform.name} connected via {platform.cli_tool} CLI (auto-detected)"
                )
                return {}
            else:
                console.print_error(
                    f"{platform.cli_tool} CLI not found. Install it or provide a token."
                )
                if platform.setup_instructions:
                    console.print_info(f"  Setup: {platform.setup_instructions}")
                return {}

        if not token:
            console.print_info(f"Usage: /connect {platform_id} <token>")
            if platform.setup_instructions:
                console.print_info(f"  Setup: {platform.setup_instructions}")
            if platform.setup_url:
                console.print_info(f"  URL: {platform.setup_url}")
            return {}

        from orion.security.store import get_secure_store

        store = get_secure_store()
        backend = store.set_key(platform.secure_store_key or platform.id, token)
        if platform.env_var:
            os.environ[platform.env_var] = token
        registry.refresh()
        console.print_success(f"{platform.name} connected (stored in {backend})")
    except Exception as e:
        console.print_error(f"Connect failed: {e}")
    return {}


def _handle_disconnect(parts, console):
    """Handle /disconnect <platform> -- Disconnect a platform."""
    if len(parts) < 2:
        console.print_info("Usage: /disconnect <platform>")
        return {}

    platform_id = parts[1].lower()
    try:
        from orion.integrations.platforms import get_platform_registry
        from orion.security.store import get_secure_store

        registry = get_platform_registry()
        platform = registry.get(platform_id)
        if not platform:
            console.print_error(f"Unknown platform: {platform_id}")
            return {}

        store = get_secure_store()
        store.delete_key(platform.secure_store_key or platform.id)
        if platform.env_var:
            os.environ.pop(platform.env_var, None)
        registry.refresh()
        console.print_success(f"{platform.name} disconnected")
    except Exception as e:
        console.print_error(f"Disconnect failed: {e}")
    return {}


def _handle_key(parts, console):
    """Handle /key set|remove|status -- Manage API keys."""
    if len(parts) < 2:
        console.print_info("Usage:")
        console.print_info("  /key status              -- Show configured keys")
        console.print_info("  /key set <provider> <key> -- Store an API key")
        console.print_info("  /key remove <provider>    -- Remove an API key")
        return {}

    action = parts[1].lower()

    if action == "status":
        try:
            from orion.security.store import get_secure_store

            store = get_secure_store()
            providers = store.list_providers()
            if providers:
                console.print_info("Configured API keys:")
                for p in providers:
                    console._print(f"  ✓ {p}")
            else:
                console.print_info("No API keys stored")
        except Exception as e:
            console.print_error(f"Could not check keys: {e}")
        return {}

    if action == "set":
        if len(parts) < 4:
            console.print_info("Usage: /key set <provider> <key>")
            return {}
        provider = parts[2]
        key = parts[3]
        try:
            from orion.security.store import get_secure_store

            store = get_secure_store()
            backend = store.set_key(provider, key)
            console.print_success(f"Key for '{provider}' stored in {backend}")
        except Exception as e:
            console.print_error(f"Failed to store key: {e}")
        return {}

    if action == "remove":
        if len(parts) < 3:
            console.print_info("Usage: /key remove <provider>")
            return {}
        provider = parts[2]
        try:
            from orion.security.store import get_secure_store

            store = get_secure_store()
            store.delete_key(provider)
            console.print_success(f"Key for '{provider}' removed")
        except Exception as e:
            console.print_error(f"Failed to remove key: {e}")
        return {}

    console.print_error(f"Unknown key action: {action}. Use: set, remove, status")
    return {}


def _handle_memory(parts, console):
    """Handle /memory [search <query> | stats | evolution] -- View memory stats or search."""
    try:
        from orion.core.memory.engine import get_memory_engine

        engine = get_memory_engine()

        if len(parts) >= 3 and parts[1].lower() == "search":
            query = " ".join(parts[2:])
            memories = engine.recall(query, max_results=5)
            if memories:
                console.print_info(f"Found {len(memories)} memories for '{query}':")
                for m in memories:
                    tier_label = {1: "Session", 2: "Project", 3: "Global"}[m.tier]
                    conf = f"{m.confidence:.0%}"
                    console._print(f"  [{tier_label}/{conf}] {m.content[:120]}")
            else:
                console.print_info(f"No memories found for '{query}'")
            return {}

        if len(parts) >= 2 and parts[1].lower() == "evolution":
            snapshot = engine.get_evolution_snapshot()
            console.print_info("Evolution Snapshot:")
            console._print(f"  Total interactions:  {snapshot.total_interactions}")
            console._print(f"  Approval rate:       {snapshot.approval_rate:.1%}")
            console._print(f"  Avg quality:         {snapshot.avg_quality_score:.2f}")
            console._print(f"  Patterns learned:    {snapshot.patterns_learned}")
            console._print(f"  Anti-patterns:       {snapshot.anti_patterns_learned}")
            console._print(f"  Domains mastered:    {snapshot.domains_mastered}")
            console._print(f"  Project memories:    {snapshot.tier2_entries}")
            console._print(f"  Global memories:     {snapshot.tier3_entries}")
            if snapshot.top_strengths:
                console._print(f"  Strengths:           {', '.join(snapshot.top_strengths)}")
            if snapshot.top_weaknesses:
                console._print(f"  Weaknesses:          {', '.join(snapshot.top_weaknesses)}")
            return {}

        stats = engine.get_stats()
        console.print_info("Memory Engine Stats:")
        console._print(f"  Session (Tier 1):    {stats.tier1_entries} entries")
        console._print(f"  Project (Tier 2):    {stats.tier2_entries} entries")
        console._print(f"  Global  (Tier 3):    {stats.tier3_entries} entries")
        console._print(f"  Approvals:           {stats.total_approvals}")
        console._print(f"  Rejections:          {stats.total_rejections}")
        console._print(
            f"  Approval rate:       {stats.approval_rate:.1%}"
            if (stats.total_approvals + stats.total_rejections) > 0
            else "  Approval rate:       N/A"
        )
        console._print(f"  Patterns learned:    {stats.patterns_learned}")
        console._print(f"  Anti-patterns:       {stats.anti_patterns_learned}")
        console._print(f"  Preferences stored:  {stats.preferences_stored}")
        console._print(f"  Promotions (T2->T3): {stats.promotions_count}")
    except Exception as e:
        console.print_info(f"Memory engine not available: {e}")
    return {}


def _handle_bridge(parts, console):
    """Handle /bridge [enable|disable|status|revoke] -- Messaging bridge management."""
    try:
        from orion.bridges.base import get_bridge_manager

        if len(parts) < 2:
            # Show status
            manager = get_bridge_manager()
            status = manager.get_status()
            if not status:
                console.print_info("No bridges configured. Use: /bridge enable <platform> <token>")
                console.print_info("Supported platforms: telegram, slack, discord")
            else:
                console.print_info("Messaging Bridges:")
                for name, info in status.items():
                    state = (
                        "🟢 running"
                        if info["running"]
                        else ("🟡 enabled" if info["enabled"] else "⚫ disabled")
                    )
                    console._print(
                        f"  {name}: {state} | {info['authorized_users']} users | {info['total_requests']} requests"
                    )
            return {}

        subcmd = parts[1].lower()

        if subcmd == "enable":
            if len(parts) < 4:
                console.print_info("Usage: /bridge enable <telegram|slack|discord> <bot_token>")
                return {}
            platform = parts[2].lower()
            token = parts[3]
            if platform not in ("telegram", "slack", "discord"):
                console.print_error(f"Unknown platform: {platform}. Use: telegram, slack, discord")
                return {}
            manager = get_bridge_manager()
            passphrase = manager.enable(platform, token)
            console.print_info(f"✅ {platform.title()} bridge enabled!")
            console.print_info(f"🔑 Auth passphrase: {passphrase}")
            console.print_info(
                f"Send this passphrase to your {platform.title()} bot to authenticate."
            )
            console.print_info("⚠️  Keep this passphrase secret -- it controls access to Orion.")

        elif subcmd == "disable":
            if len(parts) < 3:
                console.print_info("Usage: /bridge disable <telegram|slack|discord>")
                return {}
            platform = parts[2].lower()
            manager = get_bridge_manager()
            if manager.disable(platform):
                console.print_info(f"⚫ {platform.title()} bridge disabled.")
            else:
                console.print_error(f"No {platform} bridge found.")

        elif subcmd == "status":
            manager = get_bridge_manager()
            status = manager.get_status()
            if not status:
                console.print_info("No bridges configured.")
            else:
                for name, info in status.items():
                    state = (
                        "🟢 running"
                        if info["running"]
                        else ("🟡 enabled" if info["enabled"] else "⚫ disabled")
                    )
                    console._print(f"\n  [{name.upper()}] {state}")
                    console._print(f"    Authorized users: {info['authorized_users']}")
                    console._print(f"    Total requests:   {info['total_requests']}")
                    console._print(f"    Rate limit:       {info['rate_limit']}/min")
                    console._print(f"    Workspace:        {info['workspace'] or '(not set)'}")

        elif subcmd == "revoke":
            if len(parts) < 4:
                console.print_info("Usage: /bridge revoke <platform> <user_id>")
                return {}
            platform = parts[2].lower()
            user_id = parts[3]
            manager = get_bridge_manager()
            if manager.revoke(platform, user_id):
                console.print_info(f"🔒 Revoked access for user {user_id} on {platform}.")
            else:
                console.print_error(f"User {user_id} not found on {platform}.")

        else:
            console.print_info("Bridge commands: enable, disable, status, revoke")

    except Exception as e:
        console.print_error(f"Bridge error: {e}")
    return {}


# =============================================================================
# ARA COMMAND HANDLERS (Autonomous Role Architecture)
# =============================================================================


def _handle_ara_work(parts, console, workspace_path):
    """Handle /work <role> <goal> -- Start an autonomous session."""
    if len(parts) < 3:
        console.print_info("Usage: /work <role> <goal>")
        console.print_info('  Example: /work software-engineer "Add error handling to api.py"')
        try:
            from orion.ara.cli_commands import list_available_roles

            roles = list_available_roles()
            if roles:
                console.print_info(f"  Available roles: {', '.join(roles)}")
        except Exception:
            pass
        return {}

    role_name = parts[1]
    goal = " ".join(parts[2:]).strip('"').strip("'")
    try:
        from orion.ara.cli_commands import cmd_work

        result = cmd_work(role_name, goal, workspace_path=workspace_path)
        if result.success:
            console.print_success(result.message)
        else:
            console.print_error(result.message)
    except Exception as e:
        console.print_error(f"ARA work failed: {e}")
    return {}


def _handle_ara_session_control(command, console):
    """Handle /pause, /resume, /cancel -- Session control."""
    cmd_map = {
        "/pause": "cmd_pause",
        "/resume": "cmd_resume",
        "/cancel": "cmd_cancel",
    }
    try:
        from orion.ara import cli_commands as ara

        func = getattr(ara, cmd_map[command])
        result = func()
        if result.success:
            console.print_success(result.message)
        else:
            console.print_error(result.message)
    except Exception as e:
        console.print_error(f"ARA {command} failed: {e}")
    return {}


def _handle_ara_review(parts, console):
    """Handle /review [session_id] -- Review sandbox changes for promotion."""
    session_id = parts[1] if len(parts) > 1 else None
    try:
        from orion.ara.cli_commands import cmd_review

        result = cmd_review(session_id=session_id)
        if result.success:
            console.print_success(result.message)
            if result.data:
                for key, val in result.data.items():
                    if key != "raw":
                        console._print(f"    {key}: {val}")
        else:
            console.print_error(result.message)
    except Exception as e:
        console.print_error(f"ARA review failed: {e}")
    return {}


def _handle_ara_role(parts, console):
    """Handle /role <subcommand> -- Role management."""
    if len(parts) < 2:
        console.print_info("Usage:")
        console.print_info("  /role list              -- List all roles")
        console.print_info("  /role show <name>       -- Show role details")
        console.print_info("  /role create <name>     -- Create a new role")
        console.print_info("  /role delete <name>     -- Delete a user role")
        console.print_info("  /role example           -- Show example YAML")
        console.print_info("  /role validate <path>   -- Validate a role file")
        return {}

    sub = parts[1].lower()
    try:
        from orion.ara import cli_commands as ara

        if sub == "list":
            result = ara.cmd_role_list()
            if result.success:
                console.print_info(result.message)
                if result.data and result.data.get("roles"):
                    for r in result.data["roles"]:
                        source = r.get("source", "")
                        tag = " (starter)" if source == "starter" else ""
                        console._print(
                            f"    {r['name']}{tag} — scope: {r.get('scope', '?')}, auth: {r.get('auth_method', '?')}"
                        )
            else:
                console.print_error(result.message)

        elif sub == "show":
            if len(parts) < 3:
                console.print_info("Usage: /role show <name>")
                return {}
            result = ara.cmd_role_show(parts[2])
            if result.success:
                console.print_info(result.message)
            else:
                console.print_error(result.message)

        elif sub == "create":
            if len(parts) < 3:
                console.print_info("Usage: /role create <name> [--scope coding] [--auth pin]")
                return {}
            name = parts[2]
            scope = "coding"
            auth = "pin"
            for i, p in enumerate(parts[3:], 3):
                if p == "--scope" and i + 1 < len(parts):
                    scope = parts[i + 1]
                elif p == "--auth" and i + 1 < len(parts):
                    auth = parts[i + 1]
            result = ara.cmd_role_create(name, scope=scope, auth_method=auth)
            if result.success:
                console.print_success(result.message)
            else:
                console.print_error(result.message)

        elif sub == "delete":
            if len(parts) < 3:
                console.print_info("Usage: /role delete <name>")
                return {}
            result = ara.cmd_role_delete(parts[2])
            if result.success:
                console.print_success(result.message)
            else:
                console.print_error(result.message)

        elif sub == "example":
            result = ara.cmd_role_example()
            console._print(result.message)

        elif sub == "validate":
            if len(parts) < 3:
                console.print_info("Usage: /role validate <path-to-yaml>")
                return {}
            result = ara.cmd_role_validate(parts[2])
            if result.success:
                console.print_success(result.message)
            else:
                console.print_error(result.message)

        else:
            console.print_error(f"Unknown role subcommand: {sub}")

    except Exception as e:
        console.print_error(f"ARA role failed: {e}")
    return {}


def _handle_ara_sessions(parts, console):
    """Handle /sessions [cleanup] -- List or clean up sessions."""
    try:
        from orion.ara import cli_commands as ara

        if len(parts) > 1 and parts[1].lower() == "cleanup":
            max_age = 30
            if len(parts) > 2:
                try:
                    max_age = int(parts[2])
                except ValueError:
                    pass
            result = ara.cmd_sessions_cleanup(max_age_days=max_age)
        else:
            result = ara.cmd_sessions()

        if result.success:
            console.print_info(result.message)
            if result.data and result.data.get("sessions"):
                for s in result.data["sessions"]:
                    status_icon = {
                        "running": "▶",
                        "paused": "⏸",
                        "completed": "✓",
                        "failed": "✗",
                        "cancelled": "⊘",
                    }.get(s.get("status", ""), "?")
                    console._print(
                        f"    {status_icon} {s['session_id'][:8]}  {s.get('role', '?')} — {s.get('goal', '?')[:60]}"
                    )
        else:
            console.print_error(result.message)
    except Exception as e:
        console.print_error(f"ARA sessions failed: {e}")
    return {}


def _handle_ara_setup(console):
    """Handle /setup -- Run ARA first-time setup wizard."""
    try:
        from orion.ara.cli_commands import cmd_setup

        result = cmd_setup()
        if result.success:
            console.print_success(result.message)
        else:
            console.print_info(result.message)

        if result.data and result.data.get("dry_run_scenarios"):
            console._print("\n  Dry-run scenarios:")
            for s in result.data["dry_run_scenarios"]:
                console._print(f"    {s['action']}: {s['result']}")
    except Exception as e:
        console.print_error(f"ARA setup failed: {e}")
    return {}


def _handle_ara_dashboard(console, workspace_path):
    """Handle /dashboard -- Show ARA morning dashboard."""
    try:
        from orion.ara.dashboard import MorningDashboard

        dash = MorningDashboard()

        # Check for pending reviews first
        pending = dash.check_pending_reviews()
        if pending:
            startup_msg = dash.get_startup_message()
            if startup_msg:
                console.print_info(startup_msg)
            # Show the most recent pending session's dashboard
            session_id = pending[0]["session_id"]
            output = dash.render(session_id)
            console._print(output)
        else:
            console.print_info(
                "No pending ARA sessions to review. Start one with /work <role> <goal>."
            )
    except Exception as e:
        console.print_error(f"ARA dashboard failed: {e}")
    return {}


def _handle_ara_rollback(parts, console):
    """Handle /rollback <checkpoint_id> [session_id] -- Rollback to checkpoint."""
    if len(parts) < 2:
        console.print_info("Usage: /rollback <checkpoint_id> [session_id]")
        return {}
    checkpoint_id = parts[1]
    session_id = parts[2] if len(parts) > 2 else None
    try:
        from orion.ara.cli_commands import cmd_rollback

        result = cmd_rollback(checkpoint_id, session_id=session_id)
        if result.success:
            console.print_success(result.message)
        else:
            console.print_error(result.message)
    except Exception as e:
        console.print_error(f"ARA rollback failed: {e}")
    return {}


def _handle_ara_plan_review(parts, console):
    """Handle /plan-review [session_id] -- Review the current task plan."""
    session_id = parts[1] if len(parts) > 1 else None
    try:
        from orion.ara.cli_commands import cmd_plan_review

        result = cmd_plan_review(session_id=session_id)
        if result.success:
            console.print_info(result.message)
        else:
            console.print_error(result.message)
    except Exception as e:
        console.print_error(f"ARA plan-review failed: {e}")
    return {}


def _handle_ara_settings(parts, console):
    """Handle /ara-settings [key=value ...] -- View or update ARA settings."""
    try:
        from orion.ara.cli_commands import cmd_settings_ara

        settings = None
        if len(parts) > 1:
            settings = {}
            for part in parts[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    # Auto-convert booleans and numbers
                    if v.lower() in ("true", "false"):
                        v = v.lower() == "true"
                    else:
                        try:
                            v = int(v)
                        except ValueError:
                            try:
                                v = float(v)
                            except ValueError:
                                pass
                    settings[k] = v

        result = cmd_settings_ara(settings=settings)
        if result.success:
            console.print_info(result.message)
        else:
            console.print_error(result.message)
    except Exception as e:
        console.print_error(f"ARA settings failed: {e}")
    return {}


def _handle_ara_auth_switch(parts, console):
    """Handle /auth-switch <method> <current_credential> -- Switch auth method."""
    if len(parts) < 3:
        console.print_info("Usage: /auth-switch <pin|totp|none> <current_credential>")
        return {}
    try:
        from orion.ara.cli_commands import cmd_auth_switch

        result = cmd_auth_switch(parts[1], parts[2])
        if result.success:
            console.print_success(result.message)
        else:
            console.print_error(result.message)
    except Exception as e:
        console.print_error(f"ARA auth-switch failed: {e}")
    return {}


def _handle_ara_promote(parts, console):
    """Handle /promote [session_id] [pin] -- Promote sandbox files to workspace."""
    session_id = parts[1] if len(parts) > 1 else None
    credential = parts[2] if len(parts) > 2 else None
    try:
        from orion.ara.cli_commands import cmd_promote

        result = cmd_promote(session_id=session_id, credential=credential)
        if result.success:
            console.print_success(result.message)
        else:
            console.print_error(result.message)
            if "auth" in result.message.lower():
                console.print_info("Hint: /promote <session_id> <pin>")
    except Exception as e:
        console.print_error(f"Promote failed: {e}")
    return {}


def _handle_ara_reject(parts, console):
    """Handle /reject [session_id] -- Reject sandbox changes."""
    session_id = parts[1] if len(parts) > 1 else None
    try:
        from orion.ara.cli_commands import cmd_reject

        result = cmd_reject(session_id=session_id)
        if result.success:
            console.print_success(result.message)
        else:
            console.print_error(result.message)
    except Exception as e:
        console.print_error(f"Reject failed: {e}")
    return {}


def _handle_ara_feedback(parts, console):
    """Handle /feedback <session_id> <rating> [comment] -- Submit user feedback."""
    if len(parts) < 3:
        console.print_info("Usage: /feedback <session_id> <1-5> [comment]")
        return {}
    try:
        from orion.ara.cli_commands import cmd_feedback

        session_id = parts[1]
        rating = int(parts[2])
        comment = " ".join(parts[3:]) if len(parts) > 3 else None
        result = cmd_feedback(session_id=session_id, rating=rating, comment=comment)
        if result.success:
            console.print_success(result.message)
        else:
            console.print_error(result.message)
    except ValueError:
        console.print_error("Rating must be a number 1-5.")
    except Exception as e:
        console.print_error(f"Feedback failed: {e}")
    return {}


def _handle_ara_skill(parts, console):
    """Handle /skill <subcommand> -- Skill management."""
    if len(parts) < 2:
        console.print_info("Usage:")
        console.print_info("  /skill list              -- List all skills")
        console.print_info("  /skill show <name>       -- Show skill details")
        console.print_info("  /skill create <name>     -- Create a new skill")
        console.print_info("  /skill delete <name>     -- Delete a skill")
        console.print_info("  /skill scan <name>       -- Re-scan skill with SkillGuard")
        console.print_info("  /skill assign <skill> <role>   -- Assign skill to role")
        console.print_info("  /skill unassign <skill> <role> -- Remove skill from role")
        console.print_info("  /skill groups            -- List skill groups")
        console.print_info("  /skill group-create <name>     -- Create a skill group")
        console.print_info("  /skill group-delete <name>     -- Delete a skill group")
        console.print_info("  /skill group-add <skill> <group> -- Add skill to group")
        return {}

    sub = parts[1].lower()
    try:
        from orion.ara import cli_commands as ara

        if sub == "list":
            tag = None
            for i, p in enumerate(parts[2:], 2):
                if p == "--tag" and i + 1 < len(parts):
                    tag = parts[i + 1]
            result = ara.cmd_skill_list(tag=tag)
            if result.success:
                console.print_info(result.message)
            else:
                console.print_error(result.message)

        elif sub == "show":
            if len(parts) < 3:
                console.print_info("Usage: /skill show <name>")
                return {}
            result = ara.cmd_skill_show(parts[2])
            if result.success:
                console.print_info(result.message)
            else:
                console.print_error(result.message)

        elif sub == "create":
            if len(parts) < 3:
                console.print_info(
                    'Usage: /skill create <name> [--desc "description"] [--tag tag1,tag2]'
                )
                return {}
            name = parts[2]
            desc = ""
            tags = []
            for i, p in enumerate(parts[3:], 3):
                if p == "--desc" and i + 1 < len(parts):
                    desc = parts[i + 1]
                elif p == "--tag" and i + 1 < len(parts):
                    tags = [t.strip() for t in parts[i + 1].split(",")]
            result = ara.cmd_skill_create(name=name, description=desc, tags=tags if tags else None)
            if result.success:
                console.print_success(result.message)
            else:
                console.print_error(result.message)

        elif sub == "delete":
            if len(parts) < 3:
                console.print_info("Usage: /skill delete <name>")
                return {}
            result = ara.cmd_skill_delete(parts[2])
            if result.success:
                console.print_success(result.message)
            else:
                console.print_error(result.message)

        elif sub == "scan":
            if len(parts) < 3:
                console.print_info("Usage: /skill scan <name>")
                return {}
            result = ara.cmd_skill_scan(parts[2])
            if result.success:
                console.print_info(result.message)
            else:
                console.print_error(result.message)

        elif sub == "assign":
            if len(parts) < 4:
                console.print_info("Usage: /skill assign <skill-name> <role-name>")
                return {}
            result = ara.cmd_skill_assign(parts[2], parts[3])
            if result.success:
                console.print_success(result.message)
            else:
                console.print_error(result.message)

        elif sub == "unassign":
            if len(parts) < 4:
                console.print_info("Usage: /skill unassign <skill-name> <role-name>")
                return {}
            result = ara.cmd_skill_unassign(parts[2], parts[3])
            if result.success:
                console.print_success(result.message)
            else:
                console.print_error(result.message)

        elif sub == "groups":
            result = ara.cmd_skill_group_list()
            if result.success:
                console.print_info(result.message)
            else:
                console.print_error(result.message)

        elif sub == "group-create":
            if len(parts) < 3:
                console.print_info("Usage: /skill group-create <name> [--type general|specialized]")
                return {}
            gtype = "general"
            for i, p in enumerate(parts[3:], 3):
                if p == "--type" and i + 1 < len(parts):
                    gtype = parts[i + 1]
            result = ara.cmd_skill_group_create(name=parts[2], group_type=gtype)
            if result.success:
                console.print_success(result.message)
            else:
                console.print_error(result.message)

        elif sub == "group-delete":
            if len(parts) < 3:
                console.print_info("Usage: /skill group-delete <name>")
                return {}
            result = ara.cmd_skill_group_delete(parts[2])
            if result.success:
                console.print_success(result.message)
            else:
                console.print_error(result.message)

        elif sub == "group-add":
            if len(parts) < 4:
                console.print_info("Usage: /skill group-add <skill-name> <group-name>")
                return {}
            result = ara.cmd_skill_group_assign(parts[2], parts[3])
            if result.success:
                console.print_success(result.message)
            else:
                console.print_error(result.message)

        else:
            console.print_error(f"Unknown skill subcommand: {sub}")

    except Exception as e:
        console.print_error(f"ARA skill failed: {e}")
    return {}


def _handle_google(parts, console):
    """Handle /google [login|status|disconnect] -- Google Account for sandbox LLM access."""
    sub = parts[1].lower() if len(parts) > 1 else "status"

    try:
        from orion.security.egress.google_credentials import (
            ALLOWED_SCOPES,
            BLOCKED_SCOPES,
            GoogleCredentialManager,
        )

        manager = GoogleCredentialManager()

        if sub == "login":
            import webbrowser

            from orion.security.egress.google_oauth_config import resolve_client_id

            client_id = resolve_client_id()

            if not client_id:
                console.print_error(
                    "Google OAuth client_id not configured.\n"
                    "Run /google setup to configure your Google Cloud credentials,\n"
                    "or set the ORION_GOOGLE_CLIENT_ID environment variable.\n"
                    "See docs/GOOGLE_SETUP.md for step-by-step instructions."
                )
                return {}

            # Start the API server flow
            console.print_info("Opening Google sign-in in your browser...")
            console.print_info(f"Scopes requested: {len(ALLOWED_SCOPES)} (LLM access only)")
            console.print_info(
                f"Blocked services: {len(BLOCKED_SCOPES)} (Drive, Gmail, Calendar, YouTube, ...)"
            )
            console.print_info(
                "Orion will NEVER see your Google password -- standard OAuth browser redirect."
            )

            # Build a simple connect URL that hits the API endpoint
            connect_url = "http://localhost:8001/api/google/connect"
            console.print_info(f"\nIf the browser doesn't open, visit:\n  {connect_url}")

            # Try to trigger the flow via the API
            try:
                import httpx

                with httpx.Client(timeout=5.0) as client:
                    resp = client.post(connect_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        auth_url = data.get("auth_url", "")
                        if auth_url:
                            webbrowser.open(auth_url)
                            console.print_success(
                                "Browser opened. Complete sign-in with Google, then return here."
                            )
                        else:
                            console.print_error("No auth_url in response")
                    else:
                        console.print_error(f"API error: {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                console.print_error(
                    f"Could not reach API server at localhost:8001: {e}\n"
                    "Make sure the API server is running "
                    "(uvicorn orion.api.server:app --port 8001)"
                )

        elif sub == "status":
            status = manager.get_status()
            if status.get("configured"):
                console.print_success("Google Account: Connected")
                console.print_info(f"  Email: {status.get('email', 'unknown')}")
                console.print_info(f"  Token expired: {status.get('is_expired', True)}")
                console.print_info(f"  Has refresh token: {status.get('has_refresh_token', False)}")
                console.print_info(f"  Scopes: {status.get('scope', 'none')}")
                if status.get("has_blocked_scopes"):
                    console.print_error(
                        f"  BLOCKED SCOPES DETECTED: {status.get('blocked_scopes')}"
                    )
                if status.get("refresh_count", 0) > 0:
                    console.print_info(f"  Token refreshes: {status['refresh_count']}")
            else:
                console.print_info("Google Account: Not connected")
                console.print_info("  Use /google login to connect a Google account")
                console.print_info(
                    "  This enables governed access to Google LLM services (Gemini, Vertex AI)"
                )

        elif sub == "disconnect":
            if not manager.has_credentials:
                console.print_info("No Google account connected")
                return {}
            creds = manager.get_credentials(auto_refresh=False)
            email = creds.email if creds else "unknown"
            manager.clear()
            console.print_success(f"Google account disconnected ({email})")
            console.print_info("All stored credentials have been cleared")

        elif sub == "setup":
            _handle_google_setup(console)

        else:
            console.print_info(
                "Usage: /google [login|status|disconnect|setup]\n"
                "  login      -- Open browser for Google sign-in (LLM-only scopes)\n"
                "  status     -- Show connected Google account status\n"
                "  disconnect -- Revoke access and clear stored credentials\n"
                "  setup      -- Configure Google OAuth app credentials (client_id)"
            )

    except Exception as e:
        console.print_error(f"Google command failed: {e}")
    return {}


def _handle_google_setup(console):
    """Interactive setup wizard for Google OAuth app credentials.

    Guides the user through:
      1. Creating a Google Cloud OAuth application
      2. Entering the client_id (validated)
      3. Optionally entering the client_secret
      4. Saving to ~/.orion/google_oauth.json
    """
    from orion.security.egress.google_oauth_config import (
        save,
        validate,
    )
    from orion.security.egress.google_oauth_config import (
        status as cfg_status,
    )

    current = cfg_status()
    if current["configured"]:
        console.print_info(
            f"Google OAuth is already configured (source: {current['source']})\n"
            f"  Client ID: {current['client_id_masked']}\n"
            f"  Has secret: {current['has_client_secret']}"
        )
        console.print_info("Enter new credentials to overwrite, or press Enter to keep current.")

    console.print_info(
        "\n--- Google OAuth Setup ---\n"
        "You need a Google Cloud OAuth 2.0 Client ID.\n"
        "Steps:\n"
        "  1. Go to https://console.cloud.google.com/apis/credentials\n"
        "  2. Create a project (or select existing)\n"
        "  3. Click 'Create Credentials' -> 'OAuth 2.0 Client ID'\n"
        "  4. Application type: 'Desktop app' (recommended for PKCE)\n"
        "  5. Copy the Client ID below\n"
    )

    try:
        client_id = input("Client ID: ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print_info("\nSetup cancelled.")
        return

    if not client_id:
        if current["configured"]:
            console.print_info("Keeping existing configuration.")
        else:
            console.print_info("No client_id entered. Setup cancelled.")
        return

    # Validate before asking for secret
    valid, reason = validate(client_id)
    if not valid:
        console.print_error(f"Invalid client_id: {reason}")
        return

    console.print_info(
        "\nClient secret (optional -- Desktop apps using PKCE can leave this empty):"
    )
    try:
        client_secret = input("Client Secret (or Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        client_secret = ""

    try:
        path = save(client_id, client_secret)
        console.print_success(f"Google OAuth credentials saved to {path}")
        console.print_info("You can now use /google login to connect your Google account.")
    except ValueError as e:
        console.print_error(f"Save failed: {e}")
        return

    # Also show how to delete
    console.print_info(
        "\nTo remove these credentials later:\n"
        "  /google setup  (enter empty client_id)\n"
        "  Or delete ~/.orion/google_oauth.json manually"
    )


def _handle_sandbox(parts, console):
    """Handle /sandbox [start|stop|status|restart|reload] -- Governed Docker sandbox."""
    sub = parts[1].lower() if len(parts) > 1 else "status"

    try:
        from orion.security.sandbox_lifecycle import get_sandbox_lifecycle

        lifecycle = get_sandbox_lifecycle()

        if sub == "start":
            if lifecycle.is_available:
                console.print_info("Sandbox is already running")
                return {}
            if lifecycle.is_booting:
                console.print_info("Sandbox is currently booting...")
                return {}
            console.print_info("Starting governed sandbox (6-step boot)...")
            ok = lifecycle.manual_start()
            if ok:
                console.print_success(
                    f"Sandbox started successfully ({lifecycle.get_status().get('boot_time_seconds', '?')}s)"
                )
            else:
                status = lifecycle.get_status()
                console.print_error(f"Sandbox boot failed: {status.get('error', 'unknown')}")

        elif sub == "stop":
            if not lifecycle.is_available and not lifecycle.is_booting:
                console.print_info("Sandbox is not running")
                return {}
            lifecycle.manual_stop()
            console.print_success("Sandbox stopped (manual override -- will not auto-restart)")

        elif sub == "restart":
            console.print_info("Restarting sandbox...")
            lifecycle.shutdown()
            ok = lifecycle.manual_start()
            if ok:
                console.print_success("Sandbox restarted successfully")
            else:
                status = lifecycle.get_status()
                console.print_error(f"Sandbox restart failed: {status.get('error', 'unknown')}")

        elif sub == "status":
            status = lifecycle.get_status()
            console.print_info(f"Phase: {status.get('phase', 'unknown')}")
            console.print_info(f"Available: {status.get('available', False)}")
            if status.get("boot_time_seconds"):
                console.print_info(f"Boot time: {status['boot_time_seconds']}s")
            if status.get("manually_stopped"):
                console.print_info("Manually stopped: yes (use /sandbox start to re-enable)")
            console.print_info(
                f"Egress proxy: {'running' if status.get('egress_proxy') else 'stopped'}"
            )
            console.print_info(
                f"DNS filter: {'running' if status.get('dns_filter') else 'stopped'}"
            )
            console.print_info(
                f"Approval queue: {'running' if status.get('approval_queue') else 'stopped'}"
            )
            if status.get("container_healthy") is not None:
                console.print_info(
                    f"Container: {'healthy' if status.get('container_healthy') else 'running' if status.get('container_running') else 'stopped'}"
                )
            if status.get("uptime_s", 0) > 0:
                console.print_info(f"Uptime: {status['uptime_s']:.0f}s")
            if status.get("error"):
                console.print_error(f"Error: {status['error']}")

        elif sub == "reload":
            if not lifecycle.is_available:
                console.print_info("Sandbox is not running")
                return {}
            # Delegate reload to the orchestrator via lifecycle
            orch = lifecycle._orchestrator
            if orch:
                orch.reload_config()
                console.print_success("Configuration reloaded")
            else:
                console.print_error("Orchestrator not available")

        else:
            console.print_info(
                "Usage: /sandbox [start|stop|status|restart|reload]\n"
                "  start   -- Launch governed Docker sandbox (6-step boot)\n"
                "  stop    -- Graceful reverse shutdown (prevents auto-restart)\n"
                "  status  -- Show current sandbox state\n"
                "  restart -- Stop + start\n"
                "  reload  -- Hot-reload egress/DNS config"
            )

    except Exception as e:
        console.print_error(f"Sandbox command failed: {e}")
    return {}


def _handle_ara_notifications(parts, console):
    """Handle /notifications [--read] -- Show pending notifications."""
    mark_read = "--read" in parts or "-r" in parts
    try:
        from orion.ara.cli_commands import cmd_notifications

        result = cmd_notifications(mark_read=mark_read)
        if result.success:
            console.print_info(result.message)
        else:
            console.print_error(result.message)
    except Exception as e:
        console.print_error(f"Notifications failed: {e}")
    return {}
