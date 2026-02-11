# Changelog

All notable changes to Orion Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
