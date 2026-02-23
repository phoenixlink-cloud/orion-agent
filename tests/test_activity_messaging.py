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
"""Unit tests for Phase 4E.3 — Activity Log Streaming to Messaging.

Minimum 8 tests covering:
  1. ActivityMessagingSummary construction
  2. attach / detach on ActivityLogger
  3. Phase-change triggers summary
  4. Error triggers immediate summary
  5. Batch threshold triggers summary
  6. _summarize_phase formatting
  7. _send_summary with notification manager
  8. Multiple phase transitions accumulate sent_summaries
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orion.ara.activity_logger import (
    ActivityEntry,
    ActivityLogger,
    ActivityMessagingSummary,
)

# =========================================================================
# Helpers
# =========================================================================


def _entry(
    phase: str = "execute", status: str = "running", desc: str = "cmd", dur: float | None = None
) -> ActivityEntry:
    return ActivityEntry(
        session_id="s1",
        action_type="command",
        description=desc,
        phase=phase,
        status=status,
        duration_seconds=dur,
    )


# =========================================================================
# 1. Construction
# =========================================================================


class TestActivityMessagingSummaryConstruction:
    def test_defaults(self):
        ams = ActivityMessagingSummary()
        assert ams.pending_count == 0
        assert ams.sent_summaries == []

    def test_custom_params(self):
        nm = MagicMock()
        ams = ActivityMessagingSummary(
            notification_manager=nm, platform="slack", channel="C1", batch_threshold=5
        )
        assert ams._notification_manager is nm
        assert ams._platform == "slack"
        assert ams._channel == "C1"
        assert ams._batch_threshold == 5


# =========================================================================
# 2. Attach / Detach
# =========================================================================


class TestAttachDetach:
    def test_attach_registers_callback(self):
        al = ActivityLogger(session_id="s1")
        ams = ActivityMessagingSummary()
        ams.attach(al)
        assert ams.on_activity in al._callbacks

    def test_detach_removes_callback(self):
        al = ActivityLogger(session_id="s1")
        ams = ActivityMessagingSummary()
        ams.attach(al)
        assert len(al._callbacks) == 1
        ams.detach(al)
        assert len(al._callbacks) == 0
        assert ams._bound_callback is None


# =========================================================================
# 3. Phase-change triggers summary
# =========================================================================


class TestPhaseChangeTrigger:
    def test_phase_transition_sends_summary(self):
        ams = ActivityMessagingSummary()

        # Phase 1: install
        ams.on_activity(_entry(phase="install", status="success"))
        ams.on_activity(_entry(phase="install", status="success"))
        assert len(ams.sent_summaries) == 0  # no phase change yet

        # Phase 2: execute — triggers summary for "install"
        ams.on_activity(_entry(phase="execute", status="running"))
        assert len(ams.sent_summaries) == 1
        assert ams.sent_summaries[0]["phase"] == "install"
        assert ams.sent_summaries[0]["entry_count"] == 2

    def test_multiple_phase_transitions(self):
        ams = ActivityMessagingSummary()
        ams.on_activity(_entry(phase="install"))
        ams.on_activity(_entry(phase="execute"))  # triggers install summary
        ams.on_activity(_entry(phase="test"))  # triggers execute summary
        assert len(ams.sent_summaries) == 2
        assert ams.sent_summaries[0]["phase"] == "install"
        assert ams.sent_summaries[1]["phase"] == "execute"


# =========================================================================
# 4. Error triggers immediate summary
# =========================================================================


class TestErrorTrigger:
    def test_error_sends_immediately(self):
        ams = ActivityMessagingSummary()
        ams.on_activity(_entry(phase="execute", status="running"))
        ams.on_activity(_entry(phase="execute", status="failed", desc="pip install failed"))

        assert len(ams.sent_summaries) == 1
        assert ams.sent_summaries[0]["error"] is True
        assert "pip install failed" in ams.sent_summaries[0]["text"]
        assert ams.pending_count == 0  # pending cleared after error


# =========================================================================
# 5. Batch threshold triggers summary
# =========================================================================


class TestBatchThreshold:
    def test_batch_threshold_triggers(self):
        ams = ActivityMessagingSummary(batch_threshold=3)
        ams.on_activity(_entry(phase="execute"))
        ams.on_activity(_entry(phase="execute"))
        assert len(ams.sent_summaries) == 0
        ams.on_activity(_entry(phase="execute"))  # hits threshold
        assert len(ams.sent_summaries) == 1
        assert ams.sent_summaries[0]["entry_count"] == 3
        assert ams.pending_count == 0


# =========================================================================
# 6. _summarize_phase formatting
# =========================================================================


class TestSummarizePhase:
    def test_empty_entries(self):
        text = ActivityMessagingSummary._summarize_phase("install", [])
        assert "no entries" in text.lower()

    def test_normal_summary(self):
        entries = [
            _entry(status="success", dur=1.5),
            _entry(status="success", dur=0.5),
            _entry(status="running"),
        ]
        text = ActivityMessagingSummary._summarize_phase("execute", entries)
        assert "Phase: execute" in text
        assert "3" in text  # total actions
        assert "2 ok" in text
        assert "2.0s" in text

    def test_error_summary_shows_last_error(self):
        entries = [
            _entry(status="success"),
            _entry(status="failed", desc="connection timeout"),
        ]
        text = ActivityMessagingSummary._summarize_phase("install", entries, error=True)
        assert "Error in phase: install" in text
        assert "connection timeout" in text


# =========================================================================
# 7. _send_summary with notification manager
# =========================================================================


class TestSendSummaryWithNM:
    def test_send_via_notification_manager(self):
        nm = MagicMock()
        nm.notify = MagicMock(return_value=True)
        ams = ActivityMessagingSummary(notification_manager=nm)

        entries = [_entry(phase="install", status="success")]
        ams._send_summary("install", entries)

        nm.notify.assert_called_once()
        assert ams.sent_summaries[-1]["sent"] is True


# =========================================================================
# 8. Integration with ActivityLogger
# =========================================================================


class TestIntegrationWithLogger:
    def test_logger_fires_summary_on_phase_change(self):
        al = ActivityLogger(session_id="s1")
        ams = ActivityMessagingSummary()
        ams.attach(al)

        al.log("command", "pip install", phase="install", status="success")
        al.log("command", "python app.py", phase="execute", status="running")

        assert len(ams.sent_summaries) == 1
        assert ams.sent_summaries[0]["phase"] == "install"
