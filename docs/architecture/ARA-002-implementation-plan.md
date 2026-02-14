# ARA-002: Phased Implementation Plan

**Status:** Active
**Date:** 2026-02-14
**Branch:** feature/ara-phase-{N} (one branch per phase)
**Depends on:** ARA-001

---

## Pre-Implementation State

- **Local main** is 17 commits ahead of `origin/main`
- Unpushed work: slim persona (v7.5.0-beta), NLA (v7.6.0→v7.8.0-beta), test fixes, ARA docs
- **Current version:** 7.8.0-beta
- **Tests:** 678 collected, all passing locally
- **CI pipeline:** lint → typecheck → test (3.10/3.11/3.12) → security → frontend → docker → release

## Ground Rules

1. **Feature branch per phase** — `feature/ara-phase-0`, `feature/ara-phase-1`, etc.
2. **Test gate at every phase** — all tests must pass before merging to main
3. **Lint gate** — `ruff check` + `ruff format --check` must pass
4. **No version bump until final step** — version stays at 7.8.0-beta until everything is done
5. **No push to GitHub until all phases complete + CI validated**
6. **README update is second-to-last step**
7. **Version bump + `_version.py` update is THE LAST step**

---

## Phase 0: Pre-Flight — Push Existing Work + Validate CI

**Goal:** Get origin/main in sync with local main. Validate CI passes
on GitHub before we start building ARA.

### Steps

0.1. Run full local test suite: `pytest tests/unit/ -q`
0.2. Run lint: `ruff check src/ tests/` + `ruff format --check src/ tests/`
0.3. Push local main to GitHub: `git push origin main --tags`
0.4. Monitor CI pipeline on GitHub — all 7 jobs must pass
0.5. Fix any CI failures before proceeding

### Test Gate
- [ ] 678+ tests pass locally
- [ ] Ruff lint clean
- [ ] CI pipeline green on GitHub (all 7 jobs)

### Output
- `origin/main` synced with local
- All NLA tags (v7.5.0-beta through v7.8.0-beta) on GitHub
- CI baseline established

---

## Phase 1: Hard Sandbox — Docker Hardening + AEGIS Traffic Gate

**Branch:** `feature/ara-phase-1`
**Version tag:** None (no version bump yet)

### Steps

1.1. Create branch from main
1.2. Harden `workspace_sandbox.py` Docker launch:
     - Add `--no-new-privileges`
     - Add `--cap-drop ALL`
     - Add `--user 1000:1000`
     - Add `--read-only` + `--tmpfs /tmp:rw,noexec,nosuid,size=64m`
     - Split mounts: workspace `:ro` + writable overlay `:rw`
     - Add `--security-opt seccomp=default` (use Docker default seccomp)
1.3. Create `src/orion/security/seccomp_profile.py` — loads custom seccomp if available
1.4. Create `src/orion/security/secret_scanner.py` — regex-based scanner (ARA-001 §C.7)
1.5. Create `src/orion/security/write_limits.py` — AEGIS write limits (ARA-001 §C.8)
1.6. Add sandbox escape tests: `tests/ara/test_sandbox_security.py`
     - test_cannot_access_host_filesystem
     - test_cannot_make_network_requests
     - test_cannot_escalate_privileges
     - test_cannot_write_to_readonly_workspace
     - test_can_write_to_overlay
     - test_pids_limit_enforced
     - test_memory_limit_enforced
     (All marked `@pytest.mark.docker` — skipped if Docker not available)
1.7. Add secret scanner tests: `tests/ara/test_secret_scanner.py`
     - test_detects_aws_key
     - test_detects_github_token
     - test_detects_private_key
     - test_detects_connection_string
     - test_detects_generic_password
     - test_respects_allowlist
     - test_redacts_output
1.8. Add write limit tests: `tests/ara/test_write_limits.py`
     - test_blocks_oversized_file
     - test_blocks_too_many_files
     - test_blocks_total_volume_exceeded
     - test_allows_within_limits
     - test_user_limits_cannot_exceed_aegis_ceiling

### Test Gate
- [ ] All existing 678 tests still pass (no regressions)
- [ ] All new sandbox/scanner/limits tests pass
- [ ] `ruff check` + `ruff format --check` clean
- [ ] Merge to main locally

---

## Phase 2: Role Profile System + Auth

**Branch:** `feature/ara-phase-2`

### Steps

2.1. Create `src/orion/ara/` package with `__init__.py`
2.2. Create `src/orion/ara/role_profile.py`:
     - `RoleProfile` dataclass (schema from ARA-001 §2.2)
     - YAML loader + validator
     - Required field enforcement
     - Authority overlap detection (autonomous ∩ forbidden = error)
     - Confidence threshold defaults
2.3. Create `src/orion/ara/auth.py`:
     - `PINAuth` class — set, verify, lockout (bcrypt hash)
     - `TOTPAuth` class — setup, verify, backup codes (pyotp)
     - `AuthManager` — method selection, switching, keychain storage
     - Lockout: 3 PIN failures → 15 min; 5 TOTP failures → 30 min
2.4. Create `src/orion/ara/aegis_gate.py`:
     - `AEGISRoleGate` — base restrictions (hardcoded) + user limits (per role)
     - Action validation: autonomous / requires_approval / forbidden
     - Confidence gate: auto_execute / execute_and_flag / pause_and_ask
2.5. Create 4 starter role templates: `data/roles/`
     - `software_engineer.yaml`
     - `technical_writer.yaml`
     - `qa_engineer.yaml`
     - `devops_engineer.yaml`
2.6. Create `src/orion/ara/lifecycle.py`:
     - `SessionLifecycleManager` — TTL, cleanup triggers, checkpoint pruning
     - Orphan container detection
     - Disk pressure handling
2.7. Add role CLI commands to settings or new `orion role` command group
2.8. Tests:
     - `tests/ara/test_role_profile.py` (validation, templates, overlap detection)
     - `tests/ara/test_auth.py` (PIN set/verify/lockout, TOTP setup/verify, method switching)
     - `tests/ara/test_aegis_gate.py` (base restrictions, role authority, confidence gate)
     - `tests/ara/test_lifecycle.py` (cleanup, TTL, pruning)

### Test Gate
- [ ] All existing tests pass
- [ ] All new ARA tests pass
- [ ] Role templates load and validate
- [ ] PIN auth round-trip works
- [ ] TOTP wired and functional (manual test with authenticator app)
- [ ] Lint clean
- [ ] Merge to main locally

---

## Phase 3: Session Engine + Goal Decomposition

**Branch:** `feature/ara-phase-3`

### Steps

3.1. Create `src/orion/ara/session.py`:
     - `SessionState` dataclass (ARA-001 §5.2)
     - Serialization to/from JSON
     - Session directory management (`~/.orion/sessions/{id}/`)
     - Heartbeat file writing
3.2. Create `src/orion/ara/goal_engine.py`:
     - `GoalEngine` — decomposes goal into task DAG via LLM
     - Structured prompt template for decomposition
     - AEGIS validation of every task at plan-time
     - DAG validation (no circular deps, topological sort)
     - Re-planning logic (every N tasks)
3.3. Create `src/orion/ara/execution.py`:
     - `ExecutionLoop` — runs tasks in dependency order
     - Confidence gating per task
     - Atomic task execution (.staging/ pattern)
     - Decision logging
     - Cost tracking (LLM call counter)
3.4. Create `src/orion/ara/checkpoint.py`:
     - Git-based checkpoints on sandbox branch
     - SessionState snapshot
     - Rollback support
3.5. Create `src/orion/ara/drift_monitor.py`:
     - `WorkspaceDriftMonitor` (ARA-001 §C.6)
     - Compare sandbox base commit vs current workspace HEAD
     - Conflict detection
3.6. Create `src/orion/ara/recovery.py`:
     - Recovery state machine (ARA-001 §C.1)
     - Interrupted session detection
     - Auto-retry logic for transient failures
     - OOM handling
3.7. Add stop conditions to execution loop:
     - Goal complete
     - Time limit
     - Cost limit
     - Confidence collapse (3+ consecutive < 50%)
     - Error threshold (5+ consecutive failures)
3.8. Create `MockLLMProvider` for testing: `tests/ara/conftest.py`
3.9. Tests:
     - `tests/ara/test_session.py` (state serialization, heartbeat, directory management)
     - `tests/ara/test_goal_engine.py` (decomposition, DAG validation, AEGIS plan-time gate)
     - `tests/ara/test_execution.py` (loop, confidence gating, atomic tasks, stop conditions)
     - `tests/ara/test_checkpoint.py` (create, rollback, pruning)
     - `tests/ara/test_drift_monitor.py` (no drift, low severity, high severity)
     - `tests/ara/test_recovery.py` (state transitions, auto-retry, interrupted detection)

### Test Gate
- [ ] All existing tests pass
- [ ] All new engine tests pass (using MockLLMProvider)
- [ ] Session create → execute → checkpoint → rollback round-trip works
- [ ] Drift monitor detects real git changes
- [ ] Lint clean
- [ ] Merge to main locally

---

## Phase 4: Daemon Mode + CLI Commands

**Branch:** `feature/ara-phase-4`

### Steps

4.1. Create `src/orion/ara/daemon.py`:
     - Background process launcher (Windows: `pythonw.exe`, Linux/Mac: `nohup`)
     - PID file management
     - Named pipe (Windows) / Unix socket (Linux/Mac) for IPC
     - Health check endpoint
     - Graceful shutdown
4.2. Create `src/orion/ara/commands.py`:
     - `orion work` — start autonomous session (foreground or background)
     - `orion status` — show current session state
     - `orion pause` — checkpoint and stop
     - `orion resume` — pick up from checkpoint
     - `orion cancel` — abort and rollback
     - `orion review` — morning review TUI
     - `orion sessions` — list all sessions
     - `orion sessions cleanup` — interactive cleanup
     - `orion role create|list|test|edit` — role management
     - `orion undo-promote {id}` — revert promotion
4.3. Wire commands into CLI (`cli/app.py` or new command group)
4.4. Create `src/orion/ara/review.py`:
     - CLI TUI for morning review (task-by-task, diff, approve/reject)
     - Interactive approval flow with PIN/TOTP
4.5. Tests:
     - `tests/ara/test_daemon.py` (start, health check, shutdown)
     - `tests/ara/test_commands.py` (CLI arg parsing, command dispatch)
     - `tests/ara/test_review.py` (approval flow, PIN prompt, diff display)

### Test Gate
- [ ] All existing tests pass
- [ ] Daemon starts and stops cleanly on Windows
- [ ] CLI commands parse and dispatch correctly
- [ ] Review flow works end-to-end with mock data
- [ ] Lint clean
- [ ] Merge to main locally

---

## Phase 5: Notifications + Dashboard WebSocket

**Branch:** `feature/ara-phase-5`

### Steps

5.1. Create `src/orion/ara/notifications.py`:
     - `NotificationProvider` abstract base
     - `EmailProvider` (SMTP send-only, AEGIS-locked)
     - `WebhookProvider` (Slack, Discord, Teams, generic)
     - `DesktopProvider` (OS-native: Windows toast, Mac notification center)
     - Template rendering for all providers
     - Rate limiting (max 5 per session)
5.2. Create `src/orion/ara/feedback.py`:
     - `TaskOutcome` dataclass
     - Append-only outcomes.jsonl store
     - Confidence calibration function
     - Estimation calibration function
5.3. Create `src/orion/api/routes/ara.py`:
     - REST endpoints:
       - `GET /api/ara/sessions` — list sessions
       - `GET /api/ara/session/{id}` — session detail
       - `GET /api/ara/session/{id}/tasks` — task list
       - `GET /api/ara/session/{id}/decisions` — decision log
       - `POST /api/ara/session/{id}/approve/{task_id}` — approve task
       - `POST /api/ara/session/{id}/reject/{task_id}` — reject task
       - `POST /api/ara/session/{id}/promote` — promote with auth
     - WebSocket: `/ws/ara/{session_id}` — real-time events
5.4. Wire notification settings into settings UI
5.5. Tests:
     - `tests/ara/test_notifications.py` (email, webhook, desktop, rate limit)
     - `tests/ara/test_feedback.py` (outcomes, calibration)
     - `tests/ara/test_api_ara.py` (REST endpoints, WebSocket events)

### Test Gate
- [ ] All existing tests pass
- [ ] Email sends (manual test with real SMTP)
- [ ] Webhook sends (mock server)
- [ ] Desktop notification fires on Windows
- [ ] WebSocket events stream correctly
- [ ] Lint clean
- [ ] Merge to main locally

---

## Phase 6: End-to-End Integration Test

**Branch:** `feature/ara-phase-6`

### Steps

6.1. Create `tests/ara/test_e2e.py`:
     - Full session: goal → decompose → execute → checkpoint → review → promote
     - Uses MockLLMProvider + real Docker sandbox
     - Verifies: file changes in sandbox, promotion with PIN, cleanup
6.2. Create `tests/ara/test_e2e_security.py`:
     - Verify forbidden actions blocked end-to-end
     - Verify secrets scanner blocks tainted promotion
     - Verify write limits prevent runaway output
6.3. Fix any integration issues discovered
6.4. Run full test suite: `pytest tests/ -q`

### Test Gate
- [ ] All unit tests pass
- [ ] All E2E tests pass (with Docker)
- [ ] E2E security tests pass
- [ ] No regressions in existing 678 tests
- [ ] Lint clean
- [ ] Merge to main locally

---

## Phase 7: README Update

**Branch:** `feature/ara-readme`

### Steps

7.1. Update README.md with all features since last GitHub push:

**New sections to add:**
- Natural Language Architecture (NLA) — v7.5.0 through v7.8.0
  - ConversationBuffer (session memory)
  - ExemplarBank (200 seed exemplars)
  - IntentClassifier (embedding + keyword fallback)
  - ClarificationDetector
  - BriefBuilder + TaskBrief
  - RequestAnalyzer
  - EnglishFoundation
  - LearningBridge
- Autonomous Role Architecture (ARA) — new feature
  - User-configurable roles (YAML + CLI)
  - AEGIS two-layer governance
  - Docker sandbox hardening
  - PIN / TOTP authentication
  - Session lifecycle (work/pause/resume/cancel)
  - Goal decomposition engine
  - Morning review dashboard
  - Email + webhook notifications
  - Secret scanner
- Slim persona system (intent-aware prompt optimization)

**Sections to update:**
- Test count badge (678 → new count)
- Architecture diagram (add NLA + ARA layers)
- Project structure (add `core/understanding/`, `ara/`)
- Key Features section (add NLA + ARA subsections)
- "Why Orion?" comparison table

7.2. Update `docs/` references if needed
7.3. Verify all links work

### Test Gate
- [ ] README renders correctly on GitHub (preview)
- [ ] All badge links valid
- [ ] No broken doc links
- [ ] Lint clean
- [ ] Merge to main locally

---

## Phase 8: Version Bump + CI Validation (FINAL STEP)

**Branch:** main (direct commit or tiny branch)

### Steps

8.1. Update `src/orion/_version.py`:
     ```python
     __version__ = "8.0.0-beta"
     ```
     (Major bump: ARA is a significant new capability)
8.2. Update test badge count in README
8.3. Final full test run: `pytest tests/ -q`
8.4. Final lint: `ruff check src/ tests/` + `ruff format --check src/ tests/`
8.5. Commit: `chore: bump version to 8.0.0-beta`
8.6. **DO NOT PUSH YET** — simulate CI locally:
     - Run tests on Python 3.10, 3.11, 3.12 (if available)
     - Run `bandit -r src/orion/ -ll -ii`
     - Run `mypy src/orion/ --ignore-missing-imports`
     - Build frontend: `cd orion-web && npm ci && npm run build`
     - Build Docker: `docker build -f docker/Dockerfile -t orion-agent:test .`
8.7. Push to GitHub: `git push origin main --tags`
8.8. Monitor CI pipeline — all 7 jobs must pass
8.9. If CI fails: fix on main, re-push, repeat until green
8.10. Tag release: `git tag v8.0.0-beta && git push origin v8.0.0-beta`

### Test Gate (FINAL)
- [ ] All tests pass on Python 3.10, 3.11, 3.12
- [ ] Ruff lint + format clean
- [ ] Bandit security scan clean
- [ ] MyPy passes
- [ ] Frontend builds
- [ ] Docker image builds and `--version` works
- [ ] GitHub CI pipeline fully green
- [ ] Release created on GitHub

---

## Summary Timeline

| Phase | Name                         | New Files (est.) | New Tests (est.) | Depends On |
|-------|------------------------------|------------------|------------------|------------|
| 0     | Pre-flight (push existing)   | 0                | 0                | —          |
| 1     | Hard sandbox                 | 3                | ~20              | Phase 0    |
| 2     | Role profiles + auth         | 6 + 4 templates  | ~35              | Phase 1    |
| 3     | Session engine + goals       | 7                | ~40              | Phase 2    |
| 4     | Daemon + CLI commands        | 4                | ~20              | Phase 3    |
| 5     | Notifications + API          | 4                | ~25              | Phase 4    |
| 6     | E2E integration tests        | 2                | ~15              | Phase 5    |
| 7     | README update                | 0                | 0                | Phase 6    |
| 8     | Version bump + CI (FINAL)    | 0                | 0                | Phase 7    |
| **Total** |                          | **~26 files**    | **~155 tests**   |            |

Final expected test count: **~833 tests** (678 existing + ~155 new)
Final version: **8.0.0-beta**
