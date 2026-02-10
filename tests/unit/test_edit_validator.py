"""Unit tests for EditValidator -- path safety, syntax checks, confidence scoring."""

import pytest
from orion.core.editing.validator import EditValidator, ValidationResult, EditConfidence


@pytest.fixture
def validator():
    return EditValidator(workspace_path=".")


class TestPathSafety:
    """AEGIS: EditValidator must block path traversal and dangerous paths."""

    def test_blocks_path_traversal(self, validator):
        result = validator.validate_edits([
            {"operation": "CREATE", "path": "../../../etc/passwd", "content": "bad"}
        ])
        assert result.valid is False
        assert any("Path escape" in i for i in result.blocking_issues)

    def test_blocks_double_traversal(self, validator):
        result = validator.validate_edits([
            {"operation": "CREATE", "path": "foo/../../bar/../../../secret", "content": "x"}
        ])
        assert result.valid is False

    def test_allows_safe_relative_path(self, validator):
        result = validator.validate_edits([
            {"operation": "CREATE", "path": "src/hello.py", "content": "print('hi')\n"}
        ])
        assert result.valid is True
        assert result.avg_confidence >= 0.8

    def test_allows_simple_filename(self, validator):
        result = validator.validate_edits([
            {"operation": "CREATE", "path": "test.py", "content": "x = 1\n"}
        ])
        assert result.valid is True

    def test_blocks_etc_path(self, validator):
        result = validator.validate_edits([
            {"operation": "CREATE", "path": "/etc/shadow", "content": "bad"}
        ])
        assert result.valid is False
        assert any("Dangerous path" in i or "Absolute path" in i for i in result.blocking_issues)


class TestSyntaxValidation:
    """EditValidator should detect Python syntax errors."""

    def test_valid_python_scores_high(self, validator):
        conf = validator.score_edit("test.py", "def hello():\n    return 42\n", "CREATE")
        assert conf.syntax_valid is True
        assert conf.overall_score >= 0.8

    def test_invalid_python_scores_low(self, validator):
        conf = validator.score_edit("test.py", "def hello(\n    return\n", "CREATE")
        assert conf.syntax_valid is False
        assert conf.overall_score < 0.8

    def test_non_python_skips_syntax(self, validator):
        conf = validator.score_edit("readme.md", "# Hello\nSome text", "CREATE")
        assert conf.syntax_valid is True  # Syntax check only applies to .py


class TestBracketBalance:
    """EditValidator should detect unbalanced brackets."""

    def test_balanced_brackets(self, validator):
        conf = validator.score_edit("test.py", "x = [1, 2, (3, 4)]\n", "CREATE")
        assert conf.brackets_balanced is True

    def test_unbalanced_brackets(self, validator):
        conf = validator.score_edit("test.py", "x = [1, 2, (3, 4\n", "CREATE")
        assert conf.brackets_balanced is False


class TestContentSanity:
    """EditValidator should flag LLM artifacts."""

    def test_flags_markdown_fences_in_python(self, validator):
        conf = validator.score_edit("test.py", "```python\nprint('hi')\n```\n", "CREATE")
        assert len(conf.issues) > 0
        assert any("markdown" in i.lower() or "fence" in i.lower() for i in conf.issues)

    def test_flags_placeholder_code(self, validator):
        conf = validator.score_edit("test.py", "def main():\n    pass  # placeholder\n", "CREATE")
        assert len(conf.issues) > 0


class TestAutoRecover:
    """EditValidator auto-recovery for common LLM mistakes."""

    def test_strips_markdown_fences(self, validator):
        content = "```python\nprint('hello')\n```"
        fixed, fixes = validator.auto_recover("test.py", content)
        assert "```" not in fixed
        assert any("markdown" in f.lower() or "fence" in f.lower() for f in fixes)

    def test_normalizes_mixed_indent(self, validator):
        content = "def f():\n\treturn 1\n    x = 2\n"
        fixed, fixes = validator.auto_recover("test.py", content)
        assert "\t" not in fixed
        assert any("tab" in f.lower() or "indent" in f.lower() for f in fixes)

    def test_adds_trailing_newline(self, validator):
        content = "x = 1"
        fixed, fixes = validator.auto_recover("test.py", content)
        assert fixed.endswith("\n")


class TestBatchValidation:
    """Test validate_edits with multiple actions."""

    def test_mixed_batch(self, validator):
        result = validator.validate_edits([
            {"operation": "CREATE", "path": "good.py", "content": "x = 1\n"},
            {"operation": "CREATE", "path": "../bad.py", "content": "x = 1\n"},
        ])
        assert result.total_edits == 2
        assert result.valid is False  # One bad path makes batch invalid
        assert result.passed >= 1
