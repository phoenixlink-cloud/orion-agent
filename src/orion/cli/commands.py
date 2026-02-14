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
        console.print_info("  Example: /work software-engineer \"Add error handling to api.py\"")
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
                        console._print(f"    {r['name']}{tag} — scope: {r.get('scope', '?')}, auth: {r.get('auth_method', '?')}")
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
                    status_icon = {"running": "▶", "paused": "⏸", "completed": "✓", "failed": "✗", "cancelled": "⊘"}.get(s.get("status", ""), "?")
                    console._print(f"    {status_icon} {s['session_id'][:8]}  {s.get('role', '?')} — {s.get('goal', '?')[:60]}")
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

        dash = MorningDashboard(workspace_path=workspace_path or ".")
        data = dash.gather_data()
        output = dash.render(data)
        console._print(output)
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
