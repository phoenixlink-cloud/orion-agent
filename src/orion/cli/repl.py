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
Orion Agent -- Interactive REPL (v9.0.0)

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

import asyncio
import os

from orion._version import __version__


class OrionConsole:
    """Minimal console for the REPL. Provides print helpers."""

    def print_banner(self):
        print("\n" + "=" * 60)
        print(f"  ORION AGENT v{__version__}")
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

    def print_status(self, workspace: str | None, mode: str):
        print(f"  Workspace: {workspace or '(not set)'}")
        print(f"  Mode: {mode.upper()}")

    def print_help(self):
        print("""
  ╭─────────────────────────────────────────────╮
  │          Orion -- Command Reference           │
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

  AUTONOMOUS ROLE ARCHITECTURE (ARA)
    /setup                   Run first-time ARA setup wizard
    /work <role> <goal>      Start an autonomous background session
    /pause                   Pause the running session
    /resume                  Resume a paused session
    /cancel                  Cancel the running session
    /review [session_id]     Review sandbox changes for promotion
    /sessions                List all sessions
    /sessions cleanup [days] Clean up old sessions
    /dashboard               Show morning dashboard (overview, approvals, tasks)
    /rollback <id>           Roll back to a checkpoint
    /plan-review             Review current task plan

  ROLE MANAGEMENT
    /role list               List all available roles
    /role show <name>        Show full role details
    /role create <name>      Create a new role
    /role delete <name>      Delete a user role
    /role example            Show annotated YAML example
    /role validate <path>    Validate a role YAML file

  ARA SETTINGS & AUTH
    /ara-settings            View ARA-specific settings
    /ara-settings key=value  Update ARA settings
    /auth-switch <method> <cred>  Switch auth method (pin/totp/none)

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
            print(f"    {i + 1}. {op} {path}")

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
        violations = getattr(result, "violations", [])
        print(
            f"  [AEGIS] Blocked: {', '.join(violations) if violations else 'governance violation'}"
        )

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


def _collect_feedback(
    console,
    user_input: str,
    response_text: str,
    route_name: str,
    workspace_path: str | None,
    memory_engine=None,
    log=None,
    learning_bridge=None,
    nla_classification=None,
):
    """Collect rich feedback from the user after every response.

    Flow:
        1. Rate 1-5 (Enter to skip) -- lightweight, always available
        2. If rating <= 3: ask what to improve (free text or category)
        3. Wire into LearningLoop for deep pattern learning
        4. Record in memory engine for approval gate
    """
    try:
        rating_input = input("  Rate (1-5, Enter to skip): ").strip()
        if not rating_input or not rating_input.isdigit():
            return
        rating = int(rating_input)
        if not 1 <= rating <= 5:
            return

        import uuid

        task_id = str(uuid.uuid4())[:8]
        feedback_text = ""

        # For low ratings, ask what went wrong
        if rating <= 3:
            try:
                print("  What should I improve?")
                print("    [1] Too technical / robotic")
                print("    [2] Wrong answer / incorrect")
                print("    [3] Too verbose / too brief")
                print("    [4] Didn't understand my request")
                print("    [5] Other (type your feedback)")
                fb_input = input("  > ").strip()

                feedback_categories = {
                    "1": "Response was too technical or robotic. User wants more natural, conversational tone.",
                    "2": "Response contained incorrect information or wrong answer.",
                    "3": "Response length was inappropriate (too verbose or too brief).",
                    "4": "Orion did not understand the user's actual intent.",
                }

                if fb_input in feedback_categories:
                    feedback_text = feedback_categories[fb_input]
                elif fb_input == "5" or (fb_input and not fb_input.isdigit()):
                    # If they typed "5", ask for text; if they typed text directly, use it
                    if fb_input == "5":
                        feedback_text = input("  Tell me more: ").strip()
                    else:
                        feedback_text = fb_input
                elif fb_input:
                    feedback_text = fb_input
            except (EOFError, KeyboardInterrupt):
                pass

        # Record in memory engine (approval gate)
        if memory_engine:
            full_feedback = f"User rated {rating}/5"
            if feedback_text:
                full_feedback += f": {feedback_text}"

            memory_engine.record_approval(
                task_id=task_id,
                task_description=user_input[:300],
                rating=rating,
                feedback=full_feedback,
                quality_score=rating / 5.0,
            )

            if rating >= 4:
                console.print_info("Positive pattern recorded")
            elif rating <= 2:
                console.print_info("Anti-pattern recorded \u2014 Orion will learn from this")

        # Wire into LearningLoop for deeper pattern extraction
        try:
            from orion.core.learning.feedback import LearningLoop

            loop = LearningLoop(workspace_path)
            if rating >= 4:
                loop.process_feedback(user_input, response_text, "positive", feedback_text)
            elif rating <= 2:
                loop.process_feedback(user_input, response_text, "negative", feedback_text)
        except Exception:
            pass  # LearningLoop not available

        # Wire into NLA LearningBridge (feedback → exemplar bank)
        if learning_bridge:
            try:
                learning_bridge.record_rich_feedback(
                    user_message=user_input,
                    response_text=response_text,
                    classification=nla_classification,
                    rating=rating,
                    feedback_text=feedback_text,
                )
            except Exception:
                pass

        if log:
            log.approval(
                task_id=task_id,
                rating=rating,
                task_type=route_name,
                promoted=(rating >= 4 or rating <= 2),
            )

    except (EOFError, KeyboardInterrupt):
        pass


def start_repl():
    """Start the interactive Orion REPL."""
    console = OrionConsole()

    # State
    workspace_path: str | None = None
    mode: str = os.environ.get("ORION_DEFAULT_MODE", "safe")
    context_files: list[str] = []
    change_history: list[dict] = []
    router_instance = None  # Persist across requests

    # Initialize Logger
    log = None
    try:
        from orion.core.logging import get_logger

        log = get_logger()
    except Exception:
        pass

    # Initialize Memory Engine
    memory_engine = None
    try:
        from orion.core.memory.engine import get_memory_engine

        memory_engine = get_memory_engine(workspace_path)
        memory_engine.start_session()
    except Exception:
        pass

    # Initialize Conversation Buffer (NLA Phase 1A)
    conversation = None
    try:
        from orion.core.memory.conversation import ConversationBuffer

        conversation = ConversationBuffer()
    except Exception:
        pass

    # Initialize NLA Learning Bridge (NLA Phase 3B)
    learning_bridge = None
    try:
        from orion.core.understanding.exemplar_bank import ExemplarBank
        from orion.core.understanding.learning_bridge import LearningBridge

        learning_bridge = LearningBridge(exemplar_bank=ExemplarBank())
    except Exception:
        pass

    if log:
        log.session_start(workspace=workspace_path or "(not set)", mode=mode)

    # =========================================================================
    # AEGIS Invariant 6: Wire human approval callback for external writes.
    # Without this, ALL write operations to external APIs are BLOCKED.
    # =========================================================================
    try:
        from orion.integrations.platform_service import get_platform_service

        _platform_svc = get_platform_service()
        _platform_svc.set_approval_callback(console.aegis_approval_prompt)
        console.print_info("AEGIS Invariant 6 active -- external writes require your approval")
    except Exception:
        pass  # Platform service not available

    console.print_banner()

    # =========================================================================
    # SANDBOX LIFECYCLE: Auto-boot governed environment in background
    # =========================================================================
    sandbox_lifecycle = None
    try:
        from orion.security.sandbox_lifecycle import get_sandbox_lifecycle

        sandbox_lifecycle = get_sandbox_lifecycle()
        sandbox_lifecycle.set_status_callback(lambda msg: console.print_info(msg))
        console.print_info("Initializing governed environment...")
        sandbox_lifecycle.boot(background=True)
    except Exception:
        pass  # Sandbox lifecycle not available -- continue in BYOK mode

    while True:
        try:
            user_input = console.get_input()

            if not user_input:
                continue

            # Handle slash commands
            if user_input.startswith("/train"):
                from orion.cli.commands_training import handle_train_command

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures

                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            pool.submit(
                                asyncio.run,
                                handle_train_command(
                                    user_input, router_instance, memory_engine, console
                                ),
                            ).result()
                    else:
                        loop.run_until_complete(
                            handle_train_command(
                                user_input, router_instance, memory_engine, console
                            )
                        )
                except RuntimeError:
                    asyncio.run(
                        handle_train_command(user_input, router_instance, memory_engine, console)
                    )
                continue

            if user_input.startswith("/"):
                from orion.cli.commands import handle_command

                result = handle_command(
                    user_input, console, workspace_path, mode, context_files, change_history
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

            # Record user turn in conversation buffer
            if conversation:
                conversation.add("user", user_input)

            # Step 1: Intent Classification
            try:
                from orion.core.agents.router import classify_intent

                intent = classify_intent(user_input)
            except Exception:
                # Fallback intent
                from dataclasses import dataclass
                from dataclasses import field as dc_field

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
                    action_type="deliberation",
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
                    # Record Orion's response in conversation buffer
                    if conversation and response_text:
                        conversation.add("orion", response_text[:500])

                    # Router already printed response in stream mode
                    if not router_instance.stream_output:
                        console.print_response(response_text)
                    if result.get("files_modified"):
                        console.print_info(f"Files modified: {', '.join(result['files_modified'])}")

                    # Record interaction in memory
                    if router_instance:
                        router_instance.record_interaction(user_input, response_text, route_name)

                    # Log the route
                    if log:
                        exec_ms = result.get("execution_time_ms", 0)
                        scout = result.get("scout_report", {})
                        log.route(
                            route_name,
                            user_input,
                            complexity=scout.get("complexity", 0),
                            risk=scout.get("risk", ""),
                            latency_ms=exec_ms,
                        )

                    # NLA classification for learning bridge
                    _nla_classification = None
                    if hasattr(router_instance, "_fast_path") and hasattr(
                        router_instance._fast_path, "_request_analyzer"
                    ):
                        try:
                            analyzer = router_instance._fast_path._request_analyzer
                            if analyzer:
                                _nla_result = analyzer.analyze(user_input)
                                _nla_classification = (
                                    _nla_result.brief
                                )  # pass the ClassificationResult
                                from orion.core.understanding.intent_classifier import (
                                    ClassificationResult,
                                )

                                _nla_classification = ClassificationResult(
                                    intent=_nla_result.intent,
                                    sub_intent=_nla_result.sub_intent,
                                    confidence=_nla_result.confidence,
                                    method="nla",
                                )
                        except Exception:
                            pass

                    # Feedback loop (user can press Enter to skip)
                    _collect_feedback(
                        console=console,
                        user_input=user_input,
                        response_text=response_text,
                        route_name=route_name,
                        workspace_path=workspace_path,
                        memory_engine=memory_engine,
                        log=log,
                        learning_bridge=learning_bridge,
                        nla_classification=_nla_classification,
                    )
                else:
                    error = result.get("response", result.get("error", "Unknown error"))
                    console.print_error(error)

            except Exception as e:
                if log:
                    log.error("Router", f"Request failed: {e}", request=user_input[:100])
                # Fallback: simple echo if router unavailable
                console.print_info(
                    f"Router not available ({e}). "
                    f"Set workspace with /workspace and ensure dependencies are installed."
                )

        except KeyboardInterrupt:
            console.print_interrupted()
        except Exception as e:
            console.print_error(str(e))

    # =========================================================================
    # SANDBOX LIFECYCLE: Shutdown on quit
    # =========================================================================
    if sandbox_lifecycle:
        try:
            if sandbox_lifecycle.is_available:
                console.print_info("Stopping sandbox...")
            sandbox_lifecycle.shutdown()
            if sandbox_lifecycle.phase == "stopped":
                console.print_info("Sandbox stopped.")
        except Exception:
            pass

    # End memory session: promote valuable memories, consolidate
    if memory_engine:
        try:
            stats = memory_engine.get_stats()
            memory_engine.end_session()
            console.print_info(
                f"Session ended -- {stats.tier1_entries} session memories, "
                f"{stats.tier2_entries} project, {stats.tier3_entries} global"
            )
            if log:
                log.session_end(
                    tier1=stats.tier1_entries, tier2=stats.tier2_entries, tier3=stats.tier3_entries
                )
        except Exception:
            pass

    if log:
        console.print_info(f"Logs: {log.log_file}")
    console.print_goodbye()
