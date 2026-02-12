"""Tests for orion.core.context -- repo_map, python_ast, quality."""

import ast

import pytest

from orion.core.context.python_ast import (
    PythonContext,
)
from orion.core.context.quality import (
    CodeQualityAnalyzer,
    FileHealth,
    QualityIssue,
    Severity,
    calculate_complexity,
    check_docstrings,
    check_naming,
)
from orion.core.context.repo_map import (
    LANGUAGE_MAP,
    SKIP_DIRS,
    RepoMap,
    _extract_python_signatures,
    _extract_tags_python_ast,
    generate_repo_map,
)

# =========================================================================
# CODE QUALITY
# =========================================================================


class TestCalculateComplexity:
    def test_simple_function(self):
        code = "def foo():\n    return 1\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 1

    def test_if_adds_complexity(self):
        code = "def foo(x):\n    if x:\n        return 1\n    return 0\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 2

    def test_for_loop(self):
        code = "def foo(items):\n    for i in items:\n        pass\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 2

    def test_nested_branches(self):
        code = "def foo(x, y):\n    if x:\n        if y:\n            return 1\n    return 0\n"
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 3


class TestCheckNaming:
    def test_valid_class_name(self):
        code = "class MyClass:\n    pass\n"
        tree = ast.parse(code)
        issues = check_naming(tree, "test.py")
        assert len(issues) == 0

    def test_invalid_class_name(self):
        code = "class my_class:\n    pass\n"
        tree = ast.parse(code)
        issues = check_naming(tree, "test.py")
        assert len(issues) == 1
        assert "CamelCase" in issues[0].message

    def test_valid_function_name(self):
        code = "def my_function():\n    pass\n"
        tree = ast.parse(code)
        issues = check_naming(tree, "test.py")
        assert len(issues) == 0


class TestCheckDocstrings:
    def test_documented_function(self):
        code = 'def foo():\n    """Docstring."""\n    pass\n'
        tree = ast.parse(code)
        issues, coverage = check_docstrings(tree, "test.py")
        assert coverage == 1.0
        assert len(issues) == 0

    def test_undocumented_function(self):
        code = "def foo():\n    pass\n"
        tree = ast.parse(code)
        issues, coverage = check_docstrings(tree, "test.py")
        assert coverage == 0.0
        assert len(issues) == 1


class TestFileHealth:
    def test_score_no_issues(self):
        fh = FileHealth(file="test.py", lines=10, functions=1, classes=0, docstring_coverage=1.0)
        assert fh.score == 100.0
        assert fh.grade == "A"

    def test_score_with_errors(self):
        fh = FileHealth(
            file="test.py",
            lines=10,
            functions=1,
            classes=0,
            issues=[
                QualityIssue(
                    file="test.py",
                    line=1,
                    severity=Severity.ERROR,
                    category="test",
                    message="error",
                )
            ],
        )
        assert fh.score < 100.0


class TestCodeQualityAnalyzer:
    def test_analyze_workspace(self, tmp_path):
        (tmp_path / "good.py").write_text('def foo():\n    """Good."""\n    return 1\n')
        analyzer = CodeQualityAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert len(report.files) == 1
        assert report.files[0].grade in ("A", "B", "C", "D", "F")

    def test_analyze_empty_workspace(self, tmp_path):
        analyzer = CodeQualityAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert len(report.files) == 0
        assert report.avg_score == 100.0


# =========================================================================
# PYTHON CONTEXT
# =========================================================================


class TestPythonContext:
    @pytest.fixture
    def workspace(self, tmp_path):
        (tmp_path / "models.py").write_text(
            'class User:\n    """A user."""\n    def __init__(self, name):\n        self.name = name\n'
        )
        (tmp_path / "views.py").write_text(
            "from models import User\n\ndef get_user(name):\n    return User(name)\n"
        )
        return tmp_path

    def test_analyze(self, workspace):
        ctx = PythonContext(str(workspace))
        ctx.analyze()
        stats = ctx.get_stats()
        assert stats["python_files"] == 2
        assert stats["classes"] >= 1

    def test_import_graph(self, workspace):
        ctx = PythonContext(str(workspace)).analyze()
        graph = ctx.get_import_graph()
        assert isinstance(graph, dict)

    def test_class_hierarchy(self, workspace):
        ctx = PythonContext(str(workspace)).analyze()
        hierarchy = ctx.get_class_hierarchy()
        assert "User" in hierarchy

    def test_find_symbol(self, workspace):
        ctx = PythonContext(str(workspace)).analyze()
        results = ctx.find_symbol("User")
        assert len(results) >= 1
        assert results[0].kind == "class"

    def test_semantic_search(self, workspace):
        ctx = PythonContext(str(workspace)).analyze()
        results = ctx.semantic_search("user")
        assert len(results) > 0

    def test_get_context_for_file(self, workspace):
        ctx = PythonContext(str(workspace)).analyze()
        context = ctx.get_context_for_file("models.py")
        assert context["file"] == "models.py"
        assert len(context["classes"]) >= 1


# =========================================================================
# REPO MAP
# =========================================================================


class TestRepoMap:
    @pytest.fixture
    def workspace(self, tmp_path):
        (tmp_path / "main.py").write_text("from utils import helper\n\ndef main():\n    helper()\n")
        (tmp_path / "utils.py").write_text('def helper():\n    """A helper."""\n    return 42\n')
        return tmp_path

    def test_python_ast_fallback(self, workspace):
        fpath = workspace / "main.py"
        tags = _extract_tags_python_ast(fpath, "main.py")
        defs = [t for t in tags if t.kind == "def"]
        assert any(t.name == "main" for t in defs)

    def test_python_signatures(self, workspace):
        fpath = workspace / "utils.py"
        sigs = _extract_python_signatures(fpath)
        assert len(sigs) >= 1
        assert "helper" in sigs[0][1]

    def test_repo_map_get_stats(self, workspace):
        rm = RepoMap(str(workspace))
        stats = rm.get_stats()
        assert stats["files"] >= 2
        assert stats["definitions"] >= 2
        rm.close()

    def test_repo_map_get_map(self, workspace):
        rm = RepoMap(str(workspace), max_tokens=2000)
        result = rm.get_repo_map()
        assert len(result) > 0
        rm.close()

    def test_repo_map_relevant_files(self, workspace):
        rm = RepoMap(str(workspace))
        files = rm.get_relevant_files("helper function")
        assert isinstance(files, list)
        rm.close()

    def test_generate_repo_map(self, workspace):
        result = generate_repo_map(str(workspace))
        assert len(result) > 0

    def test_language_map(self):
        assert ".py" in LANGUAGE_MAP
        assert ".js" in LANGUAGE_MAP
        assert ".ts" in LANGUAGE_MAP

    def test_skip_dirs(self):
        assert ".git" in SKIP_DIRS
        assert "node_modules" in SKIP_DIRS
        assert "__pycache__" in SKIP_DIRS
