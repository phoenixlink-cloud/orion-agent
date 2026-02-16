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
"""SkillLibrary — central registry for skills and skill groups.

Loads skills from ~/.orion/skills/, validates through SkillGuard,
manages groups via ~/.orion/skill_groups.yaml, and resolves skills
for roles at runtime.

See ARA-006 §6 for full design.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from orion.ara.skill import (
    Skill,
    SkillGroup,
    SkillLimits,
    SkillLoadError,
    load_skill,
    load_skill_groups,
    parse_skill_md,
    save_skill_groups,
    save_skill_md,
    validate_group_name,
    validate_skill_name,
)
from orion.ara.skill_guard import SkillGuard, SkillScanResult

logger = logging.getLogger("orion.ara.skill_library")

# Default directories
DEFAULT_SKILLS_DIR = Path.home() / ".orion" / "skills"
DEFAULT_GROUPS_FILE = Path.home() / ".orion" / "skill_groups.yaml"


class SkillLibrary:
    """Central registry for skills and groups.

    Loads from ~/.orion/skills/ and ~/.orion/skill_groups.yaml.
    All skills pass through SkillGuard before being marked aegis_approved.
    """

    def __init__(
        self,
        skills_dir: Path | None = None,
        groups_file: Path | None = None,
    ) -> None:
        self._skills_dir = skills_dir or DEFAULT_SKILLS_DIR
        self._groups_file = groups_file or DEFAULT_GROUPS_FILE
        self._skills: dict[str, Skill] = {}
        self._groups: dict[str, SkillGroup] = {}
        self._guard = SkillGuard()

    @property
    def skills_dir(self) -> Path:
        return self._skills_dir

    @property
    def skill_count(self) -> int:
        return len(self._skills)

    @property
    def group_count(self) -> int:
        return len(self._groups)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_all(self) -> tuple[int, list[str]]:
        """Load all skills from disk and validate through SkillGuard.

        Returns (skills_loaded, warnings).
        """
        warnings: list[str] = []
        loaded = 0

        # Load groups first
        self._groups = load_skill_groups(self._groups_file)

        # Load skills
        if not self._skills_dir.exists():
            return 0, ["Skills directory does not exist"]

        for item in sorted(self._skills_dir.iterdir()):
            if not item.is_dir():
                continue
            skill_md = item / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                skill, load_warnings = load_skill(item)
                warnings.extend(load_warnings)

                # Run SkillGuard scan
                scan_result = self._guard.scan_skill(
                    item,
                    instructions=skill.instructions,
                    supporting_files=skill.supporting_files,
                )
                warnings.extend(scan_result.warnings)

                if scan_result.approved:
                    skill.aegis_approved = True
                    skill.trust_level = scan_result.trust_recommendation
                    skill.content_hash = skill.compute_disk_hash()
                    self._skills[skill.name] = skill
                    loaded += 1
                    logger.info("Loaded skill: %s (trust: %s)", skill.name, skill.trust_level)
                else:
                    skill.aegis_approved = False
                    skill.trust_level = "blocked"
                    self._skills[skill.name] = skill
                    warnings.append(
                        f"Skill '{skill.name}' blocked by SkillGuard: "
                        f"{len(scan_result.findings)} findings"
                    )
                    logger.warning("Skill '%s' BLOCKED by SkillGuard", skill.name)

            except SkillLoadError as e:
                warnings.append(f"Failed to load skill from {item.name}: {e}")
            except Exception as e:
                warnings.append(f"Unexpected error loading {item.name}: {e}")

        # Reconcile group → skill references
        for group in self._groups.values():
            group.skill_names = [s for s in group.skill_names if s in self._skills]

        logger.info("Loaded %d skills, %d groups", loaded, len(self._groups))
        return loaded, warnings

    # ------------------------------------------------------------------
    # Skill CRUD
    # ------------------------------------------------------------------

    def get_skill(self, name: str) -> Skill | None:
        """Get a loaded skill by name.

        Verifies integrity (H1) on every access. If tampered, revokes approval.
        """
        skill = self._skills.get(name)
        if skill is None:
            return None

        # H1: Integrity check on approved skills with a directory on disk
        if skill.aegis_approved and skill.directory and skill.content_hash:
            if not skill.verify_integrity():
                logger.warning(
                    "Skill '%s' modified since last scan — revoking approval. "
                    "Run '/skills scan %s' to re-approve.",
                    name,
                    name,
                )
                skill.aegis_approved = False
                skill.trust_level = "unreviewed"

        return skill

    def create_skill(
        self,
        name: str,
        description: str,
        instructions: str,
        tags: list[str] | None = None,
        group: str | None = None,
        author: str = "",
    ) -> tuple[Skill, SkillScanResult]:
        """Create a new custom skill, scan it, and save to disk.

        Returns (Skill, SkillScanResult).
        Raises SkillLoadError if name is invalid or skill already exists.
        """
        # Validate name
        valid, reason = validate_skill_name(name)
        if not valid:
            raise SkillLoadError(f"Invalid skill name: {reason}")

        if name in self._skills:
            raise SkillLoadError(f"Skill '{name}' already exists")

        # Create skill object
        skill_dir = self._skills_dir / name
        skill = Skill(
            name=name,
            description=description,
            instructions=instructions,
            tags=tags or [],
            source="custom",
            trust_level="trusted",
            author=author,
            directory=skill_dir,
            group=group,
        )

        # H8: Scan before save
        scan_result = self._guard.scan_content(instructions, skill_name=name)

        if scan_result.approved:
            skill.aegis_approved = True
            skill.trust_level = scan_result.trust_recommendation
        else:
            skill.aegis_approved = False
            skill.trust_level = "blocked"

        # Save to disk
        save_skill_md(skill)

        # Compute and store hash from disk
        skill.content_hash = skill.compute_disk_hash()
        self._skills[name] = skill

        # Assign to group if specified
        if group and group in self._groups:
            if name not in self._groups[group].skill_names:
                self._groups[group].skill_names.append(name)
                save_skill_groups(self._groups, self._groups_file)

        logger.info(
            "Created skill '%s' (approved=%s, trust=%s)",
            name,
            skill.aegis_approved,
            skill.trust_level,
        )
        return skill, scan_result

    def update_skill(
        self,
        name: str,
        description: str | None = None,
        instructions: str | None = None,
        tags: list[str] | None = None,
    ) -> tuple[Skill, SkillScanResult]:
        """Update an existing skill. Re-scans automatically (H8).

        Returns (updated_skill, scan_result).
        """
        skill = self._skills.get(name)
        if skill is None:
            raise SkillLoadError(f"Skill '{name}' not found")

        # Apply updates
        if description is not None:
            skill.description = description
        if instructions is not None:
            skill.instructions = instructions
        if tags is not None:
            if len(tags) > SkillLimits.MAX_TAGS:
                tags = tags[: SkillLimits.MAX_TAGS]
            skill.tags = tags

        # H8: Mandatory re-scan
        scan_result = self._guard.scan_content(skill.instructions, skill_name=name)

        if scan_result.approved:
            skill.aegis_approved = True
            skill.trust_level = scan_result.trust_recommendation
        else:
            skill.aegis_approved = False
            skill.trust_level = "blocked"

        # Save and recompute hash
        if skill.directory:
            save_skill_md(skill)
        skill.content_hash = skill.compute_disk_hash()

        logger.info(
            "Updated skill '%s' (approved=%s, trust=%s)",
            name,
            skill.aegis_approved,
            skill.trust_level,
        )
        return skill, scan_result

    def delete_skill(self, name: str) -> bool:
        """Remove a skill from the library and disk."""
        skill = self._skills.pop(name, None)
        if skill is None:
            return False

        # Remove from any groups
        for group in self._groups.values():
            if name in group.skill_names:
                group.skill_names.remove(name)
        save_skill_groups(self._groups, self._groups_file)

        # Remove from disk
        if skill.directory and skill.directory.exists():
            try:
                shutil.rmtree(skill.directory)
                logger.info("Deleted skill directory: %s", skill.directory)
            except Exception as e:
                logger.warning("Failed to delete skill directory: %s", e)

        return True

    def import_skill(
        self,
        source_path: Path,
    ) -> tuple[Skill | None, SkillScanResult | None, list[str]]:
        """Import a skill from an external directory.

        Copies the skill directory into ~/.orion/skills/<name>/, scans it,
        and marks it as imported + unreviewed.

        Returns (Skill | None, ScanResult | None, warnings).
        """
        warnings: list[str] = []

        if not source_path.exists():
            return None, None, [f"Source path does not exist: {source_path}"]

        skill_md = source_path / "SKILL.md" if source_path.is_dir() else source_path
        if source_path.is_dir() and not skill_md.exists():
            return None, None, [f"No SKILL.md found in {source_path}"]

        # Load and validate from source
        try:
            if source_path.is_dir():
                skill, load_warnings = load_skill(source_path)
            else:
                # Single file import
                content = source_path.read_text(encoding="utf-8")
                frontmatter, instructions = parse_skill_md(content)
                name = frontmatter.get("name", source_path.stem)
                valid, reason = validate_skill_name(name)
                if not valid:
                    return None, None, [f"Invalid skill name '{name}': {reason}"]
                skill = Skill(
                    name=name,
                    description=frontmatter.get("description", ""),
                    version=frontmatter.get("version", "1.0.0"),
                    author=frontmatter.get("author", ""),
                    tags=frontmatter.get("tags", []),
                    source="imported",
                    trust_level="unreviewed",
                    instructions=instructions,
                )
                load_warnings = []
            warnings.extend(load_warnings)
        except SkillLoadError as e:
            return None, None, [str(e)]

        # Check for conflicts
        if skill.name in self._skills:
            return None, None, [f"Skill '{skill.name}' already exists in library"]

        # Mark as imported
        skill.source = "imported"
        skill.trust_level = "unreviewed"

        # Copy to skills directory
        dest_dir = self._skills_dir / skill.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        skill.directory = dest_dir

        if source_path.is_dir():
            # Copy all files from source
            for item in source_path.iterdir():
                if item.is_file():
                    dest_file = dest_dir / item.name
                    try:
                        shutil.copy2(item, dest_file)
                    except Exception as e:
                        warnings.append(f"Failed to copy {item.name}: {e}")
        else:
            save_skill_md(skill)

        # Scan
        scan_result = self._guard.scan_skill(
            dest_dir,
            instructions=skill.instructions,
            supporting_files=skill.supporting_files,
        )
        warnings.extend(scan_result.warnings)

        if scan_result.approved:
            skill.aegis_approved = True
            skill.trust_level = scan_result.trust_recommendation
        else:
            skill.aegis_approved = False
            skill.trust_level = "blocked"

        skill.content_hash = skill.compute_disk_hash()
        self._skills[skill.name] = skill

        logger.info(
            "Imported skill '%s' (approved=%s, trust=%s)",
            skill.name,
            skill.aegis_approved,
            skill.trust_level,
        )
        return skill, scan_result, warnings

    def rescan_skill(self, name: str) -> SkillScanResult | None:
        """Re-run SkillGuard on a skill (e.g., after manual edit)."""
        skill = self._skills.get(name)
        if skill is None or skill.directory is None:
            return None

        # Re-load from disk to pick up any changes
        try:
            reloaded, _ = load_skill(skill.directory)
            skill.instructions = reloaded.instructions
            skill.supporting_files = reloaded.supporting_files
        except SkillLoadError:
            pass

        scan_result = self._guard.scan_skill(
            skill.directory,
            instructions=skill.instructions,
            supporting_files=skill.supporting_files,
        )

        if scan_result.approved:
            skill.aegis_approved = True
            skill.trust_level = scan_result.trust_recommendation
            skill.content_hash = skill.compute_disk_hash()
        else:
            skill.aegis_approved = False
            skill.trust_level = "blocked"

        return scan_result

    def list_skills(
        self,
        group: str | None = None,
        tag: str | None = None,
        approved_only: bool = False,
    ) -> list[Skill]:
        """List skills with optional filtering."""
        result: list[Skill] = []
        for skill in self._skills.values():
            if approved_only and not skill.aegis_approved:
                continue
            if group and skill.group != group:
                # Also check group membership
                grp = self._groups.get(group)
                if not grp or skill.name not in grp.skill_names:
                    continue
            if tag and tag not in skill.tags:
                continue
            result.append(skill)
        return result

    # ------------------------------------------------------------------
    # Group CRUD
    # ------------------------------------------------------------------

    def get_group(self, name: str) -> SkillGroup | None:
        """Get a skill group by name."""
        return self._groups.get(name)

    def create_group(
        self,
        name: str,
        display_name: str,
        description: str = "",
        group_type: str = "general",
    ) -> SkillGroup:
        """Create a new skill group."""
        valid, reason = validate_group_name(name)
        if not valid:
            raise SkillLoadError(f"Invalid group name: {reason}")
        if name in self._groups:
            raise SkillLoadError(f"Group '{name}' already exists")

        group = SkillGroup(
            name=name,
            display_name=display_name,
            description=description,
            group_type=group_type,
        )
        self._groups[name] = group
        save_skill_groups(self._groups, self._groups_file)
        return group

    def delete_group(self, name: str) -> bool:
        """Delete a skill group (does NOT delete the skills in it)."""
        if name not in self._groups:
            return False
        del self._groups[name]
        save_skill_groups(self._groups, self._groups_file)
        return True

    def assign_skill_to_group(self, skill_name: str, group_name: str) -> bool:
        """Add a skill to a group."""
        if skill_name not in self._skills:
            return False
        group = self._groups.get(group_name)
        if group is None:
            return False
        if skill_name not in group.skill_names:
            group.skill_names.append(skill_name)
            save_skill_groups(self._groups, self._groups_file)
        return True

    def remove_skill_from_group(self, skill_name: str, group_name: str) -> bool:
        """Remove a skill from a group."""
        group = self._groups.get(group_name)
        if group is None or skill_name not in group.skill_names:
            return False
        group.skill_names.remove(skill_name)
        save_skill_groups(self._groups, self._groups_file)
        return True

    def list_groups(self) -> list[SkillGroup]:
        """List all skill groups."""
        return list(self._groups.values())

    # ------------------------------------------------------------------
    # Role Resolution
    # ------------------------------------------------------------------

    def resolve_skills_for_role(
        self,
        assigned_skills: list[str],
        assigned_skill_groups: list[str],
    ) -> list[Skill]:
        """Resolve all skills available to a role (groups + individual).

        Only returns aegis_approved skills. Order: groups first, then individual.
        """
        seen: set[str] = set()
        resolved: list[Skill] = []

        # Groups first (order: as listed in role)
        for group_name in assigned_skill_groups:
            group = self._groups.get(group_name)
            if not group:
                continue
            for skill_name in group.skill_names:
                if skill_name in seen:
                    continue
                skill = self.get_skill(skill_name)
                if skill and skill.aegis_approved:
                    resolved.append(skill)
                    seen.add(skill_name)

        # Then individual skills
        for skill_name in assigned_skills:
            if skill_name in seen:
                continue
            skill = self.get_skill(skill_name)
            if skill and skill.aegis_approved:
                resolved.append(skill)
                seen.add(skill_name)

        return resolved
