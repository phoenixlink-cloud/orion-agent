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
"""Unit tests for Phase 4E.1 — MessageBridge + InboundMessage/OutboundMessage.

Minimum 15 tests covering:
  1. InboundMessage / OutboundMessage dataclass construction
  2. Intent classification (new_task, correction, status, cancel, review, unknown)
  3. handle_message routing for each intent
  4. Active conversation tracking
  5. Session creation via engine
  6. Correction injection
  7. Cancel flow
  8. Status formatting
  9. Review formatting
 10. API endpoint shape
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from orion.ara.message_bridge import (
    INTENT_CANCEL,
    INTENT_CORRECTION,
    INTENT_NEW_TASK,
    INTENT_REVIEW,
    INTENT_STATUS,
    INTENT_UNKNOWN,
    InboundMessage,
    MessageBridge,
    OutboundMessage,
)


# =========================================================================
# Helpers
# =========================================================================


def _make_msg(text: str, platform: str = "telegram", user_id: str = "u1") -> InboundMessage:
    return InboundMessage(platform=platform, user_id=user_id, text=text)


def _make_engine(session_id: str = "sess1234abcd") -> MagicMock:
    """Return a mock session engine that supports create/get_status/cancel."""
    engine = MagicMock()
    engine.create_session = MagicMock(return_value=MagicMock(session_id=session_id))
    status_obj = MagicMock()
    status_obj.status = "running"
    status_obj.state = "running"
    status_obj.progress = MagicMock(completed_tasks=3, total_tasks=10)
    status_obj.checkpoint_count = 2
    status_obj.elapsed_seconds = 180
    engine.get_status = MagicMock(return_value=status_obj)
    engine.cancel_session = MagicMock(return_value=True)
    engine.inject_correction = MagicMock(return_value=None)
    engine.get_review = MagicMock(return_value={
        "state": "completed",
        "goal": "Build a Flask API",
        "completed_tasks": 10,
        "total_tasks": 10,
        "duration": "3m",
        "files_changed": 5,
    })
    return engine


# =========================================================================
# 1. Dataclass construction
# =========================================================================


class TestDataclasses:
    def test_inbound_message_defaults(self):
        msg = InboundMessage(platform="slack", user_id="u1", text="hello")
        assert msg.platform == "slack"
        assert msg.user_id == "u1"
        assert msg.text == "hello"
        assert msg.thread_id is None
        assert msg.reply_to is None
        assert msg.metadata == {}

    def test_outbound_message_defaults(self):
        out = OutboundMessage(text="hi", platform="discord", recipient_id="u2")
        assert out.text == "hi"
        assert out.session_id is None
        assert out.thread_id is None
        assert out.metadata == {}


# =========================================================================
# 2. Intent classification
# =========================================================================


class TestIntentClassification:
    def test_empty_text_is_unknown(self):
        bridge = MessageBridge()
        assert bridge.classify_intent(_make_msg("")) == INTENT_UNKNOWN
        assert bridge.classify_intent(_make_msg("   ")) == INTENT_UNKNOWN

    def test_cancel_keywords(self):
        bridge = MessageBridge()
        for word in ("stop", "cancel", "abort", "quit", "halt"):
            assert bridge.classify_intent(_make_msg(word)) == INTENT_CANCEL

    def test_status_keywords(self):
        bridge = MessageBridge()
        for word in ("status", "progress", "update"):
            assert bridge.classify_intent(_make_msg(word)) == INTENT_STATUS

    def test_status_prefix(self):
        bridge = MessageBridge()
        assert bridge.classify_intent(_make_msg("status of my task")) == INTENT_STATUS
        assert bridge.classify_intent(_make_msg("progress report")) == INTENT_STATUS

    def test_review_keywords(self):
        bridge = MessageBridge()
        for word in ("review", "results", "show me"):
            assert bridge.classify_intent(_make_msg(word)) == INTENT_REVIEW

    def test_review_prefix(self):
        bridge = MessageBridge()
        assert bridge.classify_intent(_make_msg("show the results")) == INTENT_REVIEW

    def test_correction_needs_active_session(self):
        bridge = MessageBridge()
        # No active session — correction prefix should fall through to new_task
        assert bridge.classify_intent(_make_msg("use PostgreSQL instead")) == INTENT_NEW_TASK

        # With active session
        bridge._active_conversations["u1"] = "sess1"
        assert bridge.classify_intent(_make_msg("use PostgreSQL instead")) == INTENT_CORRECTION
        assert bridge.classify_intent(_make_msg("actually, use FastAPI")) == INTENT_CORRECTION

    def test_default_is_new_task(self):
        bridge = MessageBridge()
        assert bridge.classify_intent(_make_msg("Build a Flask API with auth")) == INTENT_NEW_TASK
        assert bridge.classify_intent(_make_msg("Create a todo app")) == INTENT_NEW_TASK


# =========================================================================
# 3. handle_message routing
# =========================================================================


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_new_task_no_engine(self):
        """Without a session engine, new task should return failure message."""
        bridge = MessageBridge()
        out = await bridge.handle_message(_make_msg("Build a Flask API"))
        assert "Failed to create session" in out.text
        assert out.platform == "telegram"
        assert out.recipient_id == "u1"

    @pytest.mark.asyncio
    async def test_new_task_with_engine(self):
        """With a session engine, new task should create session and track it."""
        engine = _make_engine()
        bridge = MessageBridge(session_engine=engine)
        out = await bridge.handle_message(_make_msg("Build a Flask API"))
        assert "started" in out.text.lower() or "Task received" in out.text
        assert out.session_id is not None
        assert "u1" in bridge.active_conversations

    @pytest.mark.asyncio
    async def test_status_query_no_session(self):
        bridge = MessageBridge()
        out = await bridge.handle_message(_make_msg("status"))
        assert "No active session" in out.text

    @pytest.mark.asyncio
    async def test_status_query_with_session(self):
        engine = _make_engine()
        bridge = MessageBridge(session_engine=engine)
        bridge._active_conversations["u1"] = "sess1234abcd"
        out = await bridge.handle_message(_make_msg("status"))
        assert "RUNNING" in out.text
        assert "3/10" in out.text

    @pytest.mark.asyncio
    async def test_cancel_no_session(self):
        bridge = MessageBridge()
        out = await bridge.handle_message(_make_msg("cancel"))
        assert "No active session" in out.text

    @pytest.mark.asyncio
    async def test_cancel_with_session(self):
        engine = _make_engine()
        bridge = MessageBridge(session_engine=engine)
        bridge._active_conversations["u1"] = "sess1234abcd"
        out = await bridge.handle_message(_make_msg("cancel"))
        assert "cancelled" in out.text.lower()
        assert "u1" not in bridge.active_conversations

    @pytest.mark.asyncio
    async def test_correction_with_session(self):
        engine = _make_engine()
        bridge = MessageBridge(session_engine=engine)
        bridge._active_conversations["u1"] = "sess1234abcd"
        out = await bridge.handle_message(_make_msg("use PostgreSQL instead"))
        assert "Correction received" in out.text
        engine.inject_correction.assert_called_once()

    @pytest.mark.asyncio
    async def test_review_with_session(self):
        engine = _make_engine()
        bridge = MessageBridge(session_engine=engine)
        bridge._active_conversations["u1"] = "sess1234abcd"
        out = await bridge.handle_message(_make_msg("review"))
        assert "Complete" in out.text or "Goal" in out.text

    @pytest.mark.asyncio
    async def test_unknown_intent(self):
        bridge = MessageBridge()
        out = await bridge.handle_message(_make_msg(""))
        assert "not sure" in out.text.lower()

    @pytest.mark.asyncio
    async def test_active_session_blocks_new_task(self):
        """If user already has a running session, new task should be rejected."""
        engine = _make_engine()
        bridge = MessageBridge(session_engine=engine)
        bridge._active_conversations["u1"] = "existing_sess"
        out = await bridge.handle_message(_make_msg("Build something else"))
        assert "already have an active session" in out.text


# =========================================================================
# 4. Formatting
# =========================================================================


class TestFormatting:
    def test_format_status_running(self):
        status = MagicMock()
        status.state = "running"
        status.progress = MagicMock(completed_tasks=5, total_tasks=10)
        status.checkpoint_count = 3
        status.elapsed_seconds = 300
        text = MessageBridge._format_status_for_messaging(status)
        assert "RUNNING" in text
        assert "5/10" in text
        assert "5m" in text

    def test_format_review_completed(self):
        review = {
            "state": "completed",
            "goal": "Build API",
            "completed_tasks": 10,
            "total_tasks": 10,
            "duration": "3m",
            "files_changed": 5,
        }
        text = MessageBridge._format_review_for_messaging(review)
        assert "Complete" in text
        assert "Build API" in text
        assert "10/10" in text
        assert "5" in text

    def test_format_review_none(self):
        text = MessageBridge._format_review_for_messaging(None)
        assert "No review data" in text
