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

    elif command == "/tasks":
        return _handle_tasks(console)

    elif command == "/task":
        return _handle_task(parts, console)

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


def _handle_tasks(console):
    """Handle /tasks — List background tasks."""
    console.print_info("No background tasks")
    return {}


def _handle_task(parts, console):
    """Handle /task <id> or /task cancel <id>."""
    if len(parts) < 2:
        console.print_info("Usage: /task <id> or /task cancel <id>")
        return {}
    console.print_info(f"Task #{parts[1]} not found")
    return {}
