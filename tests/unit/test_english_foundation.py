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
"""Tests for EnglishFoundation -- linguistic normalization and pre-processing."""

import pytest

from orion.core.understanding.english_foundation import EnglishFoundation

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def ef():
    """Provide an EnglishFoundation instance."""
    return EnglishFoundation()


# =============================================================================
# TEXT NORMALIZATION
# =============================================================================


class TestNormalization:
    """Test text normalization for cleaner classification."""

    def test_strips_whitespace(self, ef):
        assert ef.normalize("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self, ef):
        assert ef.normalize("fix   the    bug") == "fix the bug"

    def test_preserves_case_by_default(self, ef):
        assert ef.normalize("Fix Auth.py") == "Fix Auth.py"

    def test_lowercase_option(self, ef):
        assert ef.normalize("Fix Auth.py", lowercase=True) == "fix auth.py"

    def test_strips_trailing_punctuation_noise(self, ef):
        assert ef.normalize("hello!!!") == "hello!"
        assert ef.normalize("fix this...") == "fix this."

    def test_preserves_code_backticks(self, ef):
        result = ef.normalize("fix the `auth.py` file")
        assert "`auth.py`" in result

    def test_preserves_file_extensions(self, ef):
        result = ef.normalize("update routes.py")
        assert "routes.py" in result

    def test_empty_input(self, ef):
        assert ef.normalize("") == ""

    def test_whitespace_only(self, ef):
        assert ef.normalize("   ") == ""


# =============================================================================
# CONTRACTION EXPANSION
# =============================================================================


class TestContractionExpansion:
    """Test expansion of English contractions."""

    def test_dont(self, ef):
        assert "do not" in ef.expand_contractions("don't do that")

    def test_cant(self, ef):
        assert "cannot" in ef.expand_contractions("can't fix this")

    def test_wont(self, ef):
        assert "will not" in ef.expand_contractions("won't work")

    def test_im(self, ef):
        assert "I am" in ef.expand_contractions("I'm stuck")

    def test_its_contraction(self, ef):
        assert "it is" in ef.expand_contractions("it's broken")

    def test_doesnt(self, ef):
        assert "does not" in ef.expand_contractions("doesn't work")

    def test_isnt(self, ef):
        assert "is not" in ef.expand_contractions("isn't right")

    def test_thats(self, ef):
        assert "that is" in ef.expand_contractions("that's wrong")

    def test_whats(self, ef):
        assert "what is" in ef.expand_contractions("what's happening")

    def test_youre(self, ef):
        assert "you are" in ef.expand_contractions("you're great")

    def test_theyve(self, ef):
        assert "they have" in ef.expand_contractions("they've changed")

    def test_no_contractions(self, ef):
        original = "fix the bug in auth.py"
        assert ef.expand_contractions(original) == original

    def test_multiple_contractions(self, ef):
        result = ef.expand_contractions("I'm stuck and it's not working, can't fix it")
        assert "I am" in result
        assert "it is" in result
        assert "cannot" in result


# =============================================================================
# TYPO / SLANG NORMALIZATION
# =============================================================================


class TestSlangNormalization:
    """Test normalization of common dev slang and typos."""

    def test_pls_to_please(self, ef):
        result = ef.normalize_slang("pls fix this")
        assert "please" in result

    def test_plz_to_please(self, ef):
        result = ef.normalize_slang("plz help")
        assert "please" in result

    def test_thx_to_thanks(self, ef):
        result = ef.normalize_slang("thx!")
        assert "thanks" in result

    def test_ty_to_thank_you(self, ef):
        result = ef.normalize_slang("ty for the help")
        assert "thank you" in result

    def test_idk_to_i_dont_know(self, ef):
        result = ef.normalize_slang("idk what went wrong")
        assert "I don't know" in result

    def test_nvm_to_never_mind(self, ef):
        result = ef.normalize_slang("nvm I found it")
        assert "never mind" in result

    def test_asap(self, ef):
        result = ef.normalize_slang("fix this asap")
        assert "as soon as possible" in result

    def test_no_slang(self, ef):
        original = "fix the bug in auth.py"
        assert ef.normalize_slang(original) == original


# =============================================================================
# GREETING STRIPPING
# =============================================================================


class TestGreetingStripping:
    """Test stripping greeting prefixes from compound messages."""

    def test_strip_hi(self, ef):
        assert ef.strip_greeting("Hi, fix the bug") == "fix the bug"

    def test_strip_hello(self, ef):
        assert ef.strip_greeting("Hello! Fix the bug") == "Fix the bug"

    def test_strip_hey(self, ef):
        assert ef.strip_greeting("Hey Orion, fix auth.py") == "fix auth.py"

    def test_strip_good_morning(self, ef):
        assert ef.strip_greeting("Good morning, fix the bug") == "fix the bug"

    def test_no_greeting(self, ef):
        assert ef.strip_greeting("Fix the bug") == "Fix the bug"

    def test_greeting_only(self, ef):
        # Pure greeting, nothing to strip to
        result = ef.strip_greeting("Hello!")
        assert result == "Hello!"

    def test_strip_preserves_content(self, ef):
        result = ef.strip_greeting("Hi there, can you fix auth.py line 42?")
        assert "auth.py" in result
        assert "42" in result


# =============================================================================
# SENTENCE SEGMENTATION
# =============================================================================


class TestSentenceSegmentation:
    """Test splitting messages into logical segments."""

    def test_single_sentence(self, ef):
        segments = ef.segment("Fix the bug in auth.py")
        assert len(segments) == 1

    def test_two_sentences(self, ef):
        segments = ef.segment("Fix the bug. Then add tests.")
        assert len(segments) == 2

    def test_question_plus_statement(self, ef):
        segments = ef.segment("What does this do? I think it's broken.")
        assert len(segments) == 2

    def test_preserves_code_dots(self, ef):
        segments = ef.segment("Fix auth.py please")
        assert len(segments) == 1
        assert "auth.py" in segments[0]

    def test_empty_input(self, ef):
        assert ef.segment("") == []

    def test_also_connector(self, ef):
        segments = ef.segment("Fix the bug, also add error handling")
        assert len(segments) >= 2


# =============================================================================
# FULL PRE-PROCESS PIPELINE
# =============================================================================


class TestPreProcess:
    """Test the full pre-processing pipeline."""

    def test_returns_string(self, ef):
        result = ef.pre_process("Hello! Fix the bug pls")
        assert isinstance(result, str)

    def test_expands_contractions(self, ef):
        result = ef.pre_process("it's broken and doesn't work")
        assert "it is" in result
        assert "does not" in result

    def test_normalizes_slang(self, ef):
        result = ef.pre_process("pls fix this thx")
        assert "please" in result
        assert "thanks" in result

    def test_normalizes_whitespace(self, ef):
        result = ef.pre_process("  fix   the   bug  ")
        assert result == "fix the bug"

    def test_preserves_file_refs(self, ef):
        result = ef.pre_process("fix auth.py pls")
        assert "auth.py" in result

    def test_idempotent_on_clean_input(self, ef):
        clean = "Fix the bug in auth.py"
        assert ef.pre_process(clean) == clean

    def test_empty(self, ef):
        assert ef.pre_process("") == ""
