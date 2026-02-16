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
"""Skill data model and SKILL.md parser for the ARA Skills system.

Skills are reusable capability packages (SKILL.md + supporting files) that teach
Orion how to perform specific tasks. They follow the Agent Skills open standard
(YAML frontmatter + markdown instructions).

See ARA-006 §3-4 for full design.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("orion.ara.skill")

# ---------------------------------------------------------------------------
# Constants & Limits (ARA-006 §7.4 H2)
# ---------------------------------------------------------------------------

_VALID_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}[a-z0-9]$")

_WIN_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)

VALID_TRUST_LEVELS = frozenset({"verified", "trusted", "unreviewed", "blocked"})
VALID_SOURCES = frozenset({"custom", "imported", "bundled"})
VALID_GROUP_TYPES = frozenset({"specialized", "general"})


class SkillLimits:
    """Hard limits enforced at load time (ARA-006 §7.4 H2)."""

    MAX_SKILL_MD_BYTES: int = 50 * 1024  # 50 KB
    MAX_INSTRUCTION_TOKENS: int = 4_000  # Injected context budget
    MAX_SUPPORTING_FILES: int = 20
    MAX_SINGLE_FILE_BYTES: int = 1 * 1024 * 1024  # 1 MB
    MAX_SKILL_DIR_BYTES: int = 10 * 1024 * 1024  # 10 MB
    MAX_NAME_LENGTH: int = 64
    MAX_TAGS: int = 20


# Allowed supporting file extensions (ARA-006 §7.4 H4)
ALLOWED_SUPPORTING_EXTENSIONS = frozenset(
    {
        ".md",
        ".txt",
        ".rst",
        ".adoc",
        ".py",
        ".js",
        ".ts",
        ".sh",
        ".bash",
        ".zsh",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".html",
        ".css",
        ".xml",
        ".csv",
        ".dockerfile",
        ".env",
    }
)

ALLOWED_SUPPORTING_NAMES = frozenset(
    {
        "Dockerfile",
        "Makefile",
        "Procfile",
        "Vagrantfile",
        ".gitignore",
        ".dockerignore",
        ".editorconfig",
    }
)

BLOCKED_EXTENSIONS = frozenset(
    {
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bat",
        ".cmd",
        ".com",
        ".msi",
        ".scr",
        ".pif",
        ".vbs",
        ".vbe",
        ".wsf",
        ".wsh",
        ".ps1",
        ".jar",
        ".war",
        ".class",
        ".bin",
        ".img",
        ".iso",
    }
)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class Skill:
    """A loaded, validated skill definition."""

    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = "custom"  # custom | imported | bundled
    trust_level: str = "trusted"  # verified | trusted | unreviewed | blocked
    instructions: str = ""  # Markdown body (below frontmatter)
    directory: Path | None = None  # Path to skill folder
    supporting_files: list[str] = field(default_factory=list)
    group: str | None = None  # Assigned skill group
    aegis_approved: bool = False  # Passed SkillGuard scan
    content_hash: str = ""  # SHA-256 (ARA-006 §7.4 H1)

    def compute_hash(self) -> str:
        """SHA-256 of SKILL.md content + sorted supporting file contents."""
        h = hashlib.sha256()
        h.update(self.instructions.encode("utf-8"))
        for f in sorted(self.supporting_files):
            filepath = self.directory / f if self.directory else None
            if filepath and filepath.exists():
                h.update(filepath.read_bytes())
        return h.hexdigest()

    def compute_disk_hash(self) -> str:
        """SHA-256 computed from actual files on disk (for tamper detection)."""
        if not self.directory:
            return ""
        skill_md = self.directory / "SKILL.md"
        if not skill_md.exists():
            return ""
        h = hashlib.sha256()
        h.update(skill_md.read_bytes())
        for f in sorted(self.supporting_files):
            filepath = self.directory / f
            if filepath.exists():
                h.update(filepath.read_bytes())
        return h.hexdigest()

    def verify_integrity(self) -> bool:
        """Returns True if disk content matches the hash recorded at scan time."""
        if not self.content_hash:
            return False
        return self.content_hash == self.compute_disk_hash()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "source": self.source,
            "trust_level": self.trust_level,
            "instructions": self.instructions,
            "directory": str(self.directory) if self.directory else None,
            "supporting_files": self.supporting_files,
            "group": self.group,
            "aegis_approved": self.aegis_approved,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        """Create a Skill from a dictionary."""
        directory = Path(data["directory"]) if data.get("directory") else None
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            source=data.get("source", "custom"),
            trust_level=data.get("trust_level", "trusted"),
            instructions=data.get("instructions", ""),
            directory=directory,
            supporting_files=data.get("supporting_files", []),
            group=data.get("group"),
            aegis_approved=data.get("aegis_approved", False),
            content_hash=data.get("content_hash", ""),
        )


@dataclass
class SkillGroup:
    """A named collection of skills."""

    name: str
    display_name: str
    description: str = ""
    group_type: str = "general"  # specialized | general
    skill_names: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "display_name": self.display_name,
            "description": self.description,
            "group_type": self.group_type,
            "skills": self.skill_names,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SkillGroup:
        """Create a SkillGroup from a dictionary."""
        return cls(
            name=name,
            display_name=data.get("display_name", name),
            description=data.get("description", ""),
            group_type=data.get("group_type", "general"),
            skill_names=data.get("skills", []),
            tags=data.get("tags", []),
        )


# ---------------------------------------------------------------------------
# Validation (ARA-006 §7.4 H5)
# ---------------------------------------------------------------------------


def validate_skill_name(name: str) -> tuple[bool, str]:
    """Validate a skill name for safety.

    Rules:
    - Lowercase alphanumeric + hyphens only
    - 2-64 characters
    - Must start and end with alphanumeric
    - No consecutive hyphens
    - No reserved names on Windows
    """
    if not name:
        return False, "Skill name cannot be empty"
    if len(name) > SkillLimits.MAX_NAME_LENGTH:
        return False, f"Skill name exceeds {SkillLimits.MAX_NAME_LENGTH} character limit"
    if not _VALID_SKILL_NAME.match(name):
        return False, "Skill name must be 2-64 lowercase alphanumeric chars with hyphens"
    if "--" in name:
        return False, "Consecutive hyphens not allowed in skill name"
    if name.split(".")[0].upper() in _WIN_RESERVED_NAMES:
        return False, f"'{name}' conflicts with a reserved system name"
    return True, "ok"


def validate_group_name(name: str) -> tuple[bool, str]:
    """Validate a skill group name."""
    if not name:
        return False, "Group name cannot be empty"
    if not _VALID_SKILL_NAME.match(name):
        return False, "Group name must be 2-64 lowercase alphanumeric chars with hyphens"
    if "--" in name:
        return False, "Consecutive hyphens not allowed in group name"
    return True, "ok"


def check_file_extension(filename: str) -> tuple[bool, str]:
    """Check if a supporting file extension is allowed (ARA-006 §7.4 H4).

    Returns (allowed, reason).
    - allowed=True, reason="ok" → file is on allowlist
    - allowed=True, reason="flagged" → file not on either list, allowed with warning
    - allowed=False, reason="blocked: ..." → file is on blocklist
    """
    name = Path(filename).name
    if name in ALLOWED_SUPPORTING_NAMES:
        return True, "ok"

    ext = Path(filename).suffix.lower()
    if not ext:
        # No extension — allow if in known names, otherwise flag
        return True, "flagged"
    if ext in BLOCKED_EXTENSIONS:
        return False, f"blocked: extension '{ext}' is not allowed in skill directories"
    if ext in ALLOWED_SUPPORTING_EXTENSIONS:
        return True, "ok"
    return True, "flagged"


# ---------------------------------------------------------------------------
# SKILL.md Parser
# ---------------------------------------------------------------------------


def parse_skill_md(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and markdown body from SKILL.md content.

    Returns (frontmatter_dict, instruction_body).
    """
    content = content.strip()
    if not content.startswith("---"):
        # No frontmatter — treat entire content as instructions
        return {}, content

    # Find closing ---
    end = content.find("---", 3)
    if end == -1:
        return {}, content

    frontmatter_raw = content[3:end].strip()
    body = content[end + 3 :].strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_raw)
        if not isinstance(frontmatter, dict):
            frontmatter = {}
    except yaml.YAMLError:
        logger.warning("Failed to parse SKILL.md frontmatter as YAML")
        frontmatter = {}

    return frontmatter, body


def _inventory_supporting_files(skill_dir: Path) -> tuple[list[str], list[str]]:
    """List supporting files in a skill directory (ARA-006 §7.4 H3+H4).

    Returns (files, warnings).
    Rejects symlinks, path traversal, blocked extensions.
    """
    files: list[str] = []
    warnings: list[str] = []

    if not skill_dir.exists() or not skill_dir.is_dir():
        return files, warnings

    real_base = skill_dir.resolve()
    dir_total_bytes = 0

    for item in sorted(skill_dir.rglob("*")):
        if not item.is_file():
            continue
        if item.name == "SKILL.md":
            continue

        # H3: Reject symlinks
        if item.is_symlink():
            warnings.append(f"Symlink rejected: {item.name}")
            continue

        # H3: Path confinement
        real_path = item.resolve()
        if not str(real_path).startswith(str(real_base)):
            warnings.append(f"Path traversal blocked: {item.name}")
            continue

        # H3: Reject filenames with null bytes, .., or absolute paths
        rel = str(item.relative_to(skill_dir))
        if "\x00" in rel or ".." in rel.split(os.sep):
            warnings.append(f"Suspicious path rejected: {rel}")
            continue

        # Windows: reject NTFS ADS (colon in filename)
        if ":" in item.name:
            warnings.append(f"NTFS ADS rejected: {item.name}")
            continue

        # H4: Check extension
        allowed, reason = check_file_extension(item.name)
        if not allowed:
            warnings.append(f"Blocked file: {item.name} ({reason})")
            continue
        if reason == "flagged":
            warnings.append(f"Unknown extension flagged: {item.name}")

        # H2: File size limit
        try:
            size = item.stat().st_size
        except OSError:
            warnings.append(f"Cannot stat file: {item.name}")
            continue

        if size > SkillLimits.MAX_SINGLE_FILE_BYTES:
            warnings.append(
                f"File too large: {item.name} ({size} bytes, "
                f"limit {SkillLimits.MAX_SINGLE_FILE_BYTES})"
            )
            continue

        dir_total_bytes += size

        # H2: Max file count
        if len(files) >= SkillLimits.MAX_SUPPORTING_FILES:
            warnings.append(
                f"Too many supporting files (limit {SkillLimits.MAX_SUPPORTING_FILES}), "
                f"skipping {item.name}"
            )
            continue

        files.append(rel)

    # H2: Total directory size
    if dir_total_bytes > SkillLimits.MAX_SKILL_DIR_BYTES:
        warnings.append(
            f"Total skill directory size ({dir_total_bytes} bytes) exceeds "
            f"limit ({SkillLimits.MAX_SKILL_DIR_BYTES})"
        )

    return files, warnings


def load_skill(skill_dir: Path) -> tuple[Skill, list[str]]:
    """Parse a skill directory into a Skill object.

    Returns (Skill, warnings).
    The Skill's aegis_approved will be False — SkillGuard must approve it.
    """
    warnings: list[str] = []
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        raise SkillLoadError(f"SKILL.md not found in {skill_dir}")

    # H2: File size check
    try:
        md_size = skill_md.stat().st_size
    except OSError as e:
        raise SkillLoadError(f"Cannot read SKILL.md: {e}") from e

    if md_size > SkillLimits.MAX_SKILL_MD_BYTES:
        raise SkillLoadError(
            f"SKILL.md too large ({md_size} bytes, limit {SkillLimits.MAX_SKILL_MD_BYTES})"
        )

    content = skill_md.read_text(encoding="utf-8")
    frontmatter, instructions = parse_skill_md(content)

    # Validate name
    name = frontmatter.get("name", skill_dir.name)
    valid, reason = validate_skill_name(name)
    if not valid:
        raise SkillLoadError(f"Invalid skill name '{name}': {reason}")

    # Validate tags count
    tags = frontmatter.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    if len(tags) > SkillLimits.MAX_TAGS:
        tags = tags[: SkillLimits.MAX_TAGS]
        warnings.append(f"Tags truncated to {SkillLimits.MAX_TAGS}")

    # Validate trust level
    trust = frontmatter.get("trust_level", "trusted")
    if trust not in VALID_TRUST_LEVELS:
        trust = "unreviewed"
        warnings.append("Unknown trust_level, defaulting to 'unreviewed'")

    # Validate source
    source = frontmatter.get("source", "custom")
    if source not in VALID_SOURCES:
        source = "custom"
        warnings.append("Unknown source, defaulting to 'custom'")

    # Inventory supporting files (with security checks)
    supporting, inv_warnings = _inventory_supporting_files(skill_dir)
    warnings.extend(inv_warnings)

    skill = Skill(
        name=name,
        description=frontmatter.get("description", ""),
        version=frontmatter.get("version", "1.0.0"),
        author=frontmatter.get("author", ""),
        tags=tags,
        source=source,
        trust_level=trust,
        instructions=instructions,
        directory=skill_dir,
        supporting_files=supporting,
        group=frontmatter.get("group"),
        aegis_approved=False,  # Must pass SkillGuard first
        content_hash="",  # Computed after SkillGuard approves
    )

    return skill, warnings


def save_skill_md(skill: Skill) -> None:
    """Write a skill's SKILL.md file to disk."""
    if not skill.directory:
        raise SkillLoadError("Skill has no directory set — cannot save")

    skill.directory.mkdir(parents=True, exist_ok=True)
    skill_md = skill.directory / "SKILL.md"

    frontmatter = {
        "name": skill.name,
        "description": skill.description,
        "version": skill.version,
    }
    if skill.author:
        frontmatter["author"] = skill.author
    if skill.tags:
        frontmatter["tags"] = skill.tags
    frontmatter["source"] = skill.source
    frontmatter["trust_level"] = skill.trust_level

    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
    content = f"---\n{fm_str}\n---\n\n{skill.instructions}\n"

    skill_md.write_text(content, encoding="utf-8")
    logger.info("Saved SKILL.md for '%s' at %s", skill.name, skill_md)


# ---------------------------------------------------------------------------
# Skill Groups I/O
# ---------------------------------------------------------------------------


def load_skill_groups(groups_file: Path) -> dict[str, SkillGroup]:
    """Load skill groups from YAML file."""
    groups: dict[str, SkillGroup] = {}
    if not groups_file.exists():
        return groups

    try:
        data = yaml.safe_load(groups_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to load skill groups from %s: %s", groups_file, e)
        return groups

    if not isinstance(data, dict):
        return groups

    groups_data = data.get("groups", data)
    if not isinstance(groups_data, dict):
        return groups

    for name, gdata in groups_data.items():
        if isinstance(gdata, dict):
            valid, reason = validate_group_name(name)
            if valid:
                groups[name] = SkillGroup.from_dict(name, gdata)
            else:
                logger.warning("Skipping invalid group name '%s': %s", name, reason)

    return groups


def save_skill_groups(groups: dict[str, SkillGroup], groups_file: Path) -> None:
    """Save skill groups to YAML file."""
    groups_file.parent.mkdir(parents=True, exist_ok=True)
    data = {"groups": {name: g.to_dict() for name, g in groups.items()}}
    groups_file.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("Saved %d skill groups to %s", len(groups), groups_file)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SkillLoadError(Exception):
    """Raised when a skill cannot be loaded."""
