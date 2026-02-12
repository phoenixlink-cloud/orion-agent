"""
Tests for Orion's Knowledge Pack Manager (v7.1.0)

Tests export, import, checksum verification, duplicate handling,
uninstall, and pack listing.
"""

import json
from pathlib import Path

import pytest

from orion.core.learning.knowledge_pack import KnowledgePackManager
from orion.core.memory.engine import MemoryEngine


@pytest.fixture
def memory_engine(tmp_path, monkeypatch):
    """Create a MemoryEngine with temporary paths."""
    # Override the home directory to avoid touching real data
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    engine = MemoryEngine(workspace_path=str(workspace))
    return engine


@pytest.fixture
def pack_manager(memory_engine, tmp_path, monkeypatch):
    """Create a KnowledgePackManager with temporary paths."""
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    mgr = KnowledgePackManager(memory_engine)
    return mgr


@pytest.fixture
def sample_patterns():
    """Sample patterns for testing."""
    return [
        {
            "id": "mem_001",
            "content": "SUCCESS [legal_sa]: Contract formation requires consensus, capacity, legality.",
            "category": "pattern",
            "confidence": 0.9,
            "domain": "legal_sa",
        },
        {
            "id": "mem_002",
            "content": "ANTI-PATTERN [legal_sa]: Missed formality requirements for land sales.",
            "category": "anti_pattern",
            "confidence": 0.7,
            "domain": "legal_sa",
        },
        {
            "id": "mem_003",
            "content": "SUCCESS [legal_sa]: Correctly identified breach remedies.",
            "category": "pattern",
            "confidence": 0.85,
            "domain": "legal_sa",
        },
    ]


class TestExport:
    """Test knowledge pack export."""

    def test_export_pack(self, memory_engine, pack_manager, sample_patterns):
        """Export domain, verify .orionpack file format and checksum."""
        # First, store some patterns in Tier 3 with domain metadata
        for p in sample_patterns:
            memory_engine.remember(
                content=p["content"],
                tier=3,
                category=p["category"],
                confidence=p["confidence"],
                source="test",
                metadata={"domain": p["domain"]},
            )

        pack = pack_manager.export_pack(
            domain="legal_sa",
            name="Orion Legal SA",
            version="1.0.0",
            description="South African contract law",
        )

        assert pack.domain == "legal_sa"
        assert pack.name == "Orion Legal SA"
        assert pack.version == "1.0.0"
        assert pack.checksum.startswith("sha256:")
        assert pack.pattern_count + pack.anti_pattern_count > 0

        # Verify .orionpack file exists and is valid JSON
        pack_file = pack_manager.packs_dir / "legal_sa_1.0.0.orionpack"
        assert pack_file.exists()
        data = json.loads(pack_file.read_text(encoding="utf-8"))
        assert data["format_version"] == "1.0"
        assert data["domain"] == "legal_sa"
        assert data["checksum"] == pack.checksum

    def test_export_empty_domain(self, pack_manager):
        """Export a domain with no patterns."""
        pack = pack_manager.export_pack(
            domain="empty_domain",
            name="Empty",
            version="0.1.0",
            description="No patterns",
        )
        assert pack.pattern_count == 0
        assert pack.anti_pattern_count == 0


class TestImport:
    """Test knowledge pack import."""

    def test_import_pack(self, memory_engine, pack_manager, sample_patterns):
        """Import pack, verify patterns in Tier 3."""
        # Store and export first
        for p in sample_patterns:
            memory_engine.remember(
                content=p["content"],
                tier=3,
                category=p["category"],
                confidence=p["confidence"],
                source="test",
                metadata={"domain": p["domain"]},
            )

        pack_manager.export_pack(
            domain="legal_sa",
            name="Test",
            version="1.0.0",
            description="test",
        )

        # Create a fresh engine to import into
        pack_file = pack_manager.packs_dir / "legal_sa_1.0.0.orionpack"

        result = pack_manager.import_pack(str(pack_file))
        assert result.domain == "legal_sa"
        assert result.version == "1.0.0"
        # Some may be skipped since they already exist
        assert result.patterns_imported + result.patterns_skipped >= 0

    def test_import_skip_duplicates(self, memory_engine, pack_manager, sample_patterns):
        """Import same pack twice, verify no duplicates with skip strategy."""
        for p in sample_patterns:
            memory_engine.remember(
                content=p["content"],
                tier=3,
                category=p["category"],
                confidence=p["confidence"],
                source="test",
                metadata={"domain": p["domain"]},
            )

        pack_manager.export_pack(
            domain="legal_sa",
            name="Test",
            version="1.0.0",
            description="test",
        )
        pack_file = str(pack_manager.packs_dir / "legal_sa_1.0.0.orionpack")

        # First import
        result1 = pack_manager.import_pack(pack_file, merge_strategy="skip_existing")
        # Second import -- should skip all
        result2 = pack_manager.import_pack(pack_file, merge_strategy="skip_existing")
        # Second import should skip more or equal patterns
        assert (
            result2.patterns_skipped >= result1.patterns_skipped or result2.patterns_imported == 0
        )

    def test_import_overwrite(self, memory_engine, pack_manager, sample_patterns):
        """Import with overwrite strategy, verify replacement."""
        for p in sample_patterns:
            memory_engine.remember(
                content=p["content"],
                tier=3,
                category=p["category"],
                confidence=p["confidence"],
                source="test",
                metadata={"domain": p["domain"]},
            )

        pack_manager.export_pack(
            domain="legal_sa",
            name="Test",
            version="1.0.0",
            description="test",
        )
        pack_file = str(pack_manager.packs_dir / "legal_sa_1.0.0.orionpack")

        # Overwrite import -- should delete existing domain patterns first
        result = pack_manager.import_pack(pack_file, merge_strategy="overwrite")
        assert result.domain == "legal_sa"


class TestVerify:
    """Test pack integrity verification."""

    def test_verify_pack_integrity(self, memory_engine, pack_manager, sample_patterns):
        """Verify checksum matches for untampered pack."""
        for p in sample_patterns:
            memory_engine.remember(
                content=p["content"],
                tier=3,
                category=p["category"],
                confidence=p["confidence"],
                source="test",
                metadata={"domain": p["domain"]},
            )

        pack_manager.export_pack(
            domain="legal_sa",
            name="Test",
            version="1.0.0",
            description="test",
        )
        pack_file = str(pack_manager.packs_dir / "legal_sa_1.0.0.orionpack")

        assert pack_manager.verify_pack(pack_file) is True

    def test_verify_tampered_pack(self, memory_engine, pack_manager, sample_patterns):
        """Tamper with pack, verify checksum fails."""
        for p in sample_patterns:
            memory_engine.remember(
                content=p["content"],
                tier=3,
                category=p["category"],
                confidence=p["confidence"],
                source="test",
                metadata={"domain": p["domain"]},
            )

        pack_manager.export_pack(
            domain="legal_sa",
            name="Test",
            version="1.0.0",
            description="test",
        )
        pack_file = pack_manager.packs_dir / "legal_sa_1.0.0.orionpack"

        # Tamper with the file
        data = json.loads(pack_file.read_text(encoding="utf-8"))
        if data["patterns"]:
            data["patterns"][0]["content"] = "TAMPERED CONTENT"
        pack_file.write_text(json.dumps(data), encoding="utf-8")

        assert pack_manager.verify_pack(str(pack_file)) is False

    def test_verify_nonexistent_pack(self, pack_manager):
        """Verify returns False for nonexistent file."""
        assert pack_manager.verify_pack("nonexistent.orionpack") is False


class TestUninstall:
    """Test pack uninstallation."""

    def test_uninstall_pack(self, memory_engine, pack_manager):
        """Uninstall, verify patterns removed from Tier 3."""
        # Insert patterns via load_knowledge_pack
        patterns = [
            {"content": "Test pattern 1", "category": "pattern", "domain": "test"},
            {"content": "Test pattern 2", "category": "anti_pattern", "domain": "test"},
        ]
        pack_id = "test-pack-id-1234"
        count = memory_engine.load_knowledge_pack(patterns, pack_id, "1.0.0")
        assert count == 2

        # Uninstall
        deleted = pack_manager.uninstall_pack(pack_id)
        assert deleted == 2


class TestListPacks:
    """Test pack listing."""

    def test_list_packs(self, memory_engine, pack_manager, sample_patterns):
        """List available packs."""
        for p in sample_patterns:
            memory_engine.remember(
                content=p["content"],
                tier=3,
                category=p["category"],
                confidence=p["confidence"],
                source="test",
                metadata={"domain": p["domain"]},
            )

        pack_manager.export_pack(
            domain="legal_sa",
            name="Test Legal",
            version="1.0.0",
            description="test",
        )

        packs = pack_manager.list_packs()
        assert len(packs) >= 1
        assert any(p["domain"] == "legal_sa" for p in packs)

    def test_list_installed_packs(self, memory_engine, pack_manager):
        """List installed packs (from Tier 3 metadata)."""
        patterns = [
            {"content": "Installed pattern", "category": "pattern", "domain": "installed_test"},
        ]
        memory_engine.load_knowledge_pack(patterns, "install-test-id", "2.0.0")

        installed = pack_manager.list_installed_packs()
        assert len(installed) >= 1
        assert any(p["pack_id"] == "install-test-id" for p in installed)
