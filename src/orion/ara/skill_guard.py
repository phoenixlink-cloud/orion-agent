# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""SkillGuard — AEGIS-integrated security scanner for skill content.

Extends PromptGuard's adversarial pattern detection with skill-specific threats:
authority escalation, data exfiltration, dangerous commands, credential exposure,
and obfuscated payloads. Scans SKILL.md AND all supporting files.

See ARA-006 §7 for full design.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.ara.skill_guard")

# ---------------------------------------------------------------------------
# Content Normalization (ARA-006 §7.4 H7)
# ---------------------------------------------------------------------------

# Zero-width and invisible characters to strip
_INVISIBLE_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u2060\ufeff"  # Zero-width chars
    r"\u00ad\u034f\u061c"  # Soft hyphen, combining grapheme joiner, etc.
    r"\u115f\u1160\u17b4\u17b5]"  # Hangul/Khmer fillers
)


def normalize_for_scan(text: str) -> str:
    """Normalize text to defeat common regex evasion techniques.

    1. NFKC normalization (homoglyphs → ASCII equivalents)
    2. Strip zero-width / invisible characters
    3. Straighten smart quotes
    4. Collapse multiple whitespace
    """
    # NFKC handles most homoglyph → ASCII mappings
    text = unicodedata.normalize("NFKC", text)
    # Strip invisible characters
    text = _INVISIBLE_CHARS.sub("", text)
    # Straighten smart quotes
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    # Collapse whitespace (preserve newlines for readability)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Skill-Specific Adversarial Patterns (ARA-006 §7.2)
# ---------------------------------------------------------------------------

_SKILL_ADVERSARIAL_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "authority_escalation",
        re.compile(
            r"(admin|root|superuser|unlimited)\s+(access|authority|permissions?)",
            re.IGNORECASE,
        ),
        "critical",
    ),
    (
        "aegis_reference",
        re.compile(
            r"(disable|bypass|ignore|override|turn\s+off)\s+aegis",
            re.IGNORECASE,
        ),
        "critical",
    ),
    (
        "data_exfiltration",
        re.compile(
            r"(curl|wget|fetch|send|post|upload)\s+.{0,40}(http|https|ftp)://",
            re.IGNORECASE,
        ),
        "high",
    ),
    (
        "dangerous_commands",
        re.compile(
            r"(rm\s+-rf|drop\s+table|truncate\s+table|format\s+c:|del\s+/[sf])",
            re.IGNORECASE,
        ),
        "critical",
    ),
    (
        "credential_access",
        re.compile(
            r"(api[_\s]?key|password|secret|token|credential)\s*=\s*['\"]",
            re.IGNORECASE,
        ),
        "high",
    ),
    (
        "encoded_content",
        re.compile(
            r"(base64|eval|exec)\s*\(",
            re.IGNORECASE,
        ),
        "high",
    ),
    (
        "shell_injection",
        re.compile(
            r"(\$\(|`[^`]+`|\|\s*sh\b|\|\s*bash\b)",
            re.IGNORECASE,
        ),
        "high",
    ),
    (
        "env_access",
        re.compile(
            r"(os\.environ|process\.env|getenv)\s*[\[\(]",
            re.IGNORECASE,
        ),
        "medium",
    ),
    (
        "network_listener",
        re.compile(
            r"(listen|bind|socket\.socket|nc\s+-l|ncat\s+-l)",
            re.IGNORECASE,
        ),
        "high",
    ),
    (
        "privilege_escalation",
        re.compile(
            r"(sudo\s|chmod\s+[0-7]*7|chown\s+root|setuid|setgid)",
            re.IGNORECASE,
        ),
        "critical",
    ),
]


# ---------------------------------------------------------------------------
# PromptGuard Base Patterns (re-imported)
# ---------------------------------------------------------------------------


def _get_prompt_guard_patterns() -> list[tuple[str, re.Pattern[str], str]]:
    """Import PromptGuard's adversarial patterns and tag them as critical."""
    try:
        from orion.ara.prompt_guard import _ADVERSARIAL_PATTERNS

        return [(name, pattern, "critical") for name, pattern in _ADVERSARIAL_PATTERNS]
    except ImportError:
        logger.warning("Could not import PromptGuard patterns — using skill patterns only")
        return []


# ---------------------------------------------------------------------------
# Scan Result
# ---------------------------------------------------------------------------


@dataclass
class SkillFinding:
    """A single security finding from a skill scan."""

    pattern_name: str
    severity: str  # critical | high | medium
    file: str  # Which file the finding was in
    match_text: str = ""  # The matched text (truncated)
    line_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern_name,
            "severity": self.severity,
            "file": self.file,
            "match": self.match_text[:100],
            "line": self.line_number,
        }


@dataclass
class SkillScanResult:
    """Result of scanning a skill directory."""

    skill_name: str
    approved: bool = True
    findings: list[SkillFinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trust_recommendation: str = "trusted"  # verified | trusted | unreviewed | blocked
    files_scanned: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")

    def summary(self) -> str:
        if self.approved:
            return f"✅ Skill '{self.skill_name}' approved ({self.files_scanned} files scanned)"
        return (
            f"❌ Skill '{self.skill_name}' BLOCKED — "
            f"{self.critical_count} critical, {self.high_count} high findings"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "approved": self.approved,
            "findings": [f.to_dict() for f in self.findings],
            "warnings": self.warnings,
            "trust_recommendation": self.trust_recommendation,
            "files_scanned": self.files_scanned,
        }


# ---------------------------------------------------------------------------
# SkillGuard
# ---------------------------------------------------------------------------


class SkillGuard:
    """AEGIS-integrated skill content scanner.

    Extends PromptGuard patterns for skill-specific threats.
    Scans SKILL.md AND all supporting files in the skill directory.
    """

    def __init__(self) -> None:
        # Combine PromptGuard base patterns + skill-specific patterns
        self._patterns: list[tuple[str, re.Pattern[str], str]] = []
        self._patterns.extend(_get_prompt_guard_patterns())
        self._patterns.extend(_SKILL_ADVERSARIAL_PATTERNS)

    @property
    def pattern_count(self) -> int:
        """Total number of registered adversarial patterns."""
        return len(self._patterns)

    def scan_text(self, text: str, filename: str = "SKILL.md") -> list[SkillFinding]:
        """Scan a single text blob for adversarial patterns.

        Content is normalized (H7) before scanning.
        """
        normalized = normalize_for_scan(text)
        findings: list[SkillFinding] = []

        lines = normalized.split("\n")
        for line_num, line in enumerate(lines, start=1):
            for name, pattern, severity in self._patterns:
                match = pattern.search(line)
                if match:
                    findings.append(
                        SkillFinding(
                            pattern_name=name,
                            severity=severity,
                            file=filename,
                            match_text=match.group(0),
                            line_number=line_num,
                        )
                    )

        return findings

    def scan_skill(
        self,
        skill_dir: Path,
        instructions: str = "",
        supporting_files: list[str] | None = None,
    ) -> SkillScanResult:
        """Full scan of a skill directory.

        Scans SKILL.md content and all supporting files for adversarial patterns.
        """
        skill_name = skill_dir.name
        result = SkillScanResult(skill_name=skill_name)
        files_scanned = 0

        # Scan SKILL.md content
        if instructions:
            text = instructions
        else:
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                try:
                    text = skill_md.read_text(encoding="utf-8")
                except Exception as e:
                    result.warnings.append(f"Cannot read SKILL.md: {e}")
                    text = ""
            else:
                result.warnings.append("No SKILL.md found")
                text = ""

        if text:
            findings = self.scan_text(text, "SKILL.md")
            result.findings.extend(findings)
            files_scanned += 1

        # Scan supporting files
        files_to_scan = supporting_files or []
        if not files_to_scan and skill_dir.exists():
            # Auto-discover
            for item in sorted(skill_dir.rglob("*")):
                if item.is_file() and item.name != "SKILL.md":
                    try:
                        rel = str(item.relative_to(skill_dir))
                        files_to_scan.append(rel)
                    except ValueError:
                        pass

        for rel_path in files_to_scan:
            filepath = skill_dir / rel_path
            if not filepath.exists() or not filepath.is_file():
                continue
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                result.warnings.append(f"Cannot read {rel_path}: {e}")
                continue

            findings = self.scan_text(content, rel_path)
            result.findings.extend(findings)
            files_scanned += 1

        result.files_scanned = files_scanned

        # Determine approval and trust recommendation
        if result.critical_count > 0:
            result.approved = False
            result.trust_recommendation = "blocked"
            logger.warning(
                "SkillGuard BLOCKED '%s': %d critical findings",
                skill_name,
                result.critical_count,
            )
        elif result.high_count > 0:
            result.approved = False
            result.trust_recommendation = "blocked"
            logger.warning(
                "SkillGuard BLOCKED '%s': %d high-severity findings",
                skill_name,
                result.high_count,
            )
        elif len(result.findings) > 0:
            # Medium-severity only — approve but flag as unreviewed
            result.approved = True
            result.trust_recommendation = "unreviewed"
            logger.info(
                "SkillGuard approved '%s' with %d medium findings (unreviewed)",
                skill_name,
                len(result.findings),
            )
        else:
            result.approved = True
            result.trust_recommendation = "trusted"
            logger.info("SkillGuard approved '%s' — clean", skill_name)

        return result

    def scan_content(self, content: str, skill_name: str = "inline") -> SkillScanResult:
        """Scan raw SKILL.md content (for import-from-paste flows)."""
        result = SkillScanResult(skill_name=skill_name)
        findings = self.scan_text(content, "SKILL.md")
        result.findings.extend(findings)
        result.files_scanned = 1

        if result.critical_count > 0 or result.high_count > 0:
            result.approved = False
            result.trust_recommendation = "blocked"
        elif len(result.findings) > 0:
            result.approved = True
            result.trust_recommendation = "unreviewed"
        else:
            result.approved = True
            result.trust_recommendation = "trusted"

        return result
