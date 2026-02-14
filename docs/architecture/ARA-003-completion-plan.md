# ARA-003: Completion Plan — Status & Remaining Work

**Status:** Active
**Author:** Jaco / Orion Design Sessions
**Date:** 2026-02-14
**Version:** 8.0.0-beta → targets 9.0.0
**Related:** ARA-001 (design spec), ARA-002 (original implementation plan), NLA-001

---

## 1. Purpose

This document provides a complete accounting of the Autonomous Role Architecture:

- **Part A:** What was built (Phases 0–8, now on `main` as v8.0.0-beta)
- **Part B:** What is missing (23 gaps identified against ARA-001 spec)
- **Part C:** Phased plan to close all gaps (Phases 9–14)

---

## Part A: What Was Built

### Overview

| Metric | Value |
|--------|-------|
| Version | 8.0.0-beta |
| Total tests | 1,004 passing |
| ARA source modules | 15 files in `src/orion/ara/` |
| ARA test files | 19 files in `tests/ara/` |
| Starter role templates | 4 YAML files in `data/roles/` |
| Lint status | Clean (ruff) |
| Branch | `main` |
| Tag | `v8.0.0-beta` |

### Phase 0: Pre-flight

- Validated 677 existing tests pass
- Confirmed lint clean across codebase
- Deferred GitHub push to Phase 8

### Phase 1: Hard Sandbox — 38 new tests

**Modules:** Test-only (validating existing sandbox infrastructure)

| Component | What It Validates |
|-----------|-------------------|
| `test_sandbox_security.py` (20 tests) | Docker hardening flags: `--cap-drop ALL`, `--no-new-privileges`, `--read-only`, `--tmpfs`, seccomp, non-root UID, PID limits, `--network none` |
| `test_secret_scanner.py` (10 tests) | Regex detection of AWS keys, GitHub tokens, private keys, passwords, JWTs, connection strings, Slack webhooks |
| `test_write_limits.py` (8 tests) | Per-file and total write size limit enforcement |

### Phase 2: Role Profiles + Auth — 73 new tests

**Modules created:**

| File | Lines | Purpose |
|------|-------|---------|
| `role_profile.py` | 305 | `RoleProfile` dataclass, YAML load/save, validation, AEGIS enforcement, `WriteLimits`, `WorkingHours`, `NotificationConfig` |
| `auth.py` | 273 | `AuthStore` (PIN + TOTP), `RoleAuthenticator`, PIN lockout (5 attempts, 5-min), TOTP RFC 6238 |
| `aegis_gate.py` | 187 | `AegisGate`: secret scan + write limits + scope check + auth verification → `GateDecision` |
| `lifecycle.py` | 281 | `LifecycleManager`: session cleanup, checkpoint pruning, stale detection, health reports |

**Data files:**
- `data/roles/night-coder.yaml` — coding scope, PIN auth
- `data/roles/researcher.yaml` — research scope, PIN auth
- `data/roles/devops-runner.yaml` — devops scope, TOTP auth
- `data/roles/full-auto.yaml` — full scope, TOTP auth

### Phase 3: Session Engine — 102 new tests

**Modules created:**

| File | Lines | Purpose |
|------|-------|---------|
| `session.py` | 187 | `SessionState` state machine (CREATED→RUNNING→PAUSED→COMPLETED/FAILED/CANCELLED), heartbeat, cost tracking, 5 stop conditions, serialization |
| `goal_engine.py` | 243 | `GoalEngine`, `TaskDAG`, `Task`, `TaskStatus`, `MockLLMProvider`, action validation |
| `execution.py` | 155 | `ExecutionLoop`: sequential task runner, confidence gating, checkpoint callbacks, `ExecutionResult` |
| `checkpoint.py` | 159 | `CheckpointManager`: git-based snapshots, rollback, listing, deletion |
| `drift_monitor.py` | 185 | `DriftMonitor`: baseline capture, change detection, severity (LOW/MEDIUM/HIGH), conflict detection |
| `recovery.py` | 177 | `RecoveryManager`: stale heartbeat (120s), failure diagnosis, `RetryPolicy` (max 3, exponential backoff) |

### Phase 4: Daemon + CLI — 36 new tests

**Modules created:**

| File | Lines | Purpose |
|------|-------|---------|
| `daemon.py` | 294 | `ARADaemon` (background runner), `DaemonControl` (file-based IPC: PID/command/status), `DaemonStatus`. Cross-platform process detection (Windows `ctypes` + POSIX `os.kill`) |
| `cli_commands.py` | 335 | 6 commands: `cmd_work`, `cmd_status`, `cmd_pause`, `cmd_resume`, `cmd_cancel`, `cmd_review`. `CommandResult` dataclass. `list_available_roles`, `_find_role` |

### Phase 5: Notifications + API — 68 new tests

**Modules created:**

| File | Lines | Purpose |
|------|-------|---------|
| `notifications.py` | 321 | `NotificationManager` (rate limit 5/session, template-only), `EmailProvider` (SMTP), `WebhookProvider` (HTTP POST), `DesktopProvider` (platform-native toast). 7 notification templates |
| `feedback_store.py` | 279 | `FeedbackStore` (JSONL), `TaskOutcome`, `SessionOutcome`, `ConfidenceStats`, duration estimation |
| `api.py` | 291 | `ARARouter` (8 REST endpoints), `WSChannel` (WebSocket broadcast, subscribe/unsubscribe, event log), `APIResponse`, `WSMessage` |

**8 API endpoints:**
- `GET /api/ara/status`
- `POST /api/ara/work`
- `POST /api/ara/pause`
- `POST /api/ara/resume`
- `POST /api/ara/cancel`
- `GET /api/ara/feedback/stats`
- `GET /api/ara/feedback/sessions`
- `POST /api/ara/feedback`

### Phase 6: E2E Tests — 10 new tests

| Test | Coverage |
|------|----------|
| Session happy path | Role → decompose → execute → checkpoint → complete |
| Notifications + feedback | Full notification + outcome recording flow |
| Daemon full session | Daemon runs, writes status, exits cleanly |
| Daemon + WebSocket | Broadcast integration |
| Recovery | Stale session recovery with checkpoint rollback |
| Drift detection | External changes during active session |
| API flow | REST status → feedback → stats |
| AEGIS review (clean) | Clean sandbox passes gate → APPROVED |
| AEGIS review (secret) | Leaked AWS key → BLOCKED |
| Confidence calibration | Multi-session stats + duration estimation |

### Phase 7: README Update

- Updated tagline, badges (1004 tests, v8.0.0-beta)
- New NLA section (7-component table)
- New ARA section (8-component table + starter roles)
- Updated architecture diagram (NLA layer, ARA daemon, WebSocket, expanded AEGIS)
- Updated project structure tree

### Phase 8: Version Bump + Tag

- `_version.py`: 7.8.0-beta → 8.0.0-beta
- `pyproject.toml`: 7.8.0-beta → 8.0.0-beta
- Git tag: `v8.0.0-beta` (annotated)
- **Pending:** GitHub push (awaiting PAT)

---

## Part B: Gap Analysis

23 gaps identified by auditing every section and appendix of ARA-001 against the implementation.

### B.1 Critical Gaps (core functionality missing)

| # | Gap | ARA-001 Ref | Impact |
|---|-----|-------------|--------|
| G1 | **Actual file promotion** — `cmd_review` checks AEGIS but never merges sandbox files into workspace | §10 | Core workflow broken: user can't actually accept work |
| G2 | **3-tier authority model** — design has `autonomous` / `requires_approval` / `forbidden`; we only have `allowed_actions` / `blocked_actions` | §2.2 | Confidence gating and approval flow don't work as designed |
| G3 | **Prompt injection defence** — no goal sanitization, no adversarial pattern stripping | §3.4 | Security gap: LLM could be manipulated |
| G4 | **Audit log** — no tamper-proof append-only log with HMAC + hash chain | §3.5 | Transparency requirement unmet |
| G5 | **Credential storage** — PIN/TOTP in plain JSON, not system keychain | §3.6 | Security: credentials accessible to any process |

### B.2 High Gaps (designed features completely absent)

| # | Gap | ARA-001 Ref | Impact |
|---|-----|-------------|--------|
| G6 | **Morning Dashboard** — CLI TUI + Web UI | §9 | Primary user interaction surface missing |
| G7 | **Role management CLI** — `orion role create/edit/delete/list/show/example` | §2.1 | Users must manually write YAML |
| G8 | **First-time setup wizard** — `orion autonomous setup` (5-step) | §12 | No guided onboarding |
| G9 | **`orion sessions`** — list all active/completed sessions | §5.3, §11 | No multi-session visibility |
| G10 | **`orion rollback`** — CLI command for checkpoint rollback | §8.3 | Internal only, not user-facing |
| G11 | **`orion plan --review`** — review task DAG before execution | §6.2 | User can't inspect/edit plan |
| G12 | **Goal queuing + priority interrupts** | Appendix C.5 | One goal at a time only |
| G13 | **Post-promotion rollback** — `orion undo-promote` with git tagging | Appendix C.9 | No undo after promotion |
| G14 | **Conflict resolution** — sandbox branch strategy + merge flow | §10 | No actual branching or merge |

### B.3 Medium Gaps (partial implementations)

| # | Gap | ARA-001 Ref | Impact |
|---|-----|-------------|--------|
| G15 | **Re-planning** during execution (every N tasks) | §6.4 | Long sessions may drift |
| G16 | **Auth method switching** with downgrade protection | §7.6 | Can't securely switch PIN↔TOTP |
| G17 | **ARA settings** — notification channels, defaults, email config | §4.3, C.11 | No user-facing configuration |
| G18 | **Role schema fields** — `competencies`, `confidence_thresholds`, `risk_tolerance`, `success_criteria` | §2.2 | Schema simpler than design |
| G19 | **Task estimation calibration** — uncertainty bands, calibration formula | Appendix C.4 | Basic `estimate_duration` only |
| G20 | **Test layer organization** — 5 layers with pytest markers | Appendix C.13 | Tests work but aren't categorized |
| G21 | **Lifecycle cleanup commands** — `orion sessions cleanup`, orphan container cleanup | Appendix C.2 | LifecycleManager exists but no CLI |

### B.4 Low Gaps (deferred or nice-to-have)

| # | Gap | ARA-001 Ref | Impact |
|---|-----|-------------|--------|
| G22 | **Multi-user isolation** — OS-user scoping, per-user containers | Appendix C.10 | Single-user only |
| G23 | **Session export** — `orion export-session` | §13 Phase 4 | No session portability |

---

## Part C: Phased Completion Plan

### Phase 9: Role Schema + Management CLI

**Branch:** `feature/ara-phase-9`
**Closes:** G2, G7, G18
**Estimated new tests:** 40–50

#### 9.1 Expand RoleProfile schema

Add missing fields from ARA-001 §2.2:

```python
@dataclass
class RoleProfile:
    # Existing fields...
    name: str
    scope: str
    auth_method: str = "pin"
    description: str = ""
    allowed_actions: list[str]      # Keep for backward compat
    blocked_actions: list[str]      # Keep for backward compat

    # NEW: 3-tier authority model (§2.2)
    authority_autonomous: list[str] = field(default_factory=list)
    authority_requires_approval: list[str] = field(default_factory=list)
    authority_forbidden: list[str] = field(default_factory=list)

    # NEW: Missing schema fields (§2.2, §2.3)
    competencies: list[str] = field(default_factory=list)
    confidence_thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    risk_tolerance: str = "medium"  # low | medium | high
    success_criteria: list[str] = field(default_factory=list)
```

```python
@dataclass
class ConfidenceThresholds:
    auto_execute: float = 0.90
    execute_and_flag: float = 0.70
    pause_and_ask: float = 0.50
```

Backward compatibility: if `allowed_actions` present but `authority_autonomous` empty, migrate automatically.

#### 9.2 Role management CLI commands

Add to `cli_commands.py`:

| Command | Purpose |
|---------|---------|
| `cmd_role_list()` | Table of all roles: name, scope, auth, source path, enabled |
| `cmd_role_show(name)` | Full role details with field descriptions |
| `cmd_role_create(name)` | Interactive wizard: scope → auth → actions → limits. Writes YAML |
| `cmd_role_edit(name, field, value)` | Modify single field (requires current auth for auth_method changes) |
| `cmd_role_delete(name)` | Remove user role (starter templates protected) |
| `cmd_role_example()` | Print annotated YAML template with field descriptions + examples |
| `cmd_role_validate(path)` | Validate a YAML file without loading it |

#### 9.3 Update starter templates

Rename to match ARA-001 §2.4 and add new fields:
- `night-coder.yaml` → `software-engineer.yaml`
- `researcher.yaml` → `technical-writer.yaml`
- `devops-runner.yaml` → `devops-engineer.yaml`
- `full-auto.yaml` → `qa-engineer.yaml`

Each template gets: `competencies`, 3-tier authority, `confidence_thresholds`, `success_criteria`.

---

### Phase 10: Security Hardening

**Branch:** `feature/ara-phase-10`
**Closes:** G3, G4, G5
**Estimated new tests:** 35–45

#### 10.1 Prompt injection defence (§3.4)

New module: `src/orion/ara/prompt_guard.py`

```python
class PromptGuard:
    """Sanitizes goal text before it reaches the LLM."""

    ADVERSARIAL_PATTERNS = [
        r"ignore\s+(previous|above|all)\s+(instructions?|rules?|prompts?)",
        r"override\s+(role|authority|aegis|security)",
        r"you\s+are\s+now\s+a",
        r"pretend\s+(you|to\s+be)",
        r"disregard\s+(your|the)\s+(role|rules?|instructions?)",
        r"jailbreak",
        r"DAN\s+mode",
        r"system\s*:\s*",
    ]

    def sanitize(self, goal: str) -> tuple[str, list[str]]:
        """Returns (sanitized_goal, list_of_stripped_patterns)."""

    def is_safe(self, goal: str) -> bool:
        """Quick check: True if no adversarial patterns found."""
```

Integration: `GoalEngine.decompose()` calls `PromptGuard.sanitize()` before LLM call.

#### 10.2 Tamper-proof audit log (§3.5)

New module: `src/orion/ara/audit_log.py`

```python
@dataclass
class AuditEntry:
    timestamp: float
    session_id: str
    event_type: str          # "task_started", "task_completed", "gate_check", "promotion", etc.
    actor: str               # "orion" | "user" | "aegis"
    details: dict[str, Any]
    prev_hash: str           # SHA-256 of previous entry (hash chain)
    hmac_sig: str            # HMAC-SHA256 of this entry

class AuditLog:
    def append(self, entry: AuditEntry) -> None: ...
    def verify_chain(self) -> tuple[bool, int]: ...  # (valid, entries_checked)
    def get_entries(self, session_id: str) -> list[AuditEntry]: ...
```

Storage: `~/.orion/audit/audit.jsonl` (append-only). HMAC key derived from machine-specific value.

#### 10.3 System keychain credential storage (§3.6)

New module: `src/orion/ara/keychain.py`

```python
class KeychainStore:
    """Platform-native credential storage."""

    def store(self, service: str, key: str, value: str) -> bool: ...
    def retrieve(self, service: str, key: str) -> str | None: ...
    def delete(self, service: str, key: str) -> bool: ...
```

Backends:
- **Windows:** `win32cred` (Windows Credential Manager)
- **macOS:** `security` CLI (Keychain)
- **Linux:** `secretstorage` (freedesktop Secret Service / GNOME Keyring)
- **Fallback:** Encrypted file with machine-derived key (for headless/CI)

Update `AuthStore` to use `KeychainStore` instead of plain JSON. Migration: on first run with new code, auto-migrate `auth.json` → keychain, then delete JSON.

---

### Phase 11: Promotion + Conflict Resolution

**Branch:** `feature/ara-phase-11`
**Closes:** G1, G13, G14
**Estimated new tests:** 40–50

#### 11.1 Sandbox branch strategy (§10.1)

New module: `src/orion/ara/promotion.py`

```python
class PromotionManager:
    """Manages the sandbox → workspace file promotion flow."""

    def create_sandbox_branch(self, session_id: str, workspace: Path) -> str:
        """Create orion-ara/{session_id} branch from current HEAD."""

    def get_diff(self, session_id: str) -> list[FileDiff]:
        """List all changed files with status (A/M/D) and diff content."""

    def promote(self, session_id: str, credential: str) -> PromotionResult:
        """
        1. git tag orion-pre-promote/{session_id} HEAD
        2. Merge sandbox branch (or copy files)
        3. git commit -m "orion(ara): {goal}"
        4. git tag orion-post-promote/{session_id} HEAD
        """

    def reject(self, session_id: str) -> None:
        """Mark session rejected. Branch preserved for reference."""

    def undo_promote(self, session_id: str) -> bool:
        """Create revert commit. Original work preserved on post-promote tag."""

    def check_conflicts(self, session_id: str) -> list[ConflictFile]:
        """Detect files changed both in sandbox and workspace since session start."""
```

```python
@dataclass
class FileDiff:
    path: str
    status: str          # "added" | "modified" | "deleted"
    additions: int
    deletions: int

@dataclass
class PromotionResult:
    success: bool
    files_promoted: int
    pre_tag: str
    post_tag: str
    conflicts: list[str]
```

#### 11.2 New CLI commands

| Command | Purpose |
|---------|---------|
| `cmd_promote(session_id, credential)` | Full promotion flow with AEGIS gate + file merge |
| `cmd_undo_promote(session_id)` | Revert commit |
| `cmd_diff(session_id)` | Show file changes before promotion |

#### 11.3 Update `cmd_review`

Wire `cmd_review` to use `PromotionManager` so it becomes the actual promotion flow:
1. Show diff summary
2. Run AEGIS gate (secret scan, write limits, auth)
3. Check conflicts
4. If clean → promote with git tags
5. If conflicts → show conflict list, ask user to resolve

---

### Phase 12: CLI Commands + Setup Wizard

**Branch:** `feature/ara-phase-12`
**Closes:** G8, G9, G10, G11, G15, G16, G17, G21
**Estimated new tests:** 50–60

#### 12.1 Missing CLI commands

| Command | Closes | Purpose |
|---------|--------|---------|
| `cmd_sessions()` | G9 | List all sessions (active, completed, failed) with status, role, duration |
| `cmd_sessions_cleanup()` | G21 | Interactive cleanup: prune checkpoints, archive old, delete orphans |
| `cmd_rollback(checkpoint_id)` | G10 | User-facing checkpoint rollback |
| `cmd_plan_review(session_id)` | G11 | Show task DAG, allow edit/reorder/remove before execution |
| `cmd_settings_ara()` | G17 | ARA settings: notification channels, defaults, email SMTP config |
| `cmd_auth_switch(new_method)` | G16 | Switch PIN↔TOTP with current auth verification first |

#### 12.2 First-time setup wizard (§12)

New function: `cmd_setup()` in `cli_commands.py`

```
$ orion autonomous setup

Step 1/5: Checking prerequisites...
  ✓ Docker installed and running
  ✓ AEGIS governance active
  ✓ Workspace sandbox functional

Step 2/5: Create or select a role
  → Available templates: Software Engineer, Technical Writer, QA Engineer, DevOps Engineer
  → Select [1-4] or 'custom': 1
  → Customize? [y/N]: N

Step 3/5: Set up authentication
  → Method: (1) PIN  (2) TOTP
  → Enter PIN: ••••••
  → Confirm:   ••••••
  ✓ PIN saved to system keychain

Step 4/5: Dry-run validation
  → Simulating 6 scenarios...
  ✓ "Write code in sandbox"        → Allowed (autonomous)
  ✓ "Run tests"                     → Allowed (autonomous)
  ✓ "Add dependency"                → Paused (requires approval)
  ✓ "Merge to main"                 → Paused (requires approval)
  ✓ "Deploy to production"          → BLOCKED (forbidden)
  ✓ "Modify AEGIS config"           → BLOCKED (AEGIS base)

Step 5/5: Ready!
  → Start your first session:
    orion work --role "Software Engineer" "Write unit tests for auth module"
```

#### 12.3 Re-planning integration (§6.4)

Add to `ExecutionLoop`:

```python
async def _maybe_replan(self, tasks_since_last_replan: int) -> bool:
    """Every N tasks, ask LLM if plan should be revised."""
    if tasks_since_last_replan < self._replan_interval:
        return False
    # LLM evaluates: original goal + completed tasks + remaining tasks
    # Returns: keep / revise / abort
```

Default interval: 5 tasks. Configurable via role profile.

---

### Phase 13: Morning Dashboard

**Branch:** `feature/ara-phase-13`
**Closes:** G6
**Estimated new tests:** 25–35

#### 13.1 CLI TUI Dashboard (§9)

New module: `src/orion/ara/dashboard.py`

Built with `rich` library (already a common Python TUI library):

```python
class MorningDashboard:
    """Interactive terminal dashboard for reviewing ARA session results."""

    def show(self, session_id: str | None = None) -> None:
        """Render the full morning review TUI."""

    def _render_header(self, session: SessionState, role: RoleProfile) -> Panel: ...
    def _render_task_table(self, dag: TaskDAG) -> Table: ...
    def _render_approval_queue(self, pending: list[Task]) -> Panel: ...
    def _render_cost_budget(self, session: SessionState) -> Panel: ...
    def _render_confidence_chart(self, stats: ConfidenceStats) -> Panel: ...
    def _render_aegis_status(self, role: RoleProfile) -> Panel: ...
```

Dashboard sections (from ARA-001 §9.2):

1. **Session header** — role, duration, cost, sandbox type
2. **Task list** — completed/pending/failed with confidence scores
3. **Approval queue** — items needing user decision (prominent)
4. **File changes** — added/modified/deleted with line counts
5. **Cost/time budget** — progress bars
6. **AEGIS status** — security gate summary
7. **Decision log** — drill-down into task reasoning

Interactive keys: `[a]pprove  [r]eject  [d]iff  [l]og  [n]ext  [q]uit`

#### 13.2 REPL startup notification (§9.1)

On REPL start, check for completed sessions:

```
Orion completed 8 tasks overnight (session: "Implement auth module").
Run `orion review` to inspect and approve.
```

#### 13.3 Web UI integration (future-ready)

The dashboard data layer already exists (`ARARouter` + `WSChannel`). Web UI integration is a frontend task for `orion-web/` (Next.js) and is outside the scope of this Python backend plan. However, Phase 13 ensures all data the Web UI needs is accessible via the existing API.

---

### Phase 14: Polish + Production Hardening

**Branch:** `feature/ara-phase-14`
**Closes:** G12, G19, G20, G22, G23
**Estimated new tests:** 30–40

#### 14.1 Goal queuing + priority interrupts (C.5)

New module: `src/orion/ara/goal_queue.py`

```python
@dataclass
class QueuedGoal:
    goal_id: str
    description: str
    role_name: str
    priority: str           # "normal" | "urgent"
    depends_on: str | None  # goal_id of prerequisite
    added_at: float

class GoalQueue:
    def enqueue(self, goal: QueuedGoal) -> None: ...
    def dequeue(self) -> QueuedGoal | None: ...
    def interrupt(self, urgent_goal: QueuedGoal) -> str: ...  # Returns paused goal_id
    def reorder(self, from_pos: int, to_pos: int) -> None: ...
    def list(self) -> list[QueuedGoal]: ...
```

CLI additions:
- `orion work --queue` — add to queue instead of starting immediately
- `orion work --urgent` — priority interrupt: checkpoint current, start urgent
- `orion queue` — view queue
- `orion queue move <from> <to>` — reorder

#### 14.2 Task estimation calibration (C.4)

Enhance `FeedbackStore` with calibration formula from ARA-001:

```python
def calibrate_estimate(self, action_type: str, role: str, raw_seconds: float) -> tuple[float, float]:
    """Returns (lower_bound, upper_bound) calibrated estimate."""
    history = self.get_task_outcomes(action_type=action_type)
    if len(history) < 5:
        return (raw_seconds, raw_seconds * 2)  # Wide band, no data
    ratio = mean(o.duration_seconds / raw_seconds for o in history if o.success)
    std = stdev(...)
    calibrated = raw_seconds * ratio
    return (max(0, calibrated - std), calibrated + std)

def calibrate_confidence(self, action_type: str, raw_confidence: float) -> float:
    """Adjust confidence by historical approval rate."""
    stats = self.get_confidence_stats(action_type=action_type)
    if not stats:
        return raw_confidence
    return raw_confidence * stats[0].accuracy
```

#### 14.3 Test layer organization (C.13)

Add pytest markers to all ARA tests:

```python
# conftest.py
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "docker: requires Docker")
    config.addinivalue_line("markers", "e2e: end-to-end test")
    config.addinivalue_line("markers", "slow: takes >5 seconds")
```

Organize into 5 layers:
- **Layer 1:** Unit tests (no LLM, no Docker) — `pytest tests/ara/ -m "not docker and not e2e"`
- **Layer 2:** Mock LLM integration — `pytest tests/ara/ -m "mock_llm"`
- **Layer 3:** Sandbox escape tests — `pytest tests/ara/ -m "docker"`
- **Layer 4:** Role boundary tests — `pytest tests/ara/ -m "role_boundary"`
- **Layer 5:** E2E smoke — `pytest tests/ara/ -m "e2e"`

#### 14.4 Multi-user isolation (C.10)

Add `UserIsolation` class to enforce OS-user scoping:

```python
class UserIsolation:
    def validate_session_access(self, session_path: Path) -> bool:
        user_orion_dir = Path.home() / ".orion"
        return session_path.resolve().is_relative_to(user_orion_dir.resolve())

    def get_container_name(self, session_id: str) -> str:
        username = getpass.getuser()
        return f"orion-ara-{username}-{session_id[:12]}"
```

#### 14.5 Session export (§13 Phase 4)

New command: `cmd_export_session(session_id, output_path)`

Exports a session as a portable archive:
- `session_state.json`
- `task_dag.json`
- `decision_log.jsonl`
- `checkpoints/` (last 3)
- `diff.patch` (unified diff of all changes)

---

## Dependency Graph

```
Phase 9:  Role Schema + Management CLI
  │
  ├─── Phase 10: Security Hardening
  │       │
  │       └─── Phase 11: Promotion + Conflict Resolution
  │               │
  │               └─── Phase 12: CLI Commands + Setup Wizard
  │                       │
  │                       └─── Phase 13: Morning Dashboard
  │                               │
  │                               └─── Phase 14: Polish + Production
```

Phases are sequential because each builds on the previous:
- Phase 10 needs expanded role schema from Phase 9
- Phase 11 needs audit log from Phase 10 (promotions are logged)
- Phase 12 needs promotion flow from Phase 11 (setup wizard references promote)
- Phase 13 needs all CLI commands from Phase 12 (dashboard renders them)
- Phase 14 is independent polish but benefits from all above

---

## Test Budget

| Phase | New Tests (est.) | Running Total |
|-------|-----------------|---------------|
| Phases 0–8 (done) | 327 ARA tests | 1,004 |
| Phase 9 | ~45 | ~1,049 |
| Phase 10 | ~40 | ~1,089 |
| Phase 11 | ~45 | ~1,134 |
| Phase 12 | ~55 | ~1,189 |
| Phase 13 | ~30 | ~1,219 |
| Phase 14 | ~35 | ~1,254 |
| **Target** | **~250 new** | **~1,250+** |

---

## Version Targets

| Phase | Version | Tag |
|-------|---------|-----|
| 0–8 (done) | 8.0.0-beta | v8.0.0-beta |
| 9 | 8.1.0-beta | v8.1.0-beta |
| 10 | 8.2.0-beta | v8.2.0-beta |
| 11 | 8.3.0-beta | v8.3.0-beta |
| 12 | 8.4.0-beta | v8.4.0-beta |
| 13 | 8.5.0-beta | v8.5.0-beta |
| 14 | 9.0.0 | v9.0.0 |

Phase 14 drops the `-beta` suffix — all ARA-001 design requirements are met.

---

## Appendix: Gap → Phase Mapping

| Gap | Description | Phase |
|-----|-------------|-------|
| G1 | Actual file promotion | 11 |
| G2 | 3-tier authority model | 9 |
| G3 | Prompt injection defence | 10 |
| G4 | Audit log (HMAC + hash chain) | 10 |
| G5 | Credential storage (system keychain) | 10 |
| G6 | Morning Dashboard (TUI + Web) | 13 |
| G7 | Role management CLI | 9 |
| G8 | First-time setup wizard | 12 |
| G9 | `orion sessions` command | 12 |
| G10 | `orion rollback` command | 12 |
| G11 | `orion plan --review` command | 12 |
| G12 | Goal queuing + priority interrupts | 14 |
| G13 | Post-promotion rollback (`undo-promote`) | 11 |
| G14 | Conflict resolution (branch + merge) | 11 |
| G15 | Re-planning during execution | 12 |
| G16 | Auth method switching | 12 |
| G17 | ARA settings | 12 |
| G18 | Role schema missing fields | 9 |
| G19 | Task estimation calibration | 14 |
| G20 | Test layer organization | 14 |
| G21 | Lifecycle cleanup commands | 12 |
| G22 | Multi-user isolation | 14 |
| G23 | Session export | 14 |

---

## Success Criteria

ARA is **complete** when:

1. All 23 gaps are closed
2. All ARA-001 sections (§1–§14) are fully implemented
3. All 13 Appendix C solutions are operational
4. Test count ≥ 1,250
5. `ruff check` clean
6. Version 9.0.0 tagged and pushed
7. README reflects final state
8. ARA-001 status changed from "Draft" to "Implemented"
