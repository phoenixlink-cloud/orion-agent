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
Orion Agent -- Knowledge Pack Manager (v7.1.0)

Export trained Tier 3 patterns for a domain into a portable, versioned package.
Import knowledge packs to bootstrap new Orion installations.

FILE FORMAT: .orionpack (JSON with SHA-256 integrity checksum)

USAGE:
    from orion.core.learning.knowledge_pack import KnowledgePackManager
    mgr = KnowledgePackManager(memory_engine)
    pack = mgr.export_pack("legal_sa", "Orion Legal SA", "1.0.0", "SA contract law")
    result = mgr.import_pack("legal_sa_1.0.0.orionpack")
"""

import hashlib
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("orion.learning.knowledge_pack")

FORMAT_VERSION = "1.0"


@dataclass
class KnowledgePack:
    """A portable, versioned snapshot of domain knowledge."""

    pack_id: str
    name: str
    domain: str
    version: str
    description: str
    created_at: str
    orion_version: str
    training_cycles: int
    graduation_score: float
    pattern_count: int
    anti_pattern_count: int
    patterns: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    checksum: str = ""


@dataclass
class ImportResult:
    """Result of importing a knowledge pack."""

    patterns_imported: int
    patterns_skipped: int
    patterns_conflicted: int
    domain: str
    version: str


class KnowledgePackManager:
    """
    Manages export, import, and versioning of domain knowledge packs.
    Storage: ~/.orion/knowledge_packs/
    """

    def __init__(self, memory_engine):
        self.memory_engine = memory_engine
        self.packs_dir = Path.home() / ".orion" / "knowledge_packs"
        self.packs_dir.mkdir(parents=True, exist_ok=True)

    def export_pack(
        self,
        domain: str,
        name: str,
        version: str,
        description: str,
        teacher_model: str = "",
        student_model: str = "",
        training_cycles: int = 0,
        graduation_score: float = 0.0,
        source_materials: list[str] = None,
    ) -> KnowledgePack:
        """
        Export domain patterns from Tier 3 as a portable knowledge pack.

        Args:
            domain: The domain to export (e.g., "legal_sa").
            name: Human-readable name for the pack.
            version: Semver version string (e.g., "1.0.0").
            description: Description of the pack contents.
            teacher_model: Teacher model used during training.
            student_model: Student model used during training.
            training_cycles: Number of training cycles completed.
            graduation_score: Average score at time of export.
            source_materials: List of source material references.

        Returns:
            KnowledgePack object with patterns and checksum.
        """
        # Query Tier 3 for all entries where metadata contains this domain
        patterns = self._query_domain_patterns(domain)

        # Split patterns and anti-patterns for the file format (canonical order)
        only_patterns = [p for p in patterns if p.get("category") != "anti_pattern"]
        only_anti_patterns = [p for p in patterns if p.get("category") == "anti_pattern"]

        pattern_count = len(only_patterns)
        anti_pattern_count = len(only_anti_patterns)

        # Compute checksum from canonical order: patterns + anti_patterns
        canonical = only_patterns + only_anti_patterns
        patterns_json = json.dumps(canonical, sort_keys=True)
        checksum = f"sha256:{hashlib.sha256(patterns_json.encode()).hexdigest()}"

        pack = KnowledgePack(
            pack_id=str(uuid.uuid4()),
            name=name,
            domain=domain,
            version=version,
            description=description,
            created_at=datetime.now(timezone.utc).isoformat(),
            orion_version="7.1.0",
            training_cycles=training_cycles,
            graduation_score=graduation_score,
            pattern_count=pattern_count,
            anti_pattern_count=anti_pattern_count,
            patterns=patterns,
            metadata={
                "source_materials": source_materials or [],
                "teacher_model": teacher_model,
                "student_model": student_model,
            },
            checksum=checksum,
        )

        # Write to .orionpack file
        pack_file = self.packs_dir / f"{domain}_{version}.orionpack"
        pack_data = {
            "format_version": FORMAT_VERSION,
            "pack_id": pack.pack_id,
            "name": pack.name,
            "domain": pack.domain,
            "version": pack.version,
            "description": pack.description,
            "created_at": pack.created_at,
            "orion_version": pack.orion_version,
            "training_cycles": pack.training_cycles,
            "graduation_score": pack.graduation_score,
            "teacher_model": teacher_model,
            "student_model": student_model,
            "pattern_count": pack.pattern_count,
            "anti_pattern_count": pack.anti_pattern_count,
            "checksum": pack.checksum,
            "patterns": only_patterns,
            "anti_patterns": only_anti_patterns,
            "metadata": pack.metadata,
        }
        pack_file.write_text(json.dumps(pack_data, indent=2), encoding="utf-8")
        logger.info(
            "Exported knowledge pack: %s v%s (%d patterns) -> %s",
            name,
            version,
            len(patterns),
            pack_file,
        )

        return pack

    def import_pack(self, pack_path: str, merge_strategy: str = "skip_existing") -> ImportResult:
        """
        Import a knowledge pack into Tier 3.

        Args:
            pack_path: Path to the .orionpack file.
            merge_strategy: One of "skip_existing", "overwrite", "merge".

        Returns:
            ImportResult with counts of imported/skipped/conflicted patterns.
        """
        pack_data = self._load_pack_file(pack_path)
        if not pack_data:
            raise ValueError(f"Could not load pack file: {pack_path}")

        # Verify checksum
        if not self._verify_checksum(pack_data):
            raise ValueError("Knowledge pack checksum verification failed -- file may be corrupted")

        domain = pack_data["domain"]
        version = pack_data["version"]
        pack_id = pack_data["pack_id"]
        patterns = pack_data.get("patterns", []) + pack_data.get("anti_patterns", [])

        if merge_strategy == "overwrite":
            self._delete_domain_patterns(domain)

        imported = 0
        skipped = 0
        conflicted = 0

        for pattern in patterns:
            content = pattern.get("content", "")
            if not content:
                continue

            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            existing = self._find_by_content_hash(content_hash)

            if existing:
                if merge_strategy == "skip_existing":
                    skipped += 1
                elif merge_strategy == "merge":
                    # Keep both -- the existing one and the new one
                    # Let confidence scoring sort them out
                    self._insert_pattern(pattern, pack_id, version, domain)
                    conflicted += 1
                    imported += 1
                else:
                    skipped += 1
            else:
                self._insert_pattern(pattern, pack_id, version, domain)
                imported += 1

        logger.info(
            "Imported knowledge pack: %s v%s -- %d imported, %d skipped, %d conflicted",
            domain,
            version,
            imported,
            skipped,
            conflicted,
        )

        return ImportResult(
            patterns_imported=imported,
            patterns_skipped=skipped,
            patterns_conflicted=conflicted,
            domain=domain,
            version=version,
        )

    def list_packs(self) -> list[dict]:
        """
        List available .orionpack files (without loading full patterns).

        Returns:
            List of pack metadata dicts.
        """
        packs = []
        for f in self.packs_dir.glob("*.orionpack"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                packs.append(
                    {
                        "file": str(f),
                        "pack_id": data.get("pack_id", ""),
                        "name": data.get("name", ""),
                        "domain": data.get("domain", ""),
                        "version": data.get("version", ""),
                        "description": data.get("description", ""),
                        "pattern_count": data.get("pattern_count", 0),
                        "anti_pattern_count": data.get("anti_pattern_count", 0),
                        "created_at": data.get("created_at", ""),
                    }
                )
            except Exception as e:
                logger.warning("Could not read pack file %s: %s", f, e)
        return packs

    def list_installed_packs(self) -> list[dict]:
        """
        List knowledge packs that are currently installed in Tier 3.
        Queries for unique pack_id values in metadata.
        """
        try:
            db_path = self.memory_engine._db_path
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT metadata FROM memories WHERE source = 'knowledge_pack'"
            ).fetchall()
            conn.close()

            packs_by_id = {}
            for (meta_str,) in rows:
                try:
                    meta = json.loads(meta_str) if meta_str else {}
                except Exception:
                    continue
                pid = meta.get("pack_id", "")
                if pid and pid not in packs_by_id:
                    packs_by_id[pid] = {
                        "pack_id": pid,
                        "pack_version": meta.get("pack_version", ""),
                        "domain": meta.get("domain", ""),
                        "pattern_count": 0,
                    }
                if pid:
                    packs_by_id[pid]["pattern_count"] += 1

            return list(packs_by_id.values())

        except Exception as e:
            logger.warning("Failed to list installed packs: %s", e)
            return []

    def uninstall_pack(self, pack_id: str) -> int:
        """
        Remove all Tier 3 entries from a specific knowledge pack.

        Returns:
            Count of deleted entries.
        """
        try:
            db_path = self.memory_engine._db_path
            conn = sqlite3.connect(db_path)
            # Find all entries with this pack_id in metadata
            rows = conn.execute(
                "SELECT id FROM memories WHERE metadata LIKE ?",
                (f'%"pack_id": "{pack_id}"%',),
            ).fetchall()
            ids = [r[0] for r in rows]

            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids)
                # Also clean up embeddings if table exists
                try:
                    conn.execute(
                        f"DELETE FROM memory_embeddings WHERE memory_id IN ({placeholders})",
                        ids,
                    )
                except sqlite3.OperationalError:
                    pass  # memory_embeddings table may not exist
                conn.commit()

            conn.close()
            logger.info("Uninstalled pack %s: %d entries removed", pack_id, len(ids))
            return len(ids)

        except Exception as e:
            logger.warning("Failed to uninstall pack %s: %s", pack_id, e)
            return 0

    def verify_pack(self, pack_path: str) -> bool:
        """
        Verify the integrity of a .orionpack file.

        Returns:
            True if the checksum matches.
        """
        pack_data = self._load_pack_file(pack_path)
        if not pack_data:
            return False
        return self._verify_checksum(pack_data)

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _load_pack_file(self, pack_path: str) -> dict | None:
        """Load and parse a .orionpack file."""
        try:
            path = Path(pack_path)
            if not path.exists():
                # Try looking in the packs directory
                path = self.packs_dir / pack_path
            if not path.exists():
                logger.warning("Pack file not found: %s", pack_path)
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to load pack file %s: %s", pack_path, e)
            return None

    def _verify_checksum(self, pack_data: dict) -> bool:
        """Recompute checksum and compare against stored checksum."""
        stored = pack_data.get("checksum", "")
        # Recombine patterns + anti_patterns to match the original checksum
        all_patterns = pack_data.get("patterns", []) + pack_data.get("anti_patterns", [])
        patterns_json = json.dumps(all_patterns, sort_keys=True)
        computed = f"sha256:{hashlib.sha256(patterns_json.encode()).hexdigest()}"
        return stored == computed

    def _query_domain_patterns(self, domain: str) -> list[dict]:
        """Query all Tier 3 entries for a specific domain."""
        try:
            db_path = self.memory_engine._db_path
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT id, content, category, confidence, metadata, created_at "
                "FROM memories WHERE metadata LIKE ?",
                (f'%"domain": "{domain}"%',),
            ).fetchall()
            conn.close()

            patterns = []
            for row in rows:
                mid, content, category, confidence, meta_str, created_at = row
                try:
                    meta = json.loads(meta_str) if meta_str else {}
                except Exception:
                    meta = {}
                patterns.append(
                    {
                        "id": mid,
                        "content": content,
                        "category": category,
                        "confidence": confidence,
                        "domain": domain,
                        "tags": meta.get("tags", []),
                        "created_at": created_at,
                    }
                )
            return patterns

        except Exception as e:
            logger.warning("Failed to query domain patterns for %s: %s", domain, e)
            return []

    def _delete_domain_patterns(self, domain: str):
        """Delete all Tier 3 entries for a domain (for overwrite strategy)."""
        try:
            db_path = self.memory_engine._db_path
            conn = sqlite3.connect(db_path)
            conn.execute(
                "DELETE FROM memories WHERE metadata LIKE ?",
                (f'%"domain": "{domain}"%',),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to delete domain patterns for %s: %s", domain, e)

    def _find_by_content_hash(self, content_hash: str) -> bool:
        """Check if an entry with this content hash exists."""
        return self.memory_engine._content_hash_exists(content_hash)

    def _insert_pattern(self, pattern: dict, pack_id: str, pack_version: str, domain: str):
        """Insert a single pattern from a knowledge pack into Tier 3."""
        self.memory_engine.load_knowledge_pack(
            patterns=[{**pattern, "domain": domain}],
            pack_id=pack_id,
            pack_version=pack_version,
        )
