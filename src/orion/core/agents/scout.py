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
#    See LICENSE-ENTERPRISE.md or contact licensing@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- Scout Module (v6.4.0)

Fast triage before expensive deliberation.
Routes requests to Fast Path, Council, or Escalation.

Based on proven approach: simple pattern matching + file count heuristics
runs in <500ms to avoid slowing down simple requests.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from orion.core.context.repo_map import RepoMap


class Route(Enum):
    """Request routing destinations."""
    FAST_PATH = "fast"      # Simple: read, answer, single file edit
    COUNCIL = "council"      # Complex: multi-file, architecture
    ESCALATION = "escalate"  # Dangerous: delete, security-critical


@dataclass
class ScoutReport:
    """Result of Scout analysis."""
    route: Route
    relevant_files: List[str]
    complexity_score: float  # 0.0 - 1.0
    risk_level: float        # 0.0 - 1.0
    reasoning: str


class Scout:
    """
    Fast triage before expensive deliberation.
    Runs in <500ms using rules + optional small model.
    """

    # Patterns that indicate simple operations
    SIMPLE_PATTERNS = [
        # File reading
        r'\b(show|display|print|read|cat|view|open)\s+(me\s+)?(the\s+)?(contents?\s+of\s+)?[\w./]+\.(py|js|ts|json|yaml|yml|md|txt|toml|cfg|ini)\b',
        r'\bwhat\s+(does|is\s+in)\s+[\w./]+\.(py|js|ts|json|yaml|yml|md|txt)\b',
        r'\bread\s+[\w./]+',
        r"read\s+(\S+)",
        r"show\s+(?:me\s+)?(\S+)",
        r"what\s+(?:does|is)\s+",
        r"explain\s+",

        # Simple fixes (typos, single line)
        r'\bfix\s+(the\s+)?(typo|spelling|grammar|mistake)\b',
        r'\bfix\s+(the\s+)?(a\s+)?bug\s+(in|on|at)\s+(line\s+)?\d+',
        r'\bcorrect\s+(the\s+)?(typo|spelling|mistake)\b',
        r'\b(change|update|fix)\s+(line\s+)?\d+\b',
        r"fix\s+(?:the\s+)?(?:bug|error|issue)\s+in\s+(\S+)",

        # Other simple operations
        r"rename\s+",
        r"add\s+(?:a\s+)?(?:comment|docstring)",
        r"list\s+(?:files|directory)",
        r"find\s+(?:where|the)",
        r"search\s+for",
        r"print\s+",
        r"display\s+",
        r"get\s+(?:the\s+)?(?:content|value)",
    ]

    # Patterns that indicate complex operations
    COMPLEX_PATTERNS = [
        r"refactor",
        r"add\s+(?:authentication|logging|caching|testing)",
        r"implement\s+",
        r"create\s+(?:a\s+)?(?:new\s+)?(?:feature|module|system|api|service)",
        r"build\s+",
        r"design\s+",
        r"migrate\s+",
        r"integrate\s+",
        r"set\s*up\s+",
        r"configure\s+",
        r"restructure",
        r"reorganize",
        r"convert\s+",
        r"upgrade\s+",
        r"add\s+(?:support\s+for|new)",
    ]

    # Patterns that require escalation (dangerous operations)
    DANGER_PATTERNS = [
        # Destructive operations
        r"delete\s+(?:all|multiple|\*|everything)",
        r"remove\s+(?:all|multiple|\*|everything)",
        r'\b(delete|remove|drop)\s+(all|every|\*|the\s+entire)',
        r"drop\s+(?:table|database|collection)",
        r"rm\s+-rf",
        r"truncate\s+",
        r"wipe\s+",
        r"destroy\s+",
        r'\b(wipe|destroy|nuke)\b',

        # Git repository destruction
        r'\b(delete|remove|rm)\b.*\.git\b',
        r'\.git\s*(directory|folder)',

        # Credentials (more specific - not "token" alone)
        r'\b(api[_-]?key|password|secret[_-]?key|credential)s?\b',
        r'\b(expose|leak|print|log|show)\s+.*(password|secret|key|credential)',
        r'\bprivate[_-]?key\b',
        r'\.env\b',

        # System-level danger
        r"sudo\s+",
        r"chmod\s+777",
        r"format\s+(?:disk|drive)",
        r'\b/(etc|var|usr|root)\b',

        # Production danger
        r'\bproduction\s+(database|server|env)\b',

        # Overwrite
        r"overwrite\s+(?:all|everything)",
    ]

    def __init__(self, workspace_path: str, repo_map: Optional['RepoMap'] = None):
        self.workspace = workspace_path
        self.repo_map = repo_map

    def analyze(self, request: str) -> ScoutReport:
        """
        Analyze request and determine routing.

        Args:
            request: User's natural language request

        Returns:
            ScoutReport with routing decision and metadata
        """
        request_lower = request.lower()

        # Check for danger patterns first (highest priority)
        for pattern in self.DANGER_PATTERNS:
            if re.search(pattern, request_lower):
                return ScoutReport(
                    route=Route.ESCALATION,
                    relevant_files=self._find_relevant_files(request),
                    complexity_score=0.9,
                    risk_level=0.9,
                    reasoning=f"Matched danger pattern: {pattern}"
                )

        # Check for simple patterns
        for pattern in self.SIMPLE_PATTERNS:
            if re.search(pattern, request_lower):
                return ScoutReport(
                    route=Route.FAST_PATH,
                    relevant_files=self._find_relevant_files(request),
                    complexity_score=0.2,
                    risk_level=0.1,
                    reasoning=f"Matched simple pattern: {pattern}"
                )

        # Check for complex patterns
        for pattern in self.COMPLEX_PATTERNS:
            if re.search(pattern, request_lower):
                return ScoutReport(
                    route=Route.COUNCIL,
                    relevant_files=self._find_relevant_files(request),
                    complexity_score=0.7,
                    risk_level=0.3,
                    reasoning=f"Matched complex pattern: {pattern}"
                )

        # Default: Use file count heuristic
        relevant = self._find_relevant_files(request)

        if len(relevant) == 0:
            # No files mentioned - likely a question or simple task
            return ScoutReport(
                route=Route.FAST_PATH,
                relevant_files=relevant,
                complexity_score=0.2,
                risk_level=0.1,
                reasoning="No specific files mentioned - treating as simple request"
            )
        elif len(relevant) == 1:
            return ScoutReport(
                route=Route.FAST_PATH,
                relevant_files=relevant,
                complexity_score=0.3,
                risk_level=0.2,
                reasoning="Single file operation"
            )
        elif len(relevant) <= 3:
            return ScoutReport(
                route=Route.COUNCIL,
                relevant_files=relevant,
                complexity_score=0.5,
                risk_level=0.3,
                reasoning=f"Multi-file operation ({len(relevant)} files)"
            )
        else:
            return ScoutReport(
                route=Route.COUNCIL,
                relevant_files=relevant,
                complexity_score=0.7,
                risk_level=0.4,
                reasoning=f"Large scope operation ({len(relevant)} files)"
            )

    def _find_relevant_files(self, request: str) -> List[str]:
        """
        Find files relevant to the request.

        Uses RepoMap if available, otherwise falls back to
        simple file path extraction from the request.
        """
        if self.repo_map:
            return self.repo_map.get_relevant_files(request, max_files=10)

        # Fallback: extract file paths from request
        return self._extract_file_paths(request)

    def _extract_file_paths(self, request: str) -> List[str]:
        """Extract file paths mentioned in the request."""
        files = []

        # Common file extensions (non-capturing group so findall returns full match)
        extensions = r'\.(?:py|js|ts|jsx|tsx|go|rs|java|cs|cpp|c|h|hpp|json|yaml|yml|md|txt|html|css|sql)'

        # Pattern for file paths
        patterns = [
            rf'([\w\-./\\]+{extensions})',  # path/to/file.ext
            r'`([^`]+)`',  # `filename` in backticks
        ]

        for pattern in patterns:
            matches = re.findall(pattern, request, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                # Clean up the match
                clean = match.strip('`').strip()
                if clean and len(clean) > 2:
                    files.append(clean)

        return list(set(files))[:10]  # Dedupe and limit


def get_scout(workspace_path: str, repo_map: Optional['RepoMap'] = None) -> Scout:
    """Factory function to get a Scout instance."""
    return Scout(workspace_path, repo_map)
