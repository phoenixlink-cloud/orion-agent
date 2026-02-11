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
Orion Agent -- Repository Map Generator (v7.4.0)

Generates an intelligent, ranked map of a codebase for LLM context.

Architecture:
    1. SCAN:      Walk workspace, find source files by extension
    2. PARSE:     Extract definition + reference tags via tree-sitter (all languages)
    3. CACHE:     Persist tags to disk, invalidate on file mtime change
    4. GRAPH:     Build a networkx DiGraph of file-to-file references
    5. RANK:      PageRank with personalization toward chat/relevant files
    6. BUDGET:    Binary search for the largest map that fits the token budget
    7. FORMAT:    Output ranked file signatures for LLM prompt injection

Supports: Python, JavaScript, TypeScript, Go, Rust, Java, C#, C, C++, Ruby
"""

import os
import ast
import hashlib
import time as _time
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, NamedTuple
from collections import defaultdict
from dataclasses import dataclass

import networkx as nx

try:
    from tree_sitter_language_pack import get_parser as _ts_get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

try:
    import diskcache
    DISKCACHE_AVAILABLE = True
except ImportError:
    DISKCACHE_AVAILABLE = False


# =============================================================================
# DATA TYPES
# =============================================================================

class Tag(NamedTuple):
    """A code tag (definition or reference)."""
    rel_fname: str
    fname: str
    line: int
    name: str
    kind: str  # 'def' or 'ref'


@dataclass
class FileEntry:
    """Cached metadata for a single file."""
    rel_path: str
    abs_path: str
    mtime: float
    tags: List[Tag]


# =============================================================================
# LANGUAGE CONFIGURATION
# =============================================================================

LANGUAGE_MAP = {
    '.py': 'python',
    '.js': 'javascript',
    '.ts': 'typescript',
    '.jsx': 'javascript',
    '.tsx': 'typescript',
    '.go': 'go',
    '.rs': 'rust',
    '.rb': 'ruby',
    '.java': 'java',
    '.cs': 'c_sharp',
    '.cpp': 'cpp',
    '.c': 'c',
    '.h': 'c',
    '.hpp': 'cpp',
}

SKIP_DIRS = {
    '.git', '.orion', 'node_modules', '__pycache__',
    'venv', 'env', '.venv', 'dist', 'build',
    '.pytest_cache', '.mypy_cache', '.next', '.tox',
    'eggs', '.eggs', 'site-packages',
}

# Tree-sitter node types that represent definitions
DEF_NODE_TYPES = {
    'function_definition', 'function_declaration',
    'class_definition', 'class_declaration',
    'method_definition', 'method_declaration',
    'interface_declaration', 'enum_declaration',
    'struct_item', 'impl_item', 'trait_item',
    'function_item', 'type_alias',
}

# Tree-sitter node types that represent identifiers (references)
REF_NODE_TYPES = {
    'identifier', 'type_identifier', 'field_identifier',
    'property_identifier', 'shorthand_property_identifier',
}


# =============================================================================
# TREE-SITTER TAG EXTRACTION
# =============================================================================

def _extract_tags_tree_sitter(fpath: Path, rel_path: str, lang: str) -> List[Tag]:
    """Extract definition and reference tags using tree-sitter."""
    if not TREE_SITTER_AVAILABLE:
        return []

    tags = []
    try:
        content = fpath.read_text(encoding='utf-8', errors='ignore')
        content_bytes = content.encode('utf-8')
        parser = _ts_get_parser(lang)
        tree = parser.parse(content_bytes)
    except Exception:
        return []

    # Collect all definitions first (to filter refs later)
    defs_in_file: Set[str] = set()

    def _walk_defs(node):
        if node.type in DEF_NODE_TYPES:
            for child in node.children:
                if child.type in ('identifier', 'name', 'type_identifier'):
                    name = content_bytes[child.start_byte:child.end_byte].decode('utf-8', errors='replace')
                    if name and len(name) > 1 and not name.startswith('_'):
                        tags.append(Tag(
                            rel_fname=rel_path,
                            fname=str(fpath),
                            line=child.start_point[0] + 1,
                            name=name,
                            kind='def',
                        ))
                        defs_in_file.add(name)
                    break
        for child in node.children:
            _walk_defs(child)

    _walk_defs(tree.root_node)

    # Second pass: collect references (identifiers not defined in this file)
    seen_refs: Set[str] = set()

    def _walk_refs(node):
        if node.type in REF_NODE_TYPES and node.parent and node.parent.type not in DEF_NODE_TYPES:
            name = content_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace')
            if (name and len(name) > 1
                    and not name.startswith('_')
                    and name not in seen_refs):
                seen_refs.add(name)
                tags.append(Tag(
                    rel_fname=rel_path,
                    fname=str(fpath),
                    line=node.start_point[0] + 1,
                    name=name,
                    kind='ref',
                ))
        for child in node.children:
            _walk_refs(child)

    _walk_refs(tree.root_node)
    return tags


# =============================================================================
# PYTHON AST FALLBACK (when tree-sitter unavailable for Python)
# =============================================================================

def _extract_tags_python_ast(fpath: Path, rel_path: str) -> List[Tag]:
    """Extract tags from Python using the built-in ast module."""
    tags = []
    try:
        content = fpath.read_text(encoding='utf-8', errors='ignore')
        tree = ast.parse(content)
    except Exception:
        return []

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef,)):
            tags.append(Tag(rel_path, str(fpath), node.lineno, node.name, 'def'))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            tags.append(Tag(rel_path, str(fpath), node.lineno, node.name, 'def'))
        elif isinstance(node, ast.Name):
            if len(node.id) > 1 and not node.id.startswith('_'):
                tags.append(Tag(rel_path, str(fpath), getattr(node, 'lineno', 0), node.id, 'ref'))
    return tags


# =============================================================================
# PYTHON SIGNATURE EXTRACTION (for rich map output)
# =============================================================================

def _extract_python_signatures(fpath: Path) -> List[Tuple[int, str]]:
    """Extract (line, signature_string) pairs from a Python file."""
    sigs = []
    try:
        content = fpath.read_text(encoding='utf-8', errors='ignore')
        tree = ast.parse(content)
    except Exception:
        return []

    def _fmt_arg(arg):
        s = arg.arg
        if arg.annotation:
            s += f": {_ast_name(arg.annotation)}"
        return s

    def _fmt_func(node, indent=""):
        args = [_fmt_arg(a) for a in node.args.args]
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        ret = f" -> {_ast_name(node.returns)}" if node.returns else ""
        return f"{indent}def {node.name}({', '.join(args)}){ret}"

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = [_ast_name(b) for b in node.bases]
            base_str = f"({', '.join(bases)})" if bases else ""
            sigs.append((node.lineno, f"class {node.name}{base_str}"))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sigs.append((item.lineno, _fmt_func(item, indent="  ")))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sigs.append((node.lineno, _fmt_func(node)))

    return sigs


def _ast_name(node) -> str:
    """Get string representation of an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_ast_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Subscript):
        return f"{_ast_name(node.value)}[{_ast_name(node.slice)}]"
    elif isinstance(node, ast.Constant):
        return str(node.value)
    elif isinstance(node, ast.Tuple):
        return ", ".join(_ast_name(e) for e in node.elts)
    return "..."


# =============================================================================
# DISK CACHE
# =============================================================================

class TagCache:
    """Persistent disk cache for file tags. Invalidates on mtime change."""

    def __init__(self, workspace: Path):
        self._cache = None
        self._workspace_key = str(workspace)
        if DISKCACHE_AVAILABLE:
            cache_dir = workspace / ".orion" / "tags_cache"
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
                self._cache = diskcache.Cache(str(cache_dir), size_limit=100 * 1024 * 1024)
            except Exception:
                self._cache = None

    def get(self, abs_path: str, mtime: float) -> Optional[List[Tag]]:
        if not self._cache:
            return None
        key = f"{abs_path}:{mtime}"
        val = self._cache.get(key)
        if val is not None:
            return [Tag(*t) for t in val]
        return None

    def put(self, abs_path: str, mtime: float, tags: List[Tag]):
        if not self._cache:
            return
        key = f"{abs_path}:{mtime}"
        self._cache.set(key, [tuple(t) for t in tags])

    def get_bulk(self, fingerprint: str) -> Optional[List[Tag]]:
        if not self._cache:
            return None
        key = f"bulk:{self._workspace_key}:{fingerprint}"
        val = self._cache.get(key)
        if val is not None:
            return [Tag(*t) for t in val]
        return None

    def put_bulk(self, fingerprint: str, tags: List[Tag]):
        if not self._cache:
            return
        key = f"bulk:{self._workspace_key}:{fingerprint}"
        self._cache.set(key, [tuple(t) for t in tags])

    def close(self):
        if self._cache:
            self._cache.close()


# =============================================================================
# REPOMAP CLASS
# =============================================================================

class RepoMap:
    """
    Build an intelligent, ranked map of a code repository.

    Uses tree-sitter for multi-language tag extraction, networkx PageRank
    for file importance ranking, diskcache for persistence, and binary
    search to fit the output within a token budget.
    """

    def __init__(self, workspace_path: str, max_tokens: int = 2048):
        self.workspace = Path(workspace_path).resolve()
        self.max_tokens = max_tokens
        self._tag_cache = TagCache(self.workspace)
        self._all_tags: Optional[List[Tag]] = None
        self._graph: Optional[nx.DiGraph] = None

    def close(self):
        self._tag_cache.close()

    # -----------------------------------------------------------------
    # PUBLIC API
    # -----------------------------------------------------------------

    def get_repo_map(self, chat_files: Optional[List[str]] = None) -> str:
        all_tags = self._get_all_tags()
        if not all_tags:
            return self._fallback_map()

        graph = self._build_graph(all_tags)
        ranked_files = self._rank_files(graph, chat_files or [])
        return self._fit_to_budget(all_tags, ranked_files)

    def get_relevant_files(self, query: str, max_files: int = 10) -> List[str]:
        # Try deep Python context search first
        try:
            from orion.core.context.python_ast import get_python_context
            ctx = get_python_context(str(self.workspace))
            results = ctx.semantic_search(query, max_results=max_files)
            if results:
                return [f for f, _ in results]
        except Exception:
            pass

        # Fallback: tag-based matching with PageRank boost
        all_tags = self._get_all_tags()
        query_terms = set(self._tokenize(query))

        file_scores: Dict[str, float] = defaultdict(float)
        for tag in all_tags:
            tag_terms = set(self._tokenize(tag.name))
            overlap = len(query_terms & tag_terms)
            if overlap > 0:
                weight = 3.0 if tag.kind == 'def' else 1.0
                file_scores[tag.rel_fname] += overlap * weight

        try:
            ranks = self.get_file_rank()
            for fname in file_scores:
                if fname in ranks:
                    file_scores[fname] *= (1.0 + ranks[fname] * 10)
        except Exception:
            pass

        ranked = sorted(file_scores.items(), key=lambda x: -x[1])
        return [f for f, _ in ranked[:max_files]]

    def get_file_rank(self, chat_files: Optional[List[str]] = None) -> Dict[str, float]:
        all_tags = self._get_all_tags()
        graph = self._build_graph(all_tags)
        if not graph or not graph.nodes():
            return {}

        personalization = None
        if chat_files:
            personalization = {
                f: (10.0 if f in chat_files else 0.1)
                for f in graph.nodes()
            }
        try:
            return nx.pagerank(graph, personalization=personalization, alpha=0.85)
        except Exception:
            return {f: 1.0 for f in graph.nodes()}

    def get_stats(self) -> Dict[str, int]:
        tags = self._get_all_tags()
        files = set(t.rel_fname for t in tags)
        defs = [t for t in tags if t.kind == 'def']
        refs = [t for t in tags if t.kind == 'ref']
        langs = set()
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in LANGUAGE_MAP:
                langs.add(LANGUAGE_MAP[ext])
        return {
            "files": len(files),
            "definitions": len(defs),
            "references": len(refs),
            "languages": len(langs),
            "language_list": sorted(langs),
            "tree_sitter": TREE_SITTER_AVAILABLE,
            "disk_cache": DISKCACHE_AVAILABLE,
        }

    # -----------------------------------------------------------------
    # TAG EXTRACTION
    # -----------------------------------------------------------------

    def _get_all_tags(self) -> List[Tag]:
        if self._all_tags is not None:
            return self._all_tags

        file_list: List[Tuple[Path, str, str, float]] = []
        for root, dirs, files in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in LANGUAGE_MAP:
                    continue
                fpath = Path(root) / fname
                rel_path = str(fpath.relative_to(self.workspace))
                try:
                    mtime = fpath.stat().st_mtime
                except OSError:
                    continue
                file_list.append((fpath, rel_path, ext, mtime))

        fp_parts = sorted(f"{rel}:{mt}" for _, rel, _, mt in file_list)
        fingerprint = hashlib.md5("|".join(fp_parts).encode()).hexdigest()

        bulk = self._tag_cache.get_bulk(fingerprint)
        if bulk is not None:
            self._all_tags = bulk
            return bulk

        tags = []
        for fpath, rel_path, ext, mtime in file_list:
            cached = self._tag_cache.get(str(fpath), mtime)
            if cached is not None:
                tags.extend(cached)
                continue
            file_tags = self._parse_file(fpath, rel_path, ext)
            self._tag_cache.put(str(fpath), mtime, file_tags)
            tags.extend(file_tags)

        self._tag_cache.put_bulk(fingerprint, tags)
        self._all_tags = tags
        return tags

    def _parse_file(self, fpath: Path, rel_path: str, ext: str) -> List[Tag]:
        lang = LANGUAGE_MAP.get(ext)
        if TREE_SITTER_AVAILABLE and lang:
            tags = _extract_tags_tree_sitter(fpath, rel_path, lang)
            if tags:
                return tags
        if ext == '.py':
            return _extract_tags_python_ast(fpath, rel_path)
        return []

    # -----------------------------------------------------------------
    # GRAPH + PAGERANK
    # -----------------------------------------------------------------

    def _build_graph(self, tags: List[Tag]) -> nx.DiGraph:
        if self._graph is not None:
            return self._graph

        graph = nx.DiGraph()
        definitions: Dict[str, Set[str]] = defaultdict(set)
        for tag in tags:
            if tag.kind == 'def':
                definitions[tag.name].add(tag.rel_fname)
                graph.add_node(tag.rel_fname)

        for tag in tags:
            if tag.kind == 'ref' and tag.name in definitions:
                for def_file in definitions[tag.name]:
                    if def_file != tag.rel_fname:
                        if graph.has_edge(tag.rel_fname, def_file):
                            graph[tag.rel_fname][def_file]['weight'] += 1
                        else:
                            graph.add_edge(tag.rel_fname, def_file, weight=1)

        self._graph = graph
        return graph

    def _rank_files(self, graph: nx.DiGraph, chat_files: List[str]) -> List[str]:
        if not graph or not graph.nodes():
            return []
        personalization = None
        if chat_files:
            personalization = {
                f: (10.0 if f in chat_files else 0.1)
                for f in graph.nodes()
            }
        try:
            ranks = nx.pagerank(graph, personalization=personalization, alpha=0.85)
            return sorted(ranks.keys(), key=lambda f: -ranks[f])
        except Exception:
            return list(graph.nodes())

    # -----------------------------------------------------------------
    # TOKEN BUDGET + OUTPUT FORMATTING
    # -----------------------------------------------------------------

    def _fit_to_budget(self, tags: List[Tag], ranked_files: List[str]) -> str:
        defs_by_file: Dict[str, List[Tag]] = defaultdict(list)
        for tag in tags:
            if tag.kind == 'def':
                defs_by_file[tag.rel_fname].append(tag)

        py_sigs: Dict[str, List[Tuple[int, str]]] = {}
        for fname in ranked_files:
            if fname.endswith('.py'):
                fpath = self.workspace / fname
                if fpath.exists():
                    sigs = _extract_python_signatures(fpath)
                    if sigs:
                        py_sigs[fname] = sigs

        def _build_map(num_files: int) -> str:
            lines = []
            for fname in ranked_files[:num_files]:
                if fname in py_sigs:
                    lines.append(f"{fname}:")
                    for _line, sig in py_sigs[fname]:
                        lines.append(f"  {sig}")
                elif fname in defs_by_file:
                    lines.append(f"{fname}:")
                    for tag in sorted(defs_by_file[fname], key=lambda t: t.line):
                        lines.append(f"  {tag.line}: {tag.name}")
                if lines:
                    lines.append("")
            return "\n".join(lines)

        lo, hi = 1, len(ranked_files) if ranked_files else 1
        best_map = ""
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = _build_map(mid)
            tokens = self._estimate_tokens(candidate)
            if tokens <= self.max_tokens:
                best_map = candidate
                lo = mid + 1
            else:
                hi = mid - 1
        return best_map if best_map else self._fallback_map()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return int(len(text) / 3.5)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        import re
        parts = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        return [t.lower() for t in re.split(r'[^a-zA-Z0-9]+', parts) if len(t) > 1]

    def _fallback_map(self) -> str:
        lines = ["# Repository Structure"]
        count = 0
        for root, dirs, files in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in SKIP_DIRS]
            level = len(Path(root).relative_to(self.workspace).parts)
            indent = "  " * level
            lines.append(f"{indent}{os.path.basename(root)}/")
            for f in sorted(files)[:10]:
                lines.append(f"{indent}  {f}")
                count += 1
            if count > 60:
                lines.append("... (truncated)")
                break
        return "\n".join(lines)


# =============================================================================
# CONVENIENCE / BACKWARD-COMPATIBLE API
# =============================================================================

def generate_repo_map(workspace_path: str, max_tokens: int = 2000) -> str:
    rm = RepoMap(workspace_path, max_tokens)
    result = rm.get_repo_map()
    rm.close()
    return result


def get_repo_map_for_prompt(workspace_path: str, context_files: Optional[List[str]] = None) -> str:
    rm = RepoMap(workspace_path)
    repo_map = rm.get_repo_map(chat_files=context_files)
    rm.close()
    result = ["<repository_map>", repo_map]
    if context_files:
        result.append("")
        result.append("Files in active context:")
        for f in context_files:
            result.append(f"  - {f}")
    result.append("</repository_map>")
    return "\n".join(result)


def generate_file_dependency_map(workspace_path: str, created_files: List[str]) -> str:
    rm = RepoMap(workspace_path)
    graph = rm._build_graph(rm._get_all_tags())
    rm.close()
    lines = ["# File Dependencies"]
    for fname in created_files:
        if not graph.has_node(fname):
            lines.append(f"{fname}: (not in graph)")
            continue
        deps = list(graph.successors(fname))
        if deps:
            lines.append(f"{fname} -> {', '.join(deps)}")
        else:
            lines.append(f"{fname}: no dependencies")
    return "\n".join(lines)


def get_compact_file_summary(workspace_path: str, filename: str, max_lines: int = 30) -> str:
    filepath = os.path.join(workspace_path, filename)
    if not os.path.exists(filepath):
        return f"{filename}: (not found)"
    fpath = Path(filepath)
    try:
        content = fpath.read_text(encoding='utf-8', errors='ignore')
        total_lines = len(content.splitlines())
        if filename.endswith('.py'):
            sigs = _extract_python_signatures(fpath)
            if sigs:
                sig_lines = [s for _, s in sigs[:max_lines]]
                return f"{filename} ({total_lines} lines):\n  " + "\n  ".join(sig_lines)
        lines = content.splitlines()
        preview = '\n'.join(lines[:max_lines])
        if total_lines > max_lines:
            preview += f"\n... ({total_lines - max_lines} more lines)"
        return f"{filename}:\n{preview}"
    except Exception as e:
        return f"{filename}: (error: {e})"


def get_repo_map_instance(workspace_path: str, max_tokens: int = 2048) -> RepoMap:
    return RepoMap(workspace_path, max_tokens)
