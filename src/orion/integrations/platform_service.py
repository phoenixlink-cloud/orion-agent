"""
Orion Agent — Platform Service (v6.4.0)

Service layer that Orion agents use to interact with connected platforms.
Handles auth token retrieval, API calls, and capability routing.

Usage by agents:
    from orion.integrations.platform_service import get_platform_service
    service = get_platform_service()

    # Check what's available
    if service.can("create_issue"):
        result = await service.github_create_issue(repo, title, body)

    # Get auth token for a platform
    token = service.get_token("github")

    # List what Orion can do right now
    caps = service.available_capabilities()
"""

import os
import logging
from typing import Optional, Dict, Any, List, Callable

logger = logging.getLogger("orion.integrations.platform_service")


class PlatformService:
    """
    Service layer for Orion agents to use connected platforms.

    Provides:
      - Token/key retrieval for any connected platform
      - Capability checking (can Orion do X right now?)
      - Authenticated HTTP calls to platform APIs
      - Platform-specific helper methods
    """

    def __init__(self):
        self._store = None
        self._registry = None
        # AEGIS Invariant 6: Human approval callback for write operations.
        # If not set, ALL write operations are BLOCKED by default.
        # This is a security invariant — Orion cannot bypass this.
        self._approval_callback: Optional[Callable[[str], bool]] = None

    @property
    def store(self):
        if self._store is None:
            try:
                from orion.security.store import get_secure_store
                self._store = get_secure_store()
            except Exception:
                pass
        return self._store

    @property
    def registry(self):
        if self._registry is None:
            from orion.integrations.platforms import get_platform_registry
            self._registry = get_platform_registry()
        return self._registry

    # =========================================================================
    # TOKEN / KEY RETRIEVAL
    # =========================================================================

    def get_token(self, platform_id: str) -> Optional[str]:
        """
        Get the auth token/key for a platform.

        Checks in order:
          1. Environment variable
          2. SecureStore
          3. OAuth token (for OAuth platforms)

        Returns None if not connected.
        """
        platform = self.registry.get(platform_id)
        if not platform:
            return None

        # 1. Environment variable
        if platform.env_var:
            val = os.environ.get(platform.env_var)
            if val:
                return val

        if platform.env_var_alt:
            val = os.environ.get(platform.env_var_alt)
            if val:
                return val

        # 2. SecureStore
        if self.store and platform.secure_store_key:
            val = self.store.get_key(platform.secure_store_key)
            if val:
                return val

        # 3. OAuth token
        if platform.oauth_provider and self.store:
            val = self.store.get_key(f"oauth_{platform.oauth_provider}_access_token")
            if val:
                return val

        return None

    def is_connected(self, platform_id: str) -> bool:
        """Check if a platform is connected and usable."""
        platform = self.registry.get(platform_id)
        if not platform:
            return False
        if platform.is_local:
            return True
        return self.get_token(platform_id) is not None

    # =========================================================================
    # CAPABILITY CHECKING
    # =========================================================================

    def can(self, capability: str) -> bool:
        """Check if Orion can perform a capability right now."""
        caps = self.registry.list_capabilities()
        return capability in caps

    def available_capabilities(self) -> Dict[str, List[str]]:
        """List all capabilities available from connected platforms."""
        return self.registry.list_capabilities()

    def get_provider_for(self, capability: str) -> Optional[str]:
        """Get the best platform ID that provides a capability."""
        platform = self.registry.get_platform_for_capability(capability)
        return platform.id if platform else None

    def describe_capabilities(self) -> str:
        """
        Get a human-readable description of available capabilities.
        Used for injecting into LLM system prompts.
        """
        caps = self.available_capabilities()
        if not caps:
            return "No external platforms connected. Orion can only use local tools."

        lines = ["Connected platform capabilities:"]
        for cap_name, providers in sorted(caps.items()):
            lines.append(f"  - {cap_name} (via {', '.join(providers)})")
        return "\n".join(lines)

    # =========================================================================
    # AUTHENTICATED HTTP CALLS
    # =========================================================================

    def set_approval_callback(self, callback: Callable[[str], bool]):
        """
        Set the human approval callback for write operations.

        The callback receives a human-readable prompt string and must
        return True (approved) or False (denied).

        Without this callback, ALL write operations are BLOCKED.
        This is AEGIS Invariant 6 — not configurable, not bypassable.
        """
        self._approval_callback = callback

    async def api_call(
        self,
        platform_id: str,
        method: str,
        url: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Make an authenticated API call to a platform.

        ALL calls pass through AEGIS Invariant 6 (External Access Control).
        Write operations (POST/PUT/PATCH/DELETE) REQUIRE human approval.

        Args:
            platform_id: Which platform to call
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            url: Full URL to call
            json_data: JSON body for POST/PUT/PATCH
            params: Query parameters
            headers: Additional headers
            description: Human-readable description of the action

        Returns:
            {"status": int, "data": dict, "ok": bool}
        """
        # =====================================================================
        # AEGIS INVARIANT 6: External Access Control (HARDCODED)
        # This gate CANNOT be removed, disabled, or bypassed.
        # =====================================================================
        from orion.core.governance.aegis import (
            check_external_access, ExternalAccessRequest
        )

        access_request = ExternalAccessRequest(
            platform_id=platform_id,
            method=method.upper(),
            url=url,
            description=description,
        )
        aegis_result = check_external_access(access_request)

        if aegis_result.requires_approval:
            if self._approval_callback is None:
                logger.warning(
                    f"AEGIS-6 BLOCKED: {method.upper()} {url} — "
                    f"no approval callback registered, write denied"
                )
                return {
                    "ok": False,
                    "status": 0,
                    "error": (
                        f"AEGIS BLOCKED: Orion cannot perform write operations "
                        f"on {platform_id} without human approval. "
                        f"Action: {description or method.upper() + ' ' + url}"
                    ),
                    "data": None,
                    "aegis_blocked": True,
                }

            # Ask human for approval
            approved = self._approval_callback(aegis_result.approval_prompt)
            if not approved:
                logger.info(
                    f"AEGIS-6 DENIED by human: {method.upper()} {url}"
                )
                return {
                    "ok": False,
                    "status": 0,
                    "error": f"Action denied by user: {description or method.upper() + ' ' + url}",
                    "data": None,
                    "aegis_denied": True,
                }

            logger.info(f"AEGIS-6 APPROVED by human: {method.upper()} {url}")

        # =====================================================================
        # END AEGIS GATE — proceed with authenticated request
        # =====================================================================

        token = self.get_token(platform_id)
        if not token:
            return {
                "ok": False,
                "status": 0,
                "error": f"Not connected to {platform_id}. Please connect it in Settings.",
                "data": None,
            }

        import httpx

        req_headers = headers or {}
        # Set auth header based on platform
        platform = self.registry.get(platform_id)
        if platform and platform.auth_method.value == "oauth":
            req_headers.setdefault("Authorization", f"Bearer {token}")
        elif platform_id == "github":
            req_headers.setdefault("Authorization", f"Bearer {token}")
            req_headers.setdefault("Accept", "application/vnd.github+json")
            req_headers.setdefault("X-GitHub-Api-Version", "2022-11-28")
        elif platform_id == "gitlab":
            req_headers.setdefault("PRIVATE-TOKEN", token)
        elif platform_id == "slack":
            req_headers.setdefault("Authorization", f"Bearer {token}")
        elif platform_id == "notion":
            req_headers.setdefault("Authorization", f"Bearer {token}")
            req_headers.setdefault("Notion-Version", "2022-06-28")
        else:
            req_headers.setdefault("Authorization", f"Bearer {token}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    method=method.upper(),
                    url=url,
                    json=json_data,
                    params=params,
                    headers=req_headers,
                )
                try:
                    data = resp.json()
                except Exception:
                    data = {"text": resp.text[:2000]}

                return {
                    "ok": resp.is_success,
                    "status": resp.status_code,
                    "data": data,
                }
        except Exception as e:
            return {
                "ok": False,
                "status": 0,
                "error": str(e),
                "data": None,
            }

    # =========================================================================
    # GITHUB HELPERS
    # =========================================================================

    async def github_list_repos(self, per_page: int = 30) -> Dict:
        """List the authenticated user's repos."""
        return await self.api_call("github", "GET", "https://api.github.com/user/repos", params={"per_page": per_page, "sort": "updated"})

    async def github_search_code(self, query: str) -> Dict:
        """Search code across GitHub."""
        return await self.api_call("github", "GET", "https://api.github.com/search/code", params={"q": query})

    async def github_create_issue(self, owner: str, repo: str, title: str, body: str = "", labels: List[str] = None) -> Dict:
        """Create a GitHub issue."""
        data = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        return await self.api_call("github", "POST", f"https://api.github.com/repos/{owner}/{repo}/issues", json_data=data)

    async def github_list_issues(self, owner: str, repo: str, state: str = "open") -> Dict:
        """List issues for a repo."""
        return await self.api_call("github", "GET", f"https://api.github.com/repos/{owner}/{repo}/issues", params={"state": state})

    async def github_get_file(self, owner: str, repo: str, path: str, ref: str = "main") -> Dict:
        """Get file contents from a repo."""
        return await self.api_call("github", "GET", f"https://api.github.com/repos/{owner}/{repo}/contents/{path}", params={"ref": ref})

    async def github_create_pr(self, owner: str, repo: str, title: str, body: str, head: str, base: str = "main") -> Dict:
        """Create a pull request."""
        return await self.api_call("github", "POST", f"https://api.github.com/repos/{owner}/{repo}/pulls",
                                   json_data={"title": title, "body": body, "head": head, "base": base})

    # =========================================================================
    # GITLAB HELPERS
    # =========================================================================

    async def gitlab_list_projects(self, per_page: int = 20) -> Dict:
        """List the authenticated user's projects."""
        return await self.api_call("gitlab", "GET", "https://gitlab.com/api/v4/projects", params={"membership": True, "per_page": per_page, "order_by": "updated_at"})

    async def gitlab_create_issue(self, project_id: int, title: str, description: str = "") -> Dict:
        """Create a GitLab issue."""
        return await self.api_call("gitlab", "POST", f"https://gitlab.com/api/v4/projects/{project_id}/issues",
                                   json_data={"title": title, "description": description})

    # =========================================================================
    # SLACK HELPERS
    # =========================================================================

    async def slack_send_message(self, channel: str, text: str) -> Dict:
        """Send a message to a Slack channel."""
        return await self.api_call("slack", "POST", "https://slack.com/api/chat.postMessage",
                                   json_data={"channel": channel, "text": text})

    async def slack_list_channels(self) -> Dict:
        """List Slack channels."""
        return await self.api_call("slack", "GET", "https://slack.com/api/conversations.list", params={"limit": 100})

    # =========================================================================
    # NOTION HELPERS
    # =========================================================================

    async def notion_search(self, query: str) -> Dict:
        """Search Notion workspace."""
        return await self.api_call("notion", "POST", "https://api.notion.com/v1/search", json_data={"query": query})

    async def notion_get_page(self, page_id: str) -> Dict:
        """Get a Notion page."""
        return await self.api_call("notion", "GET", f"https://api.notion.com/v1/pages/{page_id}")

    # =========================================================================
    # GENERIC TOOL INTERFACE (for agent use)
    # =========================================================================

    async def execute_capability(self, capability: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a capability by name.

        This is the main interface for Orion agents. They specify what
        they want to do, and the service routes to the right platform.

        Args:
            capability: e.g. "create_issue", "send_message", "list_repos"
            **kwargs: Capability-specific arguments

        Returns:
            {"ok": bool, "data": ..., "platform": str}
        """
        provider_id = self.get_provider_for(capability)
        if not provider_id:
            return {
                "ok": False,
                "error": f"No connected platform provides '{capability}'. "
                         f"Connect a platform in Settings that supports this.",
                "platform": None,
            }

        # Route to platform-specific implementation
        method_name = f"{provider_id}_{capability}"
        method = getattr(self, method_name, None)

        if method and callable(method):
            try:
                result = await method(**kwargs)
                result["platform"] = provider_id
                return result
            except Exception as e:
                return {"ok": False, "error": str(e), "platform": provider_id}

        return {
            "ok": False,
            "error": f"Capability '{capability}' exists on {provider_id} but no handler implemented yet.",
            "platform": provider_id,
        }


# =============================================================================
# SINGLETON
# =============================================================================

_service: Optional[PlatformService] = None


def get_platform_service() -> PlatformService:
    """Get or create the global platform service."""
    global _service
    if _service is None:
        _service = PlatformService()
    return _service
