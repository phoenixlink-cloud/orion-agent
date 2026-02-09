"""
Orion Agent — Request Router (v6.4.0)

Routes user requests through Scout to the appropriate execution path:
- FAST_PATH -> FastPath (direct LLM + tools)
- COUNCIL -> Informed Council (GPT + Claude deliberation)
- ESCALATION -> User confirmation -> Council

This is the main integration point for the new architecture.
"""

import asyncio
import os
import time
from typing import Optional, Callable, Any, Dict, List
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Intent:
    """Classified user intent (legacy compatibility)."""
    category: str
    requires_evidence: bool
    requires_action: bool
    confidence: float
    keywords: List[str]
    raw_input: str


def classify_intent(user_input: str, workspace_path: str = ".") -> Intent:
    """Legacy intent classification - now uses Scout internally."""
    try:
        from orion.core.agents.scout import Scout, Route
        scout = Scout(workspace_path)
        report = scout.analyze(user_input)

        if report.route == Route.FAST_PATH:
            return Intent("analysis", False, False, report.complexity_score, [], user_input)
        elif report.route == Route.COUNCIL:
            return Intent("action", True, True, report.complexity_score, [], user_input)
        else:
            return Intent("action", True, True, 0.9, ["dangerous"], user_input)
    except Exception:
        return Intent("analysis", False, False, 0.5, [], user_input)


class RequestRouter:
    """
    Routes requests through Scout to appropriate execution paths.

    Usage:
        router = RequestRouter(workspace_path)
        result = await router.handle_request("Show me main.py")
    """

    def __init__(
        self,
        workspace_path: str,
        confirm_callback: Optional[Callable[[str], bool]] = None,
        stream_output: bool = True,
        model: str = "gpt-4o",
        sandbox_enabled: Optional[bool] = None,
    ):
        self.source_path = Path(workspace_path).resolve()
        self.confirm_callback = confirm_callback or self._default_confirm
        self.stream_output = stream_output
        self.model = model

        # Sandbox: determine if enabled (env > param > default True)
        if sandbox_enabled is not None:
            self._sandbox_enabled = sandbox_enabled
        else:
            env_val = os.environ.get("ORION_SANDBOX_ENABLED", "true").lower()
            self._sandbox_enabled = env_val in ("true", "1", "yes")

        self._sandbox_session = None

        # Set working path: sandbox or direct
        if self._sandbox_enabled:
            self.workspace_path = self._init_sandbox()
        else:
            self.workspace_path = self.source_path

        # Initialize components against the working path
        self.repo_map = None
        self.scout = None
        try:
            from orion.core.context.repo_map import RepoMap
            self.repo_map = RepoMap(str(self.workspace_path))
        except Exception:
            pass

        try:
            from orion.core.agents.scout import Scout
            self.scout = Scout(str(self.workspace_path), self.repo_map)
        except Exception:
            pass

        # Lazy-loaded components
        self._fast_path = None
        self._council = None

    def _init_sandbox(self) -> Path:
        """Create a sandbox session from the source repo."""
        try:
            from orion.security.sandbox import SandboxManager
            self._sandbox_mgr = SandboxManager(
                sandbox_root=os.environ.get("ORION_SANDBOX_ROOT"),
                use_git_clone=os.environ.get("ORION_SANDBOX_USE_GIT_CLONE", "true").lower() in ("true", "1"),
            )
            self._sandbox_session = self._sandbox_mgr.create_session(str(self.source_path))
            return Path(self._sandbox_session.sandbox_path)
        except Exception:
            self._sandbox_enabled = False
            return self.source_path

    @property
    def sandbox_active(self) -> bool:
        return self._sandbox_enabled and self._sandbox_session is not None

    def get_sandbox_diff(self) -> Optional[dict]:
        if not self.sandbox_active:
            return None
        return self._sandbox_mgr.get_diff(self._sandbox_session)

    def promote_changes(self, files: Optional[List[str]] = None, dry_run: bool = False) -> dict:
        if not self.sandbox_active:
            return {"error": "Sandbox not active"}
        return self._sandbox_mgr.promote(files=files, session=self._sandbox_session, dry_run=dry_run)

    def destroy_sandbox(self) -> bool:
        if not self.sandbox_active:
            return False
        result = self._sandbox_mgr.destroy_session(self._sandbox_session.session_id)
        self._sandbox_session = None
        return result

    @property
    def fast_path(self):
        if self._fast_path is None:
            try:
                from orion.core.agents.fast_path import FastPath
                self._fast_path = FastPath(str(self.workspace_path), self.model)
            except Exception:
                self._fast_path = None
        return self._fast_path

    @property
    def council(self):
        if self._council is None:
            try:
                from orion.core.agents.table import run_table_of_three
                self._council = run_table_of_three
            except ImportError:
                self._council = None
        return self._council

    def _default_confirm(self, message: str) -> bool:
        response = input(f"\n[!] {message}\nProceed? [y/N]: ")
        return response.lower() in ('y', 'yes')

    async def handle_request(self, request: str) -> dict:
        """
        Handle a user request by routing through Scout.

        Returns:
            dict with keys: success, route, response, files_modified, execution_time_ms
        """
        start_time = time.time()

        if not self.scout:
            return {
                "success": False, "route": "UNKNOWN",
                "response": "Scout not available",
                "files_modified": [], "execution_time_ms": 0,
            }

        report = self.scout.analyze(request)

        try:
            from orion.core.agents.scout import Route
            if report.route == Route.FAST_PATH:
                response = await self._handle_fast_path(request, report)
            elif report.route == Route.COUNCIL:
                response = await self._handle_council(request, report)
            elif report.route == Route.ESCALATION:
                response = await self._handle_escalation(request, report)
            else:
                response = {"error": f"Unknown route: {report.route}"}

            execution_time = int((time.time() - start_time) * 1000)

            return {
                "success": True,
                "route": report.route.name,
                "response": response.get("content", response.get("error", "")),
                "files_modified": response.get("files_modified", []),
                "execution_time_ms": execution_time,
                "scout_report": {
                    "complexity": report.complexity_score,
                    "risk": report.risk_level,
                    "files": report.relevant_files,
                    "reasoning": report.reasoning,
                },
            }
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return {
                "success": False, "route": report.route.name,
                "response": f"Error: {str(e)}",
                "files_modified": [], "execution_time_ms": execution_time,
                "error": str(e),
            }

    async def _handle_fast_path(self, request: str, report) -> dict:
        if self.fast_path is None:
            return {"content": "FastPath not available. Run /doctor to check configuration."}
        try:
            if self.stream_output:
                # Use true token-by-token streaming
                collected = []
                try:
                    async for token in self.fast_path.execute_streaming(request, report):
                        print(token, end="", flush=True)
                        collected.append(token)
                    print()  # Final newline after streaming
                    return {"content": "".join(collected)}
                except Exception:
                    # Fallback to non-streaming if streaming fails
                    result = await self.fast_path.execute(request, report)
                    if result.success:
                        print(result.response)
                    return {"content": result.response}
            else:
                result = await self.fast_path.execute(request, report)
                return {"content": result.response}
        except Exception as e:
            return {"error": f"FastPath error: {e}"}

    async def _handle_council(self, request: str, report) -> dict:
        if self.council is None:
            # Fallback: route complex requests through FastPath
            return await self._handle_fast_path(request, report)
        context = self.repo_map.get_repo_map(report.relevant_files) if self.repo_map else ""
        try:
            result = await self._run_council(request, context)
            if isinstance(result, dict):
                return {"content": result.get("response", str(result)), "council_result": result}
            return {"content": result}
        except Exception as e:
            return {"error": f"Council error: {e}"}

    async def _handle_escalation(self, request: str, report) -> dict:
        confirmed = self.confirm_callback(
            f"This request was flagged as potentially dangerous:\n"
            f"'{request[:100]}...'\n\n"
            f"Reason: {report.reasoning}"
        )
        if not confirmed:
            return {"content": "Request cancelled by user."}
        return await self._handle_council(request, report)

    async def _run_council(self, request: str, context: str) -> Any:
        """Run Table of Three deliberation."""
        # Load current mode from settings
        mode = "safe"
        try:
            settings_file = Path.home() / ".orion" / "settings.json"
            if settings_file.exists():
                import json
                settings = json.loads(settings_file.read_text())
                mode = settings.get("default_mode", "safe")
        except Exception:
            pass

        if callable(self.council):
            # council is run_table_of_three function
            return await self.council(
                user_input=request,
                evidence_context=context,
                mode=mode,
                workspace_path=str(self.workspace_path),
            )
        return "Council deliberation not available."


def get_router(workspace_path: str, **kwargs) -> RequestRouter:
    """Factory function to get a RequestRouter instance."""
    return RequestRouter(workspace_path, **kwargs)


async def process_request(request: str, workspace_path: str = ".", stream: bool = True) -> dict:
    """Process a request through the router."""
    router = RequestRouter(workspace_path, stream_output=stream)
    return await router.handle_request(request)


def process_request_sync(request: str, workspace_path: str = ".", stream: bool = True) -> dict:
    """Synchronous wrapper for process_request."""
    return asyncio.run(process_request(request, workspace_path, stream))
