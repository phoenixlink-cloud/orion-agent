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
"""Execution Feedback Loop — LLM-driven error correction for sandbox commands.

When a command fails inside the SessionContainer, this module:
1. Classifies the error (syntax, dependency, runtime, timeout, permission)
2. Asks the LLM for a corrective action (fix command, install dep, edit file)
3. Applies the fix inside the container
4. Retries the original command
5. Repeats up to ``max_retries`` times or until success

The feedback loop is invoked by the TaskExecutor after any ``exec()`` call
that returns a non-zero exit code.

See Phase 4A.2 specification.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from orion.security.session_container import SessionContainer

logger = logging.getLogger("orion.ara.execution_feedback")

# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class ErrorCategory(str, Enum):
    """Categories for classifying execution errors."""

    SYNTAX = "syntax"
    MISSING_DEPENDENCY = "missing_dependency"
    RUNTIME = "runtime"
    TIMEOUT = "timeout"
    PERMISSION = "permission"
    FILE_NOT_FOUND = "file_not_found"
    UNKNOWN = "unknown"


# Patterns for classifying errors — checked in order, first match wins
_ERROR_PATTERNS: list[tuple[ErrorCategory, list[str]]] = [
    (
        ErrorCategory.SYNTAX,
        [
            r"SyntaxError",
            r"IndentationError",
            r"TabError",
            r"unexpected token",
            r"parse error",
            r"syntax error",
        ],
    ),
    (
        ErrorCategory.MISSING_DEPENDENCY,
        [
            r"ModuleNotFoundError",
            r"ImportError",
            r"No module named",
            r"Cannot find module",
            r"could not resolve",
            r"npm ERR! missing",
            r"package .+ is not installed",
            r"command not found",
        ],
    ),
    (
        ErrorCategory.FILE_NOT_FOUND,
        [
            r"FileNotFoundError",
            r"No such file or directory",
            r"ENOENT",
        ],
    ),
    (
        ErrorCategory.PERMISSION,
        [
            r"PermissionError",
            r"Permission denied",
            r"EACCES",
            r"Operation not permitted",
        ],
    ),
    (
        ErrorCategory.TIMEOUT,
        [
            r"timed out",
            r"TimeoutError",
            r"deadline exceeded",
        ],
    ),
    (
        ErrorCategory.RUNTIME,
        [
            r"Error",
            r"Exception",
            r"Traceback",
            r"FAILED",
            r"error",
        ],
    ),
]


def classify_error(stderr: str, stdout: str = "", exit_code: int = 1) -> ErrorCategory:
    """Classify an execution error into a category.

    Args:
        stderr: Standard error output from the failed command.
        stdout: Standard output (sometimes errors appear here).
        exit_code: Process exit code.

    Returns:
        The best-matching ErrorCategory.
    """
    if exit_code == -1 and "timed out" in stderr.lower():
        return ErrorCategory.TIMEOUT

    combined = f"{stderr}\n{stdout}"
    for category, patterns in _ERROR_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                return category

    return ErrorCategory.UNKNOWN


# ---------------------------------------------------------------------------
# Fix action
# ---------------------------------------------------------------------------


@dataclass
class FixAction:
    """A corrective action suggested by the LLM."""

    description: str = ""
    command: str | None = None
    file_path: str | None = None
    file_content: str | None = None
    install_command: str | None = None
    category: ErrorCategory = ErrorCategory.UNKNOWN
    confidence: float = 0.5


# ---------------------------------------------------------------------------
# Feedback result
# ---------------------------------------------------------------------------


@dataclass
class FeedbackResult:
    """Result of the feedback loop for a single command."""

    original_command: str = ""
    success: bool = False
    attempts: int = 0
    final_exit_code: int = -1
    final_stdout: str = ""
    final_stderr: str = ""
    error_category: ErrorCategory = ErrorCategory.UNKNOWN
    fixes_applied: list[FixAction] = field(default_factory=list)
    total_duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# LLM Fix Provider protocol
# ---------------------------------------------------------------------------


class FixProvider(Protocol):
    """Protocol for LLM-based fix suggestion."""

    async def suggest_fix(
        self,
        command: str,
        stderr: str,
        stdout: str,
        error_category: ErrorCategory,
        previous_fixes: list[FixAction],
    ) -> FixAction:
        """Suggest a fix for a failed command."""
        ...


# ---------------------------------------------------------------------------
# Default (rule-based) fix provider
# ---------------------------------------------------------------------------


class RuleBasedFixProvider:
    """Simple rule-based fix suggestions (no LLM required).

    Handles common cases:
    - Missing Python modules → ``pip install <module>``
    - Missing Node modules → ``npm install <module>``
    - File not found → suggest creating it
    - Syntax errors → no automatic fix (needs LLM)
    """

    async def suggest_fix(
        self,
        command: str,
        stderr: str,
        stdout: str,
        error_category: ErrorCategory,
        previous_fixes: list[FixAction],
    ) -> FixAction:
        combined = f"{stderr}\n{stdout}"

        if error_category == ErrorCategory.MISSING_DEPENDENCY:
            return self._fix_missing_dep(combined)

        if error_category == ErrorCategory.FILE_NOT_FOUND:
            return self._fix_file_not_found(combined)

        if error_category == ErrorCategory.PERMISSION:
            return FixAction(
                description="Permission error — cannot auto-fix in sandbox",
                category=ErrorCategory.PERMISSION,
                confidence=0.1,
            )

        if error_category == ErrorCategory.TIMEOUT:
            return FixAction(
                description="Command timed out — consider increasing timeout or simplifying",
                category=ErrorCategory.TIMEOUT,
                confidence=0.1,
            )

        return FixAction(
            description="Unable to determine automatic fix",
            category=error_category,
            confidence=0.0,
        )

    @staticmethod
    def _fix_missing_dep(output: str) -> FixAction:
        """Suggest install command for missing dependencies."""
        # Python: No module named 'flask'
        m = re.search(r"No module named ['\"]?(\w[\w.]*)['\"]?", output)
        if m:
            module = m.group(1).split(".")[0]
            return FixAction(
                description=f"Install missing Python module: {module}",
                install_command=f"pip install {module}",
                category=ErrorCategory.MISSING_DEPENDENCY,
                confidence=0.8,
            )

        # Node: Cannot find module 'express'
        m = re.search(r"Cannot find module ['\"](\S+)['\"]", output)
        if m:
            module = m.group(1)
            if not module.startswith("."):
                return FixAction(
                    description=f"Install missing Node module: {module}",
                    install_command=f"npm install {module}",
                    category=ErrorCategory.MISSING_DEPENDENCY,
                    confidence=0.8,
                )

        # Generic: command not found
        m = re.search(r"(\S+): command not found", output)
        if m:
            cmd = m.group(1)
            return FixAction(
                description=f"Command '{cmd}' not found — may need to install it",
                category=ErrorCategory.MISSING_DEPENDENCY,
                confidence=0.3,
            )

        return FixAction(
            description="Missing dependency detected but cannot determine package",
            category=ErrorCategory.MISSING_DEPENDENCY,
            confidence=0.2,
        )

    @staticmethod
    def _fix_file_not_found(output: str) -> FixAction:
        """Suggest fix for file not found errors."""
        m = re.search(r"No such file or directory:\s*['\"]?([^\s'\"]+)", output)
        if not m:
            m = re.search(r"FileNotFoundError.*?['\"]([^\s'\"]+)['\"]", output)
        if m:
            path = m.group(1)
            return FixAction(
                description=f"File not found: {path}",
                file_path=path,
                category=ErrorCategory.FILE_NOT_FOUND,
                confidence=0.5,
            )
        return FixAction(
            description="File not found error — path could not be extracted",
            category=ErrorCategory.FILE_NOT_FOUND,
            confidence=0.2,
        )


# ---------------------------------------------------------------------------
# LLM-based fix provider
# ---------------------------------------------------------------------------


class LLMFixProvider:
    """LLM-powered fix suggestions using the unified call_provider.

    Falls back to RuleBasedFixProvider if LLM call fails.
    """

    def __init__(self, provider: str = "ollama", model: str = "qwen2.5:14b"):
        self.provider = provider
        self.model = model
        self._fallback = RuleBasedFixProvider()

    async def suggest_fix(
        self,
        command: str,
        stderr: str,
        stdout: str,
        error_category: ErrorCategory,
        previous_fixes: list[FixAction],
    ) -> FixAction:
        try:
            return await self._llm_suggest(command, stderr, stdout, error_category, previous_fixes)
        except Exception as exc:
            logger.debug("LLM fix suggestion failed, using rules: %s", exc)
            return await self._fallback.suggest_fix(
                command, stderr, stdout, error_category, previous_fixes
            )

    async def _llm_suggest(
        self,
        command: str,
        stderr: str,
        stdout: str,
        error_category: ErrorCategory,
        previous_fixes: list[FixAction],
    ) -> FixAction:
        from orion.core.llm.config import RoleConfig
        from orion.core.llm.providers import call_provider

        prev_desc = ""
        if previous_fixes:
            prev_desc = "\n".join(
                f"  - Attempt {i + 1}: {f.description}" for i, f in enumerate(previous_fixes)
            )
            prev_desc = f"\nPrevious fix attempts (all failed):\n{prev_desc}\n"

        system_prompt = (
            "You are a DevOps debugging assistant. A command failed inside a Docker container. "
            "Analyze the error and suggest ONE corrective action.\n\n"
            "Reply in EXACTLY this format (no markdown, no extra text):\n"
            "DESCRIPTION: <one-line description of the fix>\n"
            "INSTALL: <install command if needed, or NONE>\n"
            "COMMAND: <corrective command to run, or NONE>\n"
            "CONFIDENCE: <0.0 to 1.0>\n"
        )

        user_prompt = (
            f"Failed command: {command}\n"
            f"Error category: {error_category.value}\n"
            f"Exit code: non-zero\n\n"
            f"STDERR:\n{stderr[:1000]}\n\n"
            f"STDOUT:\n{stdout[:500]}\n"
            f"{prev_desc}"
        )

        role_config = RoleConfig(provider=self.provider, model=self.model)
        response = await call_provider(
            role_config=role_config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=500,
            component="execution_feedback",
            temperature=0.2,
        )

        return self._parse_llm_response(response, error_category)

    @staticmethod
    def _parse_llm_response(response: str, category: ErrorCategory) -> FixAction:
        """Parse the structured LLM response into a FixAction."""
        fix = FixAction(category=category)

        for line in response.strip().splitlines():
            line = line.strip()
            if line.upper().startswith("DESCRIPTION:"):
                fix.description = line.split(":", 1)[1].strip()
            elif line.upper().startswith("INSTALL:"):
                val = line.split(":", 1)[1].strip()
                if val.upper() != "NONE" and val:
                    fix.install_command = val
            elif line.upper().startswith("COMMAND:"):
                val = line.split(":", 1)[1].strip()
                if val.upper() != "NONE" and val:
                    fix.command = val
            elif line.upper().startswith("CONFIDENCE:"):
                try:
                    fix.confidence = float(line.split(":", 1)[1].strip())
                except ValueError:
                    fix.confidence = 0.5

        if not fix.description:
            fix.description = "LLM suggested fix (could not parse description)"

        return fix


# ---------------------------------------------------------------------------
# ExecutionFeedbackLoop
# ---------------------------------------------------------------------------


class ExecutionFeedbackLoop:
    """Feedback loop that retries failed commands with LLM-guided fixes.

    Usage::

        container = SessionContainer(...)
        feedback = ExecutionFeedbackLoop(container, fix_provider=RuleBasedFixProvider())

        # Run a command with automatic error correction
        result = await feedback.run_with_feedback("python app.py")
    """

    def __init__(
        self,
        container: SessionContainer,
        fix_provider: FixProvider | RuleBasedFixProvider | LLMFixProvider | None = None,
        max_retries: int = 3,
        activity_logger: Any | None = None,
        execution_memory: Any | None = None,
    ) -> None:
        self.container = container
        self.fix_provider = fix_provider or RuleBasedFixProvider()
        self.max_retries = max_retries
        self.activity_logger = activity_logger
        self.execution_memory = execution_memory
        self._history: list[FeedbackResult] = []

    @property
    def history(self) -> list[FeedbackResult]:
        """Return feedback history for this session."""
        return list(self._history)

    async def run_with_feedback(
        self,
        command: str,
        timeout: int = 120,
    ) -> FeedbackResult:
        """Execute a command with automatic error correction.

        1. Run the command
        2. If it succeeds, return immediately
        3. If it fails, classify the error
        4. Ask the fix provider for a corrective action
        5. Apply the fix (install dep, run corrective command, edit file)
        6. Retry the original command
        7. Repeat up to max_retries

        Args:
            command: The command to execute.
            timeout: Timeout in seconds per attempt.

        Returns:
            FeedbackResult with final outcome and all fixes applied.
        """
        start = time.time()
        feedback = FeedbackResult(original_command=command)

        # Initial attempt
        exec_result = await self.container.exec(command, timeout=timeout)
        feedback.attempts = 1

        if exec_result.exit_code == 0:
            feedback.success = True
            feedback.final_exit_code = 0
            feedback.final_stdout = exec_result.stdout
            feedback.final_stderr = exec_result.stderr
            feedback.total_duration_seconds = time.time() - start
            self._history.append(feedback)
            return feedback

        # Classify the error
        feedback.error_category = classify_error(
            exec_result.stderr, exec_result.stdout, exec_result.exit_code
        )

        # Retry loop
        for attempt in range(self.max_retries):
            logger.info(
                "Feedback retry %d/%d for: %s (error=%s)",
                attempt + 1,
                self.max_retries,
                command[:80],
                feedback.error_category.value,
            )

            if self.activity_logger:
                self.activity_logger.log(
                    action_type="info",
                    description=(
                        f"Retry {attempt + 1}/{self.max_retries}: "
                        f"{feedback.error_category.value}"
                    ),
                    phase="execute",
                    status="running",
                )

            # Get fix suggestion
            fix = await self.fix_provider.suggest_fix(
                command=command,
                stderr=exec_result.stderr,
                stdout=exec_result.stdout,
                error_category=feedback.error_category,
                previous_fixes=feedback.fixes_applied,
            )
            feedback.fixes_applied.append(fix)

            # Skip if provider has no confidence
            if fix.confidence < 0.1:
                logger.info(
                    "Fix provider has low confidence (%.2f), stopping retries", fix.confidence
                )
                break

            # Apply the fix
            applied = await self._apply_fix(fix)
            if not applied:
                logger.info("Fix could not be applied, stopping retries")
                break

            # Retry original command
            exec_result = await self.container.exec(command, timeout=timeout)
            feedback.attempts += 1

            if exec_result.exit_code == 0:
                feedback.success = True
                break

            # Re-classify for the next iteration
            feedback.error_category = classify_error(
                exec_result.stderr, exec_result.stdout, exec_result.exit_code
            )

        feedback.final_exit_code = exec_result.exit_code
        feedback.final_stdout = exec_result.stdout
        feedback.final_stderr = exec_result.stderr
        feedback.total_duration_seconds = time.time() - start
        self._history.append(feedback)

        # Capture execution lesson if memory is wired
        if self.execution_memory:
            try:
                self.execution_memory.capture_lesson(
                    feedback_result=feedback,
                    task_description=command,
                    stack=getattr(self.container, "stack", "base"),
                    session_id=getattr(self.container, "session_id", ""),
                )
            except Exception as exc:
                logger.debug("Execution memory capture failed: %s", exc)

        logger.info(
            "Feedback loop %s after %d attempts: %s",
            "succeeded" if feedback.success else "failed",
            feedback.attempts,
            command[:80],
        )
        return feedback

    async def _apply_fix(self, fix: FixAction) -> bool:
        """Apply a fix action to the container.

        Returns True if the fix was applied (regardless of whether the
        original command will now succeed).
        """
        applied = False

        # Install dependency
        if fix.install_command:
            logger.info("Installing dependency: %s", fix.install_command)
            result = await self.container.exec_install(fix.install_command, timeout=120)
            if result.exit_code == 0:
                applied = True
            else:
                logger.warning("Install failed: %s", result.stderr[:200])

        # Run corrective command
        if fix.command:
            logger.info("Running corrective command: %s", fix.command)
            result = await self.container.exec(fix.command, timeout=60)
            if result.exit_code == 0:
                applied = True
            else:
                logger.warning("Corrective command failed: %s", result.stderr[:200])

        # Write file
        if fix.file_path and fix.file_content is not None:
            logger.info("Writing fix file: %s", fix.file_path)
            written = await self.container.write_file(fix.file_path, fix.file_content)
            if written:
                applied = True

        # If nothing concrete was applied but description exists, that's info-only
        if not applied and fix.description:
            logger.info("Fix is informational only: %s", fix.description)

        return applied
