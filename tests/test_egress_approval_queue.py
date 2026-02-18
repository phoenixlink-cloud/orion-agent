# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for egress approval queue service."""

import threading
import time

import pytest

from orion.security.egress.approval_queue import (
    ApprovalQueue,
    ApprovalRequest,
    ApprovalStatus,
    RequestCategory,
)


class TestApprovalRequest:
    """Tests for ApprovalRequest data structure."""

    def test_create_request(self):
        req = ApprovalRequest(
            id="test-123",
            category=RequestCategory.NETWORK_WRITE.value,
            summary="POST to https://api.github.com/repos",
            details={"method": "POST"},
            created_at=time.time(),
            expires_at=time.time() + 300,
        )
        assert req.status == ApprovalStatus.PENDING.value
        assert req.is_expired() is False

    def test_expired_request(self):
        req = ApprovalRequest(
            id="test-123",
            category=RequestCategory.NETWORK_WRITE.value,
            summary="test",
            details={},
            created_at=time.time() - 600,
            expires_at=time.time() - 1,
        )
        assert req.is_expired() is True

    def test_decided_request_not_expired(self):
        req = ApprovalRequest(
            id="test-123",
            category=RequestCategory.NETWORK_WRITE.value,
            summary="test",
            details={},
            created_at=time.time() - 600,
            expires_at=time.time() - 1,
            status=ApprovalStatus.APPROVED.value,
        )
        # Even though time is past, decided requests aren't "expired"
        assert req.is_expired() is False

    def test_to_dict(self):
        req = ApprovalRequest(
            id="test-123",
            category="network_write",
            summary="test",
            details={"key": "value"},
            created_at=time.time(),
            expires_at=time.time() + 300,
            method="POST",
            url="https://example.com",
            hostname="example.com",
        )
        d = req.to_dict()
        assert d["id"] == "test-123"
        assert d["category"] == "network_write"
        assert d["method"] == "POST"
        assert "time_remaining_s" in d
        assert "is_expired" in d


class TestApprovalQueue:
    """Tests for the approval queue service."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a fresh approval queue for each test."""
        q = ApprovalQueue(
            default_timeout_s=10.0,
            persist_path=tmp_path / "approval_queue.json",
        )
        yield q
        q.stop()

    def test_submit_request(self, queue):
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="POST to https://api.github.com/repos",
            method="POST",
            url="https://api.github.com/repos",
            hostname="api.github.com",
        )
        assert req_id is not None
        assert len(req_id) > 0

    def test_get_pending(self, queue):
        queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Request 1",
        )
        queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Request 2",
        )
        pending = queue.get_pending()
        assert len(pending) == 2

    def test_approve_request(self, queue):
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Test request",
        )
        result = queue.approve(req_id, reason="Looks good")
        assert result is True

        req = queue.get_request(req_id)
        assert req.status == ApprovalStatus.APPROVED.value
        assert req.decided_by == "user"
        assert req.decision_reason == "Looks good"

    def test_deny_request(self, queue):
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Suspicious request",
        )
        result = queue.deny(req_id, reason="Suspicious target")
        assert result is True

        req = queue.get_request(req_id)
        assert req.status == ApprovalStatus.DENIED.value

    def test_cancel_request(self, queue):
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Cancelled request",
        )
        result = queue.cancel(req_id, reason="No longer needed")
        assert result is True

        req = queue.get_request(req_id)
        assert req.status == ApprovalStatus.CANCELLED.value

    def test_cannot_approve_twice(self, queue):
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Test",
        )
        queue.approve(req_id)
        # Second approval should fail
        result = queue.approve(req_id)
        assert result is False

    def test_cannot_deny_approved(self, queue):
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Test",
        )
        queue.approve(req_id)
        result = queue.deny(req_id)
        assert result is False

    def test_nonexistent_request_returns_false(self, queue):
        assert queue.approve("nonexistent") is False
        assert queue.deny("nonexistent") is False

    def test_approved_removed_from_pending(self, queue):
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Test",
        )
        assert len(queue.get_pending()) == 1
        queue.approve(req_id)
        assert len(queue.get_pending()) == 0

    def test_get_recent(self, queue):
        for i in range(5):
            queue.submit(
                category=RequestCategory.NETWORK_WRITE,
                summary=f"Request {i}",
            )
        recent = queue.get_recent(limit=3)
        assert len(recent) == 3

    def test_get_stats(self, queue):
        rid1 = queue.submit(category=RequestCategory.NETWORK_WRITE, summary="A")
        rid2 = queue.submit(category=RequestCategory.NETWORK_WRITE, summary="B")
        rid3 = queue.submit(category=RequestCategory.NETWORK_WRITE, summary="C")
        queue.approve(rid1)
        queue.deny(rid2)

        stats = queue.get_stats()
        assert stats["total"] == 3
        assert stats["pending"] == 1
        assert stats["approved"] == 1
        assert stats["denied"] == 1

    def test_wait_for_decision_approved(self, queue):
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Wait test",
        )

        # Approve in a separate thread after a delay
        def _approve():
            time.sleep(0.2)
            queue.approve(req_id, reason="OK")

        threading.Thread(target=_approve, daemon=True).start()

        status = queue.wait_for_decision(req_id, timeout=5.0)
        assert status == ApprovalStatus.APPROVED

    def test_wait_for_decision_denied(self, queue):
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Wait test",
        )

        def _deny():
            time.sleep(0.2)
            queue.deny(req_id, reason="No")

        threading.Thread(target=_deny, daemon=True).start()

        status = queue.wait_for_decision(req_id, timeout=5.0)
        assert status == ApprovalStatus.DENIED

    def test_wait_for_decision_timeout(self, queue):
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Timeout test",
            timeout_s=0.5,
        )
        status = queue.wait_for_decision(req_id, timeout=1.0)
        assert status in (ApprovalStatus.EXPIRED, ApprovalStatus.PENDING)

    def test_queue_capacity_limit(self, tmp_path):
        queue = ApprovalQueue(
            max_pending=3,
            persist_path=tmp_path / "q.json",
        )
        queue.submit(category=RequestCategory.NETWORK_WRITE, summary="1")
        queue.submit(category=RequestCategory.NETWORK_WRITE, summary="2")
        queue.submit(category=RequestCategory.NETWORK_WRITE, summary="3")
        with pytest.raises(RuntimeError, match="queue full"):
            queue.submit(category=RequestCategory.NETWORK_WRITE, summary="4")
        queue.stop()

    def test_capacity_freed_after_decision(self, tmp_path):
        queue = ApprovalQueue(
            max_pending=2,
            persist_path=tmp_path / "q.json",
        )
        rid1 = queue.submit(category=RequestCategory.NETWORK_WRITE, summary="1")
        queue.submit(category=RequestCategory.NETWORK_WRITE, summary="2")
        # Queue is full
        with pytest.raises(RuntimeError):
            queue.submit(category=RequestCategory.NETWORK_WRITE, summary="3")
        # Approve one, freeing a slot
        queue.approve(rid1)
        # Now should work
        queue.submit(category=RequestCategory.NETWORK_WRITE, summary="3")
        queue.stop()

    def test_callback_on_submit(self, queue):
        received = []
        queue.on_request(lambda req: received.append(req))
        queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Callback test",
        )
        assert len(received) == 1
        assert received[0].summary == "Callback test"

    def test_clear_decided(self, queue):
        rid1 = queue.submit(category=RequestCategory.NETWORK_WRITE, summary="A")
        rid2 = queue.submit(category=RequestCategory.NETWORK_WRITE, summary="B")
        queue.approve(rid1)
        queue.deny(rid2)

        removed = queue.clear_decided(older_than_s=0)
        assert removed == 2
        assert queue.get_stats()["total"] == 0

    def test_persistence(self, tmp_path):
        persist_path = tmp_path / "q.json"
        queue1 = ApprovalQueue(persist_path=persist_path)
        rid = queue1.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Persistent",
            method="POST",
            url="https://example.com",
        )
        queue1.approve(rid)
        queue1.stop()

        # Verify the file exists and contains data
        assert persist_path.exists()
        import json
        data = json.loads(persist_path.read_text())
        assert len(data) >= 1
        assert data[0]["summary"] == "Persistent"

    def test_body_preview_truncated(self, queue):
        long_body = "x" * 1000
        req_id = queue.submit(
            category=RequestCategory.NETWORK_WRITE,
            summary="Long body",
            body_preview=long_body,
        )
        req = queue.get_request(req_id)
        assert len(req.body_preview) <= 500

    def test_all_categories(self, queue):
        for cat in RequestCategory:
            req_id = queue.submit(
                category=cat,
                summary=f"Test {cat.value}",
            )
            req = queue.get_request(req_id)
            assert req.category == cat.value


class TestApprovalStatus:
    """Tests for the ApprovalStatus enum."""

    def test_all_statuses(self):
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.DENIED.value == "denied"
        assert ApprovalStatus.EXPIRED.value == "expired"
        assert ApprovalStatus.CANCELLED.value == "cancelled"

    def test_string_conversion(self):
        assert str(ApprovalStatus.PENDING) == "ApprovalStatus.PENDING"
        assert ApprovalStatus("pending") == ApprovalStatus.PENDING
