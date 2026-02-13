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
"""Tests for BriefBuilder -- structured brief generation for Builder/Reviewer."""

import pytest

from orion.core.understanding.brief_builder import BriefBuilder, TaskBrief
from orion.core.understanding.clarification import ClarificationResult
from orion.core.understanding.intent_classifier import ClassificationResult

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def builder():
    """Provide a BriefBuilder."""
    return BriefBuilder()


def _cr(intent: str, sub: str = "", conf: float = 0.9) -> ClassificationResult:
    return ClassificationResult(intent=intent, sub_intent=sub, confidence=conf, method="keyword")


def _no_clarify() -> ClarificationResult:
    return ClarificationResult(needs_clarification=False, reason="clear")


def _needs_clarify(questions: list[str] | None = None) -> ClarificationResult:
    return ClarificationResult(
        needs_clarification=True,
        questions=questions or ["What file?"],
        reason="missing_context",
    )


# =============================================================================
# TASK BRIEF STRUCTURE
# =============================================================================


class TestTaskBriefStructure:
    """Test that TaskBrief has the correct shape."""

    def test_returns_task_brief(self, builder):
        brief = builder.build("Fix the bug in auth.py", _cr("coding", "fix_bug"), _no_clarify())
        assert isinstance(brief, TaskBrief)

    def test_has_intent(self, builder):
        brief = builder.build("Fix auth.py", _cr("coding", "fix_bug"), _no_clarify())
        assert brief.intent == "coding"

    def test_has_sub_intent(self, builder):
        brief = builder.build("Fix auth.py", _cr("coding", "fix_bug"), _no_clarify())
        assert brief.sub_intent == "fix_bug"

    def test_has_original_message(self, builder):
        brief = builder.build("Fix auth.py", _cr("coding", "fix_bug"), _no_clarify())
        assert brief.original_message == "Fix auth.py"

    def test_has_summary(self, builder):
        brief = builder.build("Fix the bug in auth.py", _cr("coding", "fix_bug"), _no_clarify())
        assert isinstance(brief.summary, str)
        assert len(brief.summary) > 0

    def test_has_confidence(self, builder):
        brief = builder.build("Fix auth.py", _cr("coding", "fix_bug", 0.85), _no_clarify())
        assert brief.confidence == 0.85

    def test_has_needs_clarification(self, builder):
        brief = builder.build("Fix this", _cr("ambiguous"), _needs_clarify())
        assert brief.needs_clarification is True

    def test_has_clarification_questions(self, builder):
        qs = ["Which file?", "What error?"]
        brief = builder.build("Fix this", _cr("ambiguous"), _needs_clarify(qs))
        assert brief.clarification_questions == qs

    def test_has_file_refs(self, builder):
        brief = builder.build("Fix auth.py", _cr("coding", "fix_bug"), _no_clarify())
        assert isinstance(brief.file_references, list)

    def test_has_action_verb(self, builder):
        brief = builder.build("Fix the bug", _cr("coding", "fix_bug"), _no_clarify())
        assert isinstance(brief.action_verb, str)


# =============================================================================
# FILE REFERENCE EXTRACTION
# =============================================================================


class TestFileExtraction:
    """Test file reference extraction from messages."""

    def test_extracts_python_file(self, builder):
        brief = builder.build("Fix auth.py", _cr("coding", "fix_bug"), _no_clarify())
        assert "auth.py" in brief.file_references

    def test_extracts_multiple_files(self, builder):
        brief = builder.build(
            "Update auth.py and routes.py", _cr("coding", "modify_file"), _no_clarify()
        )
        assert "auth.py" in brief.file_references
        assert "routes.py" in brief.file_references

    def test_extracts_path_file(self, builder):
        brief = builder.build("Fix src/core/auth.py", _cr("coding", "fix_bug"), _no_clarify())
        assert "src/core/auth.py" in brief.file_references

    def test_no_files_returns_empty(self, builder):
        brief = builder.build("Fix the bug", _cr("coding", "fix_bug"), _no_clarify())
        assert brief.file_references == []

    def test_extracts_js_file(self, builder):
        brief = builder.build("Update App.tsx", _cr("coding", "modify_file"), _no_clarify())
        assert "App.tsx" in brief.file_references

    def test_extracts_json_file(self, builder):
        brief = builder.build("Edit config.json", _cr("coding", "modify_file"), _no_clarify())
        assert "config.json" in brief.file_references


# =============================================================================
# ACTION VERB EXTRACTION
# =============================================================================


class TestActionVerb:
    """Test action verb detection."""

    def test_fix(self, builder):
        brief = builder.build("Fix the bug", _cr("coding", "fix_bug"), _no_clarify())
        assert brief.action_verb == "fix"

    def test_create(self, builder):
        brief = builder.build("Create a new file", _cr("coding", "create_file"), _no_clarify())
        assert brief.action_verb == "create"

    def test_refactor(self, builder):
        brief = builder.build("Refactor the router", _cr("coding", "refactor"), _no_clarify())
        assert brief.action_verb == "refactor"

    def test_add(self, builder):
        brief = builder.build("Add error handling", _cr("coding", "modify_file"), _no_clarify())
        assert brief.action_verb == "add"

    def test_explain(self, builder):
        brief = builder.build(
            "Explain this function", _cr("question", "code_explanation"), _no_clarify()
        )
        assert brief.action_verb == "explain"

    def test_no_verb_defaults(self, builder):
        brief = builder.build("auth.py", _cr("coding", "fix_bug"), _no_clarify())
        assert isinstance(brief.action_verb, str)


# =============================================================================
# SUMMARY GENERATION
# =============================================================================


class TestSummaryGeneration:
    """Test brief summary generation."""

    def test_coding_summary(self, builder):
        brief = builder.build(
            "Fix the TypeError in auth.py on line 42",
            _cr("coding", "fix_bug"),
            _no_clarify(),
        )
        assert "fix" in brief.summary.lower() or "bug" in brief.summary.lower()

    def test_question_summary(self, builder):
        brief = builder.build(
            "What does the authenticate function do?",
            _cr("question", "code_explanation"),
            _no_clarify(),
        )
        assert len(brief.summary) > 0

    def test_conversational_summary(self, builder):
        brief = builder.build("Hello!", _cr("conversational", "greeting"), _no_clarify())
        assert len(brief.summary) > 0

    def test_summary_length_bounded(self, builder):
        long_msg = "Fix " + "the very important critical " * 20 + "bug in auth.py"
        brief = builder.build(long_msg, _cr("coding", "fix_bug"), _no_clarify())
        assert len(brief.summary) <= 200


# =============================================================================
# PROMPT FORMATTING
# =============================================================================


class TestPromptFormatting:
    """Test TaskBrief formatting for LLM prompt injection."""

    def test_format_for_prompt(self, builder):
        brief = builder.build(
            "Fix the TypeError in auth.py",
            _cr("coding", "fix_bug", 0.9),
            _no_clarify(),
        )
        prompt = brief.format_for_prompt()
        assert isinstance(prompt, str)
        assert "fix" in prompt.lower() or "coding" in prompt.lower()

    def test_format_includes_intent(self, builder):
        brief = builder.build("Fix auth.py", _cr("coding", "fix_bug"), _no_clarify())
        prompt = brief.format_for_prompt()
        assert "coding" in prompt.lower()

    def test_format_includes_file_refs(self, builder):
        brief = builder.build("Fix auth.py", _cr("coding", "fix_bug"), _no_clarify())
        prompt = brief.format_for_prompt()
        assert "auth.py" in prompt

    def test_format_clarification_brief(self, builder):
        brief = builder.build("Fix this", _cr("ambiguous"), _needs_clarify(["Which file?"]))
        prompt = brief.format_for_prompt()
        assert "clarif" in prompt.lower() or "question" in prompt.lower()

    def test_format_conversational(self, builder):
        brief = builder.build("Hello!", _cr("conversational", "greeting"), _no_clarify())
        prompt = brief.format_for_prompt()
        assert len(prompt) > 0


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Edge cases."""

    def test_empty_message(self, builder):
        brief = builder.build("", _cr("conversational", "", 0.1), _no_clarify())
        assert isinstance(brief, TaskBrief)

    def test_very_long_message(self, builder):
        msg = "Fix the bug " * 200
        brief = builder.build(msg, _cr("coding", "fix_bug"), _no_clarify())
        assert isinstance(brief, TaskBrief)
        assert len(brief.summary) <= 200

    def test_message_with_code_block(self, builder):
        msg = "Fix this:\n```python\ndef foo():\n    return None\n```"
        brief = builder.build(msg, _cr("coding", "fix_bug"), _no_clarify())
        assert isinstance(brief, TaskBrief)

    def test_compound_intent(self, builder):
        brief = builder.build(
            "Hi, fix the bug in auth.py",
            _cr("compound", "greeting_plus_task"),
            _no_clarify(),
        )
        assert brief.intent == "compound"
        assert "auth.py" in brief.file_references
