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
Orion Agent -- English Foundation Layer (v7.8.0)

Linguistic normalization and pre-processing for the NLA pipeline.
Cleans, expands, and segments user input before intent classification.

Responsibilities:
    - Text normalization (whitespace, punctuation noise)
    - Contraction expansion (don't → do not)
    - Slang / abbreviation normalization (pls → please)
    - Greeting prefix stripping for compound messages
    - Sentence segmentation for multi-part requests

Part of the Natural Language Architecture (NLA-002, Phase 3A).
"""

import re

# =============================================================================
# CONTRACTION MAP
# =============================================================================

_CONTRACTIONS: dict[str, str] = {
    "i'm": "I am",
    "i've": "I have",
    "i'll": "I will",
    "i'd": "I would",
    "you're": "you are",
    "you've": "you have",
    "you'll": "you will",
    "you'd": "you would",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "we're": "we are",
    "we've": "we have",
    "we'll": "we will",
    "we'd": "we would",
    "they're": "they are",
    "they've": "they have",
    "they'll": "they will",
    "they'd": "they would",
    "that's": "that is",
    "that'll": "that will",
    "that'd": "that would",
    "who's": "who is",
    "who'll": "who will",
    "who'd": "who would",
    "what's": "what is",
    "what'll": "what will",
    "what'd": "what did",
    "where's": "where is",
    "where'd": "where did",
    "when's": "when is",
    "when'd": "when did",
    "why's": "why is",
    "why'd": "why did",
    "how's": "how is",
    "how'd": "how did",
    "how'll": "how will",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "hasn't": "has not",
    "haven't": "have not",
    "hadn't": "had not",
    "doesn't": "does not",
    "don't": "do not",
    "didn't": "did not",
    "won't": "will not",
    "wouldn't": "would not",
    "shan't": "shall not",
    "shouldn't": "should not",
    "can't": "cannot",
    "couldn't": "could not",
    "mustn't": "must not",
    "needn't": "need not",
    "let's": "let us",
    "here's": "here is",
    "there's": "there is",
}

# Build regex: match longest first to avoid partial matches
_CONTRACTION_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_CONTRACTIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# =============================================================================
# SLANG / ABBREVIATION MAP
# =============================================================================

_SLANG: dict[str, str] = {
    "pls": "please",
    "plz": "please",
    "thx": "thanks",
    "ty": "thank you",
    "idk": "I don't know",
    "nvm": "never mind",
    "asap": "as soon as possible",
    "imo": "in my opinion",
    "fyi": "for your information",
    "btw": "by the way",
    "afaik": "as far as I know",
    "tbh": "to be honest",
    "wip": "work in progress",
    "lgtm": "looks good to me",
}

_SLANG_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_SLANG, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# =============================================================================
# GREETING PATTERNS
# =============================================================================

_GREETING_PREFIX_RE = re.compile(
    r"^\s*(?:hi|hello|hey|howdy|good\s+(?:morning|afternoon|evening|day))"
    r"(?:\s+(?:orion|there|everyone))?"
    r"\s*[,!.]*\s*",
    re.IGNORECASE,
)

# File extension pattern (used to protect dots in filenames during segmentation)
_FILE_EXT_RE = re.compile(
    r"\b[\w/\\-]+\.(?:py|js|ts|jsx|tsx|json|yaml|yml|html|css|sql|go|rs|java|cs|cpp|c|h|md|txt|toml|cfg|ini|sh|bat)\b"
)

# =============================================================================
# ENGLISH FOUNDATION
# =============================================================================


class EnglishFoundation:
    """
    Linguistic normalization and pre-processing layer.

    Cleans user input for more accurate intent classification
    without changing semantic meaning.
    """

    # -----------------------------------------------------------------
    # NORMALIZATION
    # -----------------------------------------------------------------

    @staticmethod
    def normalize(text: str, lowercase: bool = False) -> str:
        """
        Normalize whitespace and reduce punctuation noise.

        Args:
            text: Raw input text.
            lowercase: If True, convert to lowercase.

        Returns:
            Cleaned text.
        """
        if not text or not text.strip():
            return ""

        result = text.strip()

        # Collapse internal whitespace
        result = re.sub(r"\s+", " ", result)

        # Reduce repeated punctuation (!!!  → !, ... → .)
        result = re.sub(r"!{2,}", "!", result)
        result = re.sub(r"\.{2,}", ".", result)
        result = re.sub(r"\?{2,}", "?", result)

        if lowercase:
            result = result.lower()

        return result

    # -----------------------------------------------------------------
    # CONTRACTION EXPANSION
    # -----------------------------------------------------------------

    @staticmethod
    def expand_contractions(text: str) -> str:
        """
        Expand English contractions to full forms.

        Preserves case of the first letter where sensible.
        """
        if not text:
            return text

        def _replace(match: re.Match) -> str:
            word = match.group(0)
            key = word.lower()
            replacement = _CONTRACTIONS.get(key, word)
            # Preserve leading capitalization
            if word[0].isupper() and replacement[0].islower():
                replacement = replacement[0].upper() + replacement[1:]
            return replacement

        return _CONTRACTION_RE.sub(_replace, text)

    # -----------------------------------------------------------------
    # SLANG NORMALIZATION
    # -----------------------------------------------------------------

    @staticmethod
    def normalize_slang(text: str) -> str:
        """Replace common dev slang and abbreviations with full forms."""
        if not text:
            return text

        def _replace(match: re.Match) -> str:
            word = match.group(0)
            key = word.lower()
            return _SLANG.get(key, word)

        return _SLANG_RE.sub(_replace, text)

    # -----------------------------------------------------------------
    # GREETING STRIPPING
    # -----------------------------------------------------------------

    @staticmethod
    def strip_greeting(text: str) -> str:
        """
        Strip greeting prefix from compound messages.

        Returns the original text unchanged if it's only a greeting.
        """
        if not text:
            return text

        stripped = _GREETING_PREFIX_RE.sub("", text).strip()

        # If nothing left, the message was a pure greeting — keep it
        if not stripped:
            return text.strip()

        return stripped

    # -----------------------------------------------------------------
    # SENTENCE SEGMENTATION
    # -----------------------------------------------------------------

    @staticmethod
    def segment(text: str) -> list[str]:
        """
        Split a message into logical segments.

        Handles sentence boundaries while protecting file extensions
        from being treated as sentence-ending dots.
        """
        if not text or not text.strip():
            return []

        working = text.strip()

        # Protect file extensions by replacing dots temporarily
        file_refs: list[str] = []
        for i, match in enumerate(_FILE_EXT_RE.finditer(working)):
            placeholder = f"__FILE{i}__"
            file_refs.append((placeholder, match.group(0)))

        protected = working
        for placeholder, original in file_refs:
            protected = protected.replace(original, placeholder)

        # Split on sentence boundaries
        parts = re.split(r"(?<=[.!?])\s+", protected)

        # Split on ", also " and ", then " connectors
        expanded: list[str] = []
        for part in parts:
            sub_parts = re.split(r",\s*(?:also|then|and\s+then|and\s+also)\s+", part)
            expanded.extend(sub_parts)

        # Restore file references
        segments: list[str] = []
        for seg in expanded:
            restored = seg.strip()
            for placeholder, original in file_refs:
                restored = restored.replace(placeholder, original)
            if restored:
                segments.append(restored)

        return segments

    # -----------------------------------------------------------------
    # FULL PRE-PROCESS PIPELINE
    # -----------------------------------------------------------------

    def pre_process(self, text: str) -> str:
        """
        Run the full pre-processing pipeline:

        1. Normalize whitespace / punctuation
        2. Expand contractions
        3. Normalize slang

        Returns cleaned text ready for intent classification.
        """
        if not text or not text.strip():
            return ""

        result = self.normalize(text)
        result = self.expand_contractions(result)
        result = self.normalize_slang(result)

        return result
