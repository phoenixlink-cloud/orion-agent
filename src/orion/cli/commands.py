"""
Orion Agent — CLI Slash Command Handler (v6.4.0)

Handles all /slash commands: /workspace, /add, /drop, /clear, /undo,
/diff, /commit, /map, /mode, /status, /help, /settings, /tasks, /task.
"""

import os
from typing import Optional


def handle_command(cmd: str, console, workspace_path: str, mode: str,
                   context_files: list = None, change_history: list = None) -> dict:
    """Handle slash commands — familiar CLI patterns users expect."""
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
                # Already in async context — schedule as task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    loop.run_in_executor(pool, lambda: asyncio.run(run_doctor(console, workspace_path)))
            except RuntimeError:
                # No running loop — safe to use asyncio.run
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

    elif command == "/log":
        try:
            from orion.core.learning.evolution import get_evolution_engine
            engine = get_evolution_engine()
            summary = engine.get_evolution_summary()
            console.print_info(f"Evolution: {summary}")
        except Exception:
            console.print_info("Activity log not available")
        return {}

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
    """Handle /add <file> — Add file to context."""
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
    """Handle /drop <file> — Remove file from context."""
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
    """Handle /undo — Revert last change using git safety net."""
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
                    console._print(f"  [{entry['index']}] {entry['hash']} {entry['description']} ({entry['files']} files)")
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
                console.print_success(f"Undo: {result.message} (restored {result.files_restored} files)")
            else:
                console.print_error(result.message)
            return {"change_history": change_history}
    except Exception:
        pass

    console.print_info("No changes to undo. Use /undo stack to see available savepoints.")
    return {"change_history": change_history}


def _handle_diff(console, workspace_path):
    """Handle /diff — Show pending changes."""
    if workspace_path:
        try:
            import subprocess
            result = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=workspace_path,
                capture_output=True,
                text=True
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
    """Handle /commit [msg] — Commit changes to git."""
    if not workspace_path:
        console.print_error("Set workspace first")
        return {}

    msg = " ".join(parts[1:]) if len(parts) > 1 else "orion: automated changes"
    try:
        import subprocess
        subprocess.run(["git", "add", "-A"], cwd=workspace_path, check=True)
        result = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=workspace_path,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            console.print_success(f"Committed: {msg}")
        else:
            console.print_info("Nothing to commit")
    except Exception as e:
        console.print_error(f"Commit failed: {e}")
    return {}


def _handle_map(console, workspace_path):
    """Handle /map — Show repository map."""
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
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', '.git']]
            level = root.replace(workspace_path, '').count(os.sep)
            indent = '  ' * level
            folder = os.path.basename(root)
            if level < 3:
                console._print(f"{indent}{folder}/")
                for f in files[:10]:
                    console._print(f"{indent}  {f}")
                if len(files) > 10:
                    console._print(f"{indent}  ... and {len(files) - 10} more")
    return {}


def _handle_mode(parts, console, mode):
    """Handle /mode [new_mode] — Show or change mode."""
    VALID_MODES = {"safe", "pro", "project"}

    if len(parts) < 2:
        console.print_info(f"Current mode: {mode.upper()}")
        return {}

    new_mode = parts[1].lower()
    if new_mode in VALID_MODES:
        mode_desc = {
            "safe": "SAFE (read-only)",
            "pro": "PRO (file operations with approval)",
            "project": "PROJECT (file + command execution with approval)"
        }
        console.print_success(f"Mode switched to: {mode_desc.get(new_mode, new_mode.upper())}")
        return {"mode": new_mode}
    else:
        console.print_error(f"Invalid mode. Use: {', '.join(sorted(VALID_MODES))}")
        return {}


def _handle_connect(parts, console):
    """Handle /connect <platform> [token] — Connect a platform."""
    if len(parts) < 2:
        console.print_info("Usage: /connect <platform> [token]")
        console.print_info("  /connect github          — auto-detect gh CLI")
        console.print_info("  /connect slack xoxb-...  — store bot token")
        console.print_info("  /connect                 — list all platforms")
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
                console.print_success(f"{platform.name} connected via {platform.cli_tool} CLI (auto-detected)")
                return {}
            else:
                console.print_error(f"{platform.cli_tool} CLI not found. Install it or provide a token.")
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
    """Handle /disconnect <platform> — Disconnect a platform."""
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
    """Handle /key set|remove|status — Manage API keys."""
    if len(parts) < 2:
        console.print_info("Usage:")
        console.print_info("  /key status              — Show configured keys")
        console.print_info("  /key set <provider> <key> — Store an API key")
        console.print_info("  /key remove <provider>    — Remove an API key")
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
    """Handle /memory [search <query> | stats | evolution] — View memory stats or search."""
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
        console._print(f"  Approval rate:       {stats.approval_rate:.1%}" if (stats.total_approvals + stats.total_rejections) > 0 else "  Approval rate:       N/A")
        console._print(f"  Patterns learned:    {stats.patterns_learned}")
        console._print(f"  Anti-patterns:       {stats.anti_patterns_learned}")
        console._print(f"  Preferences stored:  {stats.preferences_stored}")
        console._print(f"  Promotions (T2->T3): {stats.promotions_count}")
    except Exception as e:
        console.print_info(f"Memory engine not available: {e}")
    return {}


