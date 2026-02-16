# Orion Agent — Tests for ara/skill.py
"""Tests for Skill data model, SKILL.md parser, validation, and groups."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from orion.ara.skill import (
    ALLOWED_SUPPORTING_EXTENSIONS,
    BLOCKED_EXTENSIONS,
    Skill,
    SkillGroup,
    SkillLimits,
    SkillLoadError,
    check_file_extension,
    load_skill,
    load_skill_groups,
    parse_skill_md,
    save_skill_groups,
    save_skill_md,
    validate_group_name,
    validate_skill_name,
)

# ─────────────────────────────────────────────────────────────────────
# validate_skill_name
# ─────────────────────────────────────────────────────────────────────


class TestValidateSkillName:
    def test_valid_simple(self):
        ok, _ = validate_skill_name("code-review")
        assert ok

    def test_valid_numeric(self):
        ok, _ = validate_skill_name("deploy-v2")
        assert ok

    def test_valid_min_length(self):
        ok, _ = validate_skill_name("ab")
        assert ok

    def test_empty(self):
        ok, reason = validate_skill_name("")
        assert not ok
        assert "empty" in reason.lower()

    def test_too_long(self):
        ok, _ = validate_skill_name("a" * 100)
        assert not ok

    def test_uppercase_rejected(self):
        ok, _ = validate_skill_name("Code-Review")
        assert not ok

    def test_spaces_rejected(self):
        ok, _ = validate_skill_name("code review")
        assert not ok

    def test_underscore_rejected(self):
        ok, _ = validate_skill_name("code_review")
        assert not ok

    def test_consecutive_hyphens(self):
        ok, reason = validate_skill_name("code--review")
        assert not ok
        assert "hyphens" in reason.lower()

    def test_starts_with_hyphen(self):
        ok, _ = validate_skill_name("-code-review")
        assert not ok

    def test_ends_with_hyphen(self):
        ok, _ = validate_skill_name("code-review-")
        assert not ok

    def test_single_char_rejected(self):
        ok, _ = validate_skill_name("a")
        assert not ok

    def test_windows_reserved_name(self):
        ok, reason = validate_skill_name("con")
        assert not ok
        assert "reserved" in reason.lower()

    def test_windows_reserved_nul(self):
        ok, _ = validate_skill_name("nul")
        assert not ok


class TestValidateGroupName:
    def test_valid(self):
        ok, _ = validate_group_name("infrastructure")
        assert ok

    def test_empty(self):
        ok, _ = validate_group_name("")
        assert not ok


# ─────────────────────────────────────────────────────────────────────
# check_file_extension
# ─────────────────────────────────────────────────────────────────────


class TestCheckFileExtension:
    def test_allowed_md(self):
        ok, reason = check_file_extension("readme.md")
        assert ok
        assert reason == "ok"

    def test_allowed_py(self):
        ok, reason = check_file_extension("helper.py")
        assert ok
        assert reason == "ok"

    def test_allowed_yaml(self):
        ok, reason = check_file_extension("config.yaml")
        assert ok
        assert reason == "ok"

    def test_blocked_exe(self):
        ok, reason = check_file_extension("malware.exe")
        assert not ok
        assert "blocked" in reason

    def test_blocked_dll(self):
        ok, reason = check_file_extension("evil.dll")
        assert not ok

    def test_blocked_bat(self):
        ok, reason = check_file_extension("run.bat")
        assert not ok

    def test_blocked_ps1(self):
        ok, reason = check_file_extension("script.ps1")
        assert not ok

    def test_unknown_extension_flagged(self):
        ok, reason = check_file_extension("data.xyz")
        assert ok
        assert reason == "flagged"

    def test_no_extension_flagged(self):
        ok, reason = check_file_extension("somefile")
        assert ok
        assert reason == "flagged"

    def test_known_name_dockerfile(self):
        ok, reason = check_file_extension("Dockerfile")
        assert ok
        assert reason == "ok"

    def test_known_name_makefile(self):
        ok, reason = check_file_extension("Makefile")
        assert ok
        assert reason == "ok"


# ─────────────────────────────────────────────────────────────────────
# parse_skill_md
# ─────────────────────────────────────────────────────────────────────


class TestParseSkillMd:
    def test_full_frontmatter(self):
        content = textwrap.dedent("""\
        ---
        name: test-skill
        description: "A test skill"
        version: "2.0.0"
        tags: ["a", "b"]
        ---

        ## Instructions
        Do the thing.
        """)
        fm, body = parse_skill_md(content)
        assert fm["name"] == "test-skill"
        assert fm["description"] == "A test skill"
        assert fm["version"] == "2.0.0"
        assert fm["tags"] == ["a", "b"]
        assert "## Instructions" in body
        assert "Do the thing." in body

    def test_no_frontmatter(self):
        content = "Just instructions, no YAML."
        fm, body = parse_skill_md(content)
        assert fm == {}
        assert body == content

    def test_empty_frontmatter(self):
        content = "---\n---\nBody here"
        fm, body = parse_skill_md(content)
        assert fm == {} or fm is None
        assert "Body" in body

    def test_invalid_yaml_fallback(self):
        content = "---\n: invalid: yaml: {{{\n---\nBody"
        fm, body = parse_skill_md(content)
        # Should not crash, returns empty frontmatter
        assert isinstance(fm, dict)

    def test_empty_content(self):
        fm, body = parse_skill_md("")
        assert fm == {}
        assert body == ""


# ─────────────────────────────────────────────────────────────────────
# Skill dataclass
# ─────────────────────────────────────────────────────────────────────


class TestSkillDataclass:
    def test_defaults(self):
        s = Skill(name="test", description="A test")
        assert s.version == "1.0.0"
        assert s.source == "custom"
        assert s.trust_level == "trusted"
        assert s.aegis_approved is False
        assert s.tags == []
        assert s.supporting_files == []

    def test_to_dict_roundtrip(self):
        s = Skill(
            name="deploy",
            description="Deploy stuff",
            version="2.0.0",
            tags=["devops"],
            source="imported",
            trust_level="unreviewed",
            instructions="Do deploy",
        )
        d = s.to_dict()
        s2 = Skill.from_dict(d)
        assert s2.name == s.name
        assert s2.description == s.description
        assert s2.version == s.version
        assert s2.tags == s.tags
        assert s2.source == s.source
        assert s2.trust_level == s.trust_level
        assert s2.instructions == s.instructions

    def test_compute_hash_stable(self):
        s = Skill(name="test", description="x", instructions="hello world")
        h1 = s.compute_hash()
        h2 = s.compute_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_compute_hash_changes_with_content(self):
        s1 = Skill(name="test", description="x", instructions="version 1")
        s2 = Skill(name="test", description="x", instructions="version 2")
        assert s1.compute_hash() != s2.compute_hash()

    def test_verify_integrity_no_hash(self):
        s = Skill(name="test", description="x", instructions="abc")
        assert s.verify_integrity() is False

    def test_verify_integrity_matches(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nabc")
        s = Skill(name="test", description="x", instructions="abc", directory=skill_dir)
        s.content_hash = s.compute_disk_hash()
        assert s.verify_integrity() is True

    def test_verify_integrity_tampered(self, tmp_path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nabc")
        s = Skill(name="test", description="x", instructions="abc", directory=skill_dir)
        s.content_hash = s.compute_disk_hash()
        # Tamper with the file on disk
        (skill_dir / "SKILL.md").write_text("TAMPERED CONTENT")
        assert s.verify_integrity() is False


# ─────────────────────────────────────────────────────────────────────
# SkillGroup
# ─────────────────────────────────────────────────────────────────────


class TestSkillGroup:
    def test_defaults(self):
        g = SkillGroup(name="general", display_name="General")
        assert g.group_type == "general"
        assert g.skill_names == []

    def test_roundtrip(self):
        g = SkillGroup(
            name="infra",
            display_name="Infrastructure",
            description="Ops stuff",
            group_type="specialized",
            skill_names=["deploy", "docker"],
            tags=["devops"],
        )
        d = g.to_dict()
        g2 = SkillGroup.from_dict("infra", d)
        assert g2.name == g.name
        assert g2.display_name == g.display_name
        assert g2.skill_names == g.skill_names
        assert g2.group_type == g.group_type


# ─────────────────────────────────────────────────────────────────────
# load_skill (filesystem)
# ─────────────────────────────────────────────────────────────────────


class TestLoadSkill:
    def test_load_valid_skill(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
        ---
        name: my-skill
        description: "Test skill"
        tags: ["test"]
        ---

        ## Steps
        1. Do thing
        """),
            encoding="utf-8",
        )

        skill, warnings = load_skill(skill_dir)
        assert skill.name == "my-skill"
        assert skill.description == "Test skill"
        assert "## Steps" in skill.instructions
        assert skill.aegis_approved is False

    def test_load_with_supporting_files(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: test\n---\nBody")
        (skill_dir / "helper.py").write_text("print('hi')")
        (skill_dir / "config.yaml").write_text("key: val")

        skill, warnings = load_skill(skill_dir)
        assert "helper.py" in skill.supporting_files
        assert "config.yaml" in skill.supporting_files

    def test_load_rejects_blocked_extension(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: test\n---\nBody")
        (skill_dir / "evil.exe").write_bytes(b"\x00" * 10)

        skill, warnings = load_skill(skill_dir)
        assert "evil.exe" not in skill.supporting_files
        assert any("Blocked" in w for w in warnings)

    def test_load_missing_skill_md(self, tmp_path):
        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()
        with pytest.raises(SkillLoadError, match="SKILL.md not found"):
            load_skill(skill_dir)

    def test_load_oversized_skill_md(self, tmp_path):
        skill_dir = tmp_path / "big-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: big-skill\ndescription: x\n---\n"
            + "x" * (SkillLimits.MAX_SKILL_MD_BYTES + 1)
        )
        with pytest.raises(SkillLoadError, match="too large"):
            load_skill(skill_dir)

    def test_load_invalid_name(self, tmp_path):
        skill_dir = tmp_path / "BAD_NAME"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: BAD_NAME\ndescription: x\n---\nBody")
        with pytest.raises(SkillLoadError, match="Invalid skill name"):
            load_skill(skill_dir)

    def test_load_name_from_dirname_if_missing(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\nBody")
        skill, _ = load_skill(skill_dir)
        assert skill.name == "my-skill"

    def test_load_rejects_symlinks(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: x\n---\nBody")
        # Create a regular file and a symlink
        target = tmp_path / "secret.txt"
        target.write_text("secret data")
        link = skill_dir / "linked.txt"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("Cannot create symlinks on this OS/filesystem")
        skill, warnings = load_skill(skill_dir)
        assert "linked.txt" not in skill.supporting_files
        assert any("ymlink" in w for w in warnings)

    def test_max_supporting_files(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: x\n---\nBody")
        for i in range(SkillLimits.MAX_SUPPORTING_FILES + 5):
            (skill_dir / f"file{i:03d}.txt").write_text(f"content {i}")
        skill, warnings = load_skill(skill_dir)
        assert len(skill.supporting_files) <= SkillLimits.MAX_SUPPORTING_FILES
        assert any("Too many" in w for w in warnings)


# ─────────────────────────────────────────────────────────────────────
# save_skill_md
# ─────────────────────────────────────────────────────────────────────


class TestSaveSkillMd:
    def test_save_and_reload(self, tmp_path):
        skill_dir = tmp_path / "round-trip"
        skill = Skill(
            name="round-trip",
            description="Round trip test",
            version="1.2.3",
            author="tester",
            tags=["test"],
            instructions="## Steps\n1. Do it",
            directory=skill_dir,
        )
        save_skill_md(skill)
        assert (skill_dir / "SKILL.md").exists()

        loaded, _ = load_skill(skill_dir)
        assert loaded.name == "round-trip"
        assert loaded.description == "Round trip test"
        assert loaded.version == "1.2.3"
        assert "## Steps" in loaded.instructions

    def test_save_no_directory_raises(self):
        skill = Skill(name="no-dir", description="x", directory=None)
        with pytest.raises(SkillLoadError, match="no directory"):
            save_skill_md(skill)


# ─────────────────────────────────────────────────────────────────────
# Skill Groups I/O
# ─────────────────────────────────────────────────────────────────────


class TestSkillGroupsIO:
    def test_save_and_load(self, tmp_path):
        groups_file = tmp_path / "skill_groups.yaml"
        groups = {
            "infra": SkillGroup(
                name="infra",
                display_name="Infrastructure",
                group_type="specialized",
                skill_names=["deploy", "docker"],
            ),
            "quality": SkillGroup(
                name="quality",
                display_name="Code Quality",
                skill_names=["review"],
            ),
        }
        save_skill_groups(groups, groups_file)
        loaded = load_skill_groups(groups_file)
        assert "infra" in loaded
        assert "quality" in loaded
        assert loaded["infra"].skill_names == ["deploy", "docker"]
        assert loaded["infra"].group_type == "specialized"

    def test_load_missing_file(self, tmp_path):
        groups = load_skill_groups(tmp_path / "nonexistent.yaml")
        assert groups == {}

    def test_load_empty_file(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("")
        groups = load_skill_groups(f)
        assert groups == {}
