"""Unit tests for Builder's extract_json helper."""

import pytest
from orion.core.agents.builder import extract_json


class TestExtractJson:
    """Test JSON extraction from various LLM response formats."""

    def test_clean_json(self):
        result = extract_json('{"outcome": "ANSWER", "response": "hello"}')
        assert result is not None
        assert result["outcome"] == "ANSWER"
        assert result["response"] == "hello"

    def test_json_in_markdown_code_block(self):
        result = extract_json('```json\n{"outcome": "CODE_CHANGE", "response": "fix"}\n```')
        assert result is not None
        assert result["outcome"] == "CODE_CHANGE"

    def test_json_in_plain_code_block(self):
        result = extract_json('```\n{"outcome": "ANSWER", "response": "test"}\n```')
        assert result is not None
        assert result["outcome"] == "ANSWER"

    def test_json_with_surrounding_text(self):
        result = extract_json('Here is my answer:\n{"outcome": "ANSWER", "response": "test"}\nDone.')
        assert result is not None
        assert result["outcome"] == "ANSWER"

    def test_garbage_returns_none(self):
        result = extract_json("this is not json at all")
        assert result is None

    def test_empty_string_returns_none(self):
        result = extract_json("")
        assert result is None

    def test_nested_json(self):
        raw = '{"outcome": "CODE_CHANGE", "response": "adding file", "actions": [{"operation": "create", "path": "test.py", "content": "print(1)"}]}'
        result = extract_json(raw)
        assert result is not None
        assert result["outcome"] == "CODE_CHANGE"
        assert len(result["actions"]) == 1

    def test_json_with_newlines_in_values(self):
        raw = '{"outcome": "ANSWER", "response": "line1\\nline2\\nline3"}'
        result = extract_json(raw)
        assert result is not None
        assert "line1" in result["response"]
