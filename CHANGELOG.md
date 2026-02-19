# Changelog

All notable changes to Orion Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [10.0.2] -- 2026-02-19

### Added
- **PIN Management API** — 3 new endpoints for secure PIN lifecycle management
  - `GET /api/ara/auth/pin/status` — check if a PIN is configured
  - `POST /api/ara/auth/pin` — set or change PIN (requires current PIN verification when changing)
  - `POST /api/ara/auth/pin/verify` — test-verify a PIN
- **PIN Management Web UI** — dedicated card in ARA Settings tab
  - Set initial PIN or change existing PIN with current-PIN verification
  - Digit-only masked inputs (4-8 digits), confirmation field, inline success/error feedback
  - Dynamic UI adapts to whether a PIN is already configured
- **17 E2E API tests** (`tests/test_pin_api_e2e.py`) — full lifecycle coverage via FastAPI TestClient
  - Status, set, change, verify, validation (too short, non-digits, max length), and complete lifecycle flow

### Fixed
- **`cmd_work()` workspace fallback** — now reads `default_workspace` from `~/.orion/settings.json` before falling back to `Path.cwd()`, fixing failures when running under systemd or from non-project directories
- **Consent Gates approve button** — added PIN prompt modal and inline feedback banner; approve flow now correctly requests PIN when `auth_method=pin` instead of silently failing with AEGIS gate block

## [10.0.1] -- 2026-02-19

### Added
- **Google Account OAuth Sign-In** — Dedicated sign-in flow for Google LLM access (Gemini, Vertex AI)
  - `src/orion/api/routes/google.py` — 5 API endpoints: connect, callback, status, disconnect, refresh
  - OAuth2 Authorization Code flow with PKCE (S256) and state validation
  - AEGIS scope enforcement: LLM-only scopes allowed (openid, email, profile, cloud-platform, generative-language.*)
  - Blocked scopes: Drive, Gmail, Calendar, YouTube, Contacts, Photos — rejected at token exchange
  - Container receives read-only access token only (no refresh token)
  - Host-side token refresh via `GoogleCredentialManager`
- **Web UI — Google Account card** in Settings panel (connect, disconnect, refresh, status display, AEGIS scope info)
- **CLI — `/google` command** with `login`, `status`, `disconnect` subcommands
- 54 tests covering scope validation, credential storage, container security, API routes, CLI commands, and security invariants
- Automatic sandbox boot on Orion startup (CLI, Web UI, API modes)
- Graceful degradation when Docker is unavailable (BYOK-only mode)
- Sandbox status in `/api/health` endpoint and CLI banner
- Signal handler cleanup for orphaned containers on crash/SIGINT
- `/sandbox restart` command
- `SandboxLifecycle` manager (`src/orion/security/sandbox_lifecycle.py`)
- 20 unit tests + 5 integration tests for sandbox lifecycle

### Changed
- **ARA Web UI — Inline accordion expansion** for Skills and Roles lists (click to expand/collapse detail view directly beneath each item)
- **Skills detail panel** — metadata grid (version, trust, AEGIS, source), tags, full SKILL.md content viewer with monospace rendering
- **Skills SKILL.md editor** — Edit button switches to textarea for non-bundled skills; Save persists via API; bundled skills show "Read-only"
- **`PUT /api/ara/skills/{name}`** API endpoint — updates skill description, instructions, or tags via `cmd_skill_update`
- **Roles inline detail** — expanding a role shows scope/auth/source/description, assigned skills with Remove buttons, and "Add a skill" dropdown
- **Roles inline edit form** — Edit button expands edit form (scope, auth method, description) with Save/Cancel directly inside the accordion
- `/sandbox` commands now use shared lifecycle singleton (no duplicate orchestrator instances)
- Skills and Roles lists now use accordion UI pattern (detail expands inline under each item, not as a separate panel below the list)

### Fixed
- **Seed skills (debug-issue, deploy-to-staging, docker-setup) no longer display as "blocked"** — `_get_skill_library` now explicitly marks seed skills as `verified`, `bundled`, `aegis_approved: True` and fixes user copies that were incorrectly blocked by SkillGuard

## [10.0.0] -- 2026-02-18

### Major Milestone: Digital Agent Architecture -- Complete & Proven

The full governed execution pipeline is now operational. Orion can autonomously generate code
using local or cloud LLMs, with every operation governed by AEGIS, filtered through the egress
proxy, and confined to Docker sandbox isolation.

**Proven in production testing:** Task -> LLM (Ollama qwen2.5:7b) -> Builder -> Reviewer -> Governor -> Sandbox -> Workspace -> pytest 4/4 pass.

### Added

#### Phase 2: Digital Agent Architecture
- **Egress Proxy** (`src/orion/security/egress/proxy.py`) -- HTTP forward proxy with CONNECT tunneling, 6-stage security pipeline, domain whitelist (additive model), JSONL audit logging
- **Content Inspector** (`src/orion/security/egress/inspector.py`) -- 12 credential patterns (AWS, GitHub, OpenAI, Anthropic, Google, Slack, etc.)
- **Rate Limiter** (`src/orion/security/egress/rate_limiter.py`) -- Sliding window per-domain + global RPM limits
- **DNS Filter** (`src/orion/security/egress/dns_filter.py`) -- UDP DNS proxy, non-whitelisted domains get NXDOMAIN, upstream forwarding
- **Approval Queue** (`src/orion/security/egress/approval_queue.py`) -- Host-side human gate for write operations, JSON persistence, configurable timeout
- **Google OAuth Credentials** (`src/orion/security/egress/google_credentials.py`) -- Scope validation, blocked scopes (Drive/Gmail/Calendar/etc.), container gets access token only (no refresh token)
- **Antigravity Headless Integration** (`src/orion/security/egress/antigravity.py`) -- Playwright browser automation for Antigravity (VS Code fork), state machine lifecycle
- **AEGIS Invariant 7** -- Network access control (check_network_access), hardcoded blocked Google services, non-HTTPS warnings, write method awareness
- **Web UI Network Dashboard** (`orion-web/src/components/NetworkDashboard.tsx`) -- Domain whitelist tab, audit log tab, security layers visualization
- **Docker Compose** (`docker/docker-compose.yml`) -- Dual-network isolation (orion-internal: no internet, orion-egress: proxy only)

#### Phase 3: Graduated Services
- **SandboxOrchestrator** (`src/orion/security/orchestrator.py`) -- 6-step governed boot (AEGIS -> Docker -> Egress -> Approval -> DNS -> Container), reverse-order teardown, health monitoring, hot config reload
- **Google Services Toggle** -- Per-service AEGIS whitelist with 9 Google services (Drive, Gmail, Calendar, YouTube, Photos, Docs, Sheets, Slides, People), risk levels, toggle API
- **LLM Web Search Routing** -- 5 hardcoded search API domains (auto-allowed), configurable research domains (GET-only)
- **Graduated Access E2E** -- Toggle -> config update -> orchestrator reload -> proxy/DNS reload -> container access changes

#### Web UI & Wiring
- `handleReview` now calls `POST /promote` after AEGIS gate passes
- New Session form on dashboard (wires `POST /api/ara/work`)
- Notification bell with unread count badge (wires `GET /api/ara/notifications`)
- Rich diff viewer: GitHub-PR-style file tree + unified diffs in consent gates
- Reject button with inline feedback textarea, wired to learning pipeline
- `cmd_review_diff` CLI command + `GET /sessions/{id}/diff` API endpoint

#### Testing Infrastructure
- 261 Phase 2 unit tests + 36 E2E integration tests
- 87 Phase 3 unit tests + 14 E2E integration tests
- 26 operational validation tests (real Docker, real network traffic)
- 17 E2E live tests (real Ollama, real code generation, real workspace output)
- CI/CD pipeline updated with secret scanning and E2E jobs
- 17 starter roles and 85 seed skills for ARA role profiles

### Changed
- Egress proxy upstream timeout: 30s -> 120s (supports local LLM inference)
- Egress proxy httpx client: added `trust_env=False` to prevent circular proxy loop
- AEGIS version: v6.0.0 -> v7.0.0 (added Invariant 7: Network Access Control)
- LLM providers now use BYOK (API keys) exclusively -- no OAuth for LLM access
- OpenAI and Google Gemini auth changed from `AuthMethod.OAUTH` to `AuthMethod.API_KEY`
- CI test scope expanded from `tests/unit/ tests/ara/` to `tests/` (all tests)

### Removed
- OpenAI OAuth flow (port 1455 callback server, Codex client ID)
- OAuth fallback from `call_provider()` -- LLM providers are BYOK only
- `_is_oauth_credential()` function
- `oauth_capable`/`oauth_ready` from auth-status API

### Fixed
- `docker/Dockerfile.egress` -- Added missing builder stage for multi-stage build
- Egress proxy circular loop when `HTTP_PROXY` env var is set
- Egress proxy timeout too short for local LLM inference
- Approve button only ran AEGIS gate but never promoted sandbox to workspace
- Diff viewer returning 0 files for sessions already promoted
- Session ID resolution for pending consent gate cards

## [9.0.0] -- 2026-02-15

### Added
- **ARA Phases 9-14 complete** (201 tests)
  - Phase 9: Role Schema + Management (32 tests)
  - Phase 10: Security Hardening — PromptGuard, AuditLog, KeychainStore (65 tests)
  - Phase 11: Promotion + Conflict Resolution — PromotionManager (28 tests)
  - Phase 12: CLI Commands + Setup Wizard (25 tests)
  - Phase 13: Morning Dashboard TUI with 7 sections (23 tests)
  - Phase 14: Goal Queue + User Isolation (28 tests)
- Version tagged as v9.0.0

## [8.0.0] -- 2026-02-14

### Added
- **ARA Skills System (ARA-006)** — 145 tests
  - `skill.py`, `skill_guard.py`, `skill_library.py`
  - 8 bundled skills (code-review, write-tests, write-documentation, etc.)
  - SkillGuard: 22+ security patterns with NFKC normalization
  - SHA-256 integrity verification, resource limits, path traversal guard
- **Chat Pipeline Bug Fixes** — asyncio crash, retry logic, Ollama 404, JSON leak, streaming errors
- **Memory System Integration** — InstitutionalMemory connected to Router
- **ARA Task Executor** — context-aware file generation/editing in sandbox
- **ARA Daemon Launcher** — session launcher from pending state
- **Ollama Provider** — local LLM integration for task execution
- **Web UI** (`orion-web/`) — Full React (Next.js) dashboard
  - Dashboard, Consent Gates, Job Roles, Skills, Chat sidebar, Settings
  - 6 pages, WebSocket real-time updates

## [7.3.0] -- 2026-02-11

### Added
- PayFast funding integration (`.github/FUNDING.yml`)
- FUNDING.md with voluntary contribution details and tiers
- SUPPORTERS.md for contributor recognition
- Comprehensive GitHub documentation suite (18 docs in `docs/`)
- CODE_OF_CONDUCT.md, SECURITY.md (root), ROADMAP.md

### Fixed
- API port consistency: standardized on port 8001 across server.py, ChatInterface.tsx, api.ts, .env.local

## [7.1.0] -- 2026-02-10

### Added
- AEGIS 6-layer path confinement hardening (null byte, NTFS ADS, reserved devices, symlinks)
- Rate limiting middleware for API server
- Optional authentication middleware
- 108 new tests (304 -> 412 total)
- License headers on all source files

### Changed
- License changed from MIT to AGPL-3.0 with dual licensing
- Split server.py into 9 route modules (2,642 -> 233 lines)
- Consolidated plugin system (single source of truth)
- Updated all datetime.utcnow() to datetime.now(timezone.utc)

### Fixed
- Windows path bypass vulnerability in AEGIS
- Version string inconsistencies across codebase
- Model ID mismatch in curriculum/benchmark
- Intent class duplication between router.py and aegis.py

### Security
- AEGIS now blocks null byte injection, NTFS ADS, reserved devices
- 21 regression tests for path traversal attacks

## [7.0.0] -- 2026-02-09

### Added
- ORION_PERSONA.md -- Canonical persona document
- persona.py -- Runtime persona loader with compiled principles (tamper-proof)
- Agent-specific persona fragments (Builder, Reviewer, Governor, Router)
- 8 Core Principles (immutable, load-bearing)
- Hard Boundaries frozenset in Governor (6 categories)
- 10 persona tests

### Security
- Principles compiled into Python constants, not loaded from .md at runtime
- Cannot be overridden by file deletion, config changes, or prompt injection

## [6.9.0] -- 2026-02-09

### Added
- Universal Messaging Bridge System (Telegram, Slack, Discord)
- Passphrase authentication (SHA-256, timing-safe comparison)
- Chat ID allowlist for authorized users
- Per-user rate limiting (10 req/min sliding window)
- AEGIS inline/action buttons for bridge approval
- `/bridge enable|disable|status|revoke` CLI commands
- Bridge config persistence (`~/.orion/bridges.json`)
- 12 bridge tests

## [6.8.0] -- 2026-02-09

### Added
- CI/CD pipeline (GitHub Actions, 7 jobs)
- Dockerfile and docker-compose.yml
- Release automation workflow

## [6.7.0] -- 2026-02-08

### Added
- Workspace Sandbox system (local + Docker modes)
- Edit-review-promote lifecycle
- Per-language Docker execution (Python, Node, Bash)
- Network isolation in sandbox containers
- 23 sandbox tests

## [6.6.0] -- 2026-02-08

### Added
- AEGIS Invariant 6: External Access Control
- Read/write approval rules for network operations
- Hardcoded gate in PlatformService.api_call()
- Approval callback system for CLI/Web

## [6.5.0] -- 2026-02-08

### Added
- System audit remediation (12 gaps wired)
- Full Builder, Reviewer, Governor, Table of Three agents
- Security hardening (credential audit logging, per-platform rate limiting)
- Commitment tracking and plugin system

## [6.4.0] -- 2026-02-08

### Added
- Clean project structure for GitHub publishing
- Modern `src/` layout with proper packaging
- Comprehensive CI/CD pipeline

### Migrated from Orion MVP
- Three-Tier Memory Engine (session -> project -> institutional)
- Continuous Learning & Evolution Engine
- Table of Three multi-agent architecture (Builder + Reviewer + Governor)
- Edit Validator with confidence scoring and auto-recovery
- Integration Health Check system (30+ checks)
- Production Stack (health probes, graceful shutdown, metrics, rate limiting)
- 79 integrations (LLM, voice, image, video, messaging, social, automation, storage)
- Git Safety Net with auto-commit savepoints
- Plugin API with 8 lifecycle hooks
- Doctor diagnostic system (15 checks)
- Deep Python Context (AST analysis, import graph, call graph)
- Code Quality Analyzer
- Docker Sandbox for isolated code execution

## [6.2.0] -- 2026-02-08

### Added
- Three-Tier Memory System (`core/memory_engine.py`)
- Evolution Engine (`core/evolution_engine.py`)
- Edit Validator (`core/edit_validator.py`)
- Integration Health Checker (`core/integration_health.py`)
- Production Stack (`core/production.py`)
- Architecture docs and API reference
- 160 new tests

## Previous History

See Orion_MVP git log for versions v2.2.0 through v6.2.0.
