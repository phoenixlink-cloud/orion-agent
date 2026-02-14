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
"""AEGIS Write Limits — prevents runaway file generation and disk exhaustion.

Part of the AEGIS governance layer (ARA-001 §C.8). Enforced before every
file write in the sandbox. User can lower limits per role but cannot
exceed AEGIS ceilings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("orion.security.write_limits")


@dataclass(frozen=True)
class WriteLimitCeilings:
    """AEGIS hard ceilings — cannot be exceeded by any role configuration."""

    max_single_file_size_mb: float = 10.0
    max_files_created: int = 100
    max_files_modified: int = 200
    max_total_write_volume_mb: float = 200.0
    max_single_file_lines: int = 5000


# Singleton AEGIS ceiling — immutable
AEGIS_CEILINGS = WriteLimitCeilings()


@dataclass
class WriteLimits:
    """Per-role write limits. Must not exceed AEGIS ceilings."""

    max_single_file_size_mb: float = 10.0
    max_files_created: int = 100
    max_files_modified: int = 200
    max_total_write_volume_mb: float = 200.0
    max_single_file_lines: int = 5000

    def __post_init__(self):
        """Clamp all values to AEGIS ceilings."""
        self.max_single_file_size_mb = min(
            self.max_single_file_size_mb, AEGIS_CEILINGS.max_single_file_size_mb
        )
        self.max_files_created = min(
            self.max_files_created, AEGIS_CEILINGS.max_files_created
        )
        self.max_files_modified = min(
            self.max_files_modified, AEGIS_CEILINGS.max_files_modified
        )
        self.max_total_write_volume_mb = min(
            self.max_total_write_volume_mb, AEGIS_CEILINGS.max_total_write_volume_mb
        )
        self.max_single_file_lines = min(
            self.max_single_file_lines, AEGIS_CEILINGS.max_single_file_lines
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WriteLimits:
        """Create from a dictionary (e.g. role YAML write_limits section)."""
        return cls(
            max_single_file_size_mb=data.get("max_file_size_mb", 10.0),
            max_files_created=data.get("max_files_created", 100),
            max_files_modified=data.get("max_files_modified", 200),
            max_total_write_volume_mb=data.get("max_total_write_volume_mb", 200.0),
            max_single_file_lines=data.get("max_single_file_lines", 5000),
        )


@dataclass
class WriteViolation:
    """A single write limit violation."""

    violation_type: str
    message: str
    file_path: str | None = None
    limit: float | int = 0
    actual: float | int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.violation_type,
            "message": self.message,
            "file": self.file_path,
            "limit": self.limit,
            "actual": self.actual,
        }


@dataclass
class WriteTracker:
    """Tracks write operations within a session and enforces limits."""

    limits: WriteLimits = field(default_factory=WriteLimits)
    files_created: set[str] = field(default_factory=set)
    files_modified: set[str] = field(default_factory=set)
    total_bytes_written: int = 0

    @property
    def total_mb_written(self) -> float:
        return self.total_bytes_written / (1024 * 1024)

    @property
    def created_count(self) -> int:
        return len(self.files_created)

    @property
    def modified_count(self) -> int:
        return len(self.files_modified)

    def check_write(
        self,
        file_path: str,
        content: str | bytes,
        is_new_file: bool = False,
    ) -> WriteViolation | None:
        """Check if a write operation would violate limits.

        Returns None if the write is allowed, or a WriteViolation if blocked.
        """
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content

        size_mb = len(content_bytes) / (1024 * 1024)
        line_count = content.count("\n") + 1 if isinstance(content, str) else 0

        # Check single file size
        if size_mb > self.limits.max_single_file_size_mb:
            return WriteViolation(
                violation_type="file_too_large",
                message=f"File exceeds size limit: {size_mb:.1f}MB > {self.limits.max_single_file_size_mb}MB",
                file_path=file_path,
                limit=self.limits.max_single_file_size_mb,
                actual=round(size_mb, 2),
            )

        # Check line count (text files only)
        if isinstance(content, str) and line_count > self.limits.max_single_file_lines:
            return WriteViolation(
                violation_type="too_many_lines",
                message=f"File exceeds line limit: {line_count} > {self.limits.max_single_file_lines}",
                file_path=file_path,
                limit=self.limits.max_single_file_lines,
                actual=line_count,
            )

        # Check files created count
        if is_new_file and file_path not in self.files_created:
            if self.created_count >= self.limits.max_files_created:
                return WriteViolation(
                    violation_type="too_many_files_created",
                    message=f"Session file creation limit reached: {self.limits.max_files_created}",
                    file_path=file_path,
                    limit=self.limits.max_files_created,
                    actual=self.created_count,
                )

        # Check files modified count
        if not is_new_file and file_path not in self.files_modified:
            if self.modified_count >= self.limits.max_files_modified:
                return WriteViolation(
                    violation_type="too_many_files_modified",
                    message=f"Session file modification limit reached: {self.limits.max_files_modified}",
                    file_path=file_path,
                    limit=self.limits.max_files_modified,
                    actual=self.modified_count,
                )

        # Check total write volume
        new_total_mb = (self.total_bytes_written + len(content_bytes)) / (1024 * 1024)
        if new_total_mb > self.limits.max_total_write_volume_mb:
            return WriteViolation(
                violation_type="total_volume_exceeded",
                message=(
                    f"Session total write volume exceeded: "
                    f"{new_total_mb:.1f}MB > {self.limits.max_total_write_volume_mb}MB"
                ),
                file_path=file_path,
                limit=self.limits.max_total_write_volume_mb,
                actual=round(new_total_mb, 2),
            )

        return None

    def record_write(self, file_path: str, content: str | bytes, is_new_file: bool = False):
        """Record a successful write operation."""
        byte_count = len(content.encode("utf-8")) if isinstance(content, str) else len(content)

        if is_new_file:
            self.files_created.add(file_path)
        else:
            self.files_modified.add(file_path)

        self.total_bytes_written += byte_count
        logger.debug(
            "Write recorded: %s (%d bytes, total: %.1fMB)",
            file_path,
            byte_count,
            self.total_mb_written,
        )

    def check_and_record(
        self,
        file_path: str,
        content: str | bytes,
        is_new_file: bool = False,
    ) -> WriteViolation | None:
        """Check limits and record if allowed. Returns violation or None."""
        violation = self.check_write(file_path, content, is_new_file)
        if violation:
            logger.warning(
                "Write blocked: %s — %s", file_path, violation.message
            )
            return violation
        self.record_write(file_path, content, is_new_file)
        return None

    def stats(self) -> dict[str, Any]:
        """Return current write statistics."""
        return {
            "files_created": self.created_count,
            "files_modified": self.modified_count,
            "total_mb_written": round(self.total_mb_written, 2),
            "limits": {
                "max_files_created": self.limits.max_files_created,
                "max_files_modified": self.limits.max_files_modified,
                "max_total_write_volume_mb": self.limits.max_total_write_volume_mb,
                "max_single_file_size_mb": self.limits.max_single_file_size_mb,
                "max_single_file_lines": self.limits.max_single_file_lines,
            },
        }
