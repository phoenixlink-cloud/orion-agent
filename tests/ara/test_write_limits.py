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
"""Tests for AEGIS Write Limits (ARA-001 §C.8)."""

from __future__ import annotations

import pytest

from orion.security.write_limits import (
    AEGIS_CEILINGS,
    WriteLimits,
    WriteTracker,
    WriteViolation,
)


@pytest.fixture
def tracker() -> WriteTracker:
    return WriteTracker()


@pytest.fixture
def strict_tracker() -> WriteTracker:
    """Tracker with very low limits for easy testing."""
    return WriteTracker(
        limits=WriteLimits(
            max_single_file_size_mb=0.001,  # ~1KB
            max_files_created=3,
            max_files_modified=3,
            max_total_write_volume_mb=0.005,  # ~5KB
            max_single_file_lines=10,
        )
    )


class TestWriteLimitsClamping:
    """Test that user limits cannot exceed AEGIS ceilings."""

    def test_user_limits_clamped_to_ceiling(self):
        limits = WriteLimits(
            max_single_file_size_mb=999,
            max_files_created=9999,
            max_files_modified=9999,
            max_total_write_volume_mb=9999,
            max_single_file_lines=99999,
        )
        assert limits.max_single_file_size_mb == AEGIS_CEILINGS.max_single_file_size_mb
        assert limits.max_files_created == AEGIS_CEILINGS.max_files_created
        assert limits.max_files_modified == AEGIS_CEILINGS.max_files_modified
        assert limits.max_total_write_volume_mb == AEGIS_CEILINGS.max_total_write_volume_mb
        assert limits.max_single_file_lines == AEGIS_CEILINGS.max_single_file_lines

    def test_user_can_lower_limits(self):
        limits = WriteLimits(max_files_created=5, max_single_file_size_mb=1.0)
        assert limits.max_files_created == 5
        assert limits.max_single_file_size_mb == 1.0

    def test_from_dict(self):
        limits = WriteLimits.from_dict({"max_file_size_mb": 5, "max_files_created": 50})
        assert limits.max_single_file_size_mb == 5.0
        assert limits.max_files_created == 50

    def test_from_dict_empty(self):
        limits = WriteLimits.from_dict({})
        assert limits.max_single_file_size_mb == AEGIS_CEILINGS.max_single_file_size_mb

    def test_aegis_ceilings_immutable(self):
        with pytest.raises(AttributeError):
            AEGIS_CEILINGS.max_files_created = 999  # type: ignore[misc]


class TestWriteTrackerBasic:
    """Test basic write tracking functionality."""

    def test_allows_normal_write(self, tracker: WriteTracker):
        violation = tracker.check_write("src/main.py", "print('hello')\n", is_new_file=True)
        assert violation is None

    def test_records_write(self, tracker: WriteTracker):
        tracker.record_write("src/main.py", "x = 1\n", is_new_file=True)
        assert tracker.created_count == 1
        assert tracker.total_bytes_written > 0

    def test_check_and_record(self, tracker: WriteTracker):
        violation = tracker.check_and_record("src/main.py", "x = 1\n", is_new_file=True)
        assert violation is None
        assert tracker.created_count == 1

    def test_stats(self, tracker: WriteTracker):
        tracker.record_write("a.py", "x" * 1024, is_new_file=True)
        tracker.record_write("b.py", "y" * 1024, is_new_file=False)
        stats = tracker.stats()
        assert stats["files_created"] == 1
        assert stats["files_modified"] == 1
        assert tracker.total_bytes_written > 0


class TestBlockOversizedFile:
    """Test that oversized files are blocked."""

    def test_blocks_oversized_file(self, strict_tracker: WriteTracker):
        big_content = "x" * 2000  # > 1KB
        violation = strict_tracker.check_write("big.py", big_content, is_new_file=True)
        assert violation is not None
        assert violation.violation_type == "file_too_large"

    def test_allows_small_file(self, strict_tracker: WriteTracker):
        small_content = "x = 1\n"
        violation = strict_tracker.check_write("small.py", small_content, is_new_file=True)
        assert violation is None


class TestBlockTooManyFiles:
    """Test file count limits."""

    def test_blocks_too_many_created(self, strict_tracker: WriteTracker):
        for i in range(3):
            strict_tracker.record_write(f"file{i}.py", "x", is_new_file=True)
        violation = strict_tracker.check_write("file3.py", "x", is_new_file=True)
        assert violation is not None
        assert violation.violation_type == "too_many_files_created"

    def test_blocks_too_many_modified(self, strict_tracker: WriteTracker):
        for i in range(3):
            strict_tracker.record_write(f"mod{i}.py", "x", is_new_file=False)
        violation = strict_tracker.check_write("mod3.py", "x", is_new_file=False)
        assert violation is not None
        assert violation.violation_type == "too_many_files_modified"

    def test_same_file_not_double_counted(self, strict_tracker: WriteTracker):
        for _ in range(5):
            strict_tracker.record_write("same.py", "x", is_new_file=True)
        # Should still only count as 1 file
        assert strict_tracker.created_count == 1


class TestBlockTotalVolume:
    """Test total write volume limits."""

    def test_blocks_total_volume_exceeded(self, strict_tracker: WriteTracker):
        # Write ~5KB across multiple files to exceed 5KB limit
        for i in range(3):
            strict_tracker.record_write(f"f{i}.py", "x" * 2000, is_new_file=True)
        violation = strict_tracker.check_write("overflow.py", "x" * 100, is_new_file=False)
        assert violation is not None
        assert violation.violation_type == "total_volume_exceeded"


class TestBlockTooManyLines:
    """Test line count limits."""

    def test_blocks_too_many_lines(self, strict_tracker: WriteTracker):
        content = "\n".join(f"line {i}" for i in range(20))  # 20 lines > 10 limit
        violation = strict_tracker.check_write("long.py", content, is_new_file=True)
        assert violation is not None
        assert violation.violation_type == "too_many_lines"

    def test_allows_within_line_limit(self, strict_tracker: WriteTracker):
        content = "\n".join(f"line {i}" for i in range(5))
        violation = strict_tracker.check_write("short.py", content, is_new_file=True)
        assert violation is None


class TestWriteViolation:
    """Test WriteViolation data class."""

    def test_to_dict(self):
        v = WriteViolation(
            violation_type="file_too_large",
            message="File exceeds size limit",
            file_path="big.py",
            limit=10,
            actual=15,
        )
        d = v.to_dict()
        assert d["type"] == "file_too_large"
        assert d["file"] == "big.py"
        assert d["limit"] == 10
        assert d["actual"] == 15
