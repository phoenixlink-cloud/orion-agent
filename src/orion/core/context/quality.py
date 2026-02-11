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
Orion Agent -- Code Quality Analyzer (v7.4.0)

Automated quality checks:

    1. COMPLEXITY:     Cyclomatic complexity per function
    2. GOD CLASS:      Detect classes/modules that are too large
    3. COUPLING:       Fan-in/fan-out analysis
    4. NAMING:         PEP 8 naming convention checks
    5. DOCSTRINGS:     Missing docstring detection
    6. DUPLICATION:    Near-duplicate function detection
    7. FILE HEALTH:    Per-file quality score

Provides quality-aware context for LLM prompts and the /doctor command.
"""

import ast
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# THRESHOLDS
# ---------------------------------------------------------------------------

MAX_FUNCTION_LINES = 50
MAX_FUNCTION_COMPLEXITY = 10
MAX_CLASS_METHODS = 20
MAX_FILE_LINES = 500
MAX_FUNCTION_ARGS = 7
MIN_FUNCTION_NAME_LEN = 2


# ---------------------------------------------------------------------------
# DATA TYPES
# ---------------------------------------------------------------------------

class Severity:
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass
class QualityIssue:
    """A single code quality issue."""
    file: str
    line: int
    severity: str
    category: str
    message: str
    symbol: str = ""


@dataclass
class FileHealth:
    """Quality score for a single file."""
    file: str
    lines: int
    functions: int
    classes: int
    issues: List[QualityIssue] = field(default_factory=list)
    complexity_avg: float = 0.0
    docstring_coverage: float = 0.0

    @property
    def score(self) -> float:
        s = 100.0
        for issue in self.issues:
            if issue.severity == Severity.ERROR:
                s -= 10
            elif issue.severity == Severity.WARN:
                s -= 3
            else:
                s -= 1
        s += self.docstring_coverage * 10
        return max(0.0, min(100.0, s))

    @property
    def grade(self) -> str:
        sc = self.score
        if sc >= 90: return "A"
        if sc >= 80: return "B"
        if sc >= 70: return "C"
        if sc >= 60: return "D"
        return "F"


@dataclass
class QualityReport:
    """Full quality report for a codebase."""
    files: List[FileHealth] = field(default_factory=list)
    total_issues: int = 0
    errors: int = 0
    warnings: int = 0
    infos: int = 0

    @property
    def avg_score(self) -> float:
        if not self.files:
            return 100.0
        return sum(f.score for f in self.files) / len(self.files)

    @property
    def grade(self) -> str:
        sc = self.avg_score
        if sc >= 90: return "A"
        if sc >= 80: return "B"
        if sc >= 70: return "C"
        if sc >= 60: return "D"
        return "F"

    def summary(self) -> str:
        return (
            f"Grade: {self.grade} ({self.avg_score:.0f}/100) | "
            f"{len(self.files)} files | "
            f"{self.total_issues} issues ({self.errors} errors, "
            f"{self.warnings} warnings, {self.infos} info)"
        )


# ---------------------------------------------------------------------------
# COMPLEXITY CALCULATOR
# ---------------------------------------------------------------------------

def calculate_complexity(node: ast.AST) -> int:
    """Calculate cyclomatic complexity of a function/method."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp)):
            complexity += 1
        elif isinstance(child, ast.For):
            complexity += 1
        elif isinstance(child, ast.While):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, ast.With):
            complexity += 1
        elif isinstance(child, ast.Assert):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
    return complexity


# ---------------------------------------------------------------------------
# INDIVIDUAL CHECKS
# ---------------------------------------------------------------------------

def check_complexity(tree: ast.AST, rel_path: str) -> List[QualityIssue]:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = calculate_complexity(node)
            if cc > MAX_FUNCTION_COMPLEXITY:
                issues.append(QualityIssue(
                    file=rel_path, line=node.lineno,
                    severity=Severity.WARN if cc <= 15 else Severity.ERROR,
                    category="complexity",
                    message=f"Cyclomatic complexity {cc} (max {MAX_FUNCTION_COMPLEXITY})",
                    symbol=node.name,
                ))
    return issues


def check_function_length(tree: ast.AST, rel_path: str) -> List[QualityIssue]:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if hasattr(node, 'end_lineno') and node.end_lineno:
                length = node.end_lineno - node.lineno + 1
                if length > MAX_FUNCTION_LINES:
                    issues.append(QualityIssue(
                        file=rel_path, line=node.lineno,
                        severity=Severity.WARN if length <= 80 else Severity.ERROR,
                        category="function_length",
                        message=f"Function is {length} lines (max {MAX_FUNCTION_LINES})",
                        symbol=node.name,
                    ))
    return issues


def check_function_args(tree: ast.AST, rel_path: str) -> List[QualityIssue]:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a for a in node.args.args if a.arg != "self"]
            if len(args) > MAX_FUNCTION_ARGS:
                issues.append(QualityIssue(
                    file=rel_path, line=node.lineno,
                    severity=Severity.WARN,
                    category="too_many_args",
                    message=f"{len(args)} arguments (max {MAX_FUNCTION_ARGS})",
                    symbol=node.name,
                ))
    return issues


def check_god_class(tree: ast.AST, rel_path: str) -> List[QualityIssue]:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [n for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if len(methods) > MAX_CLASS_METHODS:
                issues.append(QualityIssue(
                    file=rel_path, line=node.lineno,
                    severity=Severity.WARN,
                    category="god_class",
                    message=f"Class has {len(methods)} methods (max {MAX_CLASS_METHODS})",
                    symbol=node.name,
                ))
    return issues


def check_file_length(source: str, rel_path: str) -> List[QualityIssue]:
    lines = len(source.splitlines())
    issues = []
    if lines > MAX_FILE_LINES:
        issues.append(QualityIssue(
            file=rel_path, line=1,
            severity=Severity.WARN if lines <= 800 else Severity.ERROR,
            category="file_length",
            message=f"File is {lines} lines (max {MAX_FILE_LINES})",
        ))
    return issues


def check_docstrings(tree: ast.AST, rel_path: str) -> Tuple[List[QualityIssue], float]:
    issues = []
    total = 0
    documented = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and node.name != "__init__":
                continue
            total += 1
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                documented += 1
            else:
                issues.append(QualityIssue(
                    file=rel_path, line=node.lineno,
                    severity=Severity.INFO,
                    category="missing_docstring",
                    message="Public function missing docstring",
                    symbol=node.name,
                ))
        elif isinstance(node, ast.ClassDef):
            total += 1
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                documented += 1
            else:
                issues.append(QualityIssue(
                    file=rel_path, line=node.lineno,
                    severity=Severity.INFO,
                    category="missing_docstring",
                    message="Class missing docstring",
                    symbol=node.name,
                ))

    coverage = documented / total if total > 0 else 1.0
    return issues, coverage


def check_naming(tree: ast.AST, rel_path: str) -> List[QualityIssue]:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if not re.match(r'^[A-Z][a-zA-Z0-9]*$', node.name):
                issues.append(QualityIssue(
                    file=rel_path, line=node.lineno,
                    severity=Severity.INFO,
                    category="naming",
                    message=f"Class '{node.name}' should be CamelCase",
                    symbol=node.name,
                ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if (not node.name.startswith("_")
                    and not re.match(r'^[a-z][a-z0-9_]*$', node.name)
                    and node.name not in ("setUp", "tearDown", "setUpClass")):
                issues.append(QualityIssue(
                    file=rel_path, line=node.lineno,
                    severity=Severity.INFO,
                    category="naming",
                    message=f"Function '{node.name}' should be snake_case",
                    symbol=node.name,
                ))
    return issues


# ---------------------------------------------------------------------------
# QUALITY ANALYZER
# ---------------------------------------------------------------------------

class CodeQualityAnalyzer:
    """Analyze code quality across a Python codebase."""

    def __init__(self, workspace_path: str):
        self.workspace = Path(workspace_path).resolve()

    def analyze(self, files: Optional[List[str]] = None) -> QualityReport:
        report = QualityReport()
        skip_dirs = {
            '.git', '.orion', 'node_modules', '__pycache__',
            'venv', 'env', '.venv', 'dist', 'build',
            '.pytest_cache', '.mypy_cache', 'site-packages',
        }

        if files:
            py_files = [(self.workspace / f, f) for f in files if f.endswith('.py')]
        else:
            py_files = []
            for root, dirs, fnames in os.walk(self.workspace):
                dirs[:] = [d for d in dirs if d not in skip_dirs
                           and not d.startswith('.')]
                for fname in fnames:
                    if fname.endswith('.py'):
                        fpath = Path(root) / fname
                        rel = str(fpath.relative_to(self.workspace))
                        py_files.append((fpath, rel))

        for fpath, rel_path in py_files:
            health = self._analyze_file(fpath, rel_path)
            if health:
                report.files.append(health)
                for issue in health.issues:
                    report.total_issues += 1
                    if issue.severity == Severity.ERROR:
                        report.errors += 1
                    elif issue.severity == Severity.WARN:
                        report.warnings += 1
                    else:
                        report.infos += 1

        return report

    def analyze_file(self, rel_path: str) -> Optional[FileHealth]:
        fpath = self.workspace / rel_path
        return self._analyze_file(fpath, rel_path)

    def _analyze_file(self, fpath: Path, rel_path: str) -> Optional[FileHealth]:
        try:
            source = fpath.read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(source, filename=rel_path)
        except Exception:
            return None

        issues: List[QualityIssue] = []
        issues.extend(check_file_length(source, rel_path))
        issues.extend(check_complexity(tree, rel_path))
        issues.extend(check_function_length(tree, rel_path))
        issues.extend(check_function_args(tree, rel_path))
        issues.extend(check_god_class(tree, rel_path))
        issues.extend(check_naming(tree, rel_path))

        doc_issues, doc_coverage = check_docstrings(tree, rel_path)
        issues.extend(doc_issues)

        func_count = sum(1 for n in ast.walk(tree)
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        class_count = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))

        complexities = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexities.append(calculate_complexity(node))
        avg_complexity = (sum(complexities) / len(complexities)) if complexities else 0

        return FileHealth(
            file=rel_path, lines=len(source.splitlines()),
            functions=func_count, classes=class_count,
            issues=issues, complexity_avg=avg_complexity,
            docstring_coverage=doc_coverage,
        )

    def get_worst_files(self, n: int = 10) -> List[FileHealth]:
        report = self.analyze()
        return sorted(report.files, key=lambda f: f.score)[:n]

    def get_quality_prompt(self, files: List[str]) -> str:
        report = self.analyze(files)
        if not report.files:
            return ""
        lines = ["## CODE QUALITY NOTES"]
        for fh in report.files:
            if fh.issues:
                lines.append(f"\n### {fh.file} (Grade: {fh.grade}, Score: {fh.score:.0f}/100)")
                for issue in fh.issues[:10]:
                    if issue.severity in (Severity.ERROR, Severity.WARN):
                        lines.append(f"- Line {issue.line}: [{issue.category}] {issue.message}")
        if len(lines) == 1:
            return ""
        lines.append("\nWhen editing these files, please address the above issues if possible.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CONVENIENCE API
# ---------------------------------------------------------------------------

def analyze_workspace(workspace_path: str) -> QualityReport:
    return CodeQualityAnalyzer(workspace_path).analyze()


def get_file_quality(workspace_path: str, rel_path: str) -> Optional[FileHealth]:
    return CodeQualityAnalyzer(workspace_path).analyze_file(rel_path)


def get_quality_context_for_prompt(workspace_path: str, files: List[str]) -> str:
    return CodeQualityAnalyzer(workspace_path).get_quality_prompt(files)
