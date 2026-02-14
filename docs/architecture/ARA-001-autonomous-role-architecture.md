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
