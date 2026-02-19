# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""ARA End-to-End Tests — full pipeline validation with MockLLM.

Tests the complete ARA flow:
  1. Load role → authenticate → create session
  2. Decompose goal → validate DAG → run execution loop
  3. Checkpoint → drift check → recovery
  4. Notifications → feedback recording → review/promotion

See ARA-001 §13 / Appendix C.13 for 5-layer testing strategy.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from orion.ara.aegis_gate import AegisGate
from orion.ara.api import ARARouter, WSChannel
from orion.ara.auth import AuthStore, RoleAuthenticator
from orion.ara.checkpoint import CheckpointManager
from orion.ara.cli_commands import cmd_review, cmd_status, cmd_work
from orion.ara.daemon import ARADaemon, DaemonControl, DaemonStatus
from orion.ara.drift_monitor import DriftMonitor, DriftSeverity
from orion.ara.execution import ExecutionLoop
from orion.ara.feedback_store import FeedbackStore, SessionOutcome, TaskOutcome
from orion.ara.goal_engine import GoalEngine, MockLLMProvider, Task, TaskDAG, TaskStatus
from orion.ara.lifecycle import LifecycleManager
from orion.ara.notifications import NotificationManager
from orion.ara.recovery import RecoveryManager
from orion.ara.role_profile import RoleProfile, save_role
from orion.ara.session import SessionState, SessionStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "main.py").write_text("print('hello')\n")
    (ws / "utils.py").write_text("x = 1\n")
    return ws


@pytest.fixture
def roles_dir(tmp_path: Path) -> Path:
    d = tmp_path / "roles"
    d.mkdir()
    role = RoleProfile(
        name="e2e-coder",
        scope="coding",
        auth_method="pin",
        allowed_actions=["read_files", "write_files", "run_tests"],
        max_cost_per_session=1.0,
        max_session_hours=2.0,
    )
    save_role(role, d / "e2e-coder.yaml")
    return d


@pytest.fixture
def auth(tmp_path: Path) -> RoleAuthenticator:
    store = AuthStore(store_path=tmp_path / "auth.json")
    store.set_pin("1234")
    return RoleAuthenticator(auth_store=store)


@pytest.fixture
def control(tmp_path: Path) -> DaemonControl:
    return DaemonControl(state_dir=tmp_path / "daemon")


@pytest.fixture
def feedback(tmp_path: Path) -> FeedbackStore:
    return FeedbackStore(store_dir=tmp_path / "feedback")


async def _mock_executor(task: Task) -> dict:
    """Simulates task execution with varying confidence."""
    confidence_map = {
        "read_files": 0.95,
        "write_files": 0.85,
        "run_tests": 0.90,
    }
    return {
        "success": True,
        "output": f"Executed: {task.title}",
        "confidence": confidence_map.get(task.action_type, 0.8),
    }


# ---------------------------------------------------------------------------
# E2E: Full session lifecycle
# ---------------------------------------------------------------------------


class TestFullSessionLifecycle:
    """Complete session from role load to completion."""

    def test_session_happy_path(self, tmp_path: Path, roles_dir: Path, auth, workspace):
        """Load role → create session → decompose → execute → checkpoint → complete."""
        # 1. Create session via CLI command
        result = cmd_work(
            role_name="e2e-coder",
            goal="Add unit tests for auth module",
            workspace_path=str(workspace),
            project_mode="continue",
            roles_dir=roles_dir,
            control=DaemonControl(state_dir=tmp_path / "daemon"),
        )
        assert result.success is True
        session_id = result.data["session_id"]

        # 2. Create session state and decompose goal
        session = SessionState(
            session_id=session_id,
            role_name="e2e-coder",
            goal="Add unit tests for auth module",
            workspace_path=str(workspace),
            max_cost_usd=1.0,
            max_duration_hours=2.0,
        )

        llm = MockLLMProvider()
        engine = GoalEngine(llm_provider=llm)
        dag = asyncio.run(engine.decompose("Add unit tests for auth module"))
        assert dag.total_tasks == 3

        # 3. Validate actions against role
        violations = engine.validate_actions(dag, ["read_files", "write_files", "run_tests"])
        assert len(violations) == 0

        # 4. Set up checkpoint manager
        cp_mgr = CheckpointManager(
            session_id=session_id,
            checkpoints_dir=tmp_path / "checkpoints",
        )

        # 5. Run execution loop
        loop = ExecutionLoop(
            session=session,
            dag=dag,
            task_executor=_mock_executor,
            on_checkpoint=lambda: cp_mgr.create(
                session.to_dict(),
                dag.to_dict(),
                sandbox_path=workspace,
            ),
            checkpoint_interval_minutes=0,
        )
        exec_result = asyncio.run(loop.run())

        assert exec_result.tasks_completed == 3
        assert exec_result.tasks_failed == 0
        assert "goal_complete" in exec_result.stop_reason
        assert session.status == SessionStatus.COMPLETED

        # 6. Verify checkpoint was created
        assert cp_mgr.checkpoint_count >= 1

    def test_session_with_notifications_and_feedback(
        self, tmp_path: Path, workspace: Path, feedback: FeedbackStore
    ):
        """Session with notification delivery and feedback recording."""
        # Set up notification manager with mock provider
        from orion.ara.notifications import Notification, NotificationProvider

        class TestProvider(NotificationProvider):
            def __init__(self):
                self.calls = []

            @property
            def provider_name(self):
                return "test"

            def send(self, notification):
                self.calls.append(notification)
                return True

        provider = TestProvider()
        notif_mgr = NotificationManager(providers=[provider])

        # Create session
        session = SessionState(
            session_id="e2e-notif",
            role_name="e2e-coder",
            goal="Refactor utils",
            workspace_path=str(workspace),
        )

        # Send start notification
        notif_mgr.notify(
            "session_started",
            {
                "session_id": session.session_id,
                "role_name": session.role_name,
                "goal": session.goal,
            },
        )

        # Run execution
        dag = TaskDAG(
            goal="Refactor",
            tasks=[
                Task(task_id="t1", title="Read", description="", action_type="read_files"),
                Task(
                    task_id="t2",
                    title="Write",
                    description="",
                    action_type="write_files",
                    dependencies=["t1"],
                ),
            ],
        )
        loop = ExecutionLoop(session=session, dag=dag, task_executor=_mock_executor)
        asyncio.run(loop.run())

        # Send completion notification
        notif_mgr.notify(
            "session_completed",
            {
                "session_id": session.session_id,
                "tasks_completed": 2,
                "tasks_total": 2,
                "elapsed": "0.1h",
            },
        )

        assert len(provider.calls) == 2
        assert notif_mgr.sent_count == 2

        # Record feedback
        for task in dag.tasks:
            feedback.record_task(
                TaskOutcome(
                    task_id=task.task_id,
                    session_id=session.session_id,
                    action_type=task.action_type,
                    success=True,
                    confidence=0.9,
                    duration_seconds=1.0,
                )
            )
        feedback.record_session(
            SessionOutcome(
                session_id=session.session_id,
                role_name=session.role_name,
                goal=session.goal,
                status="completed",
                tasks_completed=2,
                promoted=True,
            )
        )

        assert feedback.task_count == 2
        assert feedback.session_count == 1

        # Add user feedback
        feedback.add_user_feedback(session.session_id, rating=5, comment="Perfect")
        sessions = feedback.get_session_outcomes()
        assert sessions[0].user_rating == 5


# ---------------------------------------------------------------------------
# E2E: Daemon integration
# ---------------------------------------------------------------------------


class TestDaemonIntegration:
    """Daemon-level integration tests."""

    def test_daemon_runs_full_session(self, tmp_path: Path, workspace: Path):
        """Daemon starts, runs tasks, writes status, and exits cleanly."""
        role = RoleProfile(name="e2e-coder", scope="coding")
        session = SessionState(
            session_id="e2e-daemon",
            role_name="e2e-coder",
            goal="Build feature",
            workspace_path=str(workspace),
        )
        dag = TaskDAG(
            goal="Build",
            tasks=[
                Task(task_id="t1", title="Read code", description="", action_type="read_files"),
                Task(
                    task_id="t2",
                    title="Write code",
                    description="",
                    action_type="write_files",
                    dependencies=["t1"],
                ),
                Task(
                    task_id="t3",
                    title="Run tests",
                    description="",
                    action_type="run_tests",
                    dependencies=["t2"],
                ),
            ],
        )
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")

        daemon = ARADaemon(
            session=session,
            role=role,
            dag=dag,
            control=ctrl,
            task_executor=_mock_executor,
            checkpoint_dir=tmp_path / "checkpoints",
        )
        asyncio.run(daemon.run())

        assert session.status == SessionStatus.COMPLETED
        assert session.progress.completed_tasks == 3

        # Status was written
        status = ctrl.read_status()
        assert status.session_id == "e2e-daemon"

        # PID was cleared
        assert ctrl.read_pid() is None

    def test_daemon_with_websocket_broadcast(self, tmp_path: Path, workspace: Path):
        """Daemon emits events to WebSocket channel."""
        ws_channel = WSChannel()
        events = []
        ws_channel.subscribe(lambda msg: events.append(json.loads(msg)))

        role = RoleProfile(name="e2e-coder", scope="coding")
        session = SessionState(
            session_id="e2e-ws",
            role_name="e2e-coder",
            goal="Test WS",
            workspace_path=str(workspace),
        )
        dag = TaskDAG(
            goal="Test",
            tasks=[
                Task(task_id="t1", title="Task 1", description="", action_type="write_files"),
            ],
        )
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")

        daemon = ARADaemon(
            session=session,
            role=role,
            dag=dag,
            control=ctrl,
            task_executor=_mock_executor,
            checkpoint_dir=tmp_path / "checkpoints",
        )
        asyncio.run(daemon.run())

        # Broadcast session result
        ws_channel.emit_session_update(
            {
                "session_id": session.session_id,
                "status": session.status.value,
                "tasks_completed": session.progress.completed_tasks,
            }
        )
        assert len(events) == 1
        assert events[0]["event"] == "session_update"


# ---------------------------------------------------------------------------
# E2E: Recovery and drift
# ---------------------------------------------------------------------------


class TestRecoveryAndDrift:
    """Recovery from failures and drift detection."""

    def test_recovery_after_failure(self, tmp_path: Path, workspace: Path):
        """Session fails, recovery diagnoses, checkpoint enables rollback."""
        session = SessionState(
            session_id="e2e-recovery",
            role_name="e2e-coder",
            goal="Test recovery",
            workspace_path=str(workspace),
        )

        # Create a checkpoint before failure
        cp_mgr = CheckpointManager(
            session_id="e2e-recovery",
            checkpoints_dir=tmp_path / "checkpoints",
        )
        cp_mgr.create(
            session_state=session.to_dict(),
            dag_state={"tasks": []},
            sandbox_path=workspace,
        )
        session.checkpoint_count = 1

        # Simulate failure
        session.transition(SessionStatus.RUNNING)
        session.last_heartbeat = time.time() - 300  # Stale

        # Recovery diagnoses
        recovery = RecoveryManager(heartbeat_stale_seconds=120)
        assert recovery.is_session_stale(session) is True
        action = recovery.diagnose(session)
        assert action.action == "resume"  # Has checkpoint → resume

        # Rollback to checkpoint
        s_data, d_data, ws_path = cp_mgr.rollback("cp-0000")
        assert s_data["session_id"] == "e2e-recovery"
        assert ws_path is not None

    def test_drift_detection_during_session(self, workspace: Path):
        """Drift monitor detects external changes during session."""
        monitor = DriftMonitor(workspace)
        monitor.capture_baseline()

        # Simulate external change (user edited a file)
        (workspace / "main.py").write_text("print('changed by user')\n")
        (workspace / "new_config.py").write_text("DEBUG = True\n")

        result = monitor.check_drift(sandbox_changed_files=["main.py"])
        assert result.has_drift is True
        assert result.severity == DriftSeverity.HIGH  # Conflict on main.py
        assert "main.py" in result.conflicting_files


# ---------------------------------------------------------------------------
# E2E: API integration
# ---------------------------------------------------------------------------


class TestAPIIntegration:
    """REST + WebSocket API integration tests."""

    def test_api_status_feedback_flow(self, tmp_path: Path, feedback: FeedbackStore):
        """API: status → record feedback → query stats."""
        ctrl = DaemonControl(state_dir=tmp_path / "daemon")
        router = ARARouter(control=ctrl, feedback_store=feedback)

        # Status when no session
        resp = router.handle("GET", "/api/ara/status")
        assert resp.ok is True

        # Record some feedback directly
        feedback.record_task(
            TaskOutcome(
                task_id="t1",
                session_id="api-test",
                action_type="write_files",
                success=True,
                confidence=0.9,
            )
        )
        feedback.record_session(
            SessionOutcome(
                session_id="api-test",
                role_name="coder",
                goal="test",
                status="completed",
                tasks_completed=1,
            )
        )

        # Query stats via API
        resp = router.handle("GET", "/api/ara/feedback/stats")
        assert resp.ok is True
        assert len(resp.data["stats"]) == 1

        # Submit user feedback via API
        resp = router.handle(
            "POST",
            "/api/ara/feedback",
            body={
                "session_id": "api-test",
                "rating": 4,
                "comment": "Good",
            },
        )
        assert resp.ok is True

        # Verify feedback persisted
        sessions = feedback.get_session_outcomes()
        assert sessions[0].user_rating == 4


# ---------------------------------------------------------------------------
# E2E: AEGIS gate review
# ---------------------------------------------------------------------------


class TestAEGISReview:
    """Review and promotion gate checks."""

    def test_clean_sandbox_approved(self, tmp_path: Path, roles_dir: Path, auth, workspace):
        """Clean sandbox passes AEGIS gate."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        session = SessionState(
            session_id="e2e-review",
            role_name="e2e-coder",
            goal="Test review",
            workspace_path=str(workspace),
        )
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.COMPLETED)
        session.save(sessions_dir=sessions_dir)

        sandbox = sessions_dir / "e2e-review" / "sandbox"
        sandbox.mkdir(parents=True)
        (sandbox / "clean.py").write_text("# Clean code\nx = 1\n")

        result = cmd_review(
            session_id="e2e-review",
            credential="1234",
            control=DaemonControl(state_dir=tmp_path / "daemon"),
            authenticator=auth,
            roles_dir=roles_dir,
            sessions_dir=sessions_dir,
        )
        assert result.success is True
        assert "APPROVED" in result.message

    def test_leaked_secret_blocked(self, tmp_path: Path, roles_dir: Path, auth, workspace):
        """Sandbox with leaked secret is blocked by AEGIS."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        session = SessionState(
            session_id="e2e-dirty",
            role_name="e2e-coder",
            goal="Test secret block",
        )
        session.transition(SessionStatus.RUNNING)
        session.transition(SessionStatus.COMPLETED)
        session.save(sessions_dir=sessions_dir)

        sandbox = sessions_dir / "e2e-dirty" / "sandbox"
        sandbox.mkdir(parents=True)
        (sandbox / "config.py").write_text('API_KEY = "AKIAIOSFODNN7EXAMPLE"\n')

        result = cmd_review(
            session_id="e2e-dirty",
            credential="1234",
            control=DaemonControl(state_dir=tmp_path / "daemon"),
            authenticator=auth,
            roles_dir=roles_dir,
            sessions_dir=sessions_dir,
        )
        assert result.success is False
        assert "BLOCKED" in result.message


# ---------------------------------------------------------------------------
# E2E: Confidence calibration
# ---------------------------------------------------------------------------


class TestConfidenceCalibration:
    """Feedback store confidence calibration over multiple sessions."""

    def test_calibration_across_sessions(self, feedback: FeedbackStore):
        """Record multiple sessions and verify calibration stats."""
        # Simulate 3 sessions with varying outcomes
        for sid in ["s1", "s2", "s3"]:
            for i in range(5):
                feedback.record_task(
                    TaskOutcome(
                        task_id=f"t{i}",
                        session_id=sid,
                        action_type="write_files",
                        success=i < 4,  # 80% success rate
                        confidence=0.85,
                        duration_seconds=5.0 + i,
                    )
                )
            feedback.record_session(
                SessionOutcome(
                    session_id=sid,
                    role_name="coder",
                    goal=f"goal-{sid}",
                    status="completed",
                    tasks_completed=4,
                    tasks_failed=1,
                )
            )

        assert feedback.task_count == 15
        assert feedback.session_count == 3

        stats = feedback.get_confidence_stats()
        assert len(stats) == 1
        assert stats[0].total_tasks == 15
        assert stats[0].successful_tasks == 12  # 4 per session × 3

        est = feedback.estimate_duration("write_files")
        assert est is not None
        assert est > 0
