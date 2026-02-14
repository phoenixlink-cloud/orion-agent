# ARA-001: Autonomous Role Architecture

**Status:** Draft
**Author:** Jaco / Orion Design Sessions
**Date:** 2026-02-14
**Branch:** TBD (feature/ara-phase-0)
**Related:** NLA-001, NLA-002

---

## 1. Overview

The Autonomous Role Architecture (ARA) enables Orion to work independently within
user-defined role boundaries, governed by AEGIS safety gates, inside a hardened
Docker sandbox. Users assign a role and a goal; Orion decomposes the goal into
tasks and executes them autonomously — checkpointing progress, logging decisions,
and pausing for approval when confidence is low or actions cross security boundaries.

### Core Principles

1. **Governed autonomy** — AEGIS enforces boundaries at every step
2. **Transparency** — Every decision is logged and explainable
3. **Sandbox-first** — All autonomous work happens in isolation
4. **User control** — User defines roles, limits, and auth method
5. **Async-first** — Orion works while the user is away

---

## 2. Role Profile System

### 2.1 User-Configurable (Not Hardcoded)

Roles are defined in YAML (`~/.orion/roles.yaml` or `.orion/roles.yaml` per-project)
and editable via CLI (`orion role create`) or Web UI settings panel.

### 2.2 Role Schema

```yaml
roles:
  software_engineer:
    enabled: true
    display_name: "Software Engineer"
    description: "Writes, refactors, and tests code"

    competencies:                    # Required (min 1)
      - "Code quality and best practices"
      - "Unit and integration testing"
      - "Git workflow and version control"

    authority:
      autonomous:                    # Required (min 1) — no approval needed
        - "Write/modify code in sandbox"
        - "Run tests"
        - "Create feature branches"
      requires_approval:             # Required — pauses and asks
        - "Merge to main"
        - "Add/remove dependencies"
        - "Change database schema"
      forbidden:                     # Required — hard block, no override
        - "Deploy to production"
        - "Delete repositories"
        - "Modify CI/CD pipeline"

    confidence_thresholds:           # Optional (defaults shown)
      auto_execute: 0.90
      execute_and_flag: 0.70
      pause_and_ask: 0.50

    risk_tolerance: "medium"         # low | medium | high
    auth_method: "pin"               # pin | totp — see Section 7

    success_criteria:                # Optional
      - "All tests pass"
      - "Code coverage > 80%"
      - "Follows project style guide"
```

### 2.3 Required Fields

| Field              | Required | Validation                               |
|--------------------|----------|------------------------------------------|
| display_name       | Yes      | Non-empty string                         |
| description        | Yes      | Non-empty string                         |
| competencies       | Yes      | Min 1 entry                              |
| autonomous actions | Yes      | Min 1 entry                              |
| requires_approval  | Yes      | Min 1 entry                              |
| forbidden actions  | Yes      | Min 1 entry, no overlap with autonomous  |
| auth_method        | Yes      | "pin" or "totp"                          |
| thresholds         | No       | Defaults: 0.90 / 0.70 / 0.50            |
| risk_tolerance     | No       | Defaults: "medium"                       |
| success_criteria   | No       | Informational                            |

### 2.4 Starter Templates

Orion ships with 4 starter templates the user can enable and customize:

- **Software Engineer** — write/test/refactor code
- **Technical Writer** — documentation and READMEs
- **QA Engineer** — write tests, run coverage analysis
- **DevOps Engineer** — Dockerfiles, CI configs, infrastructure

---

## 3. Security Architecture

### 3.1 Two-Layer Restriction Model

#### Layer 1: AEGIS Base Restrictions (non-negotiable, hardcoded)

These apply to ALL roles and CANNOT be weakened by the user:

- Cannot execute outside sandbox environment
- Cannot access files outside workspace boundaries
- Cannot make network requests without explicit approval
- Cannot delete the workspace root or .git directory
- Cannot modify AEGIS governance configuration
- Cannot escalate its own authority level
- Cannot bypass the approval queue
- Cannot run with no role assigned

#### Layer 2: User-Defined Hard Limits (per role)

User adds role-specific restrictions on top of AEGIS base. These are
shown alongside AEGIS restrictions in the UI so the full picture is clear.

#### Enforcement Order

```
Action requested
  → AEGIS Base check (hardcoded, non-negotiable)
  → User Hard Limit check (per role, user-defined)
  → Role Authority check (autonomous / requires_approval)
  → Confidence Gate (auto / flag / pause)
  → Execute or block
```

### 3.2 Docker Sandbox Hardening

Current sandbox (`workspace_sandbox.py`) already provides:
- Docker + local backends with auto-detection
- Memory/CPU/PID limits
- Network disabled by default
- Session lifecycle (create → diff → promote → destroy)

ARA adds hardened Docker flags:

```bash
docker run -d \
  --name orion-ara-{session_id} \
  --memory 512m \
  --cpus 2.0 \
  --pids-limit 128 \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --no-new-privileges \
  --cap-drop ALL \
  --user 1000:1000 \
  --security-opt seccomp=orion-seccomp.json \
  -v {workspace}:/workspace:ro \
  -v {writable_overlay}:/workspace-edits:rw \
  python:3.11-slim
```

Key additions:
- `--no-new-privileges` — prevents privilege escalation
- `--cap-drop ALL` — drops all Linux capabilities
- `--user 1000:1000` — non-root execution
- `--security-opt seccomp` — restricts system calls
- Workspace mounted **read-only**, edits to writable overlay only

### 3.3 AEGIS Traffic Gate

Nothing leaves the sandbox without AEGIS approval:

```
Docker Container (hardened, --network none)
  │
  ├─ File changes  → AEGIS gate → promote/reject
  ├─ Email send    → AEGIS gate → single recipient only
  ├─ Git push      → AEGIS gate → user approval + PIN/TOTP
  └─ API calls     → BLOCKED (network none)
```

### 3.4 Prompt Injection Defence

- Goal text is sanitized by AEGIS before reaching the LLM
- Adversarial patterns stripped ("ignore previous", "override role")
- Goal inserted into structured templates, never concatenated raw
- LLM task output validated against role authority before queuing

### 3.5 Audit Log Integrity

- Append-only log with HMAC signature per entry
- Hash chain (each entry includes hash of previous)
- Tampering detected on next read if chain breaks
- Logs stored outside sandbox (host filesystem)

### 3.6 Credential Storage

| Credential    | Storage                                           |
|---------------|---------------------------------------------------|
| Email creds   | System keychain (Win Credential Store / macOS)    |
| PIN hash      | System keychain (bcrypt)                          |
| TOTP secret   | System keychain (encrypted)                       |
| API keys      | `.env` file (existing pattern)                    |
| Session tokens| Memory only (ephemeral, per-session)              |

### 3.7 Session Authentication

- Daemon listens on Unix socket (Linux/Mac) or named pipe (Windows)
- Socket permissions: user-only (0600)
- Alternative: localhost-only with auth token generated at session start
- No unauthenticated access to running sessions

---

## 4. Email Notification System

### 4.1 Core Principle: Send-Only, Never Read

- SMTP send capability only — no IMAP/POP built (not disabled, not implemented)
- Single sender address (user-provided, user-authenticated on machine)
- Single recipient (user-defined, AEGIS-locked)
- Template-only emails (no freeform composition)
- Rate-limited: max 5 emails per session

### 4.2 AEGIS Email Restrictions (non-negotiable)

- Send only to user-defined recipient
- Never read incoming mail
- Never execute instructions from email (anti-injection)
- Never access contacts/drafts/history
- Never attach files unless user pre-approves attachment types
- Never include secrets/tokens/keys in email body

### 4.3 Changing Recipient

Changing the TO address requires re-authentication through the settings UI.
Cannot be changed via config file edit alone.

### 4.4 Email Template

```
Subject: [Orion] Session Complete: "{goal_name}"

Orion Autonomous Session Report
────────────────────────────────
Role: {role_name}
Goal: {goal_description}
Duration: {duration}
Status: {status}

Tasks Completed: {completed}/{total}
{task_list}

Needs Your Review: {review_count}
{review_items}

Cost: ${cost} ({llm_calls} LLM calls)

→ Open dashboard: orion review
────────────────────────────────
This is an automated notification from Orion Agent.
Orion does not read or act on replies to this email.
```

---

## 5. Session Lifecycle

### 5.1 Starting a Session

**CLI:**
```bash
orion work --role "Software Engineer" "Implement user authentication"
```

**Web UI:** "Start Autonomous Task" modal → select role, describe goal, set limits.

### 5.2 Session State Schema

```python
@dataclass
class SessionState:
    session_id: str
    role: str                          # Role profile name
    goal: str                          # User's high-level objective
    task_dag: dict                     # Task dependency graph (JSON)
    current_task_id: str | None        # Currently executing task
    status: str                        # running | paused | completed | failed
    checkpoint_history: list[str]      # List of checkpoint IDs
    decision_log: list[dict]           # Why Orion chose approach A over B
    cost_tracker: CostTracker          # LLM calls, estimated cost
    start_time: float                  # Session start timestamp
    time_limit_seconds: int | None     # Max session duration
    cost_limit: float | None           # Max API spend
    error_count: int                   # Consecutive errors
    sandbox_session_id: str            # Linked sandbox session
    sandbox_branch: str                # e.g. "orion-ara/session-4f2a"
```

Serialized to `~/.orion/sessions/{session_id}/state.json`.

### 5.3 Session Controls

| Command             | Action                                         |
|---------------------|-------------------------------------------------|
| `orion work`        | Start new autonomous session                   |
| `orion status`      | Live view of current session                   |
| `orion pause`       | Checkpoint and stop (resume later)             |
| `orion resume`      | Pick up from last checkpoint                   |
| `orion cancel`      | Abort, rollback to last checkpoint             |
| `orion review`      | Morning review dashboard                       |
| `orion sessions`    | List all active/completed sessions             |

### 5.4 Stop Conditions

A session stops automatically when:

1. **Goal complete** — all tasks in DAG are done
2. **Time limit reached** — configurable per session
3. **Cost limit reached** — max API spend exceeded
4. **Confidence collapse** — 3+ consecutive tasks below 50% confidence
5. **Error threshold** — 5+ consecutive failures
6. **User interrupt** — `orion pause` or `orion cancel`

### 5.5 Daemon Mode

- CLI: `orion work` starts a background process
- Windows: detached `pythonw.exe` process (Phase 1), Windows Service (Phase 2)
- Linux/Mac: `nohup` + PID file (Phase 1), systemd service (Phase 2)
- State persisted in `~/.orion/sessions/`
- Health check via `orion status`
- Survives terminal close; does NOT survive reboot (by design — requires explicit restart)

---

## 6. Goal Decomposition Engine

### 6.1 Goal → Task DAG

User provides a high-level goal. Orion decomposes it into a dependency graph:

```
User: "Implement user authentication"
  │
  ├─ Task 1: Design auth schema (no deps)
  ├─ Task 2: Write user model (depends on 1)
  ├─ Task 3: Create login endpoint (depends on 2)
  ├─ Task 4: Create registration endpoint (depends on 2)
  ├─ Task 5: Add password hashing (depends on 2)
  ├─ Task 6: Add JWT token generation (depends on 3)
  ├─ Task 7: Write unit tests (depends on 3, 4, 5)
  └─ Task 8: Write integration tests (depends on 6, 7)
```

### 6.2 Decomposition Process

1. LLM call with structured prompt: role context + goal + institutional memory
2. Output: JSON task list with dependencies
3. AEGIS validates every task against role authority (plan-time gate)
4. User can review/edit the plan: `orion plan --review`
5. Approved plan enters execution queue

### 6.3 Execution Order

- Tasks execute in dependency order (topological sort)
- Independent tasks can run in sequence (not parallel in Phase 1)
- If a task fails or is low-confidence, dependent tasks are blocked
- Non-dependent tasks continue

### 6.4 Re-planning

Every N tasks (configurable, default 5), Orion re-evaluates:
- Is the current plan still aligned with the original goal?
- Have any completed tasks changed assumptions?
- Should remaining tasks be re-decomposed?

This prevents drift on long-running sessions.

---

## 7. Authentication: PIN and TOTP

### 7.1 Design Principle

Both PIN and TOTP are implemented and wired. The user selects their
preferred method in the role settings. PIN is the default for simplicity;
TOTP is available for users who want stronger security.

### 7.2 When Authentication Is Required

| Action                              | Auth Required | Why                          |
|-------------------------------------|---------------|------------------------------|
| Start autonomous session            | No            | User is present (implicit)   |
| Execute tasks in sandbox            | No            | Sandbox is isolated           |
| Checkpoint progress                 | No            | Internal to sandbox           |
| Send email notification             | No            | AEGIS-gated, template-only   |
| **Promote changes to workspace**    | **Yes**       | Crosses sandbox boundary     |
| **Merge to any branch**             | **Yes**       | Irreversible action          |
| **Change role configuration**       | **Yes**       | Prevents self-modification   |
| **Change auth method**              | **Yes**       | Prevents downgrade attacks   |

### 7.3 User Selection in Role Settings

```yaml
roles:
  software_engineer:
    auth_method: "pin"    # or "totp"
```

**Settings UI:**

```
┌─────────────────────────────────────────────────────────┐
│ 🔐 Promotion Authentication                             │
│                                                          │
│ ℹ Required when Orion promotes sandbox changes to your  │
│   real workspace or merges branches.                     │
│                                                          │
│ Method: (●) PIN    ( ) TOTP (Google Authenticator)      │
│                                                          │
│ [Configure Selected Method]                              │
└─────────────────────────────────────────────────────────┘
```

### 7.4 PIN Flow

#### Setup

```
┌─────────────────────────────────────────────────────────┐
│ Set Promotion PIN                                        │
│                                                          │
│ This PIN is required when Orion wants to promote         │
│ sandbox work to your real workspace.                     │
│                                                          │
│ PIN (6 digits):  [••••••]                                │
│ Confirm PIN:     [••••••]                                │
│                                                          │
│ ⚠ Stored as bcrypt hash in your system keychain.        │
│   Orion never sees the plaintext. AEGIS validates        │
│   against the hash only.                                 │
│                                                          │
│ [Save PIN]                                               │
└─────────────────────────────────────────────────────────┘
```

#### Promotion Flow (PIN)

```
Orion completes autonomous work
  → Orion: "Ready to promote 4 files to workspace. Enter PIN."
  → User enters PIN in CLI or Web UI
  → AEGIS: bcrypt_verify(input, stored_hash)
  → Match? → Promote files
  → No match? → 3 attempts, then lock for 15 minutes
```

#### CLI Flow

```
$ orion review
┌─ Morning Review ─────────────────────────────────────┐
│ Session: Implement user authentication               │
│ Status: Completed (8/8 tasks)                        │
│ ...                                                  │
│                                                      │
│ Ready to promote 4 changed files.                    │
│ Enter promotion PIN: ••••••                          │
│ ✓ PIN accepted. Promoting files...                   │
│ ✓ 4 files promoted to workspace.                     │
└──────────────────────────────────────────────────────┘
```

#### Web UI Flow

```
┌─────────────────────────────────────────────────────────┐
│ 🔐 Promote Changes                                      │
│                                                          │
│ Orion wants to apply 4 file changes to your workspace:  │
│                                                          │
│   M  src/auth/models.py                                  │
│   A  src/auth/endpoints.py                               │
│   A  src/auth/jwt.py                                     │
│   A  tests/test_auth.py                                  │
│                                                          │
│ [View Diff]                                              │
│                                                          │
│ Enter PIN: [••••••]                                      │
│                                                          │
│ [Approve & Promote]  [Reject]                            │
└─────────────────────────────────────────────────────────┘
```

### 7.5 TOTP Flow (Google Authenticator / Authy)

#### Setup

```
┌─────────────────────────────────────────────────────────┐
│ Set Up TOTP Authentication                               │
│                                                          │
│ Scan this QR code with Google Authenticator, Authy,     │
│ or any TOTP app:                                         │
│                                                          │
│         ┌───────────────┐                                │
│         │  ██ ██ ██ ██  │                                │
│         │  ██    ██ ██  │  (QR code)                     │
│         │  ██ ██    ██  │                                │
│         │  ██ ██ ██ ██  │                                │
│         └───────────────┘                                │
│                                                          │
│ Or enter manually: JBSW Y3DP EHPK 3PXP                  │
│                                                          │
│ Verify setup — enter current code: [______]              │
│                                                          │
│ ⚠ The secret is stored encrypted in your system          │
│   keychain. Orion never sees it. AEGIS generates codes   │
│   server-side and compares.                              │
│                                                          │
│ Backup codes (save these):                               │
│   1. 8F3K-2M9P    4. 7H2L-9K4R                          │
│   2. 4J7N-5T1W    5. 3D6F-8V2X                          │
│   3. 9R2S-6B4Q    6. 1N5M-7C3Y                          │
│                                                          │
│ [Verify & Save]                                          │
└─────────────────────────────────────────────────────────┘
```

#### Promotion Flow (TOTP)

```
Orion completes autonomous work
  → Orion: "Ready to promote 4 files. Enter TOTP code."
  → User opens authenticator app, enters 6-digit code
  → AEGIS: verify_totp(input, stored_secret)
  → Valid? → Promote files
  → Invalid? → "Code expired or incorrect. Try again."
  → 5 failed attempts → lock for 30 minutes
```

#### CLI Flow

```
$ orion review
┌─ Morning Review ─────────────────────────────────────┐
│ ...                                                  │
│ Ready to promote 4 changed files.                    │
│ Enter TOTP code from your authenticator: ______      │
│ ✓ Code accepted. Promoting files...                  │
│ ✓ 4 files promoted to workspace.                     │
└──────────────────────────────────────────────────────┘
```

### 7.6 Switching Methods

Changing auth method requires current auth verification first:

```
User selects "Switch to TOTP"
  → "Enter current PIN to confirm: ______"
  → PIN verified
  → TOTP setup flow begins
  → TOTP verified
  → Auth method updated to TOTP
  → Old PIN hash deleted from keychain
```

This prevents an attacker who gains file access from downgrading auth.

### 7.7 Implementation Phasing

| Phase | PIN                    | TOTP                          |
|-------|------------------------|-------------------------------|
| 1     | Fully implemented      | Wired + configured            |
|       | Used for testing       | Requires user setup to test   |
| 2     | Production-ready       | Production-ready              |

Both codepaths exist from Phase 1. PIN is the default and used for
development/testing. TOTP is wired and functional but requires the user
to complete the authenticator setup flow to activate.

---

## 8. Checkpoint System

### 8.1 What Is a Checkpoint

A checkpoint is a snapshot of the session at a point in time:

- Git commit in the sandbox branch (`orion-ara/{session_id}`)
- Serialized `SessionState` JSON
- Decision log up to this point
- Cost tracker snapshot

### 8.2 When Checkpoints Are Created

- Before any "medium confidence" task (70-90%)
- After every task completion
- On `orion pause`
- Before any action that crosses sandbox boundary

### 8.3 Rollback

```bash
orion rollback {checkpoint_id}
```

Restores the sandbox branch to the checkpoint commit and loads the
saved SessionState. All work after the checkpoint is discarded.

---

## 9. Morning Dashboard

### 9.1 Access Points

- **CLI:** `orion review` — interactive TUI
- **Web UI:** Sidebar button "Morning Review" (badge count when work is ready)
- **Startup:** REPL shows notification: "Orion completed 12 tasks overnight. Run `orion review`."

### 9.2 Dashboard Sections

See `ARA-dashboard-mockup.html` for the visual mockup.

#### Core Sections (from mockup)

1. **Current Status & Activity** — what Orion is doing now (idle/working/blocked)
2. **Task Queue** — kanban-style: queued / in-progress / completed / needs review
3. **Consent Gates** — pending approval items (visually prominent, badge count)
4. **Work Output & Deliverables** — completed artifacts with review/approve actions
5. **Performance Analytics** — tasks completed, success rate, hours active, cost
6. **Memory & Context** — searchable view of Orion's working knowledge
7. **Job Role Configuration** — current role, capabilities, boundaries

#### Additions (from review)

8. **AEGIS Status** — shield icon in header, security dashboard in sidebar
9. **Cost/Budget Tracking** — progress bar against session cost limit
10. **Confidence Scores** — per-task confidence visible on task cards
11. **Role Badge** — current role shown in header at all times
12. **Sandbox Indicator** — Docker/local, network status, branch name
13. **Time Budget** — progress bar against session time limit
14. **Decision Log Drill-Down** — click task → see reasoning

### 9.3 CLI Review Flow (Interactive TUI)

```
$ orion review

┌─ Orion Morning Review ──────────────────────────────────┐
│ Session: Implement user authentication                   │
│ Role: Software Engineer  |  Duration: 4h 22m            │
│ Cost: $0.47 (38 LLM calls)  |  Sandbox: Docker 🐳      │
├──────────────────────────────────────────────────────────┤
│                                                          │
│ ✅ Design auth schema              conf: 95%            │
│ ✅ Write user model                conf: 91%            │
│ ✅ Create login endpoint           conf: 88%            │
│ ✅ Create registration endpoint    conf: 92%            │
│ ✅ Add password hashing            conf: 94%            │
│ ✅ Add JWT token generation        conf: 87%            │
│ ✅ Write unit tests (14 pass)      conf: 90%            │
│ ✅ Write integration tests (6 pass) conf: 85%           │
│                                                          │
│ ⏸ APPROVAL NEEDED:                                      │
│   1. Add bcrypt dependency                               │
│   2. OAuth provider choice (conf: 62% — needs input)    │
│                                                          │
│ [a]pprove  [r]eject  [d]iff  [l]og  [n]ext  [q]uit     │
└──────────────────────────────────────────────────────────┘
```

### 9.4 Design Principles

- **Transparency over abstraction** — drill down into any decision
- **Async-first** — designed for checking in, not micromanaging
- **Conversation as escape hatch** — persistent chat panel (Web UI)

---

## 10. Conflict Resolution

### 10.1 Branch Strategy

All ARA work happens on a dedicated branch: `orion-ara/{session_id}`.
The user's working tree is never modified during autonomous work.

### 10.2 Promotion = Merge Review

When the user approves promotion:
1. Diff shown between sandbox branch and current workspace
2. If no conflicts → fast-forward merge
3. If conflicts → shown in dashboard with merge tool
4. User resolves conflicts, not Orion

### 10.3 Rejection

User can reject all changes or individual files. Rejected changes
remain on the sandbox branch for future reference.

---

## 11. Multi-Session Management

- One active session per workspace
- Multiple workspaces can have concurrent sessions
- `orion sessions` lists all active/completed sessions
- Each session is fully isolated (own sandbox, own branch)

---

## 12. First-Time Setup

```
$ orion autonomous setup

Step 1/5: Checking prerequisites...
  ✓ Docker installed and running
  ✓ AEGIS governance active
  ✓ Workspace sandbox functional

Step 2/5: Create or select a role
  → Using template: Software Engineer
  → Customize? [y/N]: N

Step 3/5: Set up authentication
  → Method: (●) PIN  ( ) TOTP
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
  ✓ All 6 scenarios passed.

Step 5/5: Ready!
  → Start your first session:
    orion work --role "Software Engineer" "Write unit tests for auth module"
```

---

## 13. Implementation Phases

### Phase 0: Hard Sandbox (prerequisite)
- Docker hardening (cap-drop, no-new-privileges, seccomp, non-root)
- Workspace mounted read-only with writable overlay
- AEGIS traffic gate (nothing leaves without approval)
- Verify isolation with escape-attempt tests

### Phase 1: Single Role Prototype
- RoleProfile dataclass + YAML loader + validator
- Role settings UI (CLI + Web)
- PIN authentication (setup + verification)
- TOTP authentication (wired + configured, requires user setup)
- Auth method selection in role settings
- AEGIS role authority gate
- Basic session lifecycle (start/pause/resume/cancel)
- Test on: "Write unit tests for existing module"

### Phase 2: Goal Engine + Execution Loop
- Goal → Task DAG decomposition (LLM-powered)
- Task execution loop with confidence gating
- Checkpoint system (git-based)
- Decision logging
- Cost tracking + time limits
- Stop conditions (5 types)
- Daemon mode (background process)

### Phase 3: Dashboard + Review
- Morning dashboard (CLI TUI + Web UI)
- `orion review` interactive flow
- Email notifications (send-only, AEGIS-gated)
- Notification settings UI
- Performance analytics

### Phase 4: Polish + Production
- Conflict resolution UI
- Audit log viewer
- Role dry-run testing
- Multi-session management
- Session export (`orion export-session`)
- TOTP full production testing

### Phase 5+ (Future)
- Multi-role collaboration
- Role switching within a session
- Table of Three multi-role (Engineer → QA → Writer pipeline)

---

## 14. Technical Architecture

```
User sets goal + assigns role
  ↓
Role Profile loaded → AEGIS validates role config
  ↓
Goal Decomposition (LLM) → Task DAG
  ↓
AEGIS validates every task at plan-time
  ↓
User reviews plan (optional: orion plan --review)
  ↓
Execution Loop (in hardened Docker sandbox):
  ┌─────────────────────────────────────┐
  │  For each task in dependency order: │
  │    1. Execute task                  │
  │    2. AEGIS validates action        │
  │    3. Check confidence              │
  │    4. Checkpoint progress           │
  │    5. Log decision + rationale      │
  │    6. Check stop conditions         │
  │    7. Continue or pause             │
  └─────────────────────────────────────┘
  ↓
Session Complete → Email notification (if enabled)
  ↓
Morning Dashboard → User reviews + approves/rejects
  ↓
PIN/TOTP verification → Promote to workspace (or reject)
```

---

## Appendix A: Existing Infrastructure

| Component                | File                                    | Status      |
|--------------------------|-----------------------------------------|-------------|
| Workspace sandbox        | security/workspace_sandbox.py (851 LOC) | Exists      |
| Code execution sandbox   | security/sandbox.py (307 LOC)           | Exists      |
| AEGIS governance         | core/agents/aegis.py                    | Exists      |
| Sandbox settings         | cli/settings_manager.py                 | Exists      |
| Router sandbox init      | core/agents/router.py                   | Exists      |
| NLA pipeline             | core/understanding/*.py                 | Exists      |
| 3-tier memory            | core/memory/*.py                        | Exists      |
| Web UI (Next.js)         | orion-web/                              | Exists      |
| CLI REPL                 | cli/repl.py                             | Exists      |

## Appendix B: Dashboard Mockup

See `docs/architecture/ARA-dashboard-mockup.html` for the full
interactive mockup of the AI Employee Dashboard.

Dashboard review identified 8 enhancement areas:
1. AEGIS visibility (security status indicator)
2. Cost/budget tracking
3. Confidence scores on task cards
4. Morning Review dedicated view
5. Role badge in header
6. Sandbox indicator
7. Time/cost budget progress bars
8. Decision log drill-down

---

## Appendix C: Gap Analysis & Solutions

13 gaps were identified during design review. All are addressed below
with full design solutions and assigned to implementation phases.

### C.1 Failure Recovery Paths

**Problem:** Orion stops on failure but has no defined recovery behaviour.

**Solution: Recovery State Machine**

```
RUNNING → INTERRUPTED → RECOVERABLE → RESUMED
              │                          ↑
              ├→ UNRECOVERABLE → ARCHIVED │
              │                           │
              └→ STALE → (user decides) ──┘
```

| Failure Type              | Detection                        | Recovery                                              | Mode          |
|---------------------------|----------------------------------|-------------------------------------------------------|---------------|
| LLM API down              | HTTP 5xx / timeout               | Backoff (30s→1m→5m→15m), max 3 retries → checkpoint + pause | Auto → manual |
| Machine sleep/hibernate   | Heartbeat file stale > 2 min     | On wake: detect interrupted session, offer resume     | Manual        |
| Docker daemon crash       | Container not found on inspect   | If overlay intact → restart container, resume. Else → rollback to checkpoint | Auto if overlay OK |
| Disk full                 | OSError                          | Emergency checkpoint, prune oldest checkpoints, notify | Manual        |
| Partial task failure      | Task crashes mid-write           | Atomic execution: writes go to `.staging/`, committed on success, discarded on failure | Auto          |
| Network loss (host)       | Can't reach LLM API              | Same as LLM API down                                 | Auto → manual |
| OOM kill                  | Container exit code 137          | Increase memory 50% (up to cap), restart, resume      | Auto once     |

**Heartbeat file:** Daemon writes `~/.orion/sessions/{id}/heartbeat` every 30s.
On startup, sessions where `state.json` says running but heartbeat > 2 min old
are flagged `INTERRUPTED` and surfaced in `orion status`.

**Atomic task execution:**
```
Pre-task checkpoint
  → Task writes to /workspace-edits/.staging/
  → Success? → mv .staging/* → /workspace-edits/
  → Failure? → rm -rf .staging/ → state unchanged
```

**Session state addition:**
```python
recovery_state: str  # "normal" | "interrupted" | "recoverable" | "unrecoverable"
last_heartbeat: float
```

**Phase:** 2

---

### C.2 Resource Cleanup / TTL

**Problem:** Sessions, checkpoints, containers, logs accumulate without bound.

**Solution: Session Lifecycle Manager**

```python
SESSION_TTL_DAYS = 30              # Auto-archive after 30 days
MAX_CHECKPOINTS_PER_SESSION = 20   # Prune older
MAX_TOTAL_SESSION_DISK_MB = 500    # Per session
MAX_SESSIONS_RETAINED = 50         # Total
LOG_ROTATION_MAX_MB = 50           # Per log file
ORPHAN_CONTAINER_TTL_HOURS = 24    # Kill containers with no active session
```

| Trigger                       | What Gets Cleaned                                  |
|-------------------------------|----------------------------------------------------|
| Session promoted              | Sandbox branch, overlay, staging. Checkpoints → last 3 |
| Session rejected              | All artifacts deleted                              |
| TTL expires (30 days)         | Archive to `~/.orion/archive/`, then delete        |
| `orion sessions cleanup`      | Interactive: user picks what to purge              |
| Disk pressure (>80%)          | Auto-prune oldest checkpoints, then oldest archives |
| Orphan containers (hourly)    | Kill containers with no matching active session    |

**Checkpoint pruning strategy:**
- Last hour: keep all
- Last 24 hours: keep every 5th
- Older than 24h: keep first and last only
- After promotion: keep last 3 total

**Git branch cleanup:** Orphaned `orion-ara/*` branches (no matching session)
cleaned via `orion sessions cleanup --branches`.

**Phase:** 1

---

### C.3 Learning From Outcomes

**Problem:** Orion doesn't improve from user approval/rejection patterns.

**Solution: Outcome Feedback Store**

```python
@dataclass
class TaskOutcome:
    task_type: str              # "write_code", "write_tests", "refactor", "docs"
    role: str
    confidence: float           # Orion's confidence at execution
    approved: bool
    revision_requested: bool
    rejection_reason: str | None
    estimated_duration: int     # Predicted (seconds)
    actual_duration: int        # Actual (seconds)
    timestamp: float
```

Stored in `~/.orion/feedback/outcomes.jsonl` (append-only, one JSON per line).

**Usage:**

1. **Confidence calibration:**
   `calibrated_confidence = raw_confidence × historical_approval_rate`

2. **Goal decomposition improvement:** Prompt includes last 5 rejections
   with reasons for the active role.

3. **Estimation calibration:**
   `calibrated_estimate = raw_estimate × (avg_actual / avg_estimated)`

4. **Dashboard surfacing:** "Orion's accuracy: 94% approval rate this month
   (was 87% last month)"

**Privacy:** All data local-only. `orion feedback reset` clears history.
Feedback is per-role.

**Phase:** 4

---

### C.4 Task Estimation Calibration

**Problem:** Time/cost estimates are guesswork with no data.

**Solution:** Integrated with C.3 feedback store.

**Phase 1 (no history):**
- LLM provides raw estimate during decomposition
- Display as range: "Est. 15-30 min" (2× uncertainty band)
- Show "No historical data — estimates are approximate"

**Phase 2+ (with history):**
```python
def calibrate(task_type, role, raw_estimate_seconds):
    history = get_outcomes(task_type=task_type, role=role)
    if len(history) < 5:
        return (raw_estimate_seconds, raw_estimate_seconds * 2)
    ratio = mean(o.actual / o.estimated for o in history)
    std = stdev(...)
    calibrated = raw_estimate_seconds * ratio
    return (int(calibrated - std), int(calibrated + std))
```

**Cost estimation:** Track LLM calls per task type from history.
Apply current model pricing: "Est. cost: $0.12-0.25 (based on 8 similar tasks)"

**Phase:** 3

---

### C.5 Goal Queuing / Priority Interrupts

**Problem:** One goal at a time is limiting.

**Solution: Goal Queue**

```python
@dataclass
class GoalQueue:
    workspace: str
    active_goal: str | None
    queued_goals: list[QueuedGoal]     # FIFO, user can reorder
    paused_goals: list[PausedGoal]     # Interrupted, resumable

@dataclass
class QueuedGoal:
    goal_id: str
    description: str
    role: str
    priority: str           # "normal" | "urgent"
    depends_on: str | None  # goal_id of prerequisite
    added_at: float
```

**CLI:**
```bash
orion work --role "SE" "Implement auth module"
orion work --queue --role "TW" "Write docs for auth module"
orion work --urgent --role "SE" "Fix critical login bug"
orion queue                # View queue
orion queue move 3 1       # Reorder
```

**Priority interrupt:** Current goal checkpointed + paused → urgent starts →
on completion → previous resumes.

**Goal dependencies:** B `depends_on` A means B stays queued until A is
promoted. If A is rejected, B is flagged for review.

**Phase:** 4

---

### C.6 Stale Workspace Detection

**Problem:** External changes during autonomous work make sandbox stale.

**Solution: Drift Monitor**

```python
class WorkspaceDriftMonitor:
    def check_drift(self, session) -> DriftReport:
        base_commit = session.sandbox_base_commit
        current_commit = get_workspace_head(session.workspace_path)
        if base_commit == current_commit:
            return DriftReport(drifted=False)
        changed_files = git_diff_names(base_commit, current_commit)
        orion_files = session.modified_files
        conflicts = set(changed_files) & set(orion_files)
        return DriftReport(
            drifted=True,
            workspace_changes=len(changed_files),
            conflict_files=list(conflicts),
            severity="high" if conflicts else "low"
        )
```

**When to check:**
- Every 5 tasks → low severity: log + continue; high severity: pause + notify
- Before promotion → always; show conflicts in promotion UI
- On `orion resume` → warn if workspace moved since pause

**Session state addition:**
```python
sandbox_base_commit: str       # Git HEAD when sandbox created
drift_checks: list[dict]       # History of drift results
```

**Phase:** 2

---

### C.7 Secrets Scanner Pre-Promotion

**Problem:** LLM-generated code may contain hardcoded secrets.

**Solution: AEGIS Secret Scanner**

Runs automatically before every promotion. Part of the AEGIS traffic gate.

```python
class SecretScanner:
    PATTERNS = {
        "aws_access_key":    r"AKIA[0-9A-Z]{16}",
        "aws_secret_key":    r"[0-9a-zA-Z/+]{40}",
        "github_token":      r"gh[pousr]_[A-Za-z0-9_]{36,}",
        "jwt_token":         r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+",
        "generic_api_key":   r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"][A-Za-z0-9]{20,}['\"]",
        "generic_password":  r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
        "private_key":       r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----",
        "connection_string": r"(?i)(mongodb|postgres|mysql|redis):\/\/[^\s]+@[^\s]+",
        "slack_webhook":     r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+",
        "generic_secret":    r"(?i)(secret|token|credential)\s*[:=]\s*['\"][A-Za-z0-9+/=]{20,}['\"]",
    }
```

**Enforcement:**
- 0 findings → proceed to PIN/TOTP
- 1+ findings → **BLOCK** promotion, show findings with redacted values
- User options: mark false positive / edit file / add to allowlist / cancel

**User-managed allowlist:** `~/.orion/secrets_allowlist.yaml`
```yaml
allowlist:
  - pattern: "EXAMPLE_API_KEY"
    reason: "Used in documentation"
  - file: "tests/**"
    reason: "Test fixtures use fake credentials"
```

**Phase:** 1

---

### C.8 Output Size Limits

**Problem:** Runaway generation could fill disk or produce unusable output.

**Solution: AEGIS Write Limits**

```python
MAX_SINGLE_FILE_SIZE_MB = 10
MAX_FILES_CREATED_PER_SESSION = 100
MAX_FILES_MODIFIED_PER_SESSION = 200
MAX_TOTAL_WRITE_VOLUME_MB = 200
MAX_SINGLE_FILE_LINES = 5000
```

Enforced before every file write in the sandbox. Any violation → block write,
log to decision log, continue to next task.

User can lower limits per role but cannot exceed AEGIS ceilings:
```yaml
roles:
  software_engineer:
    write_limits:
      max_file_size_mb: 5       # User can lower, not raise above 10
      max_files_created: 50
```

**Phase:** 1

---

### C.9 Post-Promotion Rollback

**Problem:** User promotes, then realizes work is wrong.

**Solution: Promotion Tagging + Undo**

On every promotion:
```bash
git tag orion-pre-promote/{session_id} HEAD       # Tag pre-state
git add . && git commit -m "orion(ara): {goal}"   # Apply changes
git tag orion-post-promote/{session_id} HEAD       # Tag post-state
```

Undo:
```bash
$ orion undo-promote {session_id}
# Creates a revert commit (non-destructive, history preserved)
# Original work preserved on tag orion-post-promote/{session_id}
```

Key: revert commit, not force-push. User can cherry-pick individual files.

**Phase:** 4

---

### C.10 Multi-User Isolation

**Problem:** Shared machines — users shouldn't see each other's data.

**Solution: OS-User Scoping**

All artifacts scoped to `~/.orion/` (per OS user home directory).

```python
class UserIsolation:
    def validate_session_access(self, session_path: Path) -> bool:
        user_orion_dir = Path.home() / ".orion"
        return session_path.resolve().is_relative_to(user_orion_dir.resolve())
```

- Containers named `orion-ara-{username}-{session_id}`
- PIN/TOTP per-user (different keychain entries)
- Shared workspace → each user gets own sandbox branch:
  `orion-ara/{username}/{session_id}`

**Phase:** 4

---

### C.11 Webhook / Chat Notifications

**Problem:** Email-only is limiting. Teams use Slack, Discord, Teams.

**Solution: Notification Provider Interface**

```python
class NotificationProvider(ABC):
    @abstractmethod
    async def send(self, notification: Notification) -> bool: ...
    @abstractmethod
    def validate_config(self) -> list[str]: ...

class EmailProvider(NotificationProvider): ...     # Already designed
class WebhookProvider(NotificationProvider): ...   # Slack, Discord, Teams, generic
class DesktopProvider(NotificationProvider): ...   # OS-native toast/notification
```

Same AEGIS rules for all providers:
- Single destination per provider
- Template-only payloads
- Rate-limited: max 5 per session
- Changing destination requires PIN/TOTP
- Send-only (never read responses)

Settings UI allows enabling multiple channels and selecting trigger events
(session complete, approval needed, error, cost limit 80%).

**Phase:** 3

---

### C.12 Dashboard WebSocket Channel

**Problem:** Dashboard needs real-time updates, not polling.

**Solution: ARA WebSocket Protocol**

New route: `/ws/ara/{session_id}`

Events:
```
status_change    — Session status changed
task_started     — New task began
task_completed   — Task finished (with result + confidence)
activity         — Human-readable activity update
progress         — Progress percentage updated
consent_request  — New approval needed (pushes to UI)
consent_resolved — Approval granted/denied
checkpoint       — Checkpoint created
drift_warning    — Workspace drift detected
cost_update      — Cost tracker updated
error            — Error occurred
session_complete — All work done
```

Message format:
```json
{
    "event": "task_completed",
    "session_id": "4f2a...",
    "timestamp": 1739512800,
    "data": {
        "task_id": "task-003",
        "task_name": "Create login endpoint",
        "confidence": 0.88,
        "duration_seconds": 340,
        "files_modified": ["src/auth/endpoints.py"],
        "next_task": "task-004"
    }
}
```

Fallback: If WebSocket drops, dashboard polls
`GET /api/ara/session/{id}/status` every 5 seconds.

**Phase:** 3

---

### C.13 ARA Integration Testing Strategy

**Problem:** Can't test autonomous workflows without hours and LLM credits.

**Solution: 5-Layer Test Strategy**

**Layer 1 — Unit tests (no LLM, no Docker):**
- Role validation, confidence gates, secret scanner, write limits,
  PIN/TOTP verification, session state serialization.
- Fast, run in CI on every commit.

**Layer 2 — Mock LLM integration tests:**
- `MockLLMProvider` returns pre-recorded responses.
- Tests goal decomposition, execution loop, checkpoint/restore.
- No API credits consumed.

**Layer 3 — Sandbox escape tests (Docker required):**
- Verify: can't access host filesystem, can't make network requests,
  can't escalate privileges, can't write to read-only workspace,
  PID/memory limits enforced.
- Run in CI with Docker.

**Layer 4 — Role boundary tests:**
- Verify AEGIS blocks forbidden actions, requires approval for
  restricted actions, base restrictions can't be overridden.

**Layer 5 — End-to-end smoke test:**
- Full session: goal → decompose → execute → checkpoint → review → promote.
- Uses mock LLM + real Docker sandbox.
- Verifies complete lifecycle including cleanup.

**CI integration:**
```yaml
test-ara-unit:     pytest tests/ara/ -m "not docker and not e2e"
test-ara-sandbox:  pytest tests/ara/ -m "docker" --timeout=120
test-ara-e2e:      pytest tests/ara/ -m "e2e" --timeout=300
```

**Phase:** 0 (escape tests), 1 (unit + role), 2 (mock LLM + e2e)

---

### Gap Summary

| # | Gap                          | Severity   | Phase |
|---|------------------------------|------------|-------|
| 1 | Failure recovery paths       | **High**   | 2     |
| 2 | Resource cleanup / TTL       | **High**   | 1     |
| 3 | Learning from outcomes       | Medium     | 4     |
| 4 | Task estimation calibration  | Medium     | 3     |
| 5 | Goal queuing / interrupts    | Medium     | 4     |
| 6 | Stale workspace detection    | Medium     | 2     |
| 7 | Secrets scanner              | **High**   | 1     |
| 8 | Output size limits           | Medium     | 1     |
| 9 | Post-promotion rollback      | Low        | 4     |
| 10| Multi-user isolation         | Low        | 4     |
| 11| Webhook notifications        | Low        | 3     |
| 12| Dashboard WebSocket          | Medium     | 3     |
| 13| ARA testing strategy         | **High**   | 0     |
