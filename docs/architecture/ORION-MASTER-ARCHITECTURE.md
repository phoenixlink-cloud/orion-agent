# Orion Agent — Master Architecture & Structured Flow Reference

**Status:** Living Document
**Author:** Jaco / Orion Design Sessions
**Date:** 2026-02-16
**Version:** v9.0.0+
**Purpose:** Definitive reference for the entire Orion/AEGIS system.
Use this when designing any new add-on to understand **where** it plugs in
and **what** it must not break.

---

## 1. System Overview

Orion is a governed, multi-provider AI coding agent with autonomous capabilities,
persistent memory, and a human-authority-first security model.

```
Human authority  →  Governance framework  →  AI autonomy
       ↑                                         ↑
  Never overridden                        Always governed
```

### System Layers (top to bottom)

```
┌─────────────────────────────────────────────────────────────────┐
│  ENTRY POINTS                                                   │
│  CLI (REPL) │ REST API │ WebSocket │ Discord │ Telegram │ Slack │
├─────────────────────────────────────────────────────────────────┤
│  ROUTING & UNDERSTANDING                                        │
│  NLA (RequestAnalyzer → IntentClassifier → BriefBuilder)        │
│  Scout (fast triage: FastPath / Council / Escalation)           │
│  Router (orchestrates everything below)                         │
├─────────────────────────────────────────────────────────────────┤
│  EXECUTION                                                      │
│  FastPath (simple: single LLM call + tools)                     │
│  Table of Three (complex: Builder → Reviewer → Governor)        │
│  ARA Executor (autonomous: role-governed task execution)        │
├─────────────────────────────────────────────────────────────────┤
│  GOVERNANCE                                                     │
│  AEGIS (6 invariants — pure, stateless, hardcoded)              │
│  ARA AEGIS Gate (secrets, write limits, role scope, auth)       │
│  PromptGuard (adversarial pattern stripping)                    │
├─────────────────────────────────────────────────────────────────┤
│  MEMORY & LEARNING                                              │
│  MemoryEngine (3-tier: session / project / global)              │
│  InstitutionalMemory (patterns, anti-patterns, corrections)     │
│  LearningLoop (feedback → pattern extraction → memory)          │
│  Teaching Engine (seed knowledge, curriculum)                    │
├─────────────────────────────────────────────────────────────────┤
│  LLM PROVIDERS                                                  │
│  call_provider → 11 providers (Ollama, OpenAI, Anthropic, etc.) │
│  retry_api_call (exponential backoff, error classification)     │
│  ModelConfiguration (presets, per-role routing)                  │
├─────────────────────────────────────────────────────────────────┤
│  SECURITY                                                       │
│  WorkspaceSandbox (Docker or local isolation)                   │
│  SecretScanner │ SecureStore │ WriteLimits / WriteTracker       │
├─────────────────────────────────────────────────────────────────┤
│  EDITING                                                        │
│  EditFormatSelector │ EditValidator │ GitSafetyNet              │
├─────────────────────────────────────────────────────────────────┤
│  INTEGRATIONS                                                   │
│  PlatformService │ OAuthManager │ Bridges │ Plugin API          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Module Map

### Source Tree (`src/orion/`)

| Package | Key Modules | Purpose |
|---------|-------------|---------|
| `cli/` | `repl.py` (24KB), `commands.py` (43KB), `doctor.py`, `settings_manager.py`, `commands_training.py` | 37 CLI commands, interactive REPL |
| `api/` | `server.py`, `middleware.py`, `routes/` (10 modules, 95 endpoints) | FastAPI REST + WebSocket |
| `core/agents/` | `router.py`, `scout.py`, `fast_path.py`, `builder.py`, `reviewer.py`, `governor.py`, `table.py` | Agent pipeline |
| `core/governance/` | `aegis.py`, `commitment.py` | AEGIS hard gate (pure, stateless) |
| `core/memory/` | `engine.py` (40KB), `institutional.py` (18KB), `project.py`, `conversation.py`, `embeddings.py`, `seed_knowledge.py`, `teaching.py` | 3-tier memory + institutional wisdom |
| `core/understanding/` | `request_analyzer.py`, `intent_classifier.py`, `clarification.py`, `brief_builder.py`, `english_foundation.py`, `exemplar_bank.py`, `learning_bridge.py` | NLA pipeline |
| `core/learning/` | `patterns.py`, `feedback.py`, `curriculum.py`, `evolution.py`, `benchmark.py`, `knowledge_pack.py` | Learning loop |
| `core/llm/` | `config.py` (22KB), `providers.py` (21KB), `prompts.py` | 11-provider LLM abstraction |
| `core/context/` | `repo_map.py` (25KB), `python_ast.py`, `quality.py`, `capability_injector.py` | Code understanding |
| `core/editing/` | `formats.py`, `validator.py`, `safety.py` | Edit pipeline + git safety |
| `core/production/` | `health.py`, `logging.py`, `metrics.py`, `shutdown.py` | Production ops |
| `ara/` | `role_profile.py`, `aegis_gate.py`, `prompt_guard.py`, `session.py`, `goal_engine.py`, `execution.py`, `task_executor.py`, `daemon.py`, `checkpoint.py`, `promotion.py`, + 10 more | Autonomous Role Architecture |
| `security/` | `workspace_sandbox.py` (34KB), `sandbox.py`, `secret_scanner.py`, `store.py` (21KB), `write_limits.py` | Security layer |
| `integrations/` | `platform_service.py`, `platforms.py`, `oauth_manager.py`, `registry.py`, `health.py` | External platforms |
| `bridges/` | `base.py`, `discord_bridge.py`, `telegram_bridge.py`, `slack_bridge.py` | Chat bots |
| `plugins/` | `api.py` | Plugin system |

### Frontend (`orion-web/src/app/`)

| Page | Purpose |
|------|---------|
| `page.tsx` | Home |
| `chat/page.tsx` | Chat (WebSocket streaming) |
| `ara/page.tsx` | ARA dashboard (sessions, roles) |
| `settings/page.tsx` | Settings panel |
| `aegis/page.tsx` | AEGIS governance info |

### API Routes (10 modules, 95 endpoints)

| Module | Prefix | Key Endpoints |
|--------|--------|--------------|
| `health.py` | `/api/health` | Health check |
| `chat.py` | `/api/chat` | REST chat, WS streaming |
| `models.py` | `/api/models` | Config, switch provider |
| `settings.py` | `/api/settings` | User preferences |
| `auth.py` | `/api/auth` | OAuth, API keys |
| `platforms.py` | `/api/platforms` | Connected services |
| `tools.py` | `/api/tools` | Sandbox, diff, promote |
| `training.py` | `/api/training` | Teach, curriculum |
| `gdpr.py` | `/api/gdpr` | Export, delete user data |
| `ara.py` | `/api/ara` | Sessions, roles, dashboard |

---

## 3. Entry Points

All 6 entry points converge to the same core pipeline.

| Entry | File | Connects To |
|-------|------|-------------|
| **CLI REPL** | `cli/repl.py` | `RequestRouter.handle_request()` |
| **REST API** | `api/routes/chat.py` | `RequestRouter.handle_request()` |
| **WebSocket** | `api/routes/chat.py` | `FastPath.execute_streaming()` |
| **ARA Dashboard** | `api/routes/ara.py` | `DaemonLauncher.launch()` |
| **Chat Bridges** | `bridges/*.py` | `RequestRouter.handle_request()` |
| **AEGIS Approval** | `api/server.py` | `_web_approval_callback()` |

---

## 4. The Two Execution Pipelines

### 4.1 Interactive Pipeline (User-Driven)

```
User Request
    │
    ▼
NLA: RequestAnalyzer → IntentClassifier → TaskBrief
    │
    ▼
Scout (triage <500ms) → FAST_PATH / COUNCIL / ESCALATION
    │
    ├── FAST_PATH → FastPath.execute()
    │     Single LLM call, slim persona, memory-injected
    │     → Response to user
    │
    ├── COUNCIL → Table of Three
    │     Builder (generate) → Reviewer (check) → Governor (decide)
    │     → ANSWER / PLAN / ACTION_INTENT
    │     → If ACTION_INTENT: AEGIS check → EditValidator → Sandbox → Promote
    │
    └── ESCALATION → User confirmation → COUNCIL
```

### 4.2 Autonomous Pipeline (ARA — Role-Driven)

```
/work --role <name> --goal "<text>"
    │
    ▼
PromptGuard.sanitize(goal) → RoleProfile (AEGIS-clamped)
    │
    ▼
GoalEngine → TaskDAG (AEGIS validates plan)
    │
    ▼
ExecutionLoop: for each task:
    ├── ARATaskExecutor.execute(task)
    │     Context: sandbox inventory + task history + institutional wisdom
    │     → call_provider(any of 11 LLMs) → persist to sandbox
    ├── learn_from_outcome → InstitutionalMemory
    ├── Check 5 stop conditions
    └── Checkpoint if interval reached
    │
    ▼
AegisGate.evaluate() → SecretScanner + WriteLimits + RoleScope + Auth
    │
    ▼
PromotionManager → sandbox files → real workspace
```

### 4.3 Shared Resources

| Resource | Interactive | Autonomous |
|----------|-------------|-----------|
| `call_provider` (11 LLMs) | ✅ | ✅ |
| `InstitutionalMemory` READ | ✅ Router._get_memory_context | ✅ Executor._build_context_block |
| `InstitutionalMemory` WRITE | ✅ LearningLoop | ✅ ExecutionLoop._learn_from_outcome |
| `MemoryEngine` | ✅ Router.record_interaction | ❌ ARA uses FeedbackStore |
| `AEGIS governance` | ✅ check_aegis_gate | ✅ AegisGate.evaluate |
| `WorkspaceSandbox` | ✅ Router._init_sandbox | ✅ Per-session sandbox |
| `SecureStore` | ✅ | ✅ |

---

## 5. Agent Layer — The Table of Three

### Scout (`core/agents/scout.py`)
Fast triage (<500ms). Routes to FAST_PATH (simple), COUNCIL (complex), ESCALATION (dangerous).

### FastPath (`core/agents/fast_path.py`)
Direct LLM execution. Target: <3 seconds. Intent-classified slim personas (50-120 tokens).
NLA-integrated via `_nla_classify()` (falls back to regex).

### Builder (`core/agents/builder.py`)
Generates code solutions, plans, answers. Uses builder RoleConfig.
Outcomes: `ANSWER` | `PLAN` | `ACTION_INTENT`.

### Reviewer (`core/agents/reviewer.py`)
Reviews Builder proposals. Uses reviewer RoleConfig (can be different provider).
Decisions: `APPROVE` | `REVISE_AND_APPROVE` | `BLOCK`.

### Governor (`core/agents/governor.py`)
**Deterministic logic, NOT an LLM call.** Takes Builder + Reviewer → final outcome.
Hard boundaries: financial, legal, ethical, production deploy, credential exposure.
Autonomy tiers: GREEN → YELLOW → RED → HARD (never).

---

## 6. AEGIS Governance — The Hard Gate

AEGIS is **pure, stateless, side-effect-free, hardcoded**. It classifies and returns
results; enforcement happens in the calling code.

### 6.1 Core AEGIS Invariants (`core/governance/aegis.py`)

| # | Invariant | Checks |
|---|-----------|--------|
| 1 | **Workspace Confinement** | Path exists, all actions within workspace. Hardened: case, symlinks, null bytes, NTFS ADS, Win reserved names |
| 2 | **Mode Enforcement** | File modifications require PRO or PROJECT mode |
| 3 | **Action Scope** | Operations must be: CREATE, OVERWRITE, PATCH, DELETE, RUN, VALIDATE |
| 4 | **Risk Validation** | Warns on delete of important files, warns on overwrites |
| 5 | **Command Execution** | PROJECT mode only; no shell operators (`&&`, `||`, `;`, `|`, `>`, `<`, backticks) |
| 6 | **External Access** | READ (GET) auto-approved; WRITE (POST/PUT/DELETE) requires human approval via web UI |

### 6.2 AEGIS-6 Web Approval Queue (`api/server.py`)

```
PlatformService.api_call() → check_external_access()
  Write op → _web_approval_callback() → pending queue
  Frontend polls: GET /api/aegis/pending
  Human responds: POST /api/aegis/respond/{id} → unblock
  Timeout: 120s → denied by default
```

### 6.3 ARA AEGIS Gate (`ara/aegis_gate.py`)

Runs at **promotion time** (sandbox → real workspace). 4 checks, ALL must pass:
1. `check_secrets()` — SecretScanner scans sandbox
2. `check_write_limits()` — WriteTracker within bounds
3. `check_role_scope()` — actions within role authority
4. `check_auth()` — PIN or TOTP if `require_review_before_promote`

### 6.4 PromptGuard (`ara/prompt_guard.py`)

12 adversarial patterns stripped from goal text: ignore_instructions, override_role,
identity_hijack, pretend_hijack, disregard_rules, jailbreak, dan_mode,
system_prompt_inject, new_instructions, act_as, forget_everything, disable_safety.

### 6.5 Hardcoded Blocked Actions (role_profile.py)

No role can ever enable these:
```
delete_repository, force_push, modify_ci_pipeline, access_credentials_store,
disable_aegis, modify_aegis_rules, execute_as_root, access_host_filesystem
```

---

## 7. Memory System — The Three Tiers

### Architecture

```
MemoryEngine (memory_engine.db)        InstitutionalMemory (institutional_memory.db)
├── Tier 1: Session (RAM, per-request)  ├── patterns (success learnings)
├── Tier 2: Project (per-workspace)     ├── anti_patterns (failure learnings)
└── Tier 3: Global (promoted)           ├── corrections (user overrides)
                                        ├── user_preferences
                                        ├── domain_expertise
                                        ├── execution_history (ARA)
                                        └── seed_knowledge (bundled)
```

### Lifecycle
1. Interaction → Tier 1 (session)
2. User feedback → Tier 2 (project)
3. High-confidence → promoted to Tier 3 (global)
4. Tier 3 informs ALL future projects

### READ Paths

| Consumer | Sources | Method |
|----------|---------|--------|
| Router (interactive) | MemoryEngine + InstitutionalMemory | `_get_memory_context()` |
| ARATaskExecutor (autonomous) | InstitutionalMemory | `_build_context_block()` |
| FastPath | Injected via `_memory_context` | Set by Router |

### WRITE Paths

| Writer | Target | Trigger |
|--------|--------|---------|
| Router.record_interaction | MemoryEngine Tier 1 | Every request |
| LearningLoop | InstitutionalMemory + ProjectMemory | User feedback |
| ExecutionLoop._learn_from_outcome | InstitutionalMemory | Every ARA task |
| TeachingEngine | InstitutionalMemory | `/train` command |

---

## 8. NLA — Natural Language Architecture

```
User Input → EnglishFoundation (normalize, POS) →
  IntentClassifier (embedding + keyword, 200 exemplars) →
  ClarificationDetector (ambiguity check) →
  BriefBuilder → TaskBrief → Scout/FastPath
```

Integration: FastPath uses `_nla_classify()` → RequestAnalyzer (falls back to regex).
Learning: LearningBridge feeds successful interactions → ExemplarBank.

---

## 9. LLM Provider Layer

### Unified Call Path (`core/llm/providers.py`)

```python
call_provider(role_config, system_prompt, user_prompt) → str
  ├── ollama    → _call_ollama() [no API key]
  ├── openai    → _get_key("openai") → _call_openai()
  ├── anthropic → _get_key("anthropic") → _call_anthropic()
  ├── google    → _get_key("google") → _call_google()
  └── ... (groq, together, mistral, deepseek, cohere, perplexity)
  All wrapped in retry_api_call() with exponential backoff
```

### Error Handling
- `httpx.HTTPStatusError` for precise status codes
- 401/403 → auth (non-retryable) | 404 → model not found | 429 → rate limit (retryable)
- Returns `_error_json()` on final failure; FastPath parses JSON to detect errors

### Model Configuration (`core/llm/config.py`)

```python
ModelConfiguration: mode + builder: RoleConfig + reviewer: RoleConfig
RoleConfig: provider + model + light_model
Presets: local_free | power_user | cloud_budget | cloud_dual | cloud_openai_only
Storage: ~/.orion/model_config.json
```

---

## 10. Security Layer

| Component | File | Purpose |
|-----------|------|---------|
| **WorkspaceSandbox** | `security/workspace_sandbox.py` (34KB) | Docker or local file isolation. create → edit → diff → promote → destroy |
| **Code Sandbox** | `security/sandbox.py` | Untrusted code execution isolation |
| **SecretScanner** | `security/secret_scanner.py` | Pre-promotion credential detection |
| **SecureStore** | `security/store.py` (21KB) | Encrypted API key storage |
| **WriteLimits** | `security/write_limits.py` | AEGIS-enforced file/volume limits |

---

## 11. Editing Layer

| Component | File | Purpose |
|-----------|------|---------|
| **EditFormatSelector** | `core/editing/formats.py` | Selects format: WHOLE_FILE, SEARCH_REPLACE, UNIFIED_DIFF, ARCHITECT |
| **EditValidator** | `core/editing/validator.py` | 7 checks: syntax, confidence, diff integrity, imports, brackets, recovery, metrics |
| **GitSafetyNet** | `core/editing/safety.py` | Savepoints before every AI edit, `/undo` reverts, stack-based |

---

## 12. ARA — Autonomous Role Architecture

### Component Flow

```
RoleProfile (YAML, AEGIS-clamped)
  → PromptGuard.sanitize(goal)
  → GoalEngine.decompose() → TaskDAG
  → SessionState (created → running → paused → completed/failed/cancelled)
  → ExecutionLoop: for each task
      → ARATaskExecutor.execute() [context-aware, any provider]
      → learn_from_outcome → InstitutionalMemory
      → 5 stop conditions checked
      → auto-checkpoint
  → AegisGate.evaluate() (secrets, limits, scope, auth)
  → PromotionManager (sandbox → workspace)
```

### Supporting Components

| Module | Purpose |
|--------|---------|
| `daemon.py` + `daemon_launcher.py` | Background process management |
| `checkpoint.py` | Git-based snapshots + rollback |
| `feedback_store.py` | Session/task outcome recording |
| `drift_monitor.py` | Stale workspace detection |
| `goal_queue.py` | Priority goal queuing with interrupts |
| `user_isolation.py` | Multi-user OS-level scoping |
| `audit_log.py` | Action audit trail |
| `keychain.py` | ARA auth credential storage |
| `auth.py` | PIN + TOTP authentication |
| `dashboard.py` | Morning dashboard TUI (7 sections) |
| `promotion.py` | Sandbox → workspace file promotion |
| `recovery.py` | Failure recovery |

### Five Stop Conditions

| Condition | Threshold |
|-----------|-----------|
| Goal complete | All tasks done |
| Time limit | `max_session_hours` from role |
| Cost limit | `max_cost_per_session` from role |
| Confidence collapse | 3 consecutive tasks < 0.50 |
| Error threshold | 5 consecutive failures |

---

## 13. Integrations & Bridges

### PlatformService (`integrations/platform_service.py`)
Unified interface for external platforms. AEGIS-6 gated: all write operations require
human approval via web UI. Supports: GitHub, Slack, Discord, Telegram, Notion, Jira,
Linear, Google, Image AI, Voice.

### Bridges (`bridges/`)
Discord, Telegram, Slack bots. All extend `BaseBridge` → `RequestRouter.handle_request()`.

### Plugin API (`plugins/api.py`)
Register, discover, invoke custom plugins.

---

## 14. Data Storage Map

| Data | Location | Format | Scope |
|------|----------|--------|-------|
| User settings | `~/.orion/settings.json` | JSON | Global |
| Model config | `~/.orion/model_config.json` | JSON | Global |
| Role definitions | `~/.orion/roles/*.yaml` | YAML | Global |
| API keys | `~/.orion/secure_store.db` | SQLite (encrypted) | Global |
| Memory (3-tier) | `~/.orion/memory_engine.db` | SQLite | Global |
| Institutional memory | `~/.orion/institutional_memory.db` | SQLite (7 tables) | Global |
| ARA sessions | `~/.orion/sessions/` | JSON | Global |
| ARA checkpoints | `~/.orion/checkpoints/` | Files | Global |
| Daemon state | `~/.orion/daemon/` | PID + JSON | Global |
| Project memory | `{workspace}/.orion/project_memory.json` | JSON | Per-project |
| Seed exemplars | `data/seed/intent_exemplars.json` | JSON | Bundled |
| Seed curriculum | `data/seed/curriculum.json` | JSON | Bundled |

---

## 15. Complete Request Flow — Interactive (CLI → FastPath)

```
User types: "show me main.py"
  → REPL.run() → not a slash command
  → RequestRouter(workspace_path)
      init: RepoMap, Scout, Sandbox, InstitutionalMemory
  → handle_request("show me main.py")
  → Scout.analyze() → Route.FAST_PATH (simple pattern match)
  → Router._handle_fast_path()
      → _get_memory_context()
          ├── MemoryEngine.recall_for_prompt()     [Tier 1+2+3]
          └── get_learnings_for_prompt()            [InstitutionalMemory]
      → FastPath._memory_context = combined context
      → FastPath.execute_streaming()
          → _nla_classify() → "question"
          → _build_system_prompt("question") → ~70 token slim persona
          → get_model_config() → RoleConfig(ollama, qwen2.5:14b)
          → call_provider(role_config, system, user)
              → retry_api_call(_call_ollama)
                  → httpx POST localhost:11434/api/generate → SSE stream
          → yield tokens → Router prints to terminal
  → Router.record_interaction() → MemoryEngine.remember(tier=1)
```

---

## 16. Extension Points Guide — Where New Features Plug In

This is the key section. When adding any new capability to Orion, use this table
to determine where it integrates and what it must respect.

### 16.1 Adding a New LLM Provider

| Step | Where | What |
|------|-------|------|
| 1 | `core/llm/providers.py` | Add `_call_<provider>()` function |
| 2 | `core/llm/providers.py` | Add branch in `call_provider()` |
| 3 | `core/llm/config.py` | Add provider to `SUPPORTED_PROVIDERS` |
| 4 | `security/store.py` | Key retrieval (if API key needed) |
| **Must respect** | `retry_api_call` wrapper, `_error_json` return format |

### 16.2 Adding a New CLI Command

| Step | Where | What |
|------|-------|------|
| 1 | `cli/commands.py` | Add handler function `handle_<command>()` |
| 2 | `cli/repl.py` | Add to command dispatch (`if user_input == "/<cmd>"`) |
| **Must respect** | Existing command namespace, REPL async loop |

### 16.3 Adding a New API Endpoint

| Step | Where | What |
|------|-------|------|
| 1 | `api/routes/<module>.py` | Add route to existing or new router |
| 2 | `api/server.py` | `app.include_router()` if new module |
| **Must respect** | Rate limiting middleware, CORS config, request logging |

### 16.4 Adding a New Agent

| Step | Where | What |
|------|-------|------|
| 1 | `core/agents/<name>.py` | Create agent with clear input/output contract |
| 2 | `core/agents/router.py` | Wire into routing logic |
| **Must respect** | AEGIS check before any action, memory context injection |

### 16.5 Adding a New Memory Source

| Step | Where | What |
|------|-------|------|
| 1 | `core/memory/<name>.py` | Create memory class with read/write methods |
| 2 | `core/agents/router.py` | Add to `_get_memory_context()` merge |
| 3 | `ara/task_executor.py` | Add to `_build_context_block()` if ARA needs it |
| **Must respect** | Existing tier structure, confidence scoring, promotion gate |

### 16.6 Adding New AEGIS Rules

| Step | Where | What |
|------|-------|------|
| 1 | `core/governance/aegis.py` | Add invariant check in `check_aegis_gate()` |
| **Must respect** | PURE function, NO side effects, NO state, returns AegisResult |

### 16.7 Adding New ARA Capabilities

| Step | Where | What |
|------|-------|------|
| 1 | `ara/<component>.py` | New module |
| 2 | Wire into existing flow | See pipeline diagram (§12) |
| **Must respect** | RoleProfile authority, AegisGate checks, PromptGuard, SessionState lifecycle |

### 16.8 Adding Skills (ARA-006 — Designed, Not Yet Implemented)

| Step | Where | What |
|------|-------|------|
| 1 | `ara/skill.py` | Skill + SkillGroup dataclasses, SKILL.md parser |
| 2 | `ara/skill_library.py` | SkillLibrary (registry, CRUD) |
| 3 | `ara/skill_guard.py` | SkillGuard (extends PromptGuard patterns) |
| 4 | `ara/role_profile.py` | +2 fields: `assigned_skills`, `assigned_skill_groups` |
| 5 | `ara/task_executor.py` | Skill context injection in `_build_context_block()` |
| 6 | `ara/execution.py` | Pass `skill_name` through `_learn_from_outcome()` |
| **Must respect** | AEGIS Gate unchanged, PromptGuard unchanged, all existing tests pass |
| **Security** | 3 gates (SkillGuard import scan, assignment validation, runtime AEGIS) + 10 hardening measures (H1-H10: integrity hash, resource limits, path traversal guard, file type allowlist, name sanitization, URL import security, evasion hardening, re-scan on edit, runtime isolation) |
| **Details** | See `docs/architecture/ARA-006-skills-architecture.md` §7 |

### 16.9 Adding a New Platform Integration

| Step | Where | What |
|------|-------|------|
| 1 | `integrations/platforms.py` | Define platform config + capabilities |
| 2 | `integrations/platform_service.py` | Add helper methods |
| 3 | `api/routes/platforms.py` | Add endpoints if needed |
| **Must respect** | AEGIS-6 (write ops require human approval), OAuth token lifecycle |

### 16.10 Adding a New Bridge (Chat Platform)

| Step | Where | What |
|------|-------|------|
| 1 | `bridges/<name>_bridge.py` | Extend `BaseBridge` |
| 2 | Implement `on_message()` → `RequestRouter.handle_request()` |
| **Must respect** | Rate limiting, error recovery, message formatting |

### 16.11 Adding a New Web Page

| Step | Where | What |
|------|-------|------|
| 1 | `orion-web/src/app/<name>/page.tsx` | New Next.js page |
| 2 | Add API endpoints if new data needed |
| **Must respect** | Existing layout, AEGIS approval modal provider |

---

## 17. Architecture Invariants (Never Break These)

1. **AEGIS is PURE** — No state, no side effects, no flow control. Returns results only.
2. **Human authority > Governance > AI autonomy** — Never reversed.
3. **AEGIS_BLOCKED_ACTIONS are HARDCODED** — No role, no config, no API can enable them.
4. **External writes require human approval** — AEGIS-6 cannot be bypassed.
5. **Memory is tiered** — Session → Project → Global. Promotion requires confidence.
6. **Governor is DETERMINISTIC** — Never an LLM call. Pure logic.
7. **All file edits go through sandbox** — No direct workspace writes.
8. **Credentials are encrypted at rest** — SecureStore, never plaintext.
9. **ARA sessions are AEGIS-governed** — Every task, every promotion, every action.
10. **PromptGuard runs on ALL goals** — No bypass for any entry point.

---

## Appendix A: File Count Summary

| Category | Count |
|----------|-------|
| Python source files | ~132 |
| Test files | ~60+ |
| API endpoints | 95 |
| CLI commands | 37 |
| LLM providers | 11 |
| Frontend pages | 5 |
| ARA modules | 21 |
| Memory databases | 2 (SQLite) + 1 (JSON per project) |
| Architecture docs | 7 (ARA-001 through ARA-006 + this doc) |

---

## Appendix B: Version History

| Version | Milestone |
|---------|-----------|
| v6.5.0 | AEGIS governance, workspace sandbox |
| v7.4.0 | 3-tier memory, Table of Three, Scout, FastPath |
| v7.6-7.8 | NLA pipeline (9 milestones) |
| v9.0.0 | Full ARA implementation (14 phases) |
| v9.0.0+ | Skills architecture designed (ARA-006) |
