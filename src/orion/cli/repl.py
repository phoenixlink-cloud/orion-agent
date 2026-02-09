"""
Orion Agent — Interactive REPL (v6.4.0)

Main entry point workflow:
    USER REQUEST
        |
    INTENT CLASSIFICATION (via Scout)
        |
    AEGIS GOVERNANCE GATE
        |
    ROUTER (FastPath / Council / Escalation)
        |
    OUTCOME: ANSWER | PLAN | ACTION_INTENT
        |
    USER APPROVAL (PRO mode only)
        |
    TOOL EXECUTION
        |
    RESULT + RECEIPT
"""

import os
import sys
import asyncio
from typing import Optional, List


class OrionConsole:
    """Minimal console for the REPL. Provides print helpers."""

    def print_banner(self):
        print("\n" + "=" * 60)
        print("  ORION AGENT v6.4.0")
        print("  Type /help for commands, /quit to exit")
        print("=" * 60 + "\n")

    def get_input(self) -> str:
        try:
            return input("\norion> ").strip()
        except EOFError:
            return "/quit"

    def print_info(self, msg: str):
        print(f"  [info] {msg}")

    def print_success(self, msg: str):
        print(f"  [ok] {msg}")

    def print_error(self, msg: str):
        print(f"  [error] {msg}")

    def print_response(self, text: str):
        print(f"\n{text}\n")

    def print_status(self, workspace: Optional[str], mode: str):
        print(f"  Workspace: {workspace or '(not set)'}")
        print(f"  Mode: {mode.upper()}")

    def print_help(self):
        print("""
  ╭─────────────────────────────────────────────╮
  │          Orion — Command Reference           │
  ╰─────────────────────────────────────────────╯

  GETTING STARTED
    Just type a question or request in plain English.
    Example: "Create a hello world Flask app"
    Example: "Explain what main.py does"

  WORKSPACE (set your project folder first)
    /workspace <path>        Set your project folder
    /add <file>              Add a file for Orion to read
    /drop <file>             Remove a file from context
    /clear                   Clear all added files
    /map                     Show project structure
    /status                  Show current workspace and mode

  GIT & CHANGES
    /diff                    See what changed since last commit
    /undo                    Undo Orion's last change
    /undo all                Undo all changes in this session
    /commit [message]        Commit changes with a message

  SAFETY MODES
    /mode safe               Orion asks before every change (default)
    /mode pro                Auto-approve safe edits, ask for risky ones
    /mode project            Full autonomy within your project

  CONNECTIONS & API KEYS
    /connect                 List all available platforms
    /connect <platform> <token>  Connect a service (GitHub, Slack, etc.)
    /disconnect <platform>   Remove a connected service
    /key status              Check which API keys are configured
    /key set <provider> <key>    Add an API key (openai, anthropic, etc.)
    /key remove <provider>   Remove an API key

  MEMORY & LEARNING
    /memory                  Show what Orion has learned
    /memory search <query>   Search Orion's memory
    /log                     View activity and learning history

  DIAGNOSTICS
    /doctor                  Run a full system health check
    /health                  Check integration status
    /settings                View or change settings

  OTHER
    /help                    Show this help
    /quit or /exit           Exit Orion

  TIP: You don't need to memorize these. Just ask Orion
  anything and it will guide you through what it needs.
""")

    def print_proposed_actions(self, actions: list, explanation: str = ""):
        if explanation:
            print(f"\n  Explanation: {explanation}")
        print(f"\n  Proposed {len(actions)} action(s):")
        for i, action in enumerate(actions):
            op = action.get("operation", "?")
            path = action.get("path", "?")
            print(f"    {i+1}. {op} {path}")

    def get_approval(self) -> bool:
        resp = input("\n  Approve? [y/N]: ").strip().lower()
        return resp in ("y", "yes")

    def print_receipt(self, results: list):
        success = sum(1 for r in results if r.get("success"))
        print(f"\n  Executed: {success}/{len(results)} actions succeeded")

    def print_cancelled(self):
        print("  Cancelled.")

    def print_goodbye(self):
        print("\n  Goodbye!\n")

    def print_interrupted(self):
        print("\n  Interrupted.")

    def print_aegis_block(self, result):
        violations = getattr(result, 'violations', [])
        print(f"  [AEGIS] Blocked: {', '.join(violations) if violations else 'governance violation'}")

    def print_mode_required(self, required_mode: str, action: str):
        print(f"  {action} requires {required_mode.upper()} mode. Use /mode {required_mode}")

    def aegis_approval_prompt(self, prompt: str) -> bool:
        """
        AEGIS Invariant 6: Human approval gate for external write operations.

        Shows the approval prompt in the terminal and waits for y/n.
        This is the ONLY code path that can approve write actions in CLI mode.
        """
        print("\n" + "=" * 60)
        print("  ⚠  AEGIS APPROVAL REQUIRED")
        print("=" * 60)
        print(f"\n{prompt}")
        print("=" * 60)
        resp = input("\n  Approve this action? [y/N]: ").strip().lower()
        approved = resp in ("y", "yes")
        if approved:
            print("  [AEGIS] ✓ Action APPROVED by human")
        else:
            print("  [AEGIS] ✗ Action DENIED")
        return approved

    def _print(self, text: str, **kwargs):
        print(text)


def start_repl():
    """Start the interactive Orion REPL."""
    console = OrionConsole()

    # State
    workspace_path: Optional[str] = None
    mode: str = os.environ.get("ORION_DEFAULT_MODE", "safe")
    context_files: List[str] = []
    change_history: List[dict] = []
    router_instance = None  # Persist across requests

    # Initialize Memory Engine
    memory_engine = None
    try:
        from orion.core.memory.engine import get_memory_engine
        memory_engine = get_memory_engine(workspace_path)
        memory_engine.start_session()
    except Exception:
        pass

    # =========================================================================
    # AEGIS Invariant 6: Wire human approval callback for external writes.
    # Without this, ALL write operations to external APIs are BLOCKED.
    # =========================================================================
    try:
        from orion.integrations.platform_service import get_platform_service
        _platform_svc = get_platform_service()
        _platform_svc.set_approval_callback(console.aegis_approval_prompt)
        console.print_info("AEGIS Invariant 6 active — external writes require your approval")
    except Exception:
        pass  # Platform service not available

    console.print_banner()

    while True:
        try:
            user_input = console.get_input()

            if not user_input:
                continue

            # Handle slash commands
            if user_input.startswith("/"):
                from orion.cli.commands import handle_command
                result = handle_command(
                    user_input, console, workspace_path, mode,
                    context_files, change_history
                )
                if result == "QUIT":
                    break
                if isinstance(result, dict):
                    if result.get("workspace"):
                        workspace_path = result["workspace"]
                    if result.get("context_files") is not None:
                        context_files = result["context_files"]
                    if result.get("change_history") is not None:
                        change_history = result["change_history"]
                    if result.get("mode"):
                        mode = result["mode"]
                continue

            # =============================================================
            # MAIN WORKFLOW
            # =============================================================

            # Re-init memory engine if workspace changed
            if memory_engine and memory_engine.workspace_path != (workspace_path or "."):
                try:
                    memory_engine.end_session()
                    from orion.core.memory.engine import get_memory_engine
                    memory_engine = get_memory_engine(workspace_path)
                    memory_engine.start_session()
                    router_instance = None  # Force Router rebuild
                except Exception:
                    pass

            # Step 1: Intent Classification
            try:
                from orion.core.agents.router import classify_intent
                intent = classify_intent(user_input)
            except Exception:
                # Fallback intent
                from dataclasses import dataclass, field as dc_field

                @dataclass
                class _FallbackIntent:
                    category: str = "analysis"
                    requires_evidence: bool = False
                    requires_action: bool = False
                    confidence: float = 0.5
                    keywords: list = dc_field(default_factory=list)
                    raw_input: str = ""

                intent = _FallbackIntent(raw_input=user_input)

            # Step 2: AEGIS Gate (pre-check)
            try:
                from orion.core.governance.aegis import check_aegis_gate
                aegis_result = check_aegis_gate(
                    intent=intent,
                    mode=mode,
                    workspace_path=workspace_path,
                    action_type="deliberation"
                )
                if not aegis_result.passed:
                    console.print_aegis_block(aegis_result)
                    continue
            except Exception:
                pass  # Governance not available, proceed

            # Step 3: Route through RequestRouter (persistent)
            try:
                from orion.core.agents.router import RequestRouter
                if router_instance is None:
                    router_instance = RequestRouter(
                        workspace_path or ".",
                        stream_output=True,
                        sandbox_enabled=False,
                        memory_engine=memory_engine,
                    )
                result = asyncio.run(router_instance.handle_request(user_input))

                response_text = result.get("response", "")
                route_name = result.get("route", "UNKNOWN")

                if result.get("success"):
                    # Router already printed response in stream mode
                    if not router_instance.stream_output:
                        console.print_response(response_text)
                    if result.get("files_modified"):
                        console.print_info(
                            f"Files modified: {', '.join(result['files_modified'])}"
                        )

                    # Record interaction in memory
                    if router_instance:
                        router_instance.record_interaction(user_input, response_text, route_name)

                    # Optional feedback (user can press Enter to skip)
                    try:
                        feedback = input("  Rate (1-5, Enter to skip): ").strip()
                        if feedback and feedback.isdigit() and 1 <= int(feedback) <= 5:
                            rating = int(feedback)
                            if memory_engine:
                                import uuid
                                memory_engine.record_approval(
                                    task_id=str(uuid.uuid4())[:8],
                                    task_description=user_input[:300],
                                    rating=rating,
                                    feedback=f"User rated {rating}/5",
                                    quality_score=rating / 5.0,
                                )
                                if rating >= 4:
                                    console.print_info("Positive pattern recorded")
                                elif rating <= 2:
                                    console.print_info("Anti-pattern recorded — Orion will learn from this")
                    except (EOFError, KeyboardInterrupt):
                        pass
                else:
                    error = result.get("response", result.get("error", "Unknown error"))
                    console.print_error(error)

            except Exception as e:
                # Fallback: simple echo if router unavailable
                console.print_info(
                    f"Router not available ({e}). "
                    f"Set workspace with /workspace and ensure dependencies are installed."
                )

        except KeyboardInterrupt:
            console.print_interrupted()
        except Exception as e:
            console.print_error(str(e))

    # End memory session: promote valuable memories, consolidate
    if memory_engine:
        try:
            stats = memory_engine.get_stats()
            memory_engine.end_session()
            console.print_info(
                f"Session ended — {stats.tier1_entries} session memories, "
                f"{stats.tier2_entries} project, {stats.tier3_entries} global"
            )
        except Exception:
            pass

    console.print_goodbye()
