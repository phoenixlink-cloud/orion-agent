# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA Recovery Manager (ARA-001 §C.1)."""

from __future__ import annotations

import time

import pytest

from orion.ara.recovery import RecoveryAction, RecoveryManager, RetryPolicy
from orion.ara.session import SessionState, SessionStatus


def _make_session(**kwargs) -> SessionState:
    return SessionState(
        session_id="recovery-test",
        role_name="test",
        goal="Test recovery",
        **kwargs,
    )


@pytest.fixture
def manager() -> RecoveryManager:
    return RecoveryManager(heartbeat_stale_seconds=0.1)


@pytest.fixture
def retry_policy() -> RetryPolicy:
    return RetryPolicy(max_retries=3, delay_seconds=1.0, backoff_multiplier=2.0)


class TestStaleDetection:
    def test_detects_stale_session(self, manager: RecoveryManager):
        session = _make_session()
        session.transition(SessionStatus.RUNNING)
        session.last_heartbeat = time.time() - 10
        assert manager.is_session_stale(session) is True

    def test_fresh_session_not_stale(self, manager: RecoveryManager):
        session = _make_session()
        session.transition(SessionStatus.RUNNING)
        session.last_heartbeat = time.time()
        assert manager.is_session_stale(session) is False

    def test_terminal_session_not_stale(self, manager: RecoveryManager):
        session = _make_session()
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.COMPLETED)
        session.last_heartbeat = time.time() - 10
        assert manager.is_session_stale(session) is False

    def test_paused_session_not_stale(self, manager: RecoveryManager):
        session = _make_session()
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.PAUSED)
        session.last_heartbeat = time.time() - 10
        assert manager.is_session_stale(session) is False


class TestDiagnose:
    def test_stale_with_checkpoint_resumes(self, manager: RecoveryManager):
        session = _make_session()
        session.transition(SessionStatus.RUNNING)
        session.last_heartbeat = time.time() - 10
        session.checkpoint_count = 2
        action = manager.diagnose(session)
        assert action.action == "resume"

    def test_stale_without_checkpoint_aborts(self, manager: RecoveryManager):
        session = _make_session()
        session.transition(SessionStatus.RUNNING)
        session.last_heartbeat = time.time() - 10
        action = manager.diagnose(session)
        assert action.action == "abort"

    def test_retryable_error_retries(self, manager: RecoveryManager):
        session = _make_session()
        session.transition(SessionStatus.RUNNING)
        action = manager.diagnose(session, last_error="Connection timeout")
        assert action.action == "retry"

    def test_non_retryable_with_checkpoint_rollback(self, manager: RecoveryManager):
        session = _make_session()
        session.transition(SessionStatus.RUNNING)
        session.checkpoint_count = 1
        action = manager.diagnose(session, last_error="Syntax error in generated code")
        assert action.action == "rollback"

    def test_non_retryable_without_checkpoint_aborts(self, manager: RecoveryManager):
        session = _make_session()
        session.transition(SessionStatus.RUNNING)
        action = manager.diagnose(session, last_error="Fatal crash")
        assert action.action == "abort"

    def test_no_error_no_action(self, manager: RecoveryManager):
        session = _make_session()
        session.transition(SessionStatus.RUNNING)
        action = manager.diagnose(session)
        assert action.action == "none"


class TestRetryPolicy:
    def test_is_retryable(self, retry_policy: RetryPolicy):
        assert retry_policy.is_retryable("Connection timeout") is True
        assert retry_policy.is_retryable("rate_limit exceeded") is True
        assert retry_policy.is_retryable("Temporary failure") is True
        assert retry_policy.is_retryable("Syntax error") is False

    def test_exponential_backoff(self, retry_policy: RetryPolicy):
        assert retry_policy.get_delay(0) == 1.0
        assert retry_policy.get_delay(1) == 2.0
        assert retry_policy.get_delay(2) == 4.0

    def test_default_retryable_errors(self):
        policy = RetryPolicy()
        assert policy.is_retryable("connection reset") is True
        assert policy.is_retryable("transient error") is True


class TestRetryTracking:
    def test_record_retry(self, manager: RecoveryManager):
        count = manager.record_retry("task-1")
        assert count == 1
        count = manager.record_retry("task-1")
        assert count == 2

    def test_can_retry(self, manager: RecoveryManager):
        assert manager.can_retry("task-1") is True
        for _ in range(3):
            manager.record_retry("task-1")
        assert manager.can_retry("task-1") is False

    def test_get_retry_delay(self, manager: RecoveryManager):
        delay = manager.get_retry_delay("task-1")
        assert delay >= 0

    def test_reset_retries(self, manager: RecoveryManager):
        manager.record_retry("task-1")
        manager.record_retry("task-2")
        manager.reset_retries("task-1")
        assert manager.get_retry_count("task-1") == 0
        assert manager.get_retry_count("task-2") == 1

    def test_reset_all_retries(self, manager: RecoveryManager):
        manager.record_retry("task-1")
        manager.record_retry("task-2")
        manager.reset_retries()
        assert manager.get_retry_count("task-1") == 0
        assert manager.get_retry_count("task-2") == 0


class TestRecoveryAction:
    def test_to_dict(self):
        action = RecoveryAction(
            action="retry",
            reason="Connection timeout",
            retry_count=2,
        )
        d = action.to_dict()
        assert d["action"] == "retry"
        assert d["retry_count"] == 2
