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
"""Tests for Phase 4C.4 — Activity Logger Persistence.

6+ tests covering:
  - save_to_file writes JSONL
  - load_from_file restores entries
  - Round-trip save → load preserves data
  - load_from_file raises on missing file
  - list_sessions finds persisted logs
  - list_sessions returns empty for non-existent dir
  - next_id continuity after load
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orion.ara.activity_logger import ActivityEntry, ActivityLogger


class TestActivityPersistence:
    def test_save_to_file(self, tmp_path: Path):
        """save_to_file should write a JSONL file with all entries."""
        al = ActivityLogger(session_id="persist-save")
        al.log("command", "echo hello", exit_code=0, status="success")
        al.log("info", "setup complete", status="success")

        filepath = al.save_to_file(directory=tmp_path)

        assert filepath.exists()
        assert filepath.name == "persist-save.jsonl"
        lines = filepath.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        parsed = json.loads(lines[0])
        assert parsed["action_type"] == "command"

    def test_load_from_file(self, tmp_path: Path):
        """load_from_file should restore entries from a JSONL file."""
        # Create a JSONL file manually
        entries = [
            {
                "timestamp": "2025-01-01T00:00:00+00:00",
                "session_id": "load-test",
                "action_type": "command",
                "description": "cmd 1",
                "status": "success",
                "entry_id": 1,
            },
            {
                "timestamp": "2025-01-01T00:00:01+00:00",
                "session_id": "load-test",
                "action_type": "info",
                "description": "info 1",
                "status": "success",
                "entry_id": 2,
            },
        ]
        filepath = tmp_path / "load-test.jsonl"
        filepath.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

        al = ActivityLogger.load_from_file("load-test", directory=tmp_path)
        assert al.session_id == "load-test"
        assert al.entry_count == 2
        assert al._entries[0].action_type == "command"
        assert al._entries[1].description == "info 1"

    def test_save_load_roundtrip(self, tmp_path: Path):
        """Save then load should preserve all entry data."""
        al = ActivityLogger(session_id="roundtrip")
        al.log(
            "command",
            "echo test",
            command="echo test",
            exit_code=0,
            stdout="test output",
            duration_seconds=0.5,
            phase="execute",
            status="success",
        )
        al.log("file_write", "Writing app.py", phase="execute", status="success")
        al.log(
            "command",
            "python app.py",
            command="python app.py",
            exit_code=1,
            stderr="Error!",
            status="failed",
        )

        al.save_to_file(directory=tmp_path)
        loaded = ActivityLogger.load_from_file("roundtrip", directory=tmp_path)

        assert loaded.entry_count == 3
        assert loaded._entries[0].command == "echo test"
        assert loaded._entries[0].stdout == "test output"
        assert loaded._entries[0].duration_seconds == 0.5
        assert loaded._entries[2].status == "failed"
        assert loaded._entries[2].stderr == "Error!"

        # Summary should match
        orig_summary = al.get_summary()
        loaded_summary = loaded.get_summary()
        assert orig_summary["total_entries"] == loaded_summary["total_entries"]
        assert orig_summary["error_count"] == loaded_summary["error_count"]

    def test_load_from_file_missing(self, tmp_path: Path):
        """load_from_file should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError, match="Activity log not found"):
            ActivityLogger.load_from_file("nonexistent", directory=tmp_path)

    def test_list_sessions(self, tmp_path: Path):
        """list_sessions should return info about all persisted logs."""
        # Create 3 log files
        for sid in ["sess-a", "sess-b", "sess-c"]:
            al = ActivityLogger(session_id=sid)
            al.log("info", f"test for {sid}", status="success")
            al.save_to_file(directory=tmp_path)

        sessions = ActivityLogger.list_sessions(directory=tmp_path)
        assert len(sessions) == 3
        ids = [s["session_id"] for s in sessions]
        assert "sess-a" in ids
        assert "sess-b" in ids
        assert "sess-c" in ids

        # Each session should have required fields
        for s in sessions:
            assert "file_path" in s
            assert "size_bytes" in s
            assert s["size_bytes"] > 0
            assert "modified" in s

    def test_list_sessions_empty_dir(self, tmp_path: Path):
        """list_sessions should return empty list for dir with no logs."""
        sessions = ActivityLogger.list_sessions(directory=tmp_path)
        assert sessions == []

    def test_list_sessions_nonexistent_dir(self):
        """list_sessions should return empty list for non-existent dir."""
        sessions = ActivityLogger.list_sessions(directory="/nonexistent/path/xyz")
        assert sessions == []

    def test_next_id_continuity_after_load(self, tmp_path: Path):
        """After loading, new log() calls should continue with correct entry_id."""
        al = ActivityLogger(session_id="id-continuity")
        al.log("command", "cmd 1")  # id=1
        al.log("command", "cmd 2")  # id=2
        al.log("command", "cmd 3")  # id=3
        al.save_to_file(directory=tmp_path)

        loaded = ActivityLogger.load_from_file("id-continuity", directory=tmp_path)
        new_entry = loaded.log("command", "cmd 4")
        assert new_entry.entry_id == 4  # Should continue from 3+1

    def test_save_empty_logger(self, tmp_path: Path):
        """Saving an empty logger should create an empty file."""
        al = ActivityLogger(session_id="empty")
        filepath = al.save_to_file(directory=tmp_path)
        assert filepath.exists()
        content = filepath.read_text(encoding="utf-8")
        assert content == ""
