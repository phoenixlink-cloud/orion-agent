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
Orion Agent -- Edit Validator & Confidence Scorer (v7.4.0)

Validates proposed code edits before they reach the sandbox, scores confidence,
and provides automatic error recovery.

CHECKS:
    1. SYNTAX VALIDATION -- Parse proposed code to catch syntax errors before write
    2. CONFIDENCE SCORING -- Score each edit (0.0-1.0) based on multiple signals
    3. DIFF INTEGRITY -- Verify search/replace targets exist in source files
    4. IMPORT VALIDATION -- Check that all imports resolve
    5. BRACKET/INDENT CHECK -- Detect unclosed brackets, inconsistent indentation
    6. ERROR RECOVERY -- Attempt automatic fixes for common LLM edit mistakes
    7. EDIT METRICS -- Track edit quality statistics over time
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class EditConfidence:
    """Confidence assessment for a single edit operation."""

    file_path: str
    operation: str  # CREATE, MODIFY, DELETE
    overall_score: float  # 0.0 to 1.0
    syntax_valid: bool
    imports_valid: bool
    brackets_balanced: bool
    indentation_consistent: bool
    diff_targets_found: bool
    content_length: int
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    auto_fixes_applied: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of validating a batch of edits."""

    valid: bool
    total_edits: int
    passed: int
    failed: int
    avg_confidence: float
    edit_confidences: list[EditConfidence] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    recoverable_issues: list[str] = field(default_factory=list)


@dataclass
class EditMetrics:
    """Aggregate metrics for edit quality tracking."""

    total_edits_validated: int = 0
    total_passed: int = 0
    total_failed: int = 0
    total_auto_fixed: int = 0
    avg_confidence: float = 0.0
    common_issues: dict[str, int] = field(default_factory=dict)


# =============================================================================
# EDIT VALIDATOR
# =============================================================================


class EditValidator:
    """
    Validates and scores code edits before they reach the sandbox.

    Usage:
        validator = EditValidator(workspace_path="/path/to/project")
        result = validator.validate_edits(actions)
        confidence = validator.score_edit(file_path, content, operation)
        fixed_content = validator.auto_recover(file_path, broken_content)
    """

    def __init__(self, workspace_path: str = None):
        self.workspace_path = workspace_path
        self._metrics = EditMetrics()

    # =========================================================================
    # PUBLIC API: VALIDATE BATCH
    # =========================================================================

    def validate_edits(self, actions: list[dict[str, Any]]) -> ValidationResult:
        """Validate a batch of edit actions from Table of Three."""
        confidences = []
        blocking = []
        recoverable = []

        for action in actions:
            path = action.get("path", "")
            content = action.get("content", "")
            operation = action.get("operation", "CREATE")

            confidence = self.score_edit(path, content, operation)
            confidences.append(confidence)

            for issue in confidence.issues:
                if self._is_blocking(issue):
                    blocking.append(f"{path}: {issue}")
                else:
                    recoverable.append(f"{path}: {issue}")

        total = len(confidences)
        passed = sum(1 for c in confidences if c.overall_score >= 0.6)
        failed = total - passed
        avg = sum(c.overall_score for c in confidences) / total if total > 0 else 0.0

        self._metrics.total_edits_validated += total
        self._metrics.total_passed += passed
        self._metrics.total_failed += failed
        self._metrics.avg_confidence = round(avg, 3)

        return ValidationResult(
            valid=len(blocking) == 0,
            total_edits=total,
            passed=passed,
            failed=failed,
            avg_confidence=round(avg, 3),
            edit_confidences=confidences,
            blocking_issues=blocking,
            recoverable_issues=recoverable,
        )

    # =========================================================================
    # PUBLIC API: SCORE SINGLE EDIT
    # =========================================================================

    def score_edit(self, file_path: str, content: str, operation: str = "CREATE") -> EditConfidence:
        """Score confidence for a single edit operation."""
        issues = []
        warnings = []
        auto_fixes = []

        # ── Path safety check (AEGIS) ──────────────────────────────
        path_issues = self._check_path_safety(file_path)
        issues.extend(path_issues)

        ext = Path(file_path).suffix.lower() if file_path else ""

        syntax_valid = True
        if ext == ".py" and content.strip():
            syntax_valid, syntax_error = self._check_python_syntax(content)
            if not syntax_valid:
                issues.append(f"Syntax error: {syntax_error}")

        imports_valid = True
        if ext == ".py" and content.strip():
            imports_valid, import_issues = self._check_imports(content)
            for imp_issue in import_issues:
                warnings.append(f"Import: {imp_issue}")

        brackets_balanced = self._check_brackets(content)
        if not brackets_balanced:
            issues.append("Unbalanced brackets/parentheses/braces")

        indent_consistent = True
        if ext == ".py":
            indent_consistent, indent_issue = self._check_indentation(content)
            if not indent_consistent:
                warnings.append(f"Indentation: {indent_issue}")

        content_issues = self._check_content_sanity(content, ext)
        issues.extend(content_issues)

        diff_targets = True
        if operation == "MODIFY" and self.workspace_path:
            diff_targets = self._check_diff_targets(file_path, content)
            if not diff_targets:
                issues.append("Search/replace targets not found in source file")

        score = self._compute_confidence(
            syntax_valid,
            imports_valid,
            brackets_balanced,
            indent_consistent,
            diff_targets,
            len(issues),
            len(warnings),
            len(content),
        )

        return EditConfidence(
            file_path=file_path,
            operation=operation,
            overall_score=round(score, 3),
            syntax_valid=syntax_valid,
            imports_valid=imports_valid,
            brackets_balanced=brackets_balanced,
            indentation_consistent=indent_consistent,
            diff_targets_found=diff_targets,
            content_length=len(content),
            issues=issues,
            warnings=warnings,
            auto_fixes_applied=auto_fixes,
        )

    # =========================================================================
    # PUBLIC API: AUTO-RECOVER
    # =========================================================================

    def auto_recover(self, file_path: str, content: str) -> tuple[str, list[str]]:
        """Attempt automatic recovery from common LLM edit mistakes."""
        fixes = []
        result = content

        result, fixed = self._fix_markdown_fences(result)
        if fixed:
            fixes.append("Removed markdown code fences")

        result, fixed = self._fix_trailing_whitespace(result)
        if fixed:
            fixes.append("Fixed trailing whitespace")

        ext = Path(file_path).suffix.lower()
        if ext == ".py":
            result, fixed = self._fix_mixed_indentation(result)
            if fixed:
                fixes.append("Normalized mixed tabs/spaces to spaces")

        result, fixed = self._fix_unclosed_strings(result)
        if fixed:
            fixes.append("Fixed unclosed string literal")

        if result and not result.endswith("\n"):
            result += "\n"
            fixes.append("Added trailing newline")

        if fixes:
            self._metrics.total_auto_fixed += 1

        return result, fixes

    # =========================================================================
    # PUBLIC API: METRICS
    # =========================================================================

    def get_metrics(self) -> EditMetrics:
        """Get aggregate edit validation metrics."""
        return self._metrics

    def reset_metrics(self):
        """Reset edit metrics."""
        self._metrics = EditMetrics()

    # =========================================================================
    # INTERNAL: VALIDATION CHECKS
    # =========================================================================

    def _check_python_syntax(self, content: str) -> tuple[bool, str]:
        try:
            ast.parse(content)
            return True, ""
        except SyntaxError as e:
            return False, f"Line {e.lineno}: {e.msg}"

    def _check_imports(self, content: str) -> tuple[bool, list[str]]:
        issues = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return True, []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("."):
                        issues.append(f"Relative import '{alias.name}' may not resolve")
            elif isinstance(node, ast.ImportFrom):
                if node.module and "__" in node.module and node.module != "__future__":
                    issues.append(f"Suspicious import from '{node.module}'")

        return len(issues) == 0, issues

    def _check_brackets(self, content: str) -> bool:
        stack = []
        pairs = {"(": ")", "[": "]", "{": "}"}
        in_string = False
        string_char = None
        escape = False

        for char in content:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if in_string:
                if char == string_char:
                    in_string = False
                continue
            if char in ('"', "'"):
                in_string = True
                string_char = char
                continue
            if char == "#":
                break
            if char in pairs:
                stack.append(pairs[char])
            elif char in pairs.values():
                if not stack or stack[-1] != char:
                    return False
                stack.pop()

        return len(stack) == 0

    def _check_indentation(self, content: str) -> tuple[bool, str]:
        lines = content.split("\n")
        has_tabs = False
        has_spaces = False

        for line in lines:
            if not line.strip():
                continue
            leading = line[: len(line) - len(line.lstrip())]
            if "\t" in leading:
                has_tabs = True
            if " " in leading and leading.strip() == "":
                has_spaces = True

        if has_tabs and has_spaces:
            return False, "Mixed tabs and spaces"
        return True, ""

    def _check_content_sanity(self, content: str, ext: str) -> list[str]:
        issues = []

        if not content.strip():
            issues.append("Empty content")
            return issues

        if "```" in content and ext != ".md":
            issues.append("Contains markdown code fence (LLM artifact)")

        placeholders = [
            "# TODO: implement",
            "# ... rest of implementation",
            "// ... rest of implementation",
            "pass  # placeholder",
            "raise NotImplementedError",
        ]
        for ph in placeholders:
            if ph in content:
                issues.append(f"Contains placeholder: '{ph}'")

        for i, line in enumerate(content.split("\n"), 1):
            if len(line) > 500 and ext != ".json":
                issues.append(f"Line {i} is {len(line)} chars (possible LLM error)")
                break

        return issues

    def _check_diff_targets(self, file_path: str, content: str) -> bool:
        if not self.workspace_path:
            return True

        source_path = Path(self.workspace_path) / file_path
        if not source_path.exists():
            return True

        try:
            source = source_path.read_text(encoding="utf-8")
        except Exception:
            return True

        search_pattern = re.compile(r"<<<<<<< SEARCH\n(.+?)\n=======", re.DOTALL)
        matches = search_pattern.findall(content)

        return all(search_text.strip() in source for search_text in matches)

    # =========================================================================
    # INTERNAL: CONFIDENCE COMPUTATION
    # =========================================================================

    def _compute_confidence(
        self,
        syntax_valid,
        imports_valid,
        brackets_balanced,
        indent_consistent,
        diff_targets,
        issue_count,
        warning_count,
        content_length,
    ) -> float:
        score = 1.0

        if not syntax_valid:
            score -= 0.4
        if not brackets_balanced:
            score -= 0.3
        if not diff_targets:
            score -= 0.3
        if not imports_valid:
            score -= 0.1
        if not indent_consistent:
            score -= 0.1

        score -= issue_count * 0.1
        score -= warning_count * 0.03

        if content_length > 100:
            score += 0.05
        if content_length > 500:
            score += 0.05

        # Empty/whitespace-only content penalty
        if issue_count > 0 and content_length < 10:
            score -= 0.3

        return max(0.0, min(1.0, score))

    # =========================================================================
    # INTERNAL: AUTO-RECOVERY FIXES
    # =========================================================================

    def _fix_markdown_fences(self, content: str) -> tuple[str, bool]:
        if not content.startswith("```"):
            return content, False
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines), True

    def _fix_trailing_whitespace(self, content: str) -> tuple[str, bool]:
        lines = content.split("\n")
        fixed_lines = [line.rstrip() for line in lines]
        fixed = "\n".join(fixed_lines)
        return fixed, fixed != content

    def _fix_mixed_indentation(self, content: str) -> tuple[str, bool]:
        if "\t" not in content:
            return content, False
        fixed = content.replace("\t", "    ")
        return fixed, True

    def _fix_unclosed_strings(self, content: str) -> tuple[str, bool]:
        lines = content.rstrip().split("\n")
        if not lines:
            return content, False

        last_line = lines[-1]
        single_count = last_line.count("'") - last_line.count("\\'")
        double_count = last_line.count('"') - last_line.count('\\"')

        fixed = False
        if single_count % 2 != 0:
            lines[-1] = last_line + "'"
            fixed = True
        if double_count % 2 != 0:
            lines[-1] = lines[-1] + '"'
            fixed = True

        if not fixed:
            return content, False
        return "\n".join(lines), True

    def _is_blocking(self, issue: str) -> bool:
        blocking_keywords = [
            "Syntax error",
            "Unbalanced brackets",
            "Empty content",
            "targets not found",
            "Path escape",
            "Absolute path",
            "Dangerous path",
        ]
        return any(kw in issue for kw in blocking_keywords)

    def _check_path_safety(self, file_path: str) -> list[str]:
        """Check file path for traversal attacks and workspace escapes."""
        issues = []
        if not file_path:
            issues.append("Empty file path")
            return issues

        normalized = file_path.replace("\\", "/")

        # Path traversal
        if ".." in normalized:
            issues.append(f"Path escape: '{file_path}' contains '..' traversal")

        # Absolute paths
        if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
            if self.workspace_path:
                ws = str(Path(self.workspace_path).resolve()).replace("\\", "/")
                resolved = str(Path(file_path).resolve()).replace("\\", "/")
                if not resolved.startswith(ws):
                    issues.append(f"Absolute path outside workspace: '{file_path}'")
            else:
                issues.append(f"Absolute path without workspace context: '{file_path}'")

        # Dangerous system paths
        danger_prefixes = [
            "/etc/",
            "/var/",
            "/usr/",
            "/root/",
            "/bin/",
            "/sbin/",
            "C:/Windows",
            "C:/Program Files",
        ]
        for prefix in danger_prefixes:
            if normalized.lower().startswith(prefix.lower()):
                issues.append(f"Dangerous path target: '{file_path}'")
                break

        return issues


# =============================================================================
# FACTORY
# =============================================================================


def get_edit_validator(workspace_path: str = None) -> EditValidator:
    """Factory function to create an EditValidator."""
    return EditValidator(workspace_path)
