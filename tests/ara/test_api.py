# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for ARA API — REST + WebSocket (ARA-001 §13 / Appendix C.12)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from orion.ara.api import APIResponse, ARARouter, WSChannel, WSMessage
from orion.ara.daemon import DaemonControl, DaemonStatus
from orion.ara.feedback_store import FeedbackStore, SessionOutcome, TaskOutcome
from orion.ara.role_profile import RoleProfile, save_role


@pytest.fixture
def control(tmp_path: Path) -> DaemonControl:
    return DaemonControl(state_dir=tmp_path / "daemon")


@pytest.fixture
def feedback(tmp_path: Path) -> FeedbackStore:
    return FeedbackStore(store_dir=tmp_path / "feedback")


@pytest.fixture
def roles_dir(tmp_path: Path) -> Path:
    d = tmp_path / "roles"
    d.mkdir()
    save_role(RoleProfile(name="api-test", scope="coding"), d / "api-test.yaml")
    return d


@pytest.fixture
def router(control: DaemonControl, feedback: FeedbackStore) -> ARARouter:
    return ARARouter(control=control, feedback_store=feedback)


class TestAPIResponse:
    def test_ok(self):
        r = APIResponse(status=200, data={"key": "val"})
        assert r.ok is True

    def test_not_ok(self):
        r = APIResponse(status=404, error="not found")
        assert r.ok is False

    def test_to_json(self):
        r = APIResponse(status=200, data={"x": 1})
        parsed = json.loads(r.to_json())
        assert parsed["status"] == 200
        assert parsed["data"]["x"] == 1

    def test_error_in_dict(self):
        r = APIResponse(status=500, error="boom")
        d = r.to_dict()
        assert d["error"] == "boom"
        assert "data" not in d


class TestWSMessage:
    def test_to_json(self):
        m = WSMessage(event="session_update", data={"status": "running"})
        parsed = json.loads(m.to_json())
        assert parsed["event"] == "session_update"

    def test_from_json(self):
        raw = json.dumps({"event": "task_complete", "data": {"id": "t1"}, "timestamp": 1000})
        m = WSMessage.from_json(raw)
        assert m.event == "task_complete"
        assert m.data["id"] == "t1"


class TestARARouterStatus:
    def test_get_status_no_session(self, router: ARARouter):
        resp = router.handle("GET", "/api/ara/status")
        assert resp.ok is True

    def test_get_status_with_session(self, router: ARARouter, control: DaemonControl):
        control.write_pid(os.getpid())
        control.write_status(
            DaemonStatus(
                running=True,
                session_id="s1",
                session_status="running",
                tasks_completed=3,
                tasks_total=10,
            )
        )
        resp = router.handle("GET", "/api/ara/status")
        assert resp.ok is True
        assert resp.data["session_id"] == "s1"


class TestARARouterWork:
    def test_post_work_missing_params(self, router: ARARouter):
        resp = router.handle("POST", "/api/ara/work", body={})
        assert resp.status == 400

    def test_post_work_unknown_role(self, router: ARARouter):
        resp = router.handle(
            "POST",
            "/api/ara/work",
            body={
                "role_name": "nonexistent",
                "goal": "test",
            },
        )
        assert resp.status == 409


class TestARARouterControl:
    def test_pause_no_daemon(self, router: ARARouter):
        resp = router.handle("POST", "/api/ara/pause")
        assert resp.status == 409

    def test_resume_no_daemon(self, router: ARARouter):
        resp = router.handle("POST", "/api/ara/resume")
        assert resp.status == 409

    def test_cancel_no_daemon(self, router: ARARouter):
        resp = router.handle("POST", "/api/ara/cancel")
        assert resp.status == 409

    def test_pause_running(self, router: ARARouter, control: DaemonControl):
        control.write_pid(os.getpid())
        control.write_status(
            DaemonStatus(
                running=True,
                session_id="s1",
                session_status="running",
            )
        )
        resp = router.handle("POST", "/api/ara/pause")
        assert resp.ok is True

    def test_cancel_running(self, router: ARARouter, control: DaemonControl):
        control.write_pid(os.getpid())
        control.write_status(
            DaemonStatus(
                running=True,
                session_id="s1",
                session_status="running",
            )
        )
        resp = router.handle("POST", "/api/ara/cancel")
        assert resp.ok is True


class TestARARouterFeedback:
    def test_get_stats_empty(self, router: ARARouter):
        resp = router.handle("GET", "/api/ara/feedback/stats")
        assert resp.ok is True
        assert resp.data["stats"] == []

    def test_get_stats_with_data(self, router: ARARouter, feedback: FeedbackStore):
        feedback.record_task(
            TaskOutcome(
                task_id="t1",
                session_id="s1",
                action_type="write_files",
                success=True,
                confidence=0.9,
            )
        )
        resp = router.handle("GET", "/api/ara/feedback/stats")
        assert resp.ok is True
        assert len(resp.data["stats"]) == 1

    def test_get_sessions(self, router: ARARouter, feedback: FeedbackStore):
        feedback.record_session(
            SessionOutcome(
                session_id="s1",
                role_name="coder",
                goal="build",
                status="completed",
            )
        )
        resp = router.handle("GET", "/api/ara/feedback/sessions")
        assert resp.ok is True
        assert len(resp.data["sessions"]) == 1

    def test_post_feedback(self, router: ARARouter, feedback: FeedbackStore):
        feedback.record_session(
            SessionOutcome(
                session_id="s1",
                role_name="coder",
                goal="build",
                status="completed",
            )
        )
        resp = router.handle(
            "POST",
            "/api/ara/feedback",
            body={
                "session_id": "s1",
                "rating": 4,
                "comment": "Nice",
            },
        )
        assert resp.ok is True

    def test_post_feedback_invalid_rating(self, router: ARARouter):
        resp = router.handle(
            "POST",
            "/api/ara/feedback",
            body={
                "session_id": "s1",
                "rating": 0,
            },
        )
        assert resp.status == 400

    def test_post_feedback_missing_session(self, router: ARARouter, feedback: FeedbackStore):
        resp = router.handle(
            "POST",
            "/api/ara/feedback",
            body={
                "session_id": "nonexistent",
                "rating": 3,
            },
        )
        assert resp.status == 404

    def test_no_feedback_store(self, control: DaemonControl):
        router = ARARouter(control=control, feedback_store=None)
        resp = router.handle("GET", "/api/ara/feedback/stats")
        assert resp.status == 503


class TestARARouterRouting:
    def test_unknown_route(self, router: ARARouter):
        resp = router.handle("GET", "/api/ara/unknown")
        assert resp.status == 404

    def test_routes_property(self, router: ARARouter):
        routes = router.routes
        assert "GET /api/ara/status" in routes
        assert "POST /api/ara/work" in routes


class TestWSChannel:
    def test_subscribe_and_broadcast(self):
        ch = WSChannel()
        received = []
        ch.subscribe(lambda msg: received.append(msg))
        count = ch.broadcast("test_event", {"key": "val"})
        assert count == 1
        assert len(received) == 1
        parsed = json.loads(received[0])
        assert parsed["event"] == "test_event"

    def test_unsubscribe(self):
        ch = WSChannel()
        received = []

        def cb(msg):
            received.append(msg)

        ch.subscribe(cb)
        ch.unsubscribe(cb)
        ch.broadcast("test")
        assert len(received) == 0

    def test_subscriber_count(self):
        ch = WSChannel()
        assert ch.subscriber_count == 0

        def cb(msg):
            pass

        ch.subscribe(cb)
        assert ch.subscriber_count == 1

    def test_event_log(self):
        ch = WSChannel()
        ch.broadcast("e1")
        ch.broadcast("e2")
        assert len(ch.event_log) == 2
        assert ch.event_log[0].event == "e1"

    def test_emit_helpers(self):
        ch = WSChannel()
        received = []
        ch.subscribe(lambda msg: received.append(json.loads(msg)))

        ch.emit_session_update({"status": "running"})
        ch.emit_task_complete({"id": "t1"})
        ch.emit_checkpoint({"number": 1})
        ch.emit_error({"message": "oops"})

        assert len(received) == 4
        assert received[0]["event"] == "session_update"
        assert received[1]["event"] == "task_complete"
        assert received[2]["event"] == "checkpoint"
        assert received[3]["event"] == "error"

    def test_broadcast_handles_failing_subscriber(self):
        ch = WSChannel()
        ch.subscribe(lambda msg: (_ for _ in ()).throw(RuntimeError("boom")))
        ch.subscribe(lambda msg: None)
        count = ch.broadcast("test")
        # Second subscriber still gets it
        assert count == 1

    def test_event_log_capped(self):
        ch = WSChannel()
        ch._max_log = 5
        for i in range(10):
            ch.broadcast(f"e{i}")
        assert len(ch.event_log) == 5
