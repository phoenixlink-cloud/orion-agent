# Changelog

All notable changes to Orion Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [10.0.0] -- 2026-02-16

### Added
- **Web UI Audit & Wiring Fixes**
  - `handleReview` now calls `POST /promote` after AEGIS gate passes (Approve was broken E2E)
  - New Session form on dashboard (wires `POST /api/ara/work`)
  - Notification bell with unread count badge (wires `GET /api/ara/notifications`)
  - Dashboard API includes `session_id` in pending review sections
- **Diff Viewer Fixes**
  - `cmd_review_diff` shows unchanged files for already-promoted sessions
  - PM sandbox → daemon sandbox fallthrough when PM sandbox is empty
  - Recursive `rglob("*")` for nested sandbox directories
  - Partial session ID matching for truncated UI IDs
  - UI handles `unchanged` status with "(already promoted)" label
- Rich diff viewer: GitHub-PR-style file tree + unified diffs in consent gates
- Reject button with inline feedback textarea, wired to learning pipeline
- `cmd_review_diff` CLI command + `GET /sessions/{id}/diff` API endpoint

### Fixed
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
