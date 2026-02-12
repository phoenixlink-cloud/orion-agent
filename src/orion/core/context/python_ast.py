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
Orion Agent -- Deep Python Context Analysis (v7.4.0)

Provides deep understanding of Python codebases beyond tree-sitter tags:

    1. IMPORT GRAPH:     Parse imports, resolve to files, build dependency graph
    2. CLASS HIERARCHY:  Track inheritance (bases, subclasses)
    3. CALL GRAPH:       Track cross-file function calls
    4. SYMBOL TABLE:     Map every name to its definition location
    5. SCOPE ANALYSIS:   Understand module-level, class-level, function-level scope
    6. SEMANTIC SEARCH:  Find files by meaning, not just token overlap

This augments the existing repo_map.py with Python-specific intelligence.
"""

import ast
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# DATA TYPES
# ---------------------------------------------------------------------------


@dataclass
class ImportInfo:
    """A single import statement."""

    module: str
    names: list[str]
    alias: str | None = None
    is_from: bool = False
    line: int = 0
    source_file: str = ""

    @property
    def top_level(self) -> str:
        return self.module.split(".")[0] if self.module else ""


@dataclass
class ClassInfo:
    """Metadata about a Python class."""

    name: str
    file: str
    line: int
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    is_dataclass: bool = False
    is_abstract: bool = False


@dataclass
class FunctionInfo:
    """Metadata about a Python function or method."""

    name: str
    file: str
    line: int
    args: list[str] = field(default_factory=list)
    return_type: str = ""
    calls: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    is_method: bool = False
    parent_class: str = ""


@dataclass
class SymbolDef:
    """A symbol definition location."""

    name: str
    kind: str  # "class", "function", "method", "variable", "constant"
    file: str
    line: int
    scope: str = ""  # "module", "class:ClassName", "function:func_name"


# ---------------------------------------------------------------------------
# PYTHON CONTEXT ANALYZER
# ---------------------------------------------------------------------------


class PythonContext:
    """
    Deep Python codebase analyzer.

    Builds import graph, class hierarchy, call graph, and symbol table
    from AST analysis of all .py files in a workspace.
    """

    def __init__(self, workspace_path: str):
        self.workspace = Path(workspace_path).resolve()
        self._imports: dict[str, list[ImportInfo]] = {}
        self._classes: dict[str, ClassInfo] = {}
        self._functions: dict[str, FunctionInfo] = {}
        self._symbols: dict[str, list[SymbolDef]] = {}
        self._file_modules: dict[str, str] = {}
        self._module_files: dict[str, str] = {}
        self._analyzed = False

    # -----------------------------------------------------------------
    # PUBLIC API
    # -----------------------------------------------------------------

    def analyze(self) -> "PythonContext":
        """Analyze all Python files in workspace. Returns self for chaining."""
        if self._analyzed:
            return self

        self._build_module_index()

        for fpath, rel_path in self._iter_python_files():
            try:
                source = fpath.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source, filename=rel_path)
                self._extract_imports(tree, rel_path)
                self._extract_classes(tree, rel_path)
                self._extract_functions(tree, rel_path)
                self._extract_symbols(tree, rel_path)
            except (SyntaxError, Exception):
                continue

        self._analyzed = True
        return self

    def get_import_graph(self) -> dict[str, list[str]]:
        """Get import dependency graph: file -> [files it imports from]."""
        self._ensure_analyzed()
        graph: dict[str, list[str]] = defaultdict(list)

        for source_file, imports in self._imports.items():
            for imp in imports:
                resolved = self._resolve_import(imp)
                if resolved and resolved != source_file:
                    if resolved not in graph[source_file]:
                        graph[source_file].append(resolved)

        return dict(graph)

    def get_class_hierarchy(self) -> dict[str, dict[str, Any]]:
        """Get class hierarchy: class_name -> {bases, subclasses, methods, file}."""
        self._ensure_analyzed()
        hierarchy: dict[str, dict[str, Any]] = {}

        for _key, cls in self._classes.items():
            hierarchy[cls.name] = {
                "file": cls.file,
                "line": cls.line,
                "bases": cls.bases,
                "subclasses": [],
                "methods": cls.methods,
                "is_abstract": cls.is_abstract,
                "is_dataclass": cls.is_dataclass,
            }

        for _key, cls in self._classes.items():
            for base in cls.bases:
                if base in hierarchy:
                    hierarchy[base]["subclasses"].append(cls.name)

        return hierarchy

    def get_call_graph(self) -> dict[str, list[str]]:
        """Get cross-file call graph: "file:function" -> ["file:function", ...]."""
        self._ensure_analyzed()
        call_graph: dict[str, list[str]] = {}

        for key, func in self._functions.items():
            targets = []
            for called_name in func.calls:
                if called_name in self._symbols:
                    for sym in self._symbols[called_name]:
                        if sym.kind in ("function", "method", "class"):
                            target_key = f"{sym.file}:{sym.name}"
                            if target_key != key:
                                targets.append(target_key)
            if targets:
                call_graph[key] = targets

        return call_graph

    def get_symbol_table(self) -> dict[str, list[SymbolDef]]:
        self._ensure_analyzed()
        return dict(self._symbols)

    def find_symbol(self, name: str) -> list[SymbolDef]:
        self._ensure_analyzed()
        return self._symbols.get(name, [])

    def get_file_imports(self, rel_path: str) -> list[ImportInfo]:
        self._ensure_analyzed()
        return self._imports.get(rel_path, [])

    def get_file_classes(self, rel_path: str) -> list[ClassInfo]:
        self._ensure_analyzed()
        return [c for c in self._classes.values() if c.file == rel_path]

    def get_file_functions(self, rel_path: str) -> list[FunctionInfo]:
        self._ensure_analyzed()
        return [f for f in self._functions.values() if f.file == rel_path and not f.is_method]

    def get_dependents(self, rel_path: str) -> list[str]:
        """Find all files that import from the given file."""
        self._ensure_analyzed()
        dependents = []
        for source, imports in self._imports.items():
            for imp in imports:
                resolved = self._resolve_import(imp)
                if resolved == rel_path and source != rel_path:
                    dependents.append(source)
                    break
        return dependents

    def get_dependencies(self, rel_path: str) -> list[str]:
        graph = self.get_import_graph()
        return graph.get(rel_path, [])

    def semantic_search(self, query: str, max_results: int = 10) -> list[tuple[str, float]]:
        """Search for files semantically relevant to a query."""
        self._ensure_analyzed()
        query_terms = set(self._tokenize(query))
        if not query_terms:
            return []

        file_scores: dict[str, float] = defaultdict(float)

        # 1. Symbol name matching
        kind_weights = {
            "class": 5.0,
            "function": 3.0,
            "method": 2.0,
            "variable": 1.0,
            "constant": 1.5,
        }
        for name, defs in self._symbols.items():
            name_terms = set(self._tokenize(name))
            overlap = len(query_terms & name_terms)
            if overlap > 0:
                for sym in defs:
                    weight = kind_weights.get(sym.kind, 1.0) * overlap
                    file_scores[sym.file] += weight

        # 2. Import graph boost
        import_graph = self.get_import_graph()
        matching_files = set(f for f, s in file_scores.items() if s > 0)
        for mf in matching_files:
            for dep in import_graph.get(mf, []):
                file_scores[dep] += 1.5

        # 3. Class hierarchy boost
        hierarchy = self.get_class_hierarchy()
        for name in query_terms:
            cap_name = name.capitalize()
            if cap_name in hierarchy:
                info = hierarchy[cap_name]
                file_scores[info["file"]] += 3.0
                for sub in info["subclasses"]:
                    if sub in hierarchy:
                        file_scores[hierarchy[sub]["file"]] += 2.0

        # 4. Docstring matching
        for _key, cls in self._classes.items():
            if cls.docstring:
                doc_terms = set(self._tokenize(cls.docstring))
                overlap = len(query_terms & doc_terms)
                if overlap > 0:
                    file_scores[cls.file] += overlap * 1.5

        for _key, func in self._functions.items():
            if func.docstring:
                doc_terms = set(self._tokenize(func.docstring))
                overlap = len(query_terms & doc_terms)
                if overlap > 0:
                    file_scores[func.file] += overlap * 1.0

        # 5. Deprioritize test files
        for fname in list(file_scores.keys()):
            if fname.startswith("tests") or fname.startswith("tests\\"):
                file_scores[fname] *= 0.3

        ranked = sorted(file_scores.items(), key=lambda x: -x[1])
        return ranked[:max_results]

    def get_context_for_file(self, rel_path: str) -> dict[str, Any]:
        """Get rich context about a file for LLM prompt injection."""
        self._ensure_analyzed()
        imports = self.get_file_imports(rel_path)
        classes = self.get_file_classes(rel_path)
        functions = self.get_file_functions(rel_path)
        deps = self.get_dependencies(rel_path)
        dependents = self.get_dependents(rel_path)

        return {
            "file": rel_path,
            "imports": [{"module": i.module, "names": i.names} for i in imports],
            "classes": [
                {
                    "name": c.name,
                    "bases": c.bases,
                    "methods": c.methods,
                    "is_abstract": c.is_abstract,
                }
                for c in classes
            ],
            "functions": [
                {"name": f.name, "args": f.args, "return_type": f.return_type} for f in functions
            ],
            "depends_on": deps,
            "depended_by": dependents,
        }

    def get_stats(self) -> dict[str, int]:
        self._ensure_analyzed()
        return {
            "python_files": len(self._imports),
            "total_imports": sum(len(v) for v in self._imports.values()),
            "classes": len(self._classes),
            "functions": len(self._functions),
            "symbols": sum(len(v) for v in self._symbols.values()),
            "import_edges": sum(len(v) for v in self.get_import_graph().values()),
        }

    # -----------------------------------------------------------------
    # ANALYSIS INTERNALS
    # -----------------------------------------------------------------

    def _ensure_analyzed(self):
        if not self._analyzed:
            self.analyze()

    def _iter_python_files(self):
        skip_dirs = {
            ".git",
            ".orion",
            "node_modules",
            "__pycache__",
            "venv",
            "env",
            ".venv",
            "dist",
            "build",
            ".pytest_cache",
            ".mypy_cache",
            "site-packages",
        }
        for root, dirs, files in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip_dirs]
            for fname in files:
                if fname.endswith(".py"):
                    fpath = Path(root) / fname
                    rel_path = str(fpath.relative_to(self.workspace))
                    yield fpath, rel_path

    def _build_module_index(self):
        for _fpath, rel_path in self._iter_python_files():
            mod_path = rel_path.replace(os.sep, ".").replace("/", ".")
            if mod_path.endswith(".py"):
                mod_path = mod_path[:-3]
            if mod_path.endswith(".__init__"):
                mod_path = mod_path[:-9]
            self._file_modules[rel_path] = mod_path
            self._module_files[mod_path] = rel_path

    def _resolve_import(self, imp: ImportInfo) -> str | None:
        module = imp.module
        if module in self._module_files:
            return self._module_files[module]
        parts = module.split(".")
        for i in range(len(parts), 0, -1):
            partial = ".".join(parts[:i])
            if partial in self._module_files:
                return self._module_files[partial]
        return None

    def _extract_imports(self, tree: ast.AST, rel_path: str):
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ImportInfo(
                            module=alias.name,
                            names=[alias.name.split(".")[-1]],
                            alias=alias.asname,
                            is_from=False,
                            line=node.lineno,
                            source_file=rel_path,
                        )
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [a.name for a in node.names] if node.names else []
                imports.append(
                    ImportInfo(
                        module=node.module,
                        names=names,
                        is_from=True,
                        line=node.lineno,
                        source_file=rel_path,
                    )
                )
        self._imports[rel_path] = imports

    def _extract_classes(self, tree: ast.AST, rel_path: str):
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [self._ast_name(b) for b in node.bases]
                methods = [
                    item.name
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                decorators = [self._ast_name(d) for d in node.decorator_list]
                docstring = ""
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    docstring = node.body[0].value.value[:200]
                is_dataclass = "dataclass" in decorators
                is_abstract = any(b in ("ABC", "ABCMeta") for b in bases)
                key = f"{rel_path}:{node.name}"
                self._classes[key] = ClassInfo(
                    name=node.name,
                    file=rel_path,
                    line=node.lineno,
                    bases=bases,
                    methods=methods,
                    decorators=decorators,
                    docstring=docstring,
                    is_dataclass=is_dataclass,
                    is_abstract=is_abstract,
                )

    def _extract_functions(self, tree: ast.AST, rel_path: str):
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._register_function(node, rel_path, is_method=False)
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._register_function(
                            item, rel_path, is_method=True, parent_class=node.name
                        )

    def _register_function(
        self, node, rel_path: str, is_method: bool = False, parent_class: str = ""
    ):
        args = [a.arg for a in node.args.args if a.arg != "self"]
        ret = self._ast_name(node.returns) if node.returns else ""
        decorators = [self._ast_name(d) for d in node.decorator_list]
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._get_call_name(child)
                if call_name and call_name not in calls:
                    calls.append(call_name)
        docstring = ""
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            docstring = node.body[0].value.value[:200]
        prefix = f"{parent_class}." if parent_class else ""
        key = f"{rel_path}:{prefix}{node.name}"
        self._functions[key] = FunctionInfo(
            name=node.name,
            file=rel_path,
            line=node.lineno,
            args=args,
            return_type=ret,
            calls=calls,
            decorators=decorators,
            docstring=docstring,
            is_method=is_method,
            parent_class=parent_class,
        )

    def _extract_symbols(self, tree: ast.AST, rel_path: str):
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                self._add_symbol(node.name, "class", rel_path, node.lineno, "module")
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._add_symbol(
                            item.name, "method", rel_path, item.lineno, f"class:{node.name}"
                        )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._add_symbol(node.name, "function", rel_path, node.lineno, "module")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        kind = "constant" if target.id.isupper() else "variable"
                        self._add_symbol(target.id, kind, rel_path, node.lineno, "module")

    def _add_symbol(self, name: str, kind: str, file: str, line: int, scope: str):
        if name.startswith("_") and not name.startswith("__"):
            return
        sym = SymbolDef(name=name, kind=kind, file=file, line=line, scope=scope)
        if name not in self._symbols:
            self._symbols[name] = []
        self._symbols[name].append(sym)

    # -----------------------------------------------------------------
    # HELPERS
    # -----------------------------------------------------------------

    @staticmethod
    def _ast_name(node) -> str:
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{PythonContext._ast_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Subscript):
            return f"{PythonContext._ast_name(node.value)}[...]"
        if isinstance(node, ast.Constant):
            return str(node.value)
        if isinstance(node, ast.Call):
            return PythonContext._ast_name(node.func)
        return "..."

    @staticmethod
    def _get_call_name(node: ast.Call) -> str:
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return ""

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        return {t.lower() for t in re.split(r"[^a-zA-Z0-9]+", parts) if len(t) > 1}


# ---------------------------------------------------------------------------
# SINGLETON
# ---------------------------------------------------------------------------

_instances: dict[str, PythonContext] = {}


def get_python_context(workspace_path: str) -> PythonContext:
    """Get or create a PythonContext for a workspace."""
    key = os.path.normpath(workspace_path)
    if key not in _instances:
        _instances[key] = PythonContext(workspace_path)
    return _instances[key]
