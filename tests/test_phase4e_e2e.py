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
"""Phase 4E End-to-End tests — Full Messaging → Execution → Response loop.

These tests wire together:
- MessageBridge (inbound message routing)
- NotificationManager + MessagingProvider (outbound session events)
- ActivityMessagingSummary (activity streaming)
- Performance review formatting

Minimum: 10 tests (spec requirement).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from orion.ara.activity_logger import ActivityEntry, ActivityLogger, ActivityMessagingSummary
from orion.ara.message_bridge import (
    INTENT_CANCEL,
    INTENT_CORRECTION,
    INTENT_NEW_TASK,
    INTENT_REVIEW,
    INTENT_STATUS,
    InboundMessage,
    MessageBridge,
    OutboundMessage,
    format_performance_summary,
)
from orion.ara.notifications import (
    MessagingProvider,
    Notification,
    NotificationManager,
)


# =========================================================================
# Fake engines used across E2E tests
# =========================================================================


class FakeSessionEngine:
    """Minimal session engine that tracks sessions in-memory."""

    def __init__(self) -> None:
        self.sessions: dict[str, SimpleNamespace] = {}
        self._next_id = 1

    def create_session(
        self, goal: str, role: str = "", source_platform: str = "", source_user_id: str = ""
    ) -> SimpleNamespace:
        sid = f"e2e_{self._next_id:04d}"
        self._next_id += 1
        sess = SimpleNamespace(
            session_id=sid,
            goal=goal,
            role=role,
            state="running",
            status="running",
            source_platform=source_platform,
            source_user_id=source_user_id,
            progress=SimpleNamespace(completed_tasks=0, total_tasks=3),
            checkpoint_count=0,
            elapsed_seconds=0,
        )
        self.sessions[sid] = sess
        return sess

    def get_session(self, session_id: str) -> SimpleNamespace | None:
        return self.sessions.get(session_id)

    def get_status(self, session_id: str) -> SimpleNamespace | None:
        return self.sessions.get(session_id)

    def get_review(self, session_id: str) -> dict[str, Any] | None:
        sess = self.sessions.get(session_id)
        if not sess:
            return None
        return {
            "session_id": session_id,
            "state": getattr(sess, "state", "unknown"),
            "goal": getattr(sess, "goal", ""),
            "completed_tasks": getattr(sess.progress, "completed_tasks", 0),
            "total_tasks": getattr(sess.progress, "total_tasks", 0),
            "duration": "2m",
            "files_changed": 5,
        }

    def cancel_session(self, session_id: str) -> bool:
        sess = self.sessions.get(session_id)
        if sess:
            sess.state = "cancelled"
            sess.status = "cancelled"
            return True
        return False

    def inject_correction(self, session_id: str, text: str) -> None:
        sess = self.sessions.get(session_id)
        if sess:
            sess.goal = f"{sess.goal} [correction: {text}]"


class FakePerfEngine:
    """Minimal PerformanceMetrics engine returning canned data."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data

    def compute_metrics(self, session_id: str = "") -> SimpleNamespace | None:
        if not self._data:
            return SimpleNamespace(total_executions=0, to_dict=lambda: {"total_executions": 0})
        return SimpleNamespace(
            total_executions=self._data.get("total_executions", 0),
            to_dict=lambda: self._data,
        )


class RecordingMessagingProvider:
    """A fake NotificationProvider that records all sent notifications."""

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    @property
    def provider_name(self) -> str:
        return "recording"

    def send(self, notification: Notification) -> bool:
        self.sent.append(notification)
        return True


# =========================================================================
# E2E Tests
# =========================================================================


class TestE2EFullLifecycle:
    """Test 1: Complete message → session → status → correction → review → cancel flow."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        engine = FakeSessionEngine()
        nm = NotificationManager(max_per_session=20)
        recorder = RecordingMessagingProvider()
        nm.add_provider(recorder)
        perf = FakePerfEngine({
            "total_executions": 8,
            "success_rate": 0.875,
            "first_attempt_success_rate": 0.75,
            "fix_rate": 0.5,
            "mean_retries": 0.5,
            "mean_duration_seconds": 2.1,
            "mean_time_to_resolution": 3.0,
            "error_distribution": {"syntax": 1},
            "top_fixes": [],
        })
        bridge = MessageBridge(
            session_engine=engine,
            notification_manager=nm,
            performance_metrics=perf,
        )

        # 1. New task
        msg1 = InboundMessage(platform="telegram", user_id="alice", text="Build a Flask API")
        out1 = await bridge.handle_message(msg1)
        assert out1.session_id is not None
        assert "started" in out1.text.lower()
        session_id = out1.session_id

        # 2. Status query
        msg2 = InboundMessage(platform="telegram", user_id="alice", text="status")
        out2 = await bridge.handle_message(msg2)
        assert "RUNNING" in out2.text

        # 3. Correction
        msg3 = InboundMessage(platform="telegram", user_id="alice", text="use PostgreSQL instead")
        out3 = await bridge.handle_message(msg3)
        assert "correction" in out3.text.lower()

        # 4. Review
        engine.sessions[session_id].state = "completed"
        engine.sessions[session_id].status = "completed"
        msg4 = InboundMessage(platform="telegram", user_id="alice", text="review")
        out4 = await bridge.handle_message(msg4)
        assert "Session Complete" in out4.text
        assert "Performance:" in out4.text
        assert "Executions: 8" in out4.text

        # 5. Cancel (no-op since completed)
        msg5 = InboundMessage(platform="telegram", user_id="alice", text="cancel")
        out5 = await bridge.handle_message(msg5)
        # Cancellation of completed session — engine returns True (state changed)
        assert session_id[:8] in out5.text


class TestE2ENotificationFlow:
    """Test 2: Session creation triggers messaging notification wiring."""

    @pytest.mark.asyncio
    async def test_new_task_enables_messaging_notifications(self):
        engine = FakeSessionEngine()
        nm = NotificationManager(max_per_session=20)
        bridge = MessageBridge(session_engine=engine, notification_manager=nm)

        msg = InboundMessage(platform="slack", user_id="bob", text="Deploy to production")
        out = await bridge.handle_message(msg)

        assert out.session_id is not None
        # The bridge should have called enable_messaging on the NM
        mp = nm.messaging_provider
        assert mp is not None
        assert mp.platform == "slack"
        assert mp.channel == "bob"


class TestE2EActivityStreaming:
    """Test 3-4: ActivityMessagingSummary wired to ActivityLogger and NotificationManager."""

    def test_activity_summary_fires_on_phase_change(self):
        nm = NotificationManager(max_per_session=20)
        recorder = RecordingMessagingProvider()
        nm.add_provider(recorder)

        al = ActivityLogger(session_id="e2e_stream")
        summary = ActivityMessagingSummary(notification_manager=nm, batch_threshold=100)
        summary.attach(al)

        # Simulate two phases
        al.log("shell", "install deps", phase="install", status="success")
        al.log("shell", "run tests", phase="test", status="success")

        # Phase transition from install→test triggers summary of install phase
        assert len(summary.sent_summaries) >= 1
        assert summary.sent_summaries[0]["phase"] == "install"

    def test_activity_error_triggers_immediate_summary(self):
        nm = NotificationManager(max_per_session=20)
        recorder = RecordingMessagingProvider()
        nm.add_provider(recorder)

        al = ActivityLogger(session_id="e2e_err")
        summary = ActivityMessagingSummary(notification_manager=nm, batch_threshold=100)
        summary.attach(al)

        al.log("shell", "compile code", phase="build", status="success")
        al.log("shell", "compile failed", phase="build", status="failed")

        # Error should trigger immediate summary
        error_summaries = [s for s in summary.sent_summaries if s["error"]]
        assert len(error_summaries) >= 1


class TestE2EMultiplePlatforms:
    """Test 5: Different users on different platforms get independent sessions."""

    @pytest.mark.asyncio
    async def test_independent_sessions_per_platform(self):
        engine = FakeSessionEngine()
        bridge = MessageBridge(session_engine=engine)

        msg_tg = InboundMessage(platform="telegram", user_id="alice", text="Build API")
        msg_dc = InboundMessage(platform="discord", user_id="bob", text="Build CLI")

        out_tg = await bridge.handle_message(msg_tg)
        out_dc = await bridge.handle_message(msg_dc)

        assert out_tg.session_id != out_dc.session_id
        assert out_tg.platform == "telegram"
        assert out_dc.platform == "discord"

        convos = bridge.active_conversations
        assert convos["alice"] == out_tg.session_id
        assert convos["bob"] == out_dc.session_id


class TestE2EDuplicateSessionBlock:
    """Test 6: A user cannot start a second session while one is running."""

    @pytest.mark.asyncio
    async def test_block_duplicate_session(self):
        engine = FakeSessionEngine()
        bridge = MessageBridge(session_engine=engine)

        msg1 = InboundMessage(platform="telegram", user_id="alice", text="Build API")
        out1 = await bridge.handle_message(msg1)
        assert out1.session_id is not None

        msg2 = InboundMessage(platform="telegram", user_id="alice", text="Build another thing")
        out2 = await bridge.handle_message(msg2)
        assert "already have an active session" in out2.text


class TestE2EReviewWithoutPerf:
    """Test 7: Review works gracefully when no PerformanceMetrics engine is wired."""

    @pytest.mark.asyncio
    async def test_review_no_perf_engine(self):
        engine = FakeSessionEngine()
        bridge = MessageBridge(session_engine=engine)

        msg = InboundMessage(platform="telegram", user_id="alice", text="Build API")
        out = await bridge.handle_message(msg)
        sid = out.session_id
        engine.sessions[sid].state = "completed"

        msg2 = InboundMessage(platform="telegram", user_id="alice", text="review")
        out2 = await bridge.handle_message(msg2)
        assert "Session Complete" in out2.text
        assert "Performance:" not in out2.text


class TestE2ECancelAndRestart:
    """Test 8: Cancel a session, then start a new one."""

    @pytest.mark.asyncio
    async def test_cancel_then_restart(self):
        engine = FakeSessionEngine()
        bridge = MessageBridge(session_engine=engine)

        # Start
        out1 = await bridge.handle_message(
            InboundMessage(platform="slack", user_id="carol", text="Build website")
        )
        sid1 = out1.session_id
        assert sid1 is not None

        # Cancel
        out2 = await bridge.handle_message(
            InboundMessage(platform="slack", user_id="carol", text="cancel")
        )
        assert "cancelled" in out2.text.lower()
        assert "carol" not in bridge.active_conversations

        # Restart
        out3 = await bridge.handle_message(
            InboundMessage(platform="slack", user_id="carol", text="Build mobile app")
        )
        sid3 = out3.session_id
        assert sid3 is not None
        assert sid3 != sid1


class TestE2EStatusNoSession:
    """Test 9: Status query with no active session."""

    @pytest.mark.asyncio
    async def test_status_no_session(self):
        bridge = MessageBridge()
        msg = InboundMessage(platform="telegram", user_id="nobody", text="status")
        out = await bridge.handle_message(msg)
        assert "no active session" in out.text.lower()


class TestE2EPerformanceSummaryFormatting:
    """Test 10: format_performance_summary produces expected output for real-ish data."""

    def test_realistic_perf_output(self):
        perf = {
            "total_executions": 42,
            "success_rate": 0.881,
            "first_attempt_success_rate": 0.714,
            "fix_rate": 0.6,
            "mean_retries": 0.8,
            "mean_duration_seconds": 4.3,
            "mean_time_to_resolution": 7.2,
            "error_distribution": {"syntax": 3, "import": 2, "timeout": 1},
            "top_fixes": [],
        }
        text = format_performance_summary(perf)
        assert "Executions: 42" in text
        assert "Success: 88.1%" in text
        assert "First-attempt: 71.4%" in text
        assert "Fix rate: 60.0%" in text
        assert "Avg retries: 0.8" in text
        assert "Avg duration: 4.3s" in text
        assert "MTTR: 7.2s" in text
        assert "syntax (3)" in text


class TestE2ENotificationRateLimitRespected:
    """Test 11: Messaging notifications still respect the AEGIS rate limit."""

    def test_rate_limit_applies_to_messaging(self):
        nm = NotificationManager(max_per_session=3)
        recorder = RecordingMessagingProvider()
        nm.add_provider(recorder)
        nm.enable_messaging(platform="telegram", channel="test_user")

        # Send 3 notifications — should all succeed
        for i in range(3):
            assert nm.notify("session_started", {"session_id": f"s{i}", "role_name": "dev", "goal": "test"})

        # 4th should be blocked by rate limit
        result = nm.notify("session_started", {"session_id": "s3", "role_name": "dev", "goal": "test"})
        assert result is False
        assert nm.remaining == 0


class TestE2EActivityBatchThreshold:
    """Test 12: Activity summary respects batch threshold without phase change."""

    def test_batch_threshold_triggers_without_phase_change(self):
        nm = NotificationManager(max_per_session=20)
        recorder = RecordingMessagingProvider()
        nm.add_provider(recorder)

        al = ActivityLogger(session_id="e2e_batch")
        summary = ActivityMessagingSummary(notification_manager=nm, batch_threshold=3)
        summary.attach(al)

        # Log 3 entries in same phase — should trigger at threshold
        al.log("shell", "step 1", phase="build", status="success")
        al.log("shell", "step 2", phase="build", status="success")
        al.log("shell", "step 3", phase="build", status="success")

        assert len(summary.sent_summaries) >= 1
